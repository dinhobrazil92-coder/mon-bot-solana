#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tracker Solana (RPC public) -> Telegram
- WS: wss://api.mainnet-beta.solana.com
- HTTP: https://api.mainnet-beta.solana.com
- Subscriptions stored in data/subscriptions.json
- Admin HTTP endpoints protected by BOT_PASSWORD env var (X-ADMIN-PASSWORD header or JSON field)
- Telegram commands via polling (/login, /add, /remove, /list, /my)
"""

import os
import json
import time
import asyncio
import threading
import aiohttp
import websockets
import requests
from flask import Flask, request, jsonify

# === CONFIG (BOT_TOKEN intégré comme demandé) ===
BOT_TOKEN = "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
BOT_PASSWORD = os.getenv("BOT_PASSWORD")  # DOIT être défini sur Render (secret)
WS_RPC = os.getenv("WS_RPC", "wss://api.mainnet-beta.solana.com")
HTTP_RPC = os.getenv("HTTP_RPC", "https://api.mainnet-beta.solana.com")
DEBUG_CHAT_ID = os.getenv("DEBUG_CHAT_ID")  # optionnel pour fallback notifications

DATA_DIR = "data"
SUB_FILE = os.path.join(DATA_DIR, "subscriptions.json")
AUTH_FILE = os.path.join(DATA_DIR, "authorized.json")
CACHE_FILE = os.path.join(DATA_DIR, "sig_cache.json")
os.makedirs(DATA_DIR, exist_ok=True)

# defaults
if not os.path.exists(SUB_FILE):
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
if not os.path.exists(AUTH_FILE):
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
if not os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"sigs": []}, f)

RECONNECT_BASE = 1.5
MAX_RECONNECT = 60
MAX_CACHE = 2000

FLASK_PORT = int(os.getenv("PORT", 10000))

# === util ===
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("[save_json] error:", e)

# === Telegram helpers ===
def send_message_sync(chat_id, text):
    if not BOT_TOKEN:
        print("[TG] BOT_TOKEN missing")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": str(chat_id), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10
        )
        print(f"[TG] sync send {chat_id} -> {resp.status_code} {resp.text}")
        return resp
    except Exception as e:
        print("[TG] sync send exception:", e)

async def send_message_async(chat_id, text, session: aiohttp.ClientSession):
    if not BOT_TOKEN:
        print("[TG] BOT_TOKEN missing (async)")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with session.post(url, data={"chat_id": str(chat_id), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10) as r:
            txt = await r.text()
            print(f"[TG] async send {chat_id} -> {r.status} {txt}")
    except Exception as e:
        print("[TG] async send exception:", e)

# broadcast to all subscribers
async def broadcast_async(text, session):
    subs = load_json(SUB_FILE)
    recipients = set()
    for lst in subs.values():
        for c in lst:
            recipients.add(str(c))
    if not recipients and DEBUG_CHAT_ID:
        recipients.add(str(DEBUG_CHAT_ID))
    for rcpt in recipients:
        await send_message_async(rcpt, text, session)

def broadcast_sync(text):
    subs = load_json(SUB_FILE)
    recipients = set()
    for lst in subs.values():
        for c in lst:
            recipients.add(str(c))
    if not recipients and DEBUG_CHAT_ID:
        recipients.add(str(DEBUG_CHAT_ID))
    for rcpt in recipients:
        send_message_sync(rcpt, text)

# === RPC async helpers ===
async def rpc_request(session: aiohttp.ClientSession, method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": int(time.time()*1000), "method": method, "params": params}
    try:
        async with session.post(HTTP_RPC, json=payload, timeout=20) as r:
            return await r.json()
    except Exception as e:
        print("[RPC] request error:", e)
        return None

async def get_transaction(session: aiohttp.ClientSession, signature: str):
    return await rpc_request(session, "getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "finalized"}])

async def get_signatures_for_address(session: aiohttp.ClientSession, address: str, limit: int = 1):
    return await rpc_request(session, "getSignaturesForAddress", [address, {"limit": limit}])

# === message builder ===
def build_message_from_tx(tx_json):
    if not tx_json or "result" not in tx_json or not tx_json["result"]:
        return "⚠️ Transaction non trouvée / non finalisée."
    r = tx_json["result"]
    sig = (r.get("transaction", {}).get("signatures") or [None])[0] or "unknown"
    meta = r.get("meta", {})
    pre_bal = meta.get("preBalances", [])
    post_bal = meta.get("postBalances", [])
    pre_tokens = meta.get("preTokenBalances", [])
    post_tokens = meta.get("postTokenBalances", [])
    lines = [f"🔗 <b>Tx</b> : <code>{sig}</code>"]
    # SOL diffs
    if pre_bal and post_bal:
        diffs = []
        for i,(p,q) in enumerate(zip(pre_bal, post_bal)):
            d = (q - p) / 1e9
            if abs(d) > 0:
                diffs.append(f"{d:+g} SOL (acct idx {i})")
        if diffs:
            lines.append("💵 <b>SOL changes</b>:")
            lines += diffs
    # token diffs
    if pre_tokens or post_tokens:
        lines.append("🪙 <b>Token changes</b>:")
        by = {}
        for pre in pre_tokens:
            key = (pre.get("accountIndex"), pre.get("mint"))
            by.setdefault(key, {})["pre"] = pre
        for post in post_tokens:
            key = (post.get("accountIndex"), post.get("mint"))
            by.setdefault(key, {})["post"] = post
        for (acct,mint), d in by.items():
            pre_amt = d.get("pre", {}).get("uiTokenAmount", {}).get("uiAmountString", "0")
            post_amt = d.get("post", {}).get("uiTokenAmount", {}).get("uiAmountString", "0")
            lines.append(f"• <code>{mint}</code> : {pre_amt} -> {post_amt} (acctIdx {acct})")
    # instructions
    instrs = r.get("transaction", {}).get("message", {}).get("instructions", []) or []
    if instrs:
        lines.append("⚙️ <b>Instructions (extraits)</b>:")
        for ins in instrs[:3]:
            prog = ins.get("program")
            parsed = ins.get("parsed")
            if parsed:
                snippet = json.dumps(parsed)[:120]
                lines.append(f"- {prog}: {snippet}")
            else:
                lines.append(f"- {prog}: raw")
    return "\n".join(lines)

# === websocket main (async) ===
async def ws_main_loop():
    cache = load_json(CACHE_FILE)
    processed = set(cache.get("sigs", []))
    backoff = RECONNECT_BASE
    print("[WS] starting - WS_RPC:", WS_RPC, "HTTP_RPC:", HTTP_RPC)
    async with aiohttp.ClientSession() as http_sess:
        while True:
            try:
                print("[WS] connecting to", WS_RPC)
                async with websockets.connect(WS_RPC, ping_interval=20, ping_timeout=10) as ws:
                    print("[WS] connected")
                    subs = load_json(SUB_FILE)
                    watch_wallets = list(subs.keys())
                    # subscribe logs/account for each wallet
                    for w in watch_wallets:
                        try:
                            req1 = {"jsonrpc":"2.0","id":int(time.time()*1000),"method":"logsSubscribe","params":[{"mentions":[w]}, {"commitment":"finalized"}]}
                            await ws.send(json.dumps(req1))
                            req2 = {"jsonrpc":"2.0","id":int(time.time()*1000),"method":"accountSubscribe","params":[w, {"encoding":"base64","commitment":"finalized"}]}
                            await ws.send(json.dumps(req2))
                        except Exception as e:
                            print("[WS] subscribe error:", e)
                    # read loop
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception as e:
                            continue
                        print("[WS] msg:", json.dumps(msg)[:800])
                        # handle logsNotification (preferred)
                        if msg.get("method") == "logsNotification":
                            params = msg.get("params", {})
                            result = params.get("result", {})
                            value = result.get("value", {}) or {}
                            signature = value.get("signature")
                            mentions = value.get("mentions") or []
                            if not signature:
                                continue
                            if signature in processed:
                                print("[WS] seen", signature)
                                continue
                            print("[WS] new signature", signature)
                            tx = await get_transaction(http_sess, signature)
                            text = build_message_from_tx(tx)
                            # determine recipients: mentions -> direct mapping
                            recipients = set()
                            if mentions:
                                subs_local = load_json(SUB_FILE)
                                for m in mentions:
                                    for cid in subs_local.get(m, []):
                                        recipients.add(str(cid))
                            # heuristic fallback: try matching via getSignaturesForAddress for tracked wallets
                            if not recipients:
                                subs_local = load_json(SUB_FILE)
                                for tracked in subs_local.keys():
                                    try:
                                        sigs = await get_signatures_for_address(http_sess, tracked, limit=1)
                                        if sigs and sigs.get("result") and sigs["result"][0].get("signature") == signature:
                                            for cid in subs_local.get(tracked, []):
                                                recipients.add(str(cid))
                                    except Exception as e:
                                        pass
                            if not recipients and DEBUG_CHAT_ID:
                                recipients.add(str(DEBUG_CHAT_ID))
                            # send
                            for rcpt in recipients:
                                await send_message_async(rcpt, text, http_sess)
                            # persist processed
                            processed.add(signature)
                            cache.setdefault("sigs", []).append(signature)
                            if len(cache["sigs"]) > MAX_CACHE:
                                cache["sigs"] = cache["sigs"][-MAX_CACHE:]
                            save_json(CACHE_FILE, cache)
                        elif msg.get("method") == "accountNotification":
                            # fallback: check recent signature for each tracked wallet
                            subs_local = load_json(SUB_FILE)
                            for tracked in subs_local.keys():
                                try:
                                    sigs = await get_signatures_for_address(http_sess, tracked, limit=1)
                                    if sigs and sigs.get("result"):
                                        sig = sigs["result"][0].get("signature")
                                        if sig and sig not in processed:
                                            tx = await get_transaction(http_sess, sig)
                                            text = build_message_from_tx(tx)
                                            for cid in subs_local.get(tracked, []):
                                                await send_message_async(str(cid), text, http_sess)
                                            processed.add(sig)
                                            cache.setdefault("sigs", []).append(sig)
                                            if len(cache["sigs"]) > MAX_CACHE:
                                                cache["sigs"] = cache["sigs"][-MAX_CACHE:]
                                            save_json(CACHE_FILE, cache)
                                except Exception as e:
                                    pass
                        else:
                            # ignore other messages
                            pass
            except Exception as e:
                print("[WS] exception:", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, MAX_RECONNECT)

# === Flask admin endpoints and health ===
app = Flask(__name__)

def check_admin(req):
    # header first
    header = req.headers.get("X-ADMIN-PASSWORD")
    if header and BOT_PASSWORD and header == BOT_PASSWORD:
        return True
    # try json body
    try:
        j = req.get_json(silent=True) or {}
        if j.get("admin_password") and BOT_PASSWORD and j.get("admin_password") == BOT_PASSWORD:
            return True
    except:
        pass
    return False

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/admin/list", methods=["GET"])
def admin_list():
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_json(SUB_FILE)), 200

@app.route("/admin/add", methods=["POST"])
def admin_add():
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    wallet = body.get("wallet")
    chat_id = body.get("chat_id")
    if not wallet or not chat_id:
        return jsonify({"error": "wallet & chat_id required"}), 400
    subs = load_json(SUB_FILE)
    lst = subs.get(wallet, [])
    if str(chat_id) not in [str(x) for x in lst]:
        lst.append(int(chat_id))
    subs[wallet] = lst
    save_json(SUB_FILE, subs)
    return jsonify({"ok": True, "subscriptions": subs}), 200

@app.route("/admin/remove", methods=["POST"])
def admin_remove():
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    wallet = body.get("wallet")
    chat_id = body.get("chat_id")
    if not wallet or not chat_id:
        return jsonify({"error": "wallet & chat_id required"}), 400
    subs = load_json(SUB_FILE)
    if wallet in subs:
        subs[wallet] = [c for c in subs[wallet] if str(c) != str(chat_id)]
        if not subs[wallet]:
            subs.pop(wallet, None)
        save_json(SUB_FILE, subs)
    return jsonify({"ok": True, "subscriptions": subs}), 200

@app.route("/admin/test", methods=["POST"])
def admin_test():
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    text = body.get("text", "Test message")
    broadcast_sync(text)
    return jsonify({"ok": True}), 200

# === Telegram polling (commands for users) ===
def telegram_polling_loop():
    print("[Bot] Telegram polling started")
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = (msg.get("text") or "").strip()
                print("[Bot] update", chat_id, text)
                if not text.startswith("/"):
                    continue
                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                # /login
                if cmd == "/login":
                    if not args:
                        send_message_sync(chat_id, "Envoie : /login <mot_de_passe_admin>")
                        continue
                    if BOT_PASSWORD and args == BOT_PASSWORD:
                        auth = load_json(AUTH_FILE)
                        auth[str(chat_id)] = True
                        save_json(AUTH_FILE, auth)
                        send_message_sync(chat_id, "🔓 Connecté. Utilise /add /remove /list /my")
                    else:
                        send_message_sync(chat_id, "❌ Mot de passe incorrect.")
                    continue
                # other commands require logged in
                auth = load_json(AUTH_FILE)
                if not auth.get(str(chat_id)):
                    send_message_sync(chat_id, "🔐 Tu dois d'abord te connecter : /login <mot_de_passe_admin>")
                    continue
                # /add
                if cmd == "/add" and args:
                    wallet = args.strip()
                    subs = load_json(SUB_FILE)
                    lst = subs.get(wallet, [])
                    if str(chat_id) not in [str(x) for x in lst]:
                        lst.append(int(chat_id))
                        subs[wallet] = lst
                        save_json(SUB_FILE, subs)
                        send_message_sync(chat_id, f"✅ Abonné au wallet {wallet}")
                    else:
                        send_message_sync(chat_id, f"ℹ️ Déjà abonné à {wallet}")
                    continue
                # /remove
                if cmd == "/remove" and args:
                    wallet = args.strip()
                    subs = load_json(SUB_FILE)
                    if wallet in subs and int(chat_id) in subs[wallet]:
                        subs[wallet] = [c for c in subs[wallet] if int(c) != int(chat_id)]
                        if not subs[wallet]:
                            subs.pop(wallet, None)
                        save_json(SUB_FILE, subs)
                        send_message_sync(chat_id, f"✅ Désabonné de {wallet}")
                    else:
                        send_message_sync(chat_id, "❌ Tu n'étais pas abonné à ce wallet")
                    continue
                # /list
                if cmd == "/list":
                    subs = load_json(SUB_FILE)
                    if not subs:
                        send_message_sync(chat_id, "Aucun wallet suivi.")
                    else:
                        send_message_sync(chat_id, "<b>Wallets suivis:</b>\n" + "\n".join(subs.keys()))
                    continue
                # /my
                if cmd == "/my":
                    subs = load_json(SUB_FILE)
                    my = [w for w,lst in subs.items() if int(chat_id) in [int(x) for x in lst]]
                    if my:
                        send_message_sync(chat_id, "<b>Tes abonnements:</b>\n" + "\n".join(my))
                    else:
                        send_message_sync(chat_id, "Tu n'es abonné à aucun wallet.")
                    continue
        except Exception as e:
            print("[Bot] polling error", e)
            time.sleep(5)

# === start background tasks & flask ===
def start_background():
    th = threading.Thread(target=telegram_polling_loop, daemon=True)
    th.start()
    def run_async():
        asyncio.run(ws_main_loop())
    th2 = threading.Thread(target=run_async, daemon=True)
    th2.start()

if __name__ == "__main__":
    print("=== Solana RPC public tracker starting ===")
    start_background()
    app.run(host="0.0.0.0", port=FLASK_PORT, use_reloader=False)
