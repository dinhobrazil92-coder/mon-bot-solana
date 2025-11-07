#!/usr/bin/env python3
import os
import time
import threading
import json
import requests
from flask import Flask

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"

print("BOT_TOKEN = " + BOT_TOKEN[:10] + "...")
print("MY_CHAT_ID = " + MY_CHAT_ID)

# DATA
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

AUTHORIZED_FILE = DATA_DIR + "/authorized.json"
WALLETS_FILE = DATA_DIR + "/wallets.txt"
SEEN_FILE = DATA_DIR + "/seen.txt"
UPDATE_ID_FILE = DATA_DIR + "/update_id.txt"

# FICHIERS
def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        f = open(path, "r", encoding="utf-8")
        data = json.load(f)
        f.close()
        return data
    except:
        return {}

def save_json(path, data):
    try:
        f = open(path, "w", encoding="utf-8")
        json.dump(data, f, indent=2)
        f.close()
    except:
        pass

def load_list(path):
    if not os.path.exists(path):
        return []
    try:
        f = open(path, "r", encoding="utf-8")
        lines = f.readlines()
        f.close()
        return [l.strip() for l in lines if l.strip()]
    except:
        return []

def save_list(path, data):
    try:
        f = open(path, "w", encoding="utf-8")
        f.write("\n".join(data) + "\n")
        f.close()
    except:
        pass

def save_set(path, data):
    save_list(path, list(data))

# AUTH
def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print("Pre-autorise: " + MY_CHAT_ID)

# TELEGRAM
def send(chat_id, text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        print("Envoi message a " + str(chat_id) + "...")
        r = requests.post(url, data=payload, timeout=10)
        print("Reponse: " + str(r.status_code))
        if r.status_code == 200:
            print("OK: Message envoye")
        else:
            print("ERR: " + r.text)
    except Exception as e:
        print("Exception: " + str(e))

# TEST
def test_force():
    time.sleep(5)
    send(MY_CHAT_ID, "BOT VIVANT !\nTest OK.\nEnvoie /add <wallet>")

# TRACKER
def tracker():
    print("Tracker demarre")
    seen = set(load_list(SEEN_FILE))
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue
            for w in wallets:
                sigs = []
                try:
                    payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [w, {"limit": 5}]}
                    r = requests.post("https://api.mainnet-beta.solana.com", json=payload, timeout=10)
                    result = r.json().get("result", [])
                    for s in result:
                        sigs.append(s.get("signature"))
                except:
                    pass
                for sig in sigs:
                    if sig in seen:
                        continue
                    try:
                        payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "jsonParsed"}]}
                        r = requests.post("https://api.mainnet-beta.solana.com", json=payload, timeout=10)
                        tx = r.json().get("result")
                        if tx:
                            msg = "TX: <a href=\"https://solscan.io/tx/" + sig + "\">Voir</a>\nWallet: " + w[:8] + "..." + w[-6:]
                            send(MY_CHAT_ID, msg)
                    except:
                        pass
                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(20)
        except Exception as e:
            print("Tracker ERR: " + str(e))
            time.sleep(10)

# BOT
def bot():
    print("Bot polling demarre")
    offset = 0
    while True:
        try:
            url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=40)
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
                        send(cid, "Suivi: " + w)
        except Exception as e:
            print("Bot ERR: " + str(e))
            time.sleep(5)

# FLASK
app = Flask(__name__)
@app.route("/")
def index():
    return "ON"
@app.route("/health")
def health():
    return "OK", 200

# DEMARRAGE
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("Bot lance")
    app.run(host="0.0.0.0", port=PORT)
