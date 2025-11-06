#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram Tracker Solana
Detecte : ACHAT / VENTE / CREATION DE TOKEN
Fonctionnalites : /login, /add, /remove, /list, /my
Helius RPC + Render
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
PASSWORD = os.getenv("PASSWORD", "Business2026$")
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
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[load_json] Erreur {file_path}: {e}")
        return {}

def save_json(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[save_json] Erreur {file_path}: {e}")

def load_list(file_path):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[load_list] Erreur {file_path}: {e}")
        return []

def save_list(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except Exception as e:
        print(f"[save_list] Erreur {file_path}: {e}")

def load_set(file_path):
    return set(load_list(file_path))

def save_set(file_path, data):
    save_list(file_path, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE):
        return 0
    try:
        with open(UPDATE_ID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except:
        return 0

def save_update_id(uid):
    try:
        with open(UPDATE_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(uid))
    except Exception as e:
        print(f"[save_update_id] Erreur: {e}")

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) in load_json(AUTHORIZED_FILE)

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === TEMPLATES ===
def default_templates():
    return {
        "access_granted": "Acces autorise !\n\nCommandes :\n/add WALLET\n/remove WALLET\n/list\n/my",
        "must_login": "Connecte-toi :\n<code>/login {password}</code>",
        "now_following": "Suivi : <code>{wallet}</code>",
        "wallet_invalid": "Wallet invalide.",
        "no_wallets": "Aucun wallet suivi.",
        "my_subs_none": "Aucun abonnement.",
        "tx_detected": "<b>{action}</b>\n\n"
                       "<a href=\"{link}\">Voir tx</a>\n"
                       "Wallet: <code>{wallet}</code>\n"
                       "Token: <code>{mint}</code>\n"
                       "Montant: <code>{amount}</code>\n"
                       "Heure: <code>{time}</code>",
        "token_created": "NOUVEAU TOKEN CREE !\n\n"
                         "<a href=\"{link}\">Voir tx</a>\n"
                         "Wallet: <code>{wallet}</code>\n"
                         "Mint: <code>{mint}</code>\n"
                         "Heure: <code>{time}</code>"
    }

def get_template(key):
    return default_templates().get(key, "")

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN:
        print("[send_message] BOT_TOKEN manquant")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if resp.status_code != 200:
            print(f"[TG] Erreur {resp.status_code}: {resp.text}")
        else:
            print(f"[TG] Envoye a {chat_id}")
    except Exception as e:
        print(f"[TG] Exception: {e}")

# === TEST AUTO ===
def auto_test():
    time.sleep(10)
    auth = load_json(AUTHORIZED_FILE)
    if auth:
        for cid in auth:
            send_message(cid, "BOT DEMARRE !\n\nTest OK.\nUtilise /add <wallet>")
    else:
        print("[TEST] Aucun utilisateur autorise")

# === HELIUS RPC ===
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

def rpc(method, params=None):
    if params is None:
        params = []
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    try:
        r = requests.post(HELIUS_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[RPC] {method} erreur: {e}")
        return None

def get_signatures(wallet, limit=10):
    return rpc("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DETECTION ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINT_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

def detect_token_creation(tx, wallet):
    if not tx:
        return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    for instr in instructions:
        if instr.get("programId") != MINT_PROGRAM:
            continue
        parsed = instr.get("parsed", {})
        if parsed.get("type") == "initializeMint":
            info = parsed.get("info", {})
            mint = info.get("mint")
            if mint and info.get("mintAuthority") == wallet:
                return {"mint": mint}
    return None

def detect_token_transfer(tx, wallet):
    if not tx:
        return None
    all_instructions = []
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    all_instructions.extend(instructions)
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
            return {"type": "ACHAT", "mint": mint, "amount": amount, "decimals": decimals}
        if source == wallet:
            return {"type": "VENTE", "mint": mint, "amount": amount, "decimals": decimals}
    return None

# === TRACKER ===
def tracker():
    print("[Tracker] Demarre")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue

            for wallet in wallets:
                sigs = get_signatures(wallet, limit=10)
                for sig_data in sigs:
                    sig = sig_data.get("signature")
                    if not sig or sig in seen:
                        continue

                    tx = get_transaction(sig)
                    if not tx:
                        seen.add(sig)
                        save_set(SEEN_FILE, seen)
                        continue

                    # Creation
                    creation = detect_token_creation(tx, wallet)
                    if creation:
                        msg = get_template("token_created").format(
                            link=f"https://solscan.io/tx/{sig}",
                            wallet=wallet[:8] + "..." + wallet[-6:],
                            mint=creation["mint"][:8] + "..." + creation["mint"][-6:],
                            time=datetime.utcnow().strftime("%H:%M:%S")
                        )
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for cid in subs.get(wallet, []):
                            if is_authorized(cid):
                                send_message(cid, msg)

                    # Transfert
                    transfer = detect_token_transfer(tx, wallet)
                    if transfer:
                        try:
                            if transfer["decimals"] is not None:
                                amt = int(transfer["amount"]) / (10 ** int(transfer["decimals"]))
                            else:
                                amt = int(transfer["amount"]) / 1_000_000_000
                            amount = f"{amt:,.8f}".rstrip("0").rstrip(".")
                        except:
                            amount = str(transfer["amount"])

                        msg = get_template("tx_detected").format(
                            action=transfer["type"],
                            link=f"https://solscan.io/tx/{sig}",
                            wallet=wallet[:8] + "..." + wallet[-6:],
                            mint=transfer["mint"][:8] + "..." + transfer["mint"][-6:],
                            amount=amount,
                            time=datetime.utcnow().strftime("%H:%M:%S")
                        )
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for cid in subs.get(wallet, []):
                            if is_authorized(cid):
                                send_message(cid, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print(f"[Tracker] Erreur: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[Bot] Polling demarre")
    offset = load_update_id()
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()
            updates = resp.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                save_update_id(offset)
                msg = update.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"):
                    continue

                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == PASSWORD:
                    authorize(chat_id)
                    send_message(chat_id, get_template("access_granted"))
                    continue
                if not is_authorized(chat_id):
                    send_message(chat_id, get_template("must_login").format(password=PASSWORD))
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send_message(chat_id, get_template("wallet_invalid"))
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
                        send_message(chat_id, get_template("now_following").format(wallet=w))

                elif cmd == "/remove" and args:
                    w = args.strip()
                    if w in subs and chat_id in subs[w]:
                        subs[w].remove(chat_id)
                        if not subs[w]:
                            del subs[w]
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"Arret suivi : <code>{w}</code>")
                    else:
                        send_message(chat_id, "Pas suivi.")

                elif cmd == "/list":
                    wallets = load_list(WALLETS_FILE)
                    if wallets:
                        txt = "<b>Wallets suivis :</b>\n\n"
                        for w in wallets:
                            count = len([u for u in subs.get(w, []) if is_authorized(u)])
                            txt += f"• <code>{w}</code> ({count} abonnes)\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, get_template("no_wallets"))

                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        txt = "<b>Mes abonnements :</b>\n\n" + "\n".join(f"• <code>{w}</code>" for w in my)
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, get_template("my_subs_none"))

        except Exception as e:
            print(f"[Bot] Erreur: {e}")
            time.sleep(5)

# === FLASK (CORRIGE) ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot Solana Tracker ACTIF"

@app.route("/health")
def health():
    return "OK", 200

# === DEMARRAGE ===
if __name__ == "__main__":
    print("Demarrage bot + test auto...")
    threading.Thread(target=auto_test, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
