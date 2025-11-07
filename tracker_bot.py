#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Tracker Solana
- RPC Public Solana
- Notifications ACHAT/VENTE/CRÉATION
- Pré-autorisé : 8228401361
- Mdp caché : Business2026$
"""
import os
import time
import threading
import json
import requests
from datetime import datetime
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k")
PASSWORD = os.getenv("PASSWORD", "Business2026$")
PORT = int(os.getenv("PORT", 10000))

# === PRÉ-AUTORISÉ ===
MY_CHAT_ID = "8228401361"

# === FICHIERS ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# === UTILITAIRES ===
def load_json(file):
    if not os.path.exists(file):
        return {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

def load_list(file):
    if not os.path.exists(file):
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_list(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except:
        pass

def load_set(file):
    return set(load_list(file))

def save_set(file, data):
    save_list(file, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE):
        return 0
    try:
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w") as f:
            f.write(str(uid))
    except:
        pass

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) == MY_CHAT_ID or str(chat_id) in load_json(AUTHORIZED_FILE)

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN:
        print("[ERR] BOT_TOKEN manquant")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if resp.status_code == 200:
            print(f"[OK] Envoyé à {chat_id}")
        else:
            print(f"[ERR] TG {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERR] TG Exception: {e}")

# === TEST AUTO ===
def auto_test():
    time.sleep(10)
    send_message(MY_CHAT_ID, "🚀 BOT DÉMARRÉ !\n\nTest OK.\nEnvoie /add <wallet> pour tracker.")

# === RPC SOLANA ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc_post(method, params=None):
    if params is None:
        params = []
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    try:
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[ERR] RPC {method}: {e}")
        return None

def get_signatures(wallet, limit=10):
    return rpc_post("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc_post("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_token_creation(tx, wallet):
    if not tx:
        return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    for instr in instructions:
        if instr.get("programId") == MINT_PROGRAM:
            parsed = instr.get("parsed", {})
            if parsed.get("type") == "initializeMint":
                info = parsed.get("info", {})
                if info.get("mintAuthority") == wallet:
                    return info.get("mint")
    return None

def detect_token_transfer(tx, wallet):
    if not tx:
        return None
    all_instructions = []
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    all_instructions.extend(instructions)
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        all_instructions.extend(inner.get("instructions", []))
    for instr in all_instructions:
        if instr.get("programId") == TOKEN_PROGRAM:
            parsed = instr.get("parsed", {})
            if parsed.get("type") in ("transfer", "transferChecked"):
                info = parsed.get("info", {})
                source = info.get("source")
                destination = info.get("destination")
                mint = info.get("mint") or "?"
                amount = info.get("amount")
                decimals = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
                if destination == wallet:
                    return "ACHAT", mint, amount, decimals
                if source == wallet:
                    return "VENTE", mint, amount, decimals
    return None

# === TRACKER ===
def tracker():
    print("[OK] Tracker démarré")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue
            for wallet in wallets:
                sigs = get_signatures(wallet, 10)
                for sig_data in sigs:
                    sig = sig_data.get("signature")
                    if not sig or sig in seen:
                        continue
                    tx = get_transaction(sig)
                    if not tx:
                        seen.add(sig)
                        save_set(SEEN_FILE, seen)
                        continue

                    # Création
                    creation = detect_token_creation(tx, wallet)
                    if creation:
                        msg = f"🚨 <b>NOUVEAU TOKEN CRÉÉ</b>\n\n<a href=\"https://solscan.io/tx/{sig}\">Voir tx</a>\n<code>{wallet[:8]}...{wallet[-6:]}</code>\n<code>{creation[:8]}...{creation[-6:]}</code>"
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for cid in subs.get(wallet, []):
                            if is_authorized(cid):
                                send_message(cid, msg)

                    # Transfert
                    transfer = detect_token_transfer(tx, wallet)
                    if transfer:
                        action, mint, amount_raw, decimals = transfer
                        try:
                            if decimals is not None:
                                amount = int(amount_raw) / (10 ** int(decimals))
                            else:
                                amount = int(amount_raw) / 1_000_000_000
                            amount_str = f"{amount:,.8f}".rstrip("0").rstrip(".")
                        except:
                            amount_str = str(amount_raw)
                        msg = f"🚨 <b>{action}</b>\n\n<a href=\"https://solscan.io/tx/{sig}\">Voir tx</a>\n<code>{wallet[:8]}...{wallet[-6:]}</code>\n<code>{mint[:8]}...{mint[-6:]}</code>\n<code>{amount_str}</code>"
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for cid in subs.get(wallet, []):
                            if is_authorized(cid):
                                send_message(cid, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(15)
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[OK] Bot démarré")
    offset = load_update_id()
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()
            updates = resp.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                save_update_id(offset)
                msg = update.get("message") or {}
                chat_id = msg.get("chat", {}).get("type") == "private" and msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not chat_id or not text.startswith("/"):
                    continue
                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == PASSWORD:
                    authorize(chat_id)
                    send_message(chat_id, "✅ Accès autorisé !\n\n/add <wallet> pour tracker.")
                    continue
                if not is_authorized(chat_id):
                    send_message(chat_id, f"🔒 Connecte-toi :\n<code>/login {PASSWORD}</code>")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send_message(chat_id, "⚠️ Wallet invalide.")
                        continue
                    current = load_list(WALLETS_FILE)
                    if w not in current:
                        current.append(w)
                        save_list(WALLETS_FILE, current)
                    if w not in subs:
                        subs[w] = []
                    if chat_id not in subs[w]:
                        subs[w].append(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"✅ Suivi activé :\n<code>{w}</code>")
                    else:
                        send_message(chat_id, "ℹ️ Déjà suivi.")

                elif cmd == "/remove" and args:
                    w = args.strip()
                    if w in subs and chat_id in subs[w]:
                        subs[w].remove(chat_id)
                        if not subs[w]:
                            del subs[w]
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"✅ Arrêt suivi :\n<code>{w}</code>")
                    else:
                        send_message(chat_id, "❌ Pas suivi.")

                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        txt = "<b>Tes wallets :</b>\n\n"
                        for w in my:
                            txt += f"• <code>{w}</code>\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, "📭 Aucun wallet suivi.")

                elif cmd == "/list":
                    wallets = load_list(WALLETS_FILE)
                    if wallets:
                        txt = "<b>Wallets suivis :</b>\n\n"
                        for w in wallets:
                            count = len([u for u in subs.get(w, []) if is_authorized(u)])
                            txt += f"• <code>{w}</code> ({count} abonnés)\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, "📭 Aucun wallet.")

        except Exception as e:
            print(f"[ERR] Bot: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot Solana Tracker ON"

@app.route("/health")
def health():
    return "OK", 200

# === MAIN ===
if __name__ == "__main__":
    print("Démarrage bot...")
    pre_authorize()
    threading.Thread(target=auto_test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
