#!/usr/bin/env python3
import os
import time
import threading
import requests
from flask import Flask

# === CONFIG FIXE ===
BOT_TOKEN = "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k"
MY_CHAT_ID = "8228401361"
PORT = 10000

# === WALLET ULTRA-ACTIF (100+ TX/HEURE) ===
WALLET = "J1mpXz3tX4v6Z1q8W9eR2tY5uI7oP3aS4dF6gH8jK9L1"

# === RPC (HELIUS + FALLBACK) ===
HELIUS_URL = "https://mainnet.helius-rpc.com/?api-key=c888ba69-de31-43b7-b6c6-f6f841351f56"
FALLBACK_URL = "https://api.mainnet-beta.solana.com"

# === ENVOI MESSAGE ===
def send(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": MY_CHAT_ID, "text": text},
            timeout=10
        )
    except:
        pass

# === RPC AVEC FALLBACK ===
def rpc(method, params):
    for url in [HELIUS_URL, FALLBACK_URL]:
        try:
            r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10)
            if r.status_code == 200:
                return r.json().get("result")
        except:
            continue
    return None

# === TRACKER ===
seen = set()

def tracker():
    time.sleep(15)
    send(f"BOT ACTIF\n\nWallet : {WALLET[:8]}...{WALLET[-6:]}\n\nPremière TX dans < 60s")

    while True:
        sigs = rpc("getSignaturesForAddress", [WALLET, {"limit": 5}]) or []
        for s in sigs:
            sig = s.get("signature")
            if sig and sig not in seen:
                send(f"NOUVELLE TX !\n\n{sig}\nhttps://solscan.io/tx/{sig}")
                seen.add(sig)
        time.sleep(20)

# === BOT /add ===
def bot():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                txt = u.get("message", {}).get("text", "").strip()
                if txt.startswith("/add "):
                    global WALLET
                    w = txt[5:].strip()
                    if len(w) >= 32:
                        WALLET = w
                        send(f"Wallet changé : {w[:8]}...{w[-6:]}")
        except:
            time.sleep(5)

# === FLASK (CORRIGÉ) ===
app = Flask(__name__)

@app.route("/")
def index():
    return "ON"

# === LANCEMENT ===
if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
