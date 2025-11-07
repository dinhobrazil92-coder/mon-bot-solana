#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Tracker Solana Pro Debug
- Notifications : SOL, SPL, NFT
- Debug complet pour voir le flux des événements
"""

import os
import json
import time
import threading
import requests
from flask import Flask, request, jsonify

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY")
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
def send_message(chat_id, text, parse_mode="HTML"):
    print(f"[DEBUG] Envoi message à {chat_id}: {text[:50]}…")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10
        )
        if r.status_code != 200:
            print(f"[TG] Erreur {r.status_code}: {r.text}")
        else:
            print(f"[DEBUG] Message envoyé avec succès à {chat_id}")
    except Exception as e:
        print(f"[TG] Exception: {e}")

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) in load_json(AUTHORIZED_FILE)

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === FLASK APP ===
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Bot Solana Pro Debug actif avec webhook Helius"

@app.route("/health")
def health():
    return "OK", 200

# === WEBHOOK HELIUS ===
@app.route("/helius", methods=["POST"])
def helius_webhook():
    payload = request.get_json()
    print("[DEBUG] Webhook reçu :", json.dumps(payload, indent=2))

    if not payload:
        return "No data", 400

    subs = load_json(SUBSCRIPTIONS_FILE)
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        events = payload.get("events") or payload.get("tokenTransfers") or payload.get("nftTransfers") or []
    else:
        events = []

    for event in events:
        try:
            wallet = event.get("account") or event.get("fromUserAccount") or event.get("source") or "inconnu"
            tx_hash = event.get("signature") or event.get("txHash") or event.get("transactionHash") or "inconnu"
            token_standard = event.get("tokenStandard", "SOL")
            emoji = "💎" if token_standard == "SOL" else "🪙" if token_standard == "SPL" else "🖼️"

            if "lamports" in event:
                amount = round(event.get("lamports", 0)/1e9, 9)
                amount_str = f"{amount} SOL"
            else:
                amount_str = str(event.get("amount") or event.get("tokenAmount") or "?")

            mint = event.get("mint") or event.get("tokenAddress") or "?"
            name = event.get("name") or event.get("metadata", {}).get("name") or mint
            image = event.get("metadata", {}).get("image") or None
            action_type = event.get("type") or "Transaction"
            if token_standard != "SOL":
                action_type += f" ({token_standard})"

            message = f"{emoji} <b>{action_type}</b>\n\n" \
                      f"👛 Wallet: <code>{wallet}</code>\n" \
                      f"🪙 Token: <b>{name}</b> (<code>{mint}</code>)\n" \
                      f"💵 Montant: <code>{amount_str}</code>\n" \
                      f"🔗 <a href='https://solscan.io/tx/{tx_hash}'>Voir transaction</a>"

            if image:
                message += f"\n🖼️ Image NFT: {image}"

            print(f"[DEBUG] Abonnés pour {wallet}: {subs.get(wallet, [])}")

            for cid in subs.get(wallet, []):
                if is_authorized(cid):
                    print(f"[DEBUG] Envoi notification à {cid}")
                    send_message(cid, message)

        except Exception as e:
            print(f"[Helius webhook] Erreur: {e}")

    return jsonify({"status": "ok"}), 200

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
            for update in resp.get("result", []):
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
    print("🚀 Bot Solana Pro Debug lancé (Webhook + Telegram)")
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)








