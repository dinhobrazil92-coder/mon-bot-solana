#!/usr/bin/env python3
import os
import time
import threading
import json
import requests
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8104197353:AAEkh1gVe8eH9z48owFUc1KUENLVl7NG60k")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"
SECRET_PASSWORD = "Business2026$"

print("BOT_TOKEN:", BOT_TOKEN[:15] + "...")
print("MY_CHAT_ID:", MY_CHAT_ID)

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# === FICHIERS ===
def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except: pass

def load_list(path):
    if not os.path.exists(path): return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

def save_list(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except: pass

def load_set(path): return set(load_list(path))
def save_set(path, data): save_list(path, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE): return 0
    try:
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except: return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w") as f:
            f.write(str(uid))
    except: pass

# === AUTH ===
def is_authorized(cid):
    return str(cid) == MY_CHAT_ID or str(cid) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print("Pré-autorisé:", MY_CHAT_ID)

# === TELEGRAM (TEXTE BRUT) ===
def send(cid, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": cid, "text": text}, timeout=10)
        if r.status_code == 200:
            print("Envoyé à", cid)
        else:
            print("TG ERR:", r.status_code, r.text)
    except Exception as e:
        print("TG Exception:", e)

def test_force():
    time.sleep(10)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nEnvoie /add <wallet>\nEx: /add 5tzFkiKscXWK5ZX8vztjFz7eU2B3xW4kG8Y8yW8Y8yW8")

# === RPC SOLANA (ANTI-429) ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
LAST_RPC_TIME = 0

def rpc(method, params=None):
    global LAST_RPC_TIME
    if params is None: params = []
    # Anti-rate-limit
    now = time.time()
    if now - LAST_RPC_TIME < 1.5:
        time.sleep(1.5 - (now - LAST_RPC_TIME))
    LAST_RPC_TIME = time.time()

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
        if r.status_code == 429:
            print("429 → pause 15s")
            time.sleep(15)
            return None
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print("RPC ERR:", e)
        time.sleep(5)
        return None

def get_signatures(w, limit=3):
    return rpc("getSignaturesForAddress", [w, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def detect_transfer(tx, wallet):
    if not tx: return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    inner = tx.get("meta", {}).get("innerInstructions", [])
    for block in [instructions] + [i.get("instructions", []) for i in inner]:
        for i in block:
            if i.get("programId") == TOKEN_PROGRAM:
                p = i.get("parsed", {})
                if p.get("type") in ("transfer", "transferChecked"):
                    info = p.get("info", {})
                    src = info.get("source")
                    dst = info.get("destination")
                    mint = info.get("mint", "?")
                    amt = info.get("amount", "0")
                    dec = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
                    if dst == wallet: return "ACHAT", mint, amt, dec
                    if src == wallet: return "VENTE", mint, amt, dec
    return None

# === TRACKER ===
def tracker():
    print("Tracker démarré")
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

                    tx = get_transaction(sig)
                    if not tx: continue

                    result = detect_transfer(tx, w)
                    if result:
                        action, mint, amt, dec = result
                        try:
                            amount = str(int(amt) / (10 ** int(dec))) if dec else str(int(amt) / 1_000_000_000)
                            amount = amount.rstrip("0").rstrip(".")
                        except:
                            amount = str(amt)

                        short_w = w[:8] + "..." + w[-6:]
                        short_m = mint[:8] + "..." + mint[-6:]
                        link = f"https://solscan.io/tx/{sig}"
                        msg = f"{action}\n\nWallet: {short_w}\nToken: {short_m}\nMontant: {amount}\nLien: {link}"
                        send(MY_CHAT_ID, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)

                time.sleep(2)
            time.sleep(20)
        except Exception as e:
            print("Tracker ERR:", e)
            time.sleep(10)

# === BOT ===
def bot():
    print("Bot polling démarré")
    offset = load_update_id()
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                save_update_id(offset)
                m = u.get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "").strip()
                if not txt.startswith("/"): continue

                cmd = txt.split()[0].lower()
                args = " ".join(txt.split()[1:])

                if cmd == "/login" and args == SECRET_PASSWORD:
                    d = load_json(AUTHORIZED_FILE)
                    d[str(cid)] = True
                    save_json(AUTHORIZED_FILE, d)
                    send(cid, "Accès autorisé !\n/add <wallet>")
                    continue

                if not is_authorized(cid):
                    send(cid, "Connecte-toi : /login [mdp]")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send(cid, "Wallet invalide")
                        continue
                    cur = load_list(WALLETS_FILE)
                    if w not in cur:
                        cur.append(w)
                        save_list(WALLETS_FILE, cur)
                    if w not in subs: subs[w] = []
                    if cid not in subs[w]:
                        subs[w].append(cid)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send(cid, f"Suivi : {w[:8]}...{w[-6:]}")
                    else:
                        send(cid, "Déjà suivi")

                elif cmd == "/my":
                    mine = [w for w, users in subs.items() if cid in users]
                    if mine:
                        msg = "Tes wallets :\n"
                        for w in mine:
                            msg += f"• {w[:8]}...{w[-6:]}\n"
                        send(cid, msg)
                    else:
                        send(cid, "Aucun")

        except Exception as e:
            print("Bot ERR:", e)
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "ON"
@app.route("/health"): return "OK", 200

# === LANCEMENT ===
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("Bot lancé")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
