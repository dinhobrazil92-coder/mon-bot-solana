#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram + Tracker Solana via HELIUS
100% compatible Render + Disque persistant
"""
import os
import time
import threading
import json
import requests
import html
from datetime import datetime
from flask import Flask

# === CONFIG ===
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "c888ba69-de31-43b7-b6c6-f6f841351f56").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY").strip()
PASSWORD = os.getenv("PASSWORD", "Business2026$").strip()
PORT = int(os.getenv("PORT", 10000))

# === FICHIERS (disque persistant) ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

WALLETS_FILE = f"{DATA_DIR}/wallets.txt"
SEEN_FILE = f"{DATA_DIR}/seen.txt"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"
UPDATE_ID_FILE = f"{DATA_DIR}/update_id.txt"
AUTHORIZED_FILE = f"{DATA_DIR}/authorized.json"

# === HELIUS RPC ===
HELIUS_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# === UTILITAIRES ===
def load_json(file):
    if not os.path.exists(file): return {}
    try: return json.load(open(file, "r", encoding="utf-8"))
    except: return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_list(file):
    if not os.path.exists(file): return []
    return [l.strip() for l in open(file, "r", encoding="utf-8") if l.strip()]

def save_list(file, data):
    with open(file, "w", encoding="utf-8") as f:
        f.write("\n".join(data) + "\n")

def load_set(file): return set(load_list(file))
def save_set(file, data): save_list(file, list(data))

def load_update_id():
    if not os.path.exists(UPDATE_ID_FILE): return 0
    try: return int(open(UPDATE_ID_FILE).read().strip())
    except: return 0

def save_update_id(uid):
    with open(UPDATE_ID_FILE, "w") as f:
        f.write(str(uid))

# === AUTH ===
def is_authorized(chat_id):
    return str(chat_id) in load_json(AUTHORIZED_FILE)

def authorize_user(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === TEMPLATES ===
def default_templates():
    return {
        "tx_detected": "ALERTE <b>{action} DÉTECTÉ !</b>\n\n"
                       "Lien <a href=\"{link}\">Voir sur Solscan</a>\n"
                       "Wallet: <code>{wallet}</code>\n"
                       "Token: <code>{mint}</code>\n"
                       "Montant: <code>{amount}</code>\n"
                       "Heure: <code>{time}</code>",
        "access_granted": "Accès autorisé !\nUtilise /add <wallet>",
        "must_login": "Connecte-toi :\n<code>/login {password}</code>",
        "now_following": "Suivi activé : <code>{wallet}</code>",
        "wallet_invalid": "Wallet invalide (min 32 caractères).",
        "no_wallets": "Aucun wallet suivi.",
        "my_subs_none": "Aucun abonnement."
    }

def load_templates():
    return load_json("templates.json") or default_templates()

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"[send_message] Erreur: {e}")

# === HELIUS RPC ===
def rpc_post(method, params=None):
    if params is None: params = []
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(HELIUS_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        print(f"[RPC] {method} erreur: {e}")
        return None

def get_signatures(wallet, limit=10):
    return rpc_post("getSignaturesForAddress", [wallet, {"limit": limit}]) or []

def get_transaction(sig):
    return rpc_post("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

# === DÉTECTION TRANSFERT TOKEN ===
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def find_token_transfer(tx, wallet):
    if not tx: return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    meta = tx.get("meta", {}) or {}
    all_instr = instructions[:]
    for inner in meta.get("innerInstructions", []):
        all_instr.extend(inner.get("instructions", []))

    for i in all_instr:
        if i.get("programId") != TOKEN_PROGRAM: continue
        p = i.get("parsed", {}) or {}
        info = p.get("info", {})
        if p.get("type") not in ("transfer", "transferChecked"): continue

        source = info.get("source")
        dest = info.get("destination")
        mint = info.get("mint") or info.get("mintAccount") or "?"
        amount = info.get("amount")
        decimals = None

        if "tokenAmount" in info and isinstance(info["tokenAmount"], dict):
            ta = info["tokenAmount"]
            amount = ta.get("amount")
            decimals = ta.get("decimals")

        if dest == wallet:
            return {"type": "ACHAT", "mint": mint, "amount": amount, "decimals": decimals}
        if source == wallet:
            return {"type": "VENTE", "mint": mint, "amount": amount, "decimals": decimals}
    return None

# === TRACKER ===
def tracker():
    print("[Tracker] Démarré")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue

            for wallet in wallets:
                sigs = get_signatures(wallet, limit=10)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen: continue

                    tx = get_transaction(sig)
                    transfer = find_token_transfer(tx, wallet)
                    if transfer:
                        amount_raw = transfer["amount"]
                        try:
                            if transfer.get("decimals") is not None:
                                amt = int(amount_raw)
                                dec = int(transfer["decimals"])
                                amount = f"{amt / (10 ** dec):,.8f}".rstrip("0").rstrip(".")
                            else:
                                amount = f"{int(amount_raw) / 1_000_000_000:,.2f}"
                        except:
                            amount = str(amount_raw)

                        templates = default_templates()
                        msg = templates["tx_detected"].format(
                            action=transfer["type"],
                            link=f"https://solscan.io/tx/{sig}",
                            wallet=wallet[:8] + "..." + wallet[-6:],
                            mint=transfer["mint"][:8] + "..." + transfer["mint"][-6:],
                            amount=amount,
                            time=datetime.utcnow().strftime("%H:%M:%S UTC")
                        )

                        subs = load_json(SUBSCRIPTIONS_FILE)
                        for chat_id in subs.get(wallet, []):
                            if is_authorized(chat_id):
                                send_message(chat_id, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)

            time.sleep(18)
        except Exception as e:
            print(f"[Tracker] Erreur: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[Bot] Démarré (polling)")
    offset = load_update_id()
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            ).json()
            updates = resp.get("result", [])

            for u in updates:
                offset = u["update_id"] + 1
                save_update_id(offset)
                msg = u.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"): continue

                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == PASSWORD:
                    authorize_user(chat_id)
                    send_message(chat_id, default_templates()["access_granted"])
                    continue

                if not is_authorized(chat_id):
                    send_message(chat_id, default_templates()["must_login"].format(password=PASSWORD))
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send_message(chat_id, default_templates()["wallet_invalid"])
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
                        send_message(chat_id, default_templates()["now_following"].format(wallet=w))
                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        txt = "<b>Tes abonnements :</b>\n" + "\n".join(f"• <code>{w}</code>" for w in my)
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, default_templates()["my_subs_none"])
        except Exception as e:
            print(f"[Bot] Erreur: {e}")
            time.sleep(5)

# === FLASK (CORRIGÉ) ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot Solana Tracker ACTIF (Helius + Telegram)"

@app.route("/health")
def health():
    return "OK", 200

# === MAIN ===
if __name__ == "__main__":
    print("Démarrage du bot sur Render...")
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
