#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Telegram - Tracker Solana (ACHAT/VENTE)
Prêt pour Render Web Service avec mini serveur intégré.
"""

import os
import time
import threading
import json
import requests
import html
from datetime import datetime
from flask import Flask

# === CONFIG (préférer les ENV) ===
RPC_URL = os.getenv("RPC_URL", "").strip()  # ex: https://api.mainnet-beta.solana.com
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PASSWORD = os.getenv("PASSWORD", "Business2026$").strip()  # changer / mettre en env sur Render

# === FICHIERS LOCAUX ===
WALLETS_FILE = "wallets.txt"
SEEN_FILE = "seen.txt"
SUBSCRIPTIONS_FILE = "subscriptions.json"
UPDATE_ID_FILE = "update_id.txt"
AUTHORIZED_FILE = "authorized.json"
TEMPLATES_FILE = "templates.json"

# === UTILITAIRES FICHIER / JSON ===
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_list(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []

def save_list(file, data):
    with open(file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_set(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    except Exception:
        return set()

def save_set(file, data):
    with open(file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_update_id():
    try:
        with open(UPDATE_ID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_update_id(uid):
    with open(UPDATE_ID_FILE, "w", encoding="utf-8") as f:
        f.write(str(uid))

# === AUTHORIZATION ===
def load_authorized():
    return load_json(AUTHORIZED_FILE)

def save_authorized(data):
    save_json(AUTHORIZED_FILE, data)

def is_authorized(chat_id):
    return str(chat_id) in load_authorized()

def authorize_user(chat_id):
    data = load_authorized()
    data[str(chat_id)] = True
    save_authorized(data)

# === TEMPLATES ===
def default_templates():
    return {
        "access_granted": "✅ <b>Accès autorisé !</b>\n\nTu peux maintenant utiliser le bot.\n\nCommandes :\n/add WALLET → suivre\n/list → voir les wallets\n/my → mes abonnements\n/remove WALLET → arrêter",
        "access_denied": "⛔ Mot de passe incorrect.",
        "must_login": "🔒 Tu dois te connecter :\n<code>/login {password}</code>",
        "tx_detected": "🚨 <b>{action} DÉTECTÉ !</b>\n\n"
                       "🔗 <a href=\"{link}\">Voir transaction</a>\n"
                       "👤 Wallet: <code>{wallet}</code>\n"
                       "🪙 Token (mint): <code>{mint}</code>\n"
                       "💸 Montant: <code>{amount}</code>\n"
                       "🕒 Heure: <code>{time}</code>\n",
        "already_followed": "ℹ️ Déjà suivi.",
        "now_following": "✅ Tu suis :\n<code>{wallet}</code>",
        "wallet_invalid": "⚠️ Wallet invalide.",
        "no_wallets": "📭 Aucun wallet.",
        "my_subs_none": "📭 Aucun abonnement."
    }

def load_templates():
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_templates()

def format_html_safe(s):
    return html.escape(str(s))

# === TELEGRAM SEND ===
def send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True):
    if not BOT_TOKEN:
        print("[send_message] BOT_TOKEN non défini.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview
        }, timeout=10)
        if resp.status_code != 200:
            print(f"[send_message] Erreur {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[send_message error] {e}")

# === SOLANA RPC HELPERS ===
def rpc_post(payload):
    if not RPC_URL:
        print("[rpc_post] RPC_URL non défini.")
        return None
    try:
        r = requests.post(RPC_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[rpc_post error] {e}")
        return None

def get_signatures(wallet, limit=10):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": limit}]
    }
    res = rpc_post(payload)
    if not res:
        return []
    return res.get("result", [])

def get_transaction(sig):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    res = rpc_post(payload)
    if not res:
        return None
    return res.get("result")

# === DÉTECTION ACHAT / VENTE ===
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def extract_transfer_info(parsed):
    if not parsed:
        return None
    ptype = parsed.get("type")
    info = parsed.get("info", {})
    if ptype in ("transfer", "transferChecked"):
        source = info.get("source")
        dest = info.get("destination")
        mint = info.get("mint") or info.get("mintAccount") or info.get("token")
        if "tokenAmount" in info and isinstance(info.get("tokenAmount"), dict):
            ta = info.get("tokenAmount", {})
            amount = ta.get("amount")
            decimals = ta.get("decimals")
            if amount is not None and decimals is not None:
                return source, dest, mint, {"amount": amount, "decimals": decimals}
            return source, dest, mint, info.get("tokenAmount")
        else:
            amount = info.get("amount") or info.get("lamports") or info.get("uiAmountString")
            return source, dest, mint, amount
    return None

def find_token_transfer(tx, wallet, direction="in"):
    if not tx:
        return None
    message = tx.get("transaction", {}).get("message", {})
    instructions = message.get("instructions", []) or []
    token_transfers = []

    all_instructions = []
    for instr in instructions:
        all_instructions.append(instr)
    meta = tx.get("meta", {}) or {}
    for inner_group in meta.get("innerInstructions", []) or []:
        for instr in inner_group.get("instructions", []) or []:
            all_instructions.append(instr)

    for instr in all_instructions:
        program_id = instr.get("programId") or instr.get("programIdIndex")
        if program_id == TOKEN_PROGRAM_ID or (isinstance(program_id, str) and TOKEN_PROGRAM_ID in program_id):
            parsed = instr.get("parsed") or {}
            extracted = extract_transfer_info(parsed)
            if not extracted:
                continue
            source, dest, mint, amount = extracted
            if direction == "in" and dest == wallet:
                token_transfers.append({"mint": mint or "UNKNOWN", "amount": amount, "type": "ACHAT"})
            elif direction == "out" and source == wallet:
                token_transfers.append({"mint": mint or "UNKNOWN", "amount": amount, "type": "VENTE"})
    return token_transfers[0] if token_transfers else None

# === TRACKER PRINCIPAL ===
def tracker():
    print("[tracker] démarrage du tracker...")
    seen = load_set(SEEN_FILE)
    while True:
        wallets = load_list(WALLETS_FILE)
        if not wallets:
            time.sleep(20)
            continue
        for wallet in wallets:
            sigs = get_signatures(wallet)
            for s in sigs:
                sig = s.get("signature")
                if not sig or sig in seen:
                    continue
                tx = get_transaction(sig)
                buy = find_token_transfer(tx, wallet, "in")
                sell = find_token_transfer(tx, wallet, "out")

                if buy or sell:
                    action_info = buy if buy else sell
                    action = action_info.get("type", "TX")
                    mint = action_info.get("mint", "UNKNOWN")
                    amount_raw = action_info.get("amount", 0)
                    amount_display = "?"
                    try:
                        if isinstance(amount_raw, dict):
                            amt = amount_raw.get("amount")
                            dec = amount_raw.get("decimals")
                            if amt is not None and dec is not None:
                                amount_display = f"{int(amt) / (10 ** int(dec)):,}"
                        else:
                            amount_display = f"{int(amount_raw) / 1_000_000:,}"
                    except Exception:
                        amount_display = str(amount_raw)

                    link = f"https://solscan.io/tx/{sig}"
                    templates = load_templates()
                    template = templates.get("tx_detected", default_templates().get("tx_detected"))
                    message = template.format(
                        action=format_html_safe(action),
                        link=format_html_safe(link),
                        wallet=format_html_safe(wallet),
                        mint=format_html_safe(mint),
                        amount=format_html_safe(amount_display),
                        time=format_html_safe(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
                    )

                    subs = load_json(SUBSCRIPTIONS_FILE)
                    subscribers = subs.get(wallet, []) or []
                    for chat_id in subscribers:
                        if is_authorized(chat_id):
                            send_message(chat_id, message)

                seen.add(sig)
                save_set(SEEN_FILE, seen)
        time.sleep(15)

# === BOT TELEGRAM ===
def bot():
    print("[bot] démarrage du bot Telegram...")
    offset = load_update_id()
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}
            ).json()
            updates = resp.get("result", []) or []

            for update in updates:
                offset = update["update_id"] + 1
                save_update_id(offset)
                msg = update.get("message") or {}
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "") or ""
                if not chat_id or not text or not text.startswith("/"):
                    continue
                cmd = text.split()[0].lower()
                args = " ".join(text.split()[1:]).strip()
                templates = load_templates()

                # /login
                if cmd == "/login":
                    if args == PASSWORD:
                        authorize_user(chat_id)
                        send_message(chat_id, templates.get("access_granted"))
                    else:
                        send_message(chat_id, templates.get("access_denied"))
                    continue

                if not is_authorized(chat_id):
                    send_message(chat_id, templates.get("must_login").format(password=PASSWORD))
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/start":
                    send_message(chat_id, templates.get("access_granted"))
                elif cmd == "/add" and args:
                    wallet = args.strip()
                    if len(wallet) < 32:
                        send_message(ch_
