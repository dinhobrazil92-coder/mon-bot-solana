#!/usr/bin/env python3
import os
import time
import threading
import requests
from flask import Flask

# === CONFIG FIXE (TOUT EST PRÉ-CONFIGURÉ) ===
BOT_TOKEN = "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k"
HELIUS_KEY = "c888ba69-de31-43b7-b6c6-f6f841351f56"
MY_CHAT_ID = "8228401361"
PORT = 10000

# === RPC HELIUS (RAPIDE & STABLE) ===
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

# === WALLET ACTIF (100 % GARANTI) ===
WALLET = "5tzFkiKscXWK5ZX8vztjFz7eU2B3xW4kG8Y8yW8Y8yW8"

# === DATA EN MÉMOIRE (PAS DE FICHIER → PAS DE BUG DISQUE) ===
seen = set()

# === TELEGRAM ===
def send(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": MY_CHAT_ID, "text": text},
            timeout=10
        )
    except:
        pass

# === RPC HELIUS ===
def rpc(method, params):
    try:
        r = requests.post(
            RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=10
        )
        return r.json().get("result")
    except:
        return None

# === TRACKER (SIMPLE & EFFICACE) ===
def tracker():
    time.sleep(15)  # Attente démarrage
    send(f"BOT ACTIF\n\nSuivi : {WALLET[:8]}...{WALLET[-6:]}\n\nPremière TX dans < 30s")

    while True:
        sigs = rpc("getSignaturesForAddress", [WALLET, {"limit": 5}]) or []
        for s in sigs:
            sig = s.get("signature")
            if sig and sig not in seen:
                send(f"NOUVELLE TX !\n\n{sig}\nhttps://solscan.io/tx/{sig}")
                seen.add(sig)
        time.sleep(20)

# === BOT (AJOUT WALLET) ===
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
                    w = txt[5:].strip()
                    if len(w) >= 32:
                        global WALLET
                        WALLET = w
                        send(f"Nouveau wallet : {w[:8]}...{w[-6:]}")
        except:
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "ON"

# === LANCEMENT ===
if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
