#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram + Tracker Solana via HELIUS RPC
Prêt pour Render + Disque persistant
"""
import os
import time
import threading
import json
import requests
import html
from datetime import datetime
from flask import Flask

# === CONFIG ===
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "c888ba69-de31-43b7-b6c6-f6f841351f56").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY").strip()
PASSWORD = os.getenv("PASSWORD", "Business2026$").strip()
PORT = int(os.getenv("PORT", 10000))

# === FICHIERS (disque persistant) ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"
AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"

# === HELIUS RPC URL ===
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# === UTILITAIRES ===
def load_json(file): return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}
def save_json(file, data): json.dump(data, open(file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
def load_list(file): return [l.strip() for l in open(file, "r", encoding="utf-8").readlines() if l.strip()] if os.path.exists(file) else []
def save_list(file, data): open(file, "w", encoding="utf-8").write("\n".join(data) + "\n")
def load_set(file): return set(load_list(file))
def save_set(file, data): save_list(file, list(data))
def load_update_id(): return int(open(UPDATE_ID_FILE).read().strip()) if os.path.exists(UPDATE_ID_FILE) else 0
def save_update_id(uid): open(UPDATE_ID_FILE, "w").write(str(uid))

# === AUTH ===
def is_authorized(chat_id): return str(chat_id) in load_json(AUTHORIZED_FILE)
def authorize_user(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === TEMPLATES ===
def default_templates():
    return {
        "tx_detected": "🚨 <b>{action} DÉTECTÉ !</b>\n\n"
                       "🔗 <a href=\"{link}\">Voir sur Solscan</a>\n"
                       "👤 Wallet: <code>{wallet}</code>\n"
                       "🪙 Token: <code>{mint}</code>\n"
                       "💸 Montant: <code>{amount}</code>\n"
                       "🕒 Heure: <code>{time}</code>",
        "access_granted": "✅ Accès autorisé !\nUtilise /add <wallet>",
        "must_login": "🔒 /login {password}",
        "now_following": "✅ Suivi : <code>{wallet}</code>",
        "wallet_invalid": "⚠️ Wallet invalide (min 32 caractères).",
        "no_wallets": "Aucun wallet suivi."
    }
def load_templates(): return load_json("templates.json") or default_templates()

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10
        )
    except: pass

# === HELIUS RPC (corrigé) ===
def rpc_post(method, params=[]):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(HELIUS_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[RPC ERROR] {method}: {e}")
        return None

def get_signatures(wallet, limit=10):
    return rpc_post("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc_post("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION TRANSFERT TOKEN ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def find_token_transfer(tx, wallet):
    if not tx: return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    meta = tx.get("meta", {}) or {}
    all_instr = instructions[:]
    for inner in meta.get("innerInstructions", []):
        all_instr.extend(inner.get("instructions", []))

    for i in all_instr:
        if i.get("programId") != TOKEN_PROGRAM: continue
        p = i.get("parsed", {}) or {}
        info = p.get("info", {})
        if p.get("type") not in ("transfer", "transferChecked"): continue

        source = info.get("source")
        dest = info.get("destination")
        mint = info.get("mint") or info.get("mintAccount")
        amount = info.get("amount")
        if "tokenAmount" in info:
            ta = info["tokenAmount"]
            amount = ta.get("amount")
            decimals = ta.get("decimals")

        if dest == wallet:
            return {"type": "ACHAT", "mint": mint or "?", "amount": amount, "decimals": decimals}
        if source == wallet:
            return {"type": "VENTE", "mint": mint or "?", "amount": amount, "decimals": decimals}
    return None

# === TRACKER ===
def tracker():
    print("Tracker démarré (Helius)")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue

            for wallet in wallets:
                sigs = get_signatures(wallet, limit=10)
                for s in sigs:
                    sig = s["signature"]
                    if sig in seen: continue

                    tx = get_transaction(sig)
                    transfer = find_token_transfer(tx, wallet)
                    if transfer:
                        amount = transfer["amount"]
                        try:
                            if transfer.get("decimals") is not None:
                                amount = f"{int(amount) / (10 ** int(transfer['decimals'])):,.8f}".rstrip("0").rstrip(".")
                            else:
                                amount = f"{int(amount) / 1_000_000_000:,.2f}"
                        except: amount = str(amount)

                        msg = default_templates()["tx_detected"].format(
                            action=transfer["type"],
                            link=f"https://solscan.io/tx/{sig}",
                            wallet=wallet[:8] + "..." + wallet[-6:],
                            mint=transfer["mint"][:8] + "..." + transfer["mint"][-6:],
                            amount=amount,
                            time=datetime.utcnow().strftime("%H:%M:%S")
                        )
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for chat_id in subs.get(wallet, []):
                            if is_authorized(chat_id):
                                send_message(chat_id, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(15)
        except Exception as e:
            print(f"[Tracker error] {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("Bot Telegram démarré")
    offset = load_update_id()
    while True:
        try:
            updates = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}, timeout=40
            ).json().get("result", [])

            for u in updates:
                offset = u["update_id"] + 1
                save_update_id(offset)
                msg = u.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"): continue

                cmd, *args = text.split()
                args = " ".join(args)
                cmd = cmd.lower()

                if cmd == "/login" and args == PASSWORD:
                    authorize_user(chat_id)
                    send_message(chat_id, default_templates()["access_granted"])
                    continue
                if not is_authorized(chat_id):
                    send_message(chat_id, default_templates()["must_login"].format(password=PASSWORD))
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send_message(chat_id, default_templates()["wallet_invalid"])
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
                        send_message(chat_id, default_templates()["now_following"].format(wallet=w))
                elif cmd == "/my":
                    my = [w for w, u in subs.items() if chat_id in u]
                    send_message(chat_id, "\n".join([f"• <code>{w}</code>" for w in my]) or "Aucun")
        except Exception as e:
            print(f"[Bot error] {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"); return "Bot actif"
@app.route("/health"); return "OK", 200

# === MAIN ===
if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)

render.yaml
yamlservices:
  - type: web
    name: solana-bot
    env: python
    buildCommand: pip install requests flask
    startCommand: python bot.py
    envVars:
      HELIUS_API_KEY: "c888ba69-de31-43b7-b6c6-f6f841351f56"
      BOT_TOKEN: "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
      PASSWORD: "Business2026$"
    disk:
      name: data
      mountPath: /app/data
      sizeGB: 1
