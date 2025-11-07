#!/usr/bin/env python3
import os
import time
import threading
import requests
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"

print("=== BOT DÉMARRÉ ===")
print("BOT_TOKEN:", BOT_TOKEN[:15] + "...")
print("CHAT_ID:", MY_CHAT_ID)

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"

def load_list(file):
    if not os.path.exists(file): return []
    try:
        with open(file, "r") as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

def save_list(file, data):
    try:
        with open(file, "w") as f:
            f.write("\n".join(data) + "\n")
    except: pass

def load_set(file): return set(load_list(file))
def save_set(file, data): save_list(file, list(data))

# === TELEGRAM ===
def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": MY_CHAT_ID, "text": text}, timeout=10)
        print("TG STATUS:", r.status_code)
    except Exception as e:
        print("TG ERR:", e)

# === TEST ===
def test():
    time.sleep(10)
    send("BOT VIVANT !\n\nTracker en cours...\nEnvoie /add <wallet>")

# === RPC (AVEC LOGS) ===
def rpc(method, params):
    print(f"RPC → {method}")
    try:
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15
        )
        print(f"RPC STATUS: {r.status_code}")
        if r.status_code == 429:
            print("429 → pause 15s")
            time.sleep(15)
            return None
        return r.json().get("result")
    except Exception as e:
        print("RPC EXCEPTION:", e)
        return None

# === TRACKER (DEBUG MAX) ===
def tracker():
    print("THREAD TRACKER DÉMARRÉ")
    seen = load_set(SEEN_FILE)
    count = 0
    while True:
        count += 1
        print(f"\n--- BOUCLE {count} ---")
        wallets = load_list(WALLETS_FILE)
        print(f"Wallets trouvés : {wallets}")

        if not wallets:
            print("Aucun wallet → attente 30s")
            time.sleep(30)
            continue

        for w in wallets:
            print(f"Vérification wallet : {w[:8]}...")
            sigs = rpc("getSignaturesForAddress", [w, {"limit": 3}])
            if not sigs:
                print("Aucune signature")
                continue
            print(f"{len(sigs)} signatures trouvées")

            for s in sigs:
                sig = s.get("signature")
                if sig in seen:
                    print(f"{sig[:8]}... déjà vu")
                    continue
                print(f"NOUVELLE TX : {sig[:8]}...")

                # Envoi notif
                send(f"NOUVELLE TX !\n\n{sig}\nhttps://solscan.io/tx/{sig}")

                seen.add(sig)
                save_set(SEEN_FILE, seen)

            time.sleep(3)
        print("Fin boucle → attente 25s")
        time.sleep(25)

# === BOT ===
def bot():
    print("THREAD BOT DÉMARRÉ")
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            )
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "").strip()
                if txt.startswith("/add "):
                    w = txt[5:].strip()
                    if len(w) >= 32:
                        cur = load_list(WALLETS_FILE)
                        if w not in cur:
                            cur.append(w)
                            save_list(WALLETS_FILE, cur)
                        send(f"Suivi activé : {w[:8]}...{w[-6:]}")
        except: time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/")
def index():
    return "ON"

# === MAIN ===
if __name__ == "__main__":
    threading.Thread(target=test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("TOUS LES THREADS LANCÉS")
    app.run(host="0.0.0.0", port=PORT)
