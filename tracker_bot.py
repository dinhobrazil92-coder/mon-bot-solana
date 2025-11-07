#!/usr/bin/env python3
import os
import time
import threading
import requests
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
HELIUS_KEY = os.getenv("HELIUS_KEY")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"

# === RPC HELIUS ===
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"

# === WALLET PAR DÉFAUT (ACTIF) ===
DEFAULT_WALLET = "5tzFkiKscXWK5ZX8vztjFz7eU2B3xW4kG8Y8yW8Y8yW8"
if not os.path.exists(WALLETS_FILE):
    with open(WALLETS_FILE, "w") as f:
        f.write(DEFAULT_WALLET + "\n")

# === FICHIERS ===
def load_list(file):
    if not os.path.exists(file): return []
    with open(file, "r") as f:
        return [l.strip() for l in f if l.strip()]

def save_list(file, data):
    with open(file, "w") as f:
        f.write("\n".join(data) + "\n")

def load_set(file): return set(load_list(file))
def save_set(file, data): save_list(file, list(data))

# === TELEGRAM ===
def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": MY_CHAT_ID, "text": text}, timeout=10)
        print(f"TG → {r.status_code}")
    except Exception as e:
        print(f"TG ERR: {e}")

# === TEST ===
def test():
    time.sleep(10)
    send(f"BOT VIVANT !\n\nRPC Helius OK\nWallet : {DEFAULT_WALLET[:8]}...{DEFAULT_WALLET[-6:]}\n\nPremière TX dans < 30s")

# === RPC HELIUS ===
def rpc(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(RPC_URL, json=payload, timeout=10)
        return r.json().get("result")
    except Exception as e:
        print(f"RPC ERR: {e}")
        return None

# === TRACKER ===
def tracker():
    print("TRACKER DÉMARRÉ")
    seen = load_set(SEEN_FILE)
    while True:
        wallets = load_list(WALLETS_FILE)
        for w in wallets:
            sigs = rpc("getSignaturesForAddress", [w, {"limit": 5}]) or []
            for s in sigs:
                sig = s.get("signature")
                if sig in seen: continue
                send(f"NOUVELLE TX !\n\n{sig}\nhttps://solscan.io/tx/{sig}")
                seen.add(sig)
                save_set(SEEN_FILE, seen)
            time.sleep(2)
        time.sleep(15)

# === BOT ===
def bot():
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                txt = u.get("message", {}).get("text", "").strip()
                if txt.startswith("/add "):
                    w = txt[5:].strip()
                    if len(w) >= 32:
                        cur = load_list(WALLETS_FILE)
                        if w not in cur:
                            cur.append(w)
                            save_list(WALLETS_FILE, cur)
                        send(f"Ajouté : {w[:8]}...{w[-6:]}")
        except: time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/")
def index():
    return "ON"

# === MAIN ===
if __name__ == "__main__":
    print("HELIUS RPC PRÊT")
    threading.Thread(target=test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
