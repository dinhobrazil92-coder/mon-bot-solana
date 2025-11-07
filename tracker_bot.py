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

print("BOT_TOKEN:", BOT_TOKEN[:15] + "...")
print("MY_CHAT_ID:", MY_CHAT_ID)

# DATA
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# FICHIERS
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

# AUTH
def is_authorized(cid):
    return str(cid) == MY_CHAT_ID or str(cid) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print("Pré-autorisé:", MY_CHAT_ID)

# TELEGRAM
def send(cid, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
        if r.status_code == 200:
            print("Envoyé à", cid)
        else:
            print("TG ERR:", r.status_code, r.text)
    except Exception as e:
        print("TG Exception:", e)

def test_force():
    time.sleep(5)
    send(MY_CHAT_ID, "<b>BOT VIVANT !</b>\n\nTest force OK.\nEnvoie /add &lt;wallet&gt;")

# RPC SOLANA
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None: params = []
    try:
        r = requests.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except: return None

def get_signatures(w, l=10):
    return rpc("getSignaturesForAddress", [w, {"limit": l}]) or []

def get_transaction(s):
    return rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# DÉTECTION
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_creation(tx, w):
    if not tx: return None
    for i in tx.get("transaction", {}).get("message", {}).get("instructions", []):
        if i.get("programId") == MINT_PROGRAM and i.get("parsed", {}).get("type") == "initializeMint":
            info = i.get("parsed", {}).get("info", {})
            if info.get("mintAuthority") == w:
                return info.get("mint")
    return None

def detect_transfer(tx, w):
    if not tx: return None
    all_i = tx.get("transaction", {}).get("message", {}).get("instructions", [])[:]
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        all_i.extend(inner.get("instructions", []))
    for i in all_i:
        if i.get("programId") == TOKEN_PROGRAM and i.get("parsed", {}).get("type") in ("transfer", "transferChecked"):
            info = i.get("parsed", {}).get("info", {})
            src, dst = info.get("source"), info.get("destination")
            mint = info.get("mint") or "?"
            amt = info.get("amount")
            dec = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
            if dst == w: return "ACHAT", mint, amt, dec
            if src == w: return "VENTE", mint, amt, dec
    return None

# TRACKER
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
                sigs = get_signatures(w, 10)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen: continue
                    tx = get_transaction(sig)
                    if not tx: continue

                    # Création
                    if mint := detect_creation(tx, w):
                        send(MY_CHAT_ID, f"NOUVEAU TOKEN !\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>")

                    # Transfert
                    result = detect_transfer(tx, w)
                    if result:
                        action, mint, amt, dec = result
                        try:
                            amount = f"{int(amt)/(10**int(dec)):,}".rstrip("0").rstrip(".") if dec else f"{int(amt)/1_000_000_000:,}"
                        except:
                            amount = str(amt)
                        send(MY_CHAT_ID, f"<b>{action}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{amount}</code>")

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print("Tracker ERR:", e)
            time.sleep(10)

# BOT
def bot():
    print("Bot polling démarré")
    offset = load_update_id()
    while True:
        try:
            up = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40).json()
            for u in up.get("result", []):
                offset = u["update_id"] + 1
                save_update_id(offset)
                m = u.get("message") or {}
                cid = m.get("chat", {}).get("id")
                txt = (m.get("text") or "").strip()
                if not txt.startswith("/"): continue
                cmd = txt.split()[0].lower()
                args = " ".join(txt.split()[1:])

                if cmd == "/login" and args == SECRET_PASSWORD:
                    d = load_json(AUTHORIZED_FILE)
                    d[str(cid)] = True
                    save_json(AUTHORIZED_FILE, d)
                    send(cid, "Accès autorisé !\n/add &lt;wallet&gt;")
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
                        send(cid, f"Suivi activé : <code>{w}</code>")
                elif cmd == "/my":
                    mine = [w for w, users in subs.items() if cid in users]
                    send(cid, "<b>Mes wallets :</b>\n" + "\n".join(f"• <code>{w}</code>" for w in mine) if mine else "Aucun")
        except Exception as e:
            print("Bot ERR:", e)
            time.sleep(5)

# FLASK
app = Flask(__name__)
@app.route("/"): return "BOT ON"
@app.route("/health"): return "OK", 200

# LANCEMENT
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("Lancement complet...")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
