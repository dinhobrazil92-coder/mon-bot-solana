#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOLANA TRACKER BOT - ULTIMATE EDITION
- RPC Public Solana (aucun clé API)
- Notifications ACHAT/VENTE/CRÉATION
- Pré-autorisé : 8228401361
- Mot de passe caché (seul toi le connais)
- Fonctions : /add, /remove, /my, /list, /stats
- Logs clairs + Test force
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

# === TON ID (PRÉ-AUTORISÉ) ===
MY_CHAT_ID = "8228401361"

# === MOT DE PASSE CACHÉ (ne jamais l'afficher) ===
SECRET_PASSWORD = "Business2026$"  # Tu es le SEUL à le connaître

# === DATA (DISK PERSISTENT) ===
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
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except: return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w") as f:
            f.write(str(uid))
    except: pass

# === AUTH (PRÉ-AUTORISÉ + LOGIN SÉCURISÉ) ===
def is_authorized(chat_id):
    return str(chat_id) == MY_CHAT_ID or str(chat_id) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print(f"[OK] ID {MY_CHAT_ID} pré-autorisé")

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === TEMPLATES ===
def msg(text):
    return text

# === TELEGRAM (NOTIFS GARANTIES) ===
def send(chat_id, text):
    if not BOT_TOKEN: return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10
        )
        if r.status_code == 200:
            print(f"[OK] Envoyé à {chat_id}")
        else:
            print(f"[ERR] TG {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERR] TG: {e}")

# === TEST FORCE (15s après démarrage) ===
def test_force():
    time.sleep(15)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest force OK.\nEnvoie /add <wallet>")

# === RPC PUBLIC SOLANA (GRATUIT, SANS CLÉ) ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None: params = []
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[ERR] RPC: {e}")
        return None

def get_signatures(wallet, limit=10):
    return rpc("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION TOKEN ===
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
                return mint
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
        if dst == wallet: return "ACHAT", mint, amt, dec
        if src == wallet: return "VENTE", mint, amt, dec
    return None

# === TRACKER ===
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
                sigs = get_signatures(w, 10)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen: continue
                    tx = get_transaction(sig)
                    if not tx:
                        seen.add(sig)
                        save_set.SEEN_FILE, seen)
                        continue

                    # Création
                    mint = detect_creation(tx, w)
                    if mint:
                        send(MY_CHAT_ID, f"NOUVEAU TOKEN CRÉÉ !\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{mint[:8]}...{mint[-6:]}</code>")

                    # Transfert
                    result = detect_transfer(tx, w)
                    if result:
                        action, mint, amt, dec = result
                        try:
                            amount = f"{int(amt) / (10 ** int(dec)):,}" if dec else f"{int(amt) / 1_000_000_000:,}"
                            amount = amount.rstrip("0").rstrip(".")
                        except:
                            amount = str(amt)
                        send(MY_CHAT_ID, f"<b>{action}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir</a>\n<code>{w[:8]}...{w[-6:]}</code>\n<code>{amount}</code>")

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[OK] Bot polling démarré")
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
                    authorize(cid)
                    send(cid, "Accès autorisé !\n\n/add <wallet>\n/my\n/list")
                    continue

                if not is_authorized(cid):
                    send(cid, "Connecte-toi : <code>/login [mdp]</code>")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send(cid, "Wallet invalide.")
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

                elif cmd == "/remove" and args:
                    w = args.strip()
                    if w in subs and cid in subs[w]:
                        subs[w].remove(cid)
                        if not subs[w]: del subs[w]
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send(cid, f"Arrêt suivi : <code>{w}</code>")
                    else:
                        send(cid, "Pas suivi.")

                elif cmd == "/my":
                    mine = [w for w, u in subs.items() if cid in u]
                    send(cid, "<b>Mes wallets :</b>\n" + "\n".join([f"• <code>{w}</code>" for w in mine]) if mine else "Aucun")

                elif cmd == "/list":
                    all_w = load_list(WALLETS_FILE)
                    txt = "<b>Wallets suivis :</b>\n"
                    for w in all_w:
                        count = len([u for u in subs.get(w, []) if is_authorized(u)])
                        txt += f"• <code>{w}</code> ({count} abonnés)\n"
                    send(cid, txt if all_w else "Aucun wallet suivi.")

                elif cmd == "/stats":
                    send(cid, f"Wallets suivis : {len(load_list(WALLETS_FILE))}\nAbonnés : {len(load_json(AUTHORIZED_FILE))}")

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
    print("[OK] Bot démarré")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
