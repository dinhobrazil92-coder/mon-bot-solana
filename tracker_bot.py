#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Tracker Solana avec Webhook Helius
- Notifications instantanées : achat, vente, création de token
- Compatible Render (port + serveur Flask)
"""

import os
import json
import time
import threading
import requests
from flask import Flask, request

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_TELEGRAM_ICI")
PASSWORD = os.getenv("PASSWORD", "Business2026$")
PORT = int(os.getenv("PORT", 10000))

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"

# === OUTILS FICHIERS ===
def load_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[load_json] Erreur {file_path}: {e}")
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[save_json] Erreur {file_path}: {e}")

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN:
        print("[send_message] BOT_TOKEN manquant")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if resp.status_code != 200:
            print(f"[TG] Erreur {resp.status_code}: {resp.text}")
        else:
            print(f"[TG] ✅ Message envoyé à {chat_id}")
    except Exception as e:
        print(f"[TG] Exception: {e}")

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) in load_json(AUTHORIZED_FILE)

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === FLASK SERVER ===
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Bot Solana actif avec webhook Helius"

@app.route("/health")
def health():
    return "OK", 200

# === WEBHOOK HELIUS ===
@app.route("/helius", methods=["POST"])
def helius_webhook():
    data = request.get_json()
    if not data:
        return "No data", 400

    subs = load_json(SUBSCRIPTIONS_FILE)
    print(f"[Helius] Événement reçu: {json.dumps(data, indent=2)}")

    for event in data.get("events", []):
        try:
            wallet = event.get("account", "inconnu")
            tx_hash = event.get("signature", "inconnu")
            amount = event.get("amount", "?")
            mint = event.get("mint", "?")
            action_type = event.get("type", "Transaction")

            message = (
                f"💰 <b>{action_type}</b>\n\n"
                f"👛 Wallet: <code>{wallet}</code>\n"
                f"🪙 Token: <code>{mint}</code>\n"
                f"💵 Montant: <code>{amount}</code>\n"
                f"🔗 <a href='https://solscan.io/tx/{tx_hash}'>Voir la transaction</a>"
            )

            # Envoi du message à tous les abonnés du wallet
            for cid in subs.get(wallet, []):
                if is_authorized(cid):
                    send_message(cid, message)
        except Exception as e:
            print(f"[Helius webhook] Erreur lors du traitement: {e}")

    return "OK", 200

# === BOT TELEGRAM ===
def bot():
    print("[Bot] Démarrage du polling Telegram...")
    offset = 0
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
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"):
                    continue

                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/login" and args == PASSWORD:
                    authorize(chat_id)
                    send_message(chat_id, "🔓 Accès autorisé !\n\nCommandes :\n/add WALLET\n/remove WALLET\n/list\n/my")
                    continue
                if not is_authorized(chat_id):
                    send_message(chat_id, f"🔐 Connecte-toi : /login {PASSWORD}")
                    continue

                if cmd == "/add" and args:
                    wallet = args.strip()
                    if len(wallet) < 32:
                        send_message(chat_id, "⚠️ Wallet invalide.")
                        continue
                    if wallet not in subs:
                        subs[wallet] = []
                    if chat_id not in subs[wallet]:
                        subs[wallet].append(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"👀 Suivi activé pour <code>{wallet}</code>")
                    else:
                        send_message(chat_id, f"✅ Déjà abonné à <code>{wallet}</code>")

                elif cmd == "/remove" and args:
                    wallet = args.strip()
                    if wallet in subs and chat_id in subs[wallet]:
                        subs[wallet].remove(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"❌ Suivi arrêté pour <code>{wallet}</code>")
                    else:
                        send_message(chat_id, "Pas d'abonnement trouvé.")

                elif cmd == "/list":
                    wallets = list(subs.keys())
                    if not wallets:
                        send_message(chat_id, "Aucun wallet suivi.")
                    else:
                        msg = "<b>📜 Wallets suivis :</b>\n" + "\n".join(wallets)
                        send_message(chat_id, msg)

                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        send_message(chat_id, "<b>👤 Tes abonnements :</b>\n" + "\n".join(my))
                    else:
                        send_message(chat_id, "Tu n'es abonné à aucun wallet.")
        except Exception as e:
            print(f"[Bot] Erreur : {e}")
            time.sleep(5)

# === MAIN ===
if __name__ == "__main__":
    print("🚀 Bot Solana lancé (Webhook + Telegram)")
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
