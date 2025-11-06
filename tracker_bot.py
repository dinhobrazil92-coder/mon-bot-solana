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

# === CONFIG ===
RPC_URL = os.getenv("RPC_URL", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PASSWORD = os.getenv("PASSWORD", "Business2026$").strip()
PORT = int(os.getenv("PORT", 10000))

# === FICHIERS LOCAUX (persistants sur Render si disque monté) ===
WALLETS_FILE = "data/wallets.txt"
SEEN_FILE = "data/seen.txt"
SUBSCRIPTIONS_FILE = "data/subscriptions.json"
UPDATE_ID_FILE = "data/update_id.txt"
AUTHORIZED_FILE = "data/authorized.json"
TEMPLATES_FILE = "data/templates.json"

# Créer le dossier data si inexistant
os.makedirs("data", exist_ok=True)

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
            return set(line.strip() for line in f if line.strip())
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
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            },
            timeout=10
        )
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
        r = requests.post(RPC_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[rpc_post error] {e}")
        return None

def get_signatures(wallet, limit=5):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": limit}]
    }
    res = rpc_post(payload)
    return res.get("result", []) if res else []

def get_transaction(sig):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    res = rpc_post(payload)
    return res.get("result") if res else None

# === DETECTION ACHAT / VENTE ===
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def extract_transfer_info(parsed):
    if not parsed:
        return None
    ptype = parsed.get("type")
    info = parsed.get("info", {})
    if ptype in ("transfer", "transferChecked"):
        source = info.get("source")
        dest = info.get("destination")
        mint = info.get("mint") or info.get("mintAccount")
        if "tokenAmount" in info and isinstance(info["tokenAmount"], dict):
            ta = info["tokenAmount"]
            amount = ta.get("amount")
            decimals = ta.get("decimals")
            if amount and decimals is not None:
                return source, dest, mint, {"amount": amount, "decimals": decimals}
        else:
            amount = info.get("amount") or info.get("lamports")
            return source, dest, mint, amount
    return None

def find_token_transfer(tx, wallet, direction="in"):
    if not tx:
        return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    meta = tx.get("meta", {}) or {}
    all_instructions = instructions[:]
    for inner in meta.get("innerInstructions", []) or []:
        all_instructions.extend(inner.get("instructions", []))
    for instr in all_instructions:
        program_id = instr.get("programId")
        if program_id != TOKEN_PROGRAM_ID:
            continue
        parsed = instr.get("parsed") or {}
        extracted = extract_transfer_info(parsed)
        if not extracted:
            continue
        source, dest, mint, amount = extracted
        if direction == "in" and dest == wallet:
            return {"mint": mint or "UNKNOWN", "amount": amount, "type": "ACHAT"}
        elif direction == "out" and source == wallet:
            return {"mint": mint or "UNKNOWN", "amount": amount, "type": "VENTE"}
    return None

