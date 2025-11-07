#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOLANA TRACKER BOT - ULTIMATE EDITION
- RPC Public Solana
- Notifications ACHAT/VENTE/CRÉATION
- ID 8228401361 pré-autorisé
- Mot de passe caché
"""
import os
import time
import threading
import json
import requests
from datetime import datetime
from flask import Flask

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY")
PORT = int(os.getenv("PORT", 10000))
MY_CHAT_ID = "8228401361"
SECRET_PASSWORD = "Business2026$"

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# === FICHIERS ===
def load_json(f): return json.load(open(f, "r", encoding="utf-8")) if os.path.exists(f) else {}
def save_json(f, d): json.dump(d, open(f, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
def load_list(f): return [l.strip() for l in open(f, "r", encoding="utf-8").readlines() if l.strip()] if os.path.exists(f) else []
def save_list(f, d): open(f, "w", encoding="utf-8").write("\n".join(d) + "\n")
def load_set(f): return set(load_list(f))
def save_set(f, d): save_list(f, list(d))
def load_update_id(): return int(open(UPDATE_ID_FILE, "r").read().strip()) if os.path.exists(UPDATE_ID_FILE) else 0
def save_update_id(u): open(UPDATE_ID_FILE, "w").write(str(u))

# === AUTH ===
def is_authorized(cid): return str(cid) == MY_CHAT_ID or str(cid) in load_json(AUTHORIZED_FILE)
def pre_authorize():
    d = load_json(AUTHORIZED_FILE)
    d[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, d)
    print(f"[OK] ID {MY_CHAT_ID} pré-autorisé")

# === TELEGRAM ===
def send(cid, text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
        print(f"[OK] Envoyé à {cid}" if r.status_code == 200 else f"[ERR] TG {r.status_code}")
    except: print("[ERR] TG Exception")

def test_force():
    time.sleep(15)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest force OK.\nEnvoie /add <wallet>")

# === RPC PUBLIC SOLANA ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
def rpc(m, p=None): 
    try:
        r = requests.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p or []}, timeout=15)
        return r.json().get("result")
    except: return None

def get_signatures(w, l=10): return rpc("getSignaturesForAddress", [w, {"limit": l}]) or []
def get_transaction(s): return rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION ===
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
            if dst == w: return "ACHAT", info.get("mint") or "?", info.get("amount"), info.get("tokenAmount", {}).get("decimals")
            if src == w: return "VENTE", info.get("mint") or "?", info.get("amount"), info.get("tokenAmount", {}).get("decimals")
    return None

# === TRACKER ===
def tracker():
    print("[OK] Tracker démarré")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            for w in load_list(WALLETS_FILE):
                for s in get_signatures(w, 10):
                    sig = s.get("signature")
                    if not sig or sig in seen: continue
                    tx = get_transaction(sig)
                    if not tx: continue

                    if mint := detect_creation(tx, w):
                        send(MY_CHAT_ID, f"NOUVEAU TOKEN !\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>")

                    if (action := detect_transfer(tx, w)):
                        action, mint, amt, dec = action
                        amount = f"{int(amt)/(10**int(dec)):,}".rstrip("0").rstrip(".") if dec else f"{int(amt)/1_000_000_000:,}"
                        send(MY_CHAT_ID, f"<b>{action}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{amount}</code>")

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT ===
def bot():
    print("[OK] Bot démarré")
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
                cmd, args = txt.split(maxsplit=1)[0].lower(), " ".join(txt.split()[1:])

                if cmd == "/login" and args == SECRET_PASSWORD:
                    d = load_json(AUTHORIZED_FILE); d[str(cid)] = True; save_json(AUTHORIZED_FILE, d)
                    send(cid, "Accès autorisé !\n/add <wallet>")
                    continue
                if not is_authorized(cid):
                    send(cid, "Connecte-toi : /login [mdp]")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32: send(cid, "Invalide"); continue
                    cur = load_list(WALLETS_FILE)
                    if w not in cur: cur.append(w); save_list(WALLETS_FILE, cur)
                    if w not in subs: subs[w] = []
                    if cid not in subs[w]: subs[w].append(cid); save_json(SUBSCRIPTIONS_FILE, subs)
                    send(cid, f"Suivi : <code>{w}</code>")
                elif cmd == "/my":
                    mine = [w for w, u in subs.items() if cid in u]
                    send(cid, "\n".join([f"• <code>{w}</code>" for w in mine]) or "Aucun")
        except Exception as e:
            print(f"[ERR] Bot: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "Bot ON"
@app.route("/health"): return "OK", 200

# === DÉMARRAGE ===
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("[OK] Lancement...")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
