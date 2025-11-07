#!/usr/bin/env python3
import os
import time
import threading
import json
import requests
from flask import Flask

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN", "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"
SECRET_PASSWORD = "Business2026$"

print("=== DEBUG BOT ===")
print("BOT_TOKEN:", BOT_TOKEN)
print("MY_CHAT_ID:", MY_CHAT_ID)
print("==================")

# DATA
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

AUTHORIZED_FILE = DATA_DIR + "/authorized.json"
SUBSCRIPTIONS_FILE = DATA_DIR + "/subscriptions.json"
WALLETS_FILE = DATA_DIR + "/wallets.txt"
SEEN_FILE = DATA_DIR + "/seen.txt"
UPDATE_ID_FILE = DATA_DIR + "/update_id.txt"

# FICHIERS
def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

def load_list(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except:
        return []

def save_list(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except:
        pass

def load_set(path):
    return set(load_list(path))

def save_set(path, data):
    save_list(path, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE):
        return 0
    try:
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w") as f:
            f.write(str(uid))
    except:
        pass

# AUTH
def is_authorized(cid):
    return str(cid) == MY_CHAT_ID or str(cid) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print("Pre-autorise: " + MY_CHAT_ID)

# TELEGRAM (AVEC LOGS)
def send(cid, text):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "HTML"}
    try:
        print("ENVOI a", cid, ":", text[:50] + "...")
        r = requests.post(url, data=payload, timeout=10)
        print("TG STATUS:", r.status_code)
        if r.status_code == 200:
            print("MESSAGE ENVOYE !")
        else:
            print("TG ERREUR:", r.text)
    except Exception as e:
        print("TG EXCEPTION:", str(e))

# TEST FORCE
def test_force():
    time.sleep(5)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest force OK.\nEnvoie /add <wallet>")

# RPC SOLANA
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None:
        params = []
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print("RPC ERR:", str(e))
        return None

def get_signatures(w, l=10):
    return rpc("getSignaturesForAddress", [w, {"limit": l}]) or []

def get_transaction(s):
    return rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# DETECTION
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_creation(tx, w):
    if not tx:
        return None
    for i in tx.get("transaction", {}).get("message", {}).get("instructions", []):
        if i.get("programId") == MINT_PROGRAM:
            parsed = i.get("parsed", {})
            if parsed.get("type") == "initializeMint":
                info = parsed.get("info", {})
                if info.get("mintAuthority") == w:
                    return info.get("mint")
    return None

def detect_transfer(tx, w):
    if not tx:
        return None
    all_i = tx.get("transaction", {}).get("message", {}).get("instructions", [])[:]
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        all_i.extend(inner.get("instructions", []))
    for i in all_i:
        if i.get("programId") == TOKEN_PROGRAM:
            parsed = i.get("parsed", {})
            if parsed.get("type") in ("transfer", "transferChecked"):
                info = parsed.get("info", {})
                src = info.get("source")
                dst = info.get("destination")
                mint = info.get("mint") or "?"
                amt = info.get("amount")
                dec = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
                if dst == w:
                    return "ACHAT", mint, amt, dec
                if src == w:
                    return "VENTE", mint, amt, dec
    return None

# TRACKER
def tracker():
    print("Tracker demarre")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue
            for w in wallets:
                sigs = get_signatures(w, 5)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen:
                        continue
                    tx = get_transaction(sig)
                    if not tx:
                        continue

                    mint = detect_creation(tx, w)
                    if mint:
                        msg = "NOUVEAU TOKEN !\n<a href=\"https://solscan.io/tx/" + sig + "\">Voir</a>\n<code>" + w[:8] + "..." + w[-6:] + "</code>"
                        send(MY_CHAT_ID, msg)

                    result = detect_transfer(tx, w)
                    if result:
                        action, mint, amt, dec = result
                        try:
                            if dec is not None:
                                amount = str(int(amt) / (10 ** int(dec))).rstrip("0").rstrip(".")
                            else:
                                amount = str(int(amt) / 1000000000).rstrip("0").rstrip(".")
                        except:
                            amount = str(amt)
                        msg = "<b>" + action + "</b>\n<a href=\"https://solscan.io/tx/" + sig + "\">Voir</a>\n<code>" + w[:8] + "..." + w[-6:] + "</code>\n<code>" + amount + "</code>"
                        send(MY_CHAT_ID, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(20)
        except Exception as e:
            print("Tracker ERR:", str(e))
            time.sleep(10)

# BOT
def bot():
    print("Bot polling demarre")
    offset = load_update_id()
    while True:
        try:
            url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                save_update_id(offset)
                m = u.get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "").strip()
                if not txt.startswith("/"):
                    continue
                parts = txt.split(" ", 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == SECRET_PASSWORD:
                    d = load_json(AUTHORIZED_FILE)
                    d[str(cid)] = True
                    save_json(AUTHORIZED_FILE, d)
                    send(cid, "Acces OK !\n/add <wallet>")
                    continue

                if not is_authorized(cid):
                    send(cid, "Connecte-toi : /login [mdp]")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send(cid, "Invalide")
                        continue
                    cur = load_list(WALLETS_FILE)
                    if w not in cur:
                        cur.append(w)
                        save_list(WALLETS_FILE, cur)
                    if w not in subs:
                        subs[w] = []
                    if cid not in subs[w]:
                        subs[w].append(cid)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send(cid, "Suivi : <code>" + w + "</code>")
        except Exception as e:
            print("Bot ERR:", str(e))
            time.sleep(5)

# FLASK
app = Flask(__name__)
@app.route("/")
def index():
    return "ON"

@app.route("/health")
def health():
    return "OK", 200

# LANCEMENT
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("Lancement complet...")
    app.run(host="0.0.0.0", port=PORT)
