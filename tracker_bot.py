#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time

# === CONFIG ===
BOT_TOKEN = "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
CHAT_ID = 8228401361  # ton chat_id

def send_message(chat_id, text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode":"HTML"},
            timeout=10
        )
        print(f"[DEBUG] Status: {r.status_code}, Response: {r.text}")
    except Exception as e:
        print(f"[DEBUG] Exception envoi Telegram: {e}")

if __name__ == "__main__":
    print("🚀 Test Telegram démarré...")
    send_message(CHAT_ID, "✅ Test Telegram fonctionne !")

    # Optionnel : envoyer plusieurs messages pour tester
    for i in range(3):
        time.sleep(2)
        send_message(CHAT_ID, f"🔔 Message de test #{i+1}")





