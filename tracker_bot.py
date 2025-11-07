#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import requests
from flask import Flask, request, jsonify

# === CONFIG ===
BOT_TOKEN = "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
CHAT_ID = 8228401361  # ton chat_id
PORT = 10000

# === FLASK APP ===
app = Flask(__name__)

def send_message(chat_id, text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode":"HTML"},
            timeout=10
        )
        print(f"[DEBUG] Envoi à {chat_id}: Status {r.status_code}, Response: {r.text}")
    except Exception as e:
        print(f"[DEBUG] Exception envoi Telegram: {e}")

@app.route("/")
def index():
    return "✅ Bot Telegram minimal actif"

@app.route("/helius", methods=["POST"])
def helius_webhook():
    data = request.get_json()
    if not data:
        return "No data", 400

    print("[DEBUG] Payload reçu Helius:", json.dumps(data, indent=2))

    # Forcer events à toujours être une liste
    if isinstance(data, dict):
        events = data.get("events") or data.get("tokenTransfers") or data.get("nftTransfers") or []
    elif isinstance(data, list):
        events = data
    else:
        events = []

    for event in events:
        try:
            wallet = event.get("account") or event.get("fromUserAccount") or event.get("toUserAccount") or "inconnu"
            tx_hash = event.get("signature") or event.get("txHash") or "inconnu"
            token_standard = event.get("tokenStandard", "SOL")
            emoji = "💎" if token_standard=="SOL" else "🪙" if token_standard=="SPL" else "🖼️"

            # Montant
            if "lamports" in event:
                amount = round(event.get("lamports",0)/1e9,9)
                amount_str = f"{amount} SOL"
            else:
                amount_str = str(event.get("amount") or event.get("tokenAmount") or "?")

            mint = event.get("mint") or event.get("tokenAddress") or "?"
            name = event.get("name") or event.get("metadata",{}).get("name") or mint
            image = event.get("metadata",{}).get("image") or None
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

            print("[DEBUG] Envoi message Telegram:", message)
            send_message(CHAT_ID, message)

        except Exception as e:
            print(f"[DEBUG] Erreur traitement event: {e}")

    return jsonify({"status":"ok"}), 200

if __name__=="__main__":
    print("🚀 Bot Telegram minimal prêt à recevoir Helius")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)






