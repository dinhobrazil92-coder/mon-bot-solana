#!/usr/bin/env python3
import os
import time
import threading
import json
import requests
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k")
PASSWORD = os.getenv("PASSWORD", "Business2026$")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"

# === FICHIERS ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"

# === UTILITAIRES ===
def load_list(file):
    if not os.path.exists(file): return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

def save_list(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except: pass

def load_set(file): return set(load_list(file))
def save_set(file, data): save_list(file, list(data))

# === TELEGRAM (TEXTE BRUT) ===
def send(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
        if r.status_code == 200:
            print(f"[OK] Envoyé à {chat_id}")
        else:
            print(f"[ERR] TG {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERR] TG: {e}")

# === TEST ===
def test():
    time.sleep(10)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nEnvoie /add <wallet>\nEx: /add 5tzFkiKscXWK5ZX8vztjFz7eU2B3xW4kG8Y8yW8Y8yW8")

# === RPC SOLANA (ANTI-429) ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
LAST_REQUEST = 0

def rpc(method, params=None):
    global LAST_REQUEST
    if params is None: params = []
    # Anti-rate-limit
    elapsed = time.time() - LAST_REQUEST
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)
    LAST_REQUEST = time.time()

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
        if r.status_code == 429:
            print("[WARN] 429 → pause 10s")
            time.sleep(10)
            return None
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[ERR] RPC: {e}")
        time.sleep(5)
        return None

def get_signatures(w):
    return rpc("getSignaturesForAddress", [w, {"limit": 3}]) or []

def get_tx(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === TRACKER (SIMPLE & STABLE) ===
def tracker():
    print("[OK] Tracker démarré")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue

            for w in wallets:
                sigs = get_signatures(w)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen: continue

                    tx = get_tx(sig)
                    if not tx: continue

                    # Message simple
                    short_w = w[:8] + "..." + w[-6:]
                    link = f"https://solscan.io/tx/{sig}"
                    msg = f"NOUVELLE TX !\n\nWallet: {short_w}\nLien: {link}"
                    send(MY_CHAT_ID, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)

                time.sleep(2)  # Entre wallets
            time.sleep(25)  # Boucle
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT ===
def bot():
    print("[OK] Bot démarré")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "").strip()
                if not txt.startswith("/"): continue

                cmd = txt.split()[0].lower()
                args = " ".join(txt.split()[1:])

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) >= 32:
                        cur = load_list(WALLETS_FILE)
                        if w not in cur:
                            cur.append(w)
                            save_list(WALLETS_FILE, cur)
                        send(cid, f"Suivi activé : {w[:8]}...{w[-6:]}")
                    else:
                        send(cid, "Wallet invalide")
        except Exception as e:
            print(f"[ERR] Bot: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "ON"

# === MAIN ===
if __name__ == "__main__":
    threading.Thread(target=test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("Bot lancé")
    app.run(host="0.0.0.0", port=PORT)
