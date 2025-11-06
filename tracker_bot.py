#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Tracker Solana
Notifications ACHAT / VENTE / CREATION
Chat ID 8228401361 pre-autorise
Helius + Render
"""
import os
import time
import threading
import json
import requests
from datetime import datetime
from flask import Flask

# === CONFIG ===
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "c888ba69-de31-43b7-b6c6-f6f841351f56")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY")
PORT = int(os.getenv("PORT", 10000))

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"

# === FICHIERS ===
def load_json(file_path):
    if not os.path.exists(file_path): return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except: pass

def load_list(file_path):
    if not os.path.exists(file_path): return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except: return []

def save_list(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except: pass

def load_set(file_path): return set(load_list(file_path))
def save_set(file_path, data): save_list(file_path, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE): return 0
    try:
        with open(UPDATE_ID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except: return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(uid))
    except: pass

# === AUTH (PRE-AUTORISE) ===
MY_CHAT_ID = "8228401361"  # TON ID

def is_authorized(chat_id):
    return str(chat_id) == MY_CHAT_ID or str(chat_id) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN: return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if r.status_code != 200:
            print(f"TG ERROR {r.status_code}: {r.text}")
        else:
            print(f"Envoye a {chat_id}")
    except Exception as e:
        print(f"TG ERR: {e}")

# === TEST FORCE ===
def force_test():
    time.sleep(15)
    send_message(MY_CHAT_ID, "BOT DEMARRE !\n\nTest force reussi.\nEnvoie /add <wallet>")

# === HELIUS RPC ===
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

def rpc(method, params=None):
    if params is None: params = []
    try:
        r = requests.post(HELIUS_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"RPC ERR {method}: {e}")
        return None

def get_signatures(w, l=10): return rpc("getSignaturesForAddress", [w, {"limit": l}]) or []
def get_transaction(s): return rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DETECTION ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_creation(tx, wallet):
    if not tx: return None
    for i in tx.get("transaction", {}).get("message", {}).get("instructions", []):
        if i.get("programId") != MINT_PROGRAM: continue
        p = i.get("parsed", {})
        if p.get("type") == "initializeMint":
            info = p.get("info", {})
            mint = info.get("mint")
            if mint and info.get("mintAuthority") == wallet:
                return {"mint": mint}
    return None

def detect_transfer(tx, wallet):
    if not tx: return None
    all_i = tx.get("transaction", {}).get("message", {}).get("instructions", [])[:]
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        all_i.extend(inner.get("instructions", []))
    for i in all_i:
        if i.get("programId") != TOKEN_PROGRAM: continue
        p = i.get("parsed", {})
        if p.get("type") not in ("transfer", "transferChecked"): continue
        info = p.get("info", {})
        src = info.get("source")
        dst = info.get("destination")
        mint = info.get("mint") or "?"
        amt = info.get("amount")
        dec = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
        if dst == wallet: return {"type": "ACHAT", "mint": mint, "amount": amt, "decimals": dec}
        if src == wallet: return {"type": "VENTE", "mint": mint, "amount": amt, "decimals": dec}
    return None

# === TRACKER ===
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
                sigs = get_signatures(w, 10)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen: continue
                    tx = get_transaction(sig)
                    creation = detect_creation(tx, w)
                    if creation:
                        msg = f"NOUVEAU TOKEN CREE !\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{creation['mint'][:8]}...{creation['mint'][-6:]}</code>"
                        send_message(MY_CHAT_ID, msg)
                    transfer = detect_transfer(tx, w)
                    if transfer:
                        try:
                            if transfer["decimals"] is not None:
                                amt = int(transfer["amount"]) / (10 ** int(transfer["decimals"]))
                            else:
                                amt = int(transfer["amount"]) / 1_000_000_000
                            amount = f"{amt:,.8f}".rstrip("0").rstrip(".")
                        except:
                            amount = str(transfer["amount"])
                        msg = f"<b>{transfer['type']}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{amount}</code>"
                        send_message(MY_CHAT_ID, msg)
                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print(f"Tracker err: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("Bot polling demarre")
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

                if not is_authorized(cid):
                    send_message(cid, "Acces refuse. Contacte l'admin.")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send_message(cid, "Wallet invalide")
                        continue
                    cur = load_list(WALLETS_FILE)
                    if w not in cur:
                        cur.append(w)
                        save_list(WALLETS_FILE, cur)
                    if w not in subs: subs[w] = []
                    if cid not in subs[w]:
                        subs[w].append(cid)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(cid, f"Suivi : <code>{w}</code>")
                elif cmd == "/my":
                    mine = [w for w, u in subs.items() if cid in u]
                    send_message(cid, "\n".join([f"• <code>{w}</code>" for w in mine]) or "Aucun")
        except Exception as e:
            print(f"Bot err: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/"): return "Bot ON"
@app.route("/health"): return "OK", 200

# === DEMARRAGE ===
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=force_test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
