#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram tracker de wallet Solana (RPC officiel)
- Surveille les transactions récentes des wallets
- Envoie des notifications Telegram
- Compatible Render
"""

import os
import time
import requests

# === CONFIG ===
BOT_TOKEN = "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
CHAT_ID = "8228401361"  # Chat ID du groupe ou utilisateur Telegram
PASSWORD = os.getenv("PASSWORD", "**********")  # Masqué pour sécurité
RPC_URL = "https://api.mainnet-beta.solana.com"  # RPC public officiel

# Liste des wallets à suivre (tu peux en ajouter autant que tu veux)
WATCHED_WALLETS = [
    "H3px97q4yksPtBG95YkQfAkEbFJMiXe8xyr9r2DzxX6A",  # Wallet test actif
    # "TA_WALLET_ICI"
]

# === FONCTIONS UTILITAIRES ===
def send_telegram_message(text: str):
    """Envoie un message Telegram."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"[ERREUR TELEGRAM] {r.text}")
    except Exception as e:
        print(f"[ERREUR TELEGRAM] {e}")


def get_recent_transactions(wallet: str, limit=5):
    """Récupère les transactions récentes d’un wallet via RPC."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": limit}],
        }
        r = requests.post(RPC_URL, json=payload)
        data = r.json()
        return data.get("result", [])
    except Exception as e:
        print(f"[ERREUR RPC] {e}")
        return []


def get_transaction_detail(signature: str):
    """Récupère le détail complet d’une transaction."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "jsonParsed"}],
        }
        r = requests.post(RPC_URL, json=payload)
        data = r.json()
        return data.get("result", {})
    except Exception as e:
        print(f"[ERREUR TRANSACTION] {e}")
        return {}


# === LOGIQUE PRINCIPALE ===
def main():
    print("🚀 Bot Solana RPC en cours d’exécution...")
    last_tx = {w: None for w in WATCHED_WALLETS}

    while True:
        for wallet in WATCHED_WALLETS:
            txs = get_recent_transactions(wallet)
            if not txs:
                continue

            latest_sig = txs[0]["signature"]
            if last_tx[wallet] is None:
                last_tx[wallet] = latest_sig
                continue

            if latest_sig != last_tx[wallet]:
                print(f"🔍 Nouvelle transaction pour {wallet}")
                tx_detail = get_transaction_detail(latest_sig)

                msg = f"💸 Nouvelle transaction détectée pour <code>{wallet}</code>\n\n"
                msg += f"🔗 <a href='https://solscan.io/tx/{latest_sig}'>Voir sur Solscan</a>"

                send_telegram_message(msg)
                last_tx[wallet] = latest_sig

        time.sleep(15)  # Vérifie toutes les 15 secondes


if __name__ == "__main__":
    main()

