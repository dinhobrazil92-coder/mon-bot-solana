#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOLANA TRACKER BOT - VERSION FINALE SANS ERREUR
- RPC Public Solana
- ID 8228401361 pré-autorisé
- Test force en 15s
- Aucune erreur de syntaxe
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
def load_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

def load_list(file_path):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_list(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except:
        pass

def load_set(file_path):
    return set(load_list(file_path))

def save_set(file_path, data):
    save_list(file_path, list(data))

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

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) == MY_CHAT_ID or str(chat_id) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print(f"[OK] ID {MY_CHAT_ID} pré-autorisé")

# === TELEGRAM ===
def send(chat_id, text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if r.status_code == 200:
            print(f"[OK] Envoyé à {chat_id}")
        else:
            print(f"[ERR] TG {r.status_code}")
    except Exception as e:
        print(f"[ERR] TG: {e}")

def test_force():
    time.sleep(15)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest force OK.\nEnvoie /add <wallet>")

# === RPC PUBLIC SOLANA ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None:
        params = []
    try:
        r = requests.post(
            SOLANA_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("result")
    except:
        return None

def get_signatures(wallet, limit=10):
    return rpc("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_creation(tx, wallet):
    if not tx:
        return None
    for instr in tx.get("transaction", {}).get("message", {}).get("instructions", []):
        if instr.get("programId") != MINT_PROGRAM:
            continue
        parsed = instr.get("parsed", {})
        if parsed.get("type") == "initializeMint":
            info = parsed.get("info", {})
            if info.get("mintAuthority") == wallet:
                return info.get("mint")
    return None

def detect_transfer(tx, wallet):
    if not tx:
        return None
    all_instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])[:]
    for inner in tx.get("meta", {}).get("innerInstructions", []):
        all_instructions.extend(inner.get("instructions", []))
    for instr in all_instructions:
        if instr.get("programId") != TOKEN_PROGRAM:
            continue
        parsed = instr.get("parsed", {})
        if parsed.get("type") not in ("transfer", "transferChecked"):
            continue
        info = parsed.get("info", {})
        source = info.get("source")
        destination = info.get("destination")
        mint = info.get("mint") or "?"
        amount = info.get("amount")
        decimals = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
        if destination == wallet:
            return "ACHAT", mint, amount, decimals
        if source == wallet:
            return "VENTE", mint, amount, decimals
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
            for wallet in wallets:
                sigs = get_signatures(wallet, 10)
                for sig_data in sigs:
                    sig = sig_data.get("signature")
                    if not sig or sig in seen:
                        continue
                    tx = get_transaction(sig)
                    if not tx:
                        seen.add(sig)
                        save_set(SEEN_FILE, seen)
                        continue

                    # Création
                    mint = detect_creation(tx, wallet)
                    if mint:
                        msg = f"NOUVEAU TOKEN CRÉÉ !\n<a href=\"https://solscan.io/tx/{sig}\">Voir tx</a>\n<code>{wallet[:8]}...{wallet[-6:]}</code>"
                        send(MY_CHAT_ID, msg)

                    # Transfert
                    transfer = detect_transfer(tx, wallet)
                    if transfer:
                        action, mint, amount, decimals = transfer
                        try:
                            if decimals is not None:
                                amt = int(amount) / (10 ** int(decimals))
                            else:
                                amt = int(amount) / 1_000_000_000
                            amount_str = f"{amt:,.8f}".rstrip("0").rstrip(".")
                        except:
                            amount_str = str(amount)
                        msg = f"<b>{action}</b>\n<a href=\"https://solscan.io/tx/{sig}\">Voir tx</a>\n<code>{wallet[:8]}...{wallet[-6:]}</code>\n<code>{amount_str}</code>"
                        send(MY_CHAT_ID, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print(f"[ERR] Tracker: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[OK] Bot démarré")
    offset = load_update_id()
    while True:
        try:
            updates = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                save_update_id(offset)
                message = update.get("message") or {}
                chat_id = message.get("chat", {}).get("id")
                text = (message.get("text") or "").strip()
                if not text.startswith("/"):
                    continue
                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == SECRET_PASSWORD:
                    data = load_json(AUTHORIZED_FILE)
                    data[str(chat_id)] = True
                    save_json(AUTHORIZED_FILE, data)
                    send(chat_id, "Accès autorisé !\n\nUtilise /add <wallet>")
                    continue

                if not is_authorized(chat_id):
                    send(chat_id, "Connecte-toi : /login [mdp]")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send(chat_id, "Wallet invalide.")
                        continue
                    current = load_list(WALLETS_FILE)
                    if w not in current:
                        current.append(w)
                        save_list(WALLETS_FILE, current)
                    if w not in subs:
                        subs[w] = []
                    if chat_id not in subs[w]:
                        subs[w].append(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send(chat_id, f"Suivi activé : <code>{w}</code>")

                elif cmd == "/my":
                    mine = [w for w, users in subs.items() if chat_id in users]
                    if mine:
                        send(chat_id, "<b>Mes wallets :</b>\n" + "\n".join(f"• <code>{w}</code>" for w in mine))
                    else:
                        send(chat_id, "Aucun wallet suivi.")

        except Exception as e:
            print(f"[ERR] Bot: {e}")
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot Solana Tracker ON"

@app.route("/health")
def health():
    return "OK", 200

# === DÉMARRAGE ===
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("[OK] Bot lancé")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
