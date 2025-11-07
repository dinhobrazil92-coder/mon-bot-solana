#!/usr/bin/env python3
import os
import time
import threading
import json
import requests
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"
SECRET_PASSWORD = "Business2026$"

print(f"[DEBUG] BOT_TOKEN = {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
print(f"[DEBUG] MY_CHAT_ID = {MY_CHAT_ID}")
print(f"[DEBUG] PORT = {PORT}")

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# === FICHIERS ===
def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERR] load_json {path}: {e}")
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERR] save_json {path}: {e}")

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

def save_set(path, data):
    save_list(path, list(data))

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
    print(f"[OK] Pré-autorisé: {MY_CHAT_ID}")

# === TELEGRAM (TEST IMMÉDIAT) ===
def send(cid, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "HTML"}
    try:
        print(f"[DEBUG] Envoi à {cid}...")
        r = requests.post(url, data=payload, timeout=10)
        print(f"[DEBUG] Réponse TG: {r.status_code} | {r.text}")
        if r.status_code == 200:
            print(f"[OK] Message envoyé à {cid}")
        else:
            print(f"[ERR] Échec envoi: {r.json()}")
    except Exception as e:
        print(f"[ERR] Exception TG: {e}")

# === TEST FORCE (5s) ===
def test_force():
    time.sleep(5)  # Réduit à 5s pour test
    print("[TEST] Envoi du message de test...")
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest force OK.\nEnvoie /add <wallet>")

# === RPC SOLANA ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None: params = []
    try:
        r = requests.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[ERR] RPC: {e}")
        return None

def get_signatures(w, l=10):
    return rpc("getSignaturesForAddress", [w, {"limit": l}]) or []

def get_transaction(s):
    return rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION (SIMPLIFIÉE) ===
def detect_transfer(tx, wallet):
    if not tx: return None
    try:
        instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
        for i in instructions:
            if i.get("programId") == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
                p = i.get("parsed", {})
                if p.get("type") in ("transfer", "transferChecked"):
                    info = p.get("info", {})
                    if info.get("destination") == wallet:
                        return "ACHAT", info.get("mint"), info.get("amount")
                    if info.get("source") == wallet:
                        return "VENTE", info.get("mint"), info.get("amount")
    except: pass
    return None

# === TRACKER ===
def tracker():
    print("[OK] Tracker démarré")
    seen = set(load_list(SEEN_FILE))
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
                    if not sig or sig in seen: continue
                    tx = get_transaction(sig)
                    transfer = detect_transfer(tx, w)
                    if transfer:
                        action, mint, amt = transfer
                        amount = str(int(amt) / 1_000_000_000) if "So1" in mint else str(amt)
                        msg = f"<b>{action}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{amount}</code>"
                        send(MY_CHAT_ID, msg)
                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(20)
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT ===
def bot():
    print("[OK] Bot polling démarré")
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

                if cmd == "/add" and args and is_authorized(cid):
                    w = args.strip()
                    if len(w) >= 32:
                        cur = load_list(WALLETS_FILE)
                        if w not in cur:
                            cur.append(w)
                            save_list(WALLETS_FILE, cur)
                        send(cid, f"Suivi : <code>{w}</code>")
        except Exception as e:
            print(f"[ERR] Bot: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "ON"
@app.route("/health"): return "OK", 200

# === LANCEMENT ===
if __name__ == "__main__":
    pre_authorize()
    print("[START] Lancement des threads...")
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("[OK] Bot démarré — Attente message en 5s...")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
