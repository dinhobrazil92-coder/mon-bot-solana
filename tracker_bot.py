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

# === FICHIERS ===
def load_list(file):
    print(f"[LOAD] Lecture {file}")
    if not os.path.exists(file):
        print(f"[LOAD] Fichier {file} n'existe pas → []")
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        print(f"[LOAD] {len(lines)} wallets chargés")
        return lines
    except Exception as e:
        print(f"[LOAD] Erreur lecture {file}: {e}")
        return []

def save_list(file, data):
    print(f"[SAVE] Écriture dans {file} : {data}")
    try:
        with open(file, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
        print(f"[SAVE] Sauvegarde OK → {file}")
    except Exception as e:
        print(f"[SAVE] Erreur écriture {file}: {e}")

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
    send("BOT VIVANT !\n\nTracker actif.\nEnvoie /add <wallet>")

# === RPC ===
def rpc(method, params):
    print(f"RPC → {method}")
    try:
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15
        )
        print(f"RPC STATUS: {r.status_code}")
        return r.json().get("result")
    except Exception as e:
        print(f"RPC ERR: {e}")
        return None

# === TRACKER ===
def tracker():
    print("THREAD TRACKER DÉMARRÉ")
    seen = load_set(SEEN_FILE)
    while True:
        wallets = load_list(WALLETS_FILE)
        if not wallets:
            print("Aucun wallet → attente 30s")
            time.sleep(30)
            continue

        for w in wallets:
            print(f"Vérification : {w[:8]}...")
            sigs = rpc("getSignaturesForAddress", [w, {"limit": 3}])
            if not sigs:
                continue
            for s in sigs:
                sig = s.get("signature")
                if sig in seen: continue
                send(f"NOUVELLE TX !\n{sig}\nhttps://solscan.io/tx/{sig}")
                seen.add(sig)
                save_set(SEEN_FILE, seen)
            time.sleep(3)
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
                            save_list(WALLETS_FILE, cur)  # SAUVEGARDE FORCÉE
                        send(f"Suivi activé :\n{w[:8]}...{w[-6:]}")
                    else:
                        send("Wallet invalide")
        except Exception as e:
            print(f"BOT ERR: {e}")
            time.sleep(5)

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
