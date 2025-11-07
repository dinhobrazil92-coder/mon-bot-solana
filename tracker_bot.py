import os
import time
import requests
from flask import Flask, jsonify

# === CONFIGURATION ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RPC_URL = "https://api.mainnet-beta.solana.com"

# Liste des wallets à surveiller
WATCHED_WALLETS = [
    "YourWalletAddress1",
    "YourWalletAddress2"
]

# Historique simple pour éviter les doublons
last_signatures = {}

app = Flask(__name__)

def get_confirmed_transactions(wallet_address):
    """Récupère les dernières transactions d'un wallet Solana via RPC officiel."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet_address, {"limit": 5}]
    }

    try:
        response = requests.post(RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "result" in data:
            return data["result"]
        return []
    except Exception as e:
        print(f"[ERREUR RPC] {e}")
        return []


def get_transaction_details(signature):
    """Récupère les détails d'une transaction."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed"}]
    }
    try:
        response = requests.post(RPC_URL, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get("result")
    except Exception as e:
        print(f"[ERREUR DETAIL TX] {e}")
        return None


def send_telegram_message(text):
    """Envoie une notification sur Telegram."""
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("[ERREUR] Bot token ou chat_id manquant.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[ERREUR TELEGRAM] {e}")


def analyze_and_notify(wallet):
    """Analyse les transactions et envoie les alertes Telegram."""
    global last_signatures
    txs = get_confirmed_transactions(wallet)
    if not txs:
        return

    for tx in txs:
        sig = tx["signature"]
        if wallet not in last_signatures:
            last_signatures[wallet] = []
        if sig in last_signatures[wallet]:
            continue  # déjà traité

        details = get_transaction_details(sig)
        if not details:
            continue

        message = f"💰 Nouvelle transaction détectée pour {wallet}\nSignature: {sig}"
        send_telegram_message(message)

        last_signatures[wallet].append(sig)
        if len(last_signatures[wallet]) > 10:
            last_signatures[wallet].pop(0)


@app.route("/")
def home():
    return jsonify({"status": "Bot Solana RPC en ligne 🚀"})


def main_loop():
    print("🔄 Démarrage du suivi des wallets Solana...")
    while True:
        for wallet in WATCHED_WALLETS:
            analyze_and_notify(wallet)
        time.sleep(20)


if __name__ == "__main__":
    if os.getenv("RUN_MODE") == "server":
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
    else:
        main_loop()