# === TRACKER ===
def tracker():
    print("[tracker] Démarrage du tracker Solana...")
    seen = load_set(SEEN_FILE)
    while True:
        try:
            wallets = load_list(WALLETS_FILE)
            if not wallets:
                time.sleep(30)
                continue

            for wallet in wallets:
                sigs = get_signatures(wallet, limit=5)
                for s in sigs:
                    sig = s.get("signature")
                    if not sig or sig in seen:
                        continue
                    tx = get_transaction(sig)
                    buy = find_token_transfer(tx, wallet, "in")
                    sell = find_token_transfer(tx, wallet, "out")
                    if buy or sell:
                        action_info = buy or sell
                        action = action_info["type"]
                        mint = action_info["mint"]
                        amount_raw = action_info["amount"]
                        try:
                            if isinstance(amount_raw, dict):
                                amt = int(amount_raw["amount"])
                                dec = int(amount_raw["decimals"])
                                amount_display = f"{amt / (10 ** dec):,.8f}".rstrip("0").rstrip(".")
                            else:
                                amount_display = f"{int(amount_raw) / 1_000_000_000:,.2f}"
                        except:
                            amount_display = str(amount_raw)

                        link = f"https://solscan.io/tx/{sig}"
                        templates = load_templates()
                        template = templates.get("tx_detected", default_templates()["tx_detected"])
                        message = template.format(
                            action=format_html_safe(action),
                            link=format_html_safe(link),
                            wallet=format_html_safe(wallet),
                            mint=format_html_safe(mint),
                            amount=format_html_safe(amount_display),
                            time=format_html_safe(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
                        )
                        subs = load_json(SUBSCRIPTIONS_FILE)
                        subscribers = subs.get(wallet, [])
                        for chat_id in subscribers:
                            if is_authorized(chat_id):
                                send_message(chat_id, message)
                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(20)
        except Exception as e:
            print(f"[tracker] Erreur: {e}")
            time.sleep(10)

# === BOT TELEGRAM ===
def bot():
    print("[bot] Démarrage du bot Telegram (polling)...")
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
                if not chat_id or not text or not text.startswith("/"):
                    continue

                cmd_parts = text.split(maxsplit=1)
                cmd = cmd_parts[0].lower()
                args = cmd_parts[1] if len(cmd_parts) > 1 else ""

                templates = load_templates()

                # /login
                if cmd == "/login":
                    if args == PASSWORD:
                        authorize_user(chat_id)
                        send_message(chat_id, templates.get("access_granted", "Accès autorisé."))
                    else:
                        send_message(chat_id, templates.get("access_denied", "Accès refusé."))
                    continue

                if not is_authorized(chat_id):
                    send_message(chat_id, templates.get("must_login", "Connecte-toi d'abord.").format(password=PASSWORD))
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/start":
                    send_message(chat_id, templates.get("access_granted", "Bienvenue !"))
                elif cmd == "/add" and args:
                    wallet = args.strip()
                    if len(wallet) < 32:
                        send_message(chat_id, templates.get("wallet_invalid", "Wallet invalide."))
                        continue
                    current = load_list(WALLETS_FILE)
                    if wallet not in current:
                        current.append(wallet)
                        save_list(WALLETS_FILE, current)
                    if wallet not in subs:
                        subs[wallet] = []
                    if chat_id not in subs[wallet]:
                        subs[wallet].append(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, templates.get("now_following", "Suivi activé.").format(wallet=wallet))
                    else:
                        send_message(chat_id, templates.get("already_followed", "Déjà suivi."))
                elif cmd == "/list":
                    wallets = load_list(WALLETS_FILE)
                    if wallets:
                        txt = "<b>Wallets suivis :</b>\n\n"
                        for w in wallets:
                            count = len([u for u in subs.get(w, []) if is_authorized(u)])
                            txt += f"• <code>{w}</code> ({count} abonnés)\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, templates.get("no_wallets", "Aucun wallet."))
                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        txt = "<b>Tes abonnements :</b>\n\n" + "\n".join(f"• <code>{w}</code>" for w in my)
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, templates.get("my_subs_none", "Aucun abonnement."))
                elif cmd == "/remove" and args:
                    wallet = args.strip()
                    if wallet in subs and chat_id in subs[wallet]:
                        subs[wallet].remove(chat_id)
                        if not subs[wallet]:
                            del subs[wallet]
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"✅ Plus suivi :\n<code>{wallet}</code>")
                    else:
                        send_message(chat_id, "❌ Pas suivi.")
                else:
                    send_message(chat_id, "Commande inconnue.")
        except Exception as e:
            print(f"[bot] Exception: {e}")
            time.sleep(5)

# === FLASK SERVER (pour Render) ===
app = Flask(__name__)

@app.route("/")
def index():
    return "🚀 Bot Solana Tracker en marche !<br>Tracker + Bot Telegram actifs."

@app.route("/health")
def health():
    return "OK", 200

# === DEMARRAGE ===
if __name__ == "__main__":
    print("Démarrage du Bot Solana + Telegram sur Render...")
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
