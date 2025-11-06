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
RPC_URL = os.getenv("RPC_URL", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PASSWORD = os.getenv("PASSWORD", "Business2026$").strip()
PORT = int(os.getenv("PORT", 10000))

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
    except:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_list(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_list(file, data):
    with open(file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_set(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return set(f.read().splitlines())
    except:
        return set()

def save_set(file, data):
    with open(file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_update_id():
    try:
        with open(UPDATE_ID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except:
        return 0

def save_update_id(uid):
    with open(UPDATE_ID_FILE, "w", encoding="utf-8") as f:
        f.write(str(uid))

# === AUTH ===
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
        "access_granted": "✅ <b>Accès autorisé !</b>\nTu peux utiliser le bot.\nCommandes :\n/add WALLET\n/list\n/my\n/remove WALLET",
        "access_denied": "⛔ Mot de passe incorrect.",
        "must_login": "🔒 Connecte-toi :\n<code>/login {password}</code>",
        "tx_detected": "🚨 <b>{action} DÉTECTÉ !</b>\n"
                       "👤 Wallet: <code>{wallet}</code>\n"
                       "🪙 Token: <code>{mint}</code>\n"
                       "💸 Montant: <code>{amount}</code>\n"
                       "🕒 Heure: <code>{time}</code>\n"
                       "🔗 <a href=\"{link}\">Voir sur Solscan</a>",
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
    except:
        return default_templates()

def format_html_safe(s):
    return html.escape(str(s))

# === TELEGRAM ===
def send_message(chat_id, text):
    if not BOT_TOKEN:
        print("[send_message] BOT_TOKEN non défini.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
        if resp.status_code != 200:
            print(f"[send_message] Erreur {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[send_message error] {e}")

# === SOLANA RPC HELPERS ===
def rpc_post(payload):
    try:
        r = requests.post(RPC_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[rpc_post error] {e}")
        return None

def get_signatures(wallet, limit=10):
    payload = {"jsonrpc":"2.0","id":1,"method":"getSignaturesForAddress","params":[wallet,{"limit":limit}]}
    res = rpc_post(payload)
    if not res:
        return []
    return res.get("result", [])

def get_transaction(sig):
    payload = {"jsonrpc":"2.0","id":1,"method":"getTransaction","params":[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]}
    res = rpc_post(payload)
    if not res:
        return None
    return res.get("result")

# === TRANSFERS ===
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def extract_transfer_info(parsed):
    if not parsed: return None
    ptype = parsed.get("type")
    info = parsed.get("info", {})
    if ptype in ("transfer", "transferChecked"):
        source = info.get("source")
        dest = info.get("destination")
        mint = info.get("mint") or info.get("mintAccount") or info.get("token")
        if "tokenAmount" in info and isinstance(info.get("tokenAmount"), dict):
            amt = info["tokenAmount"].get("amount")
            dec = info["tokenAmount"].get("decimals")
            if amt and dec is not None:
                return source, dest, mint, {"amount": amt, "decimals": dec}
        else:
            amount = info.get("amount") or info.get("lamports") or info.get("uiAmountString")
            return source, dest, mint, amount
    return None

def find_token_transfer(tx, wallet, direction="in"):
    if not tx: return None
    instrs = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    meta = tx.get("meta", {}) or {}
    for inner_group in meta.get("innerInstructions", []) or []:
        instrs.extend(inner_group.get("instructions", []))
    for instr in instrs:
        prog = instr.get("programId") or instr.get("programIdIndex")
        if prog == TOKEN_PROGRAM_ID or (isinstance(prog,str) and TOKEN_PROGRAM_ID in prog):
            parsed = instr.get("parsed") or {}
            ex = extract_transfer_info(parsed)
            if not ex: continue
            src,dest,mint,amount = ex
            if direction=="in" and dest==wallet: return {"mint":mint,"amount":amount,"type":"ACHAT"}
            if direction=="out" and src==wallet: return {"mint":mint,"amount":amount,"type":"VENTE"}
    return None

# === TRACKER ===
def tracker():
    print("[tracker] démarrage...")
    seen = load_set(SEEN_FILE)
    while True:
        wallets = load_list(WALLETS_FILE)
        if not wallets: time.sleep(15); continue
        for wallet in wallets:
            sigs = get_signatures(wallet)
            for s in sigs:
                sig = s.get("signature")
                if not sig or sig in seen: continue
                tx = get_transaction(sig)
                buy = find_token_transfer(tx,wallet,"in")
                sell = find_token_transfer(tx,wallet,"out")
                if buy or sell:
                    info = buy if buy else sell
                    action = info.get("type","TX")
                    mint = info.get("mint","UNKNOWN")
                    amount_raw = info.get("amount",0)
                    amount_disp = "?"
                    try:
                        if isinstance(amount_raw, dict):
                            amt = int(amount_raw.get("amount",0))
                            dec = int(amount_raw.get("decimals",0))
                            amount_disp = f"{amt/(10**dec):,}"
                        else:
                            amount_disp = f"{int(amount_raw)/1_000_000:,}"
                    except: amount_disp=str(amount_raw)
                    link = f"https://solscan.io/tx/{sig}"
                    temp = load_templates().get("tx_detected")
                    msg = temp.format(
                        action=format_html_safe(action),
                        wallet=format_html_safe(wallet),
                        mint=format_html_safe(mint),
                        amount=format_html_safe(amount_disp),
                        link=format_html_safe(link),
                        time=format_html_safe(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
                    )
                    subs = load_json(SUBSCRIPTIONS_FILE)
                    for chat_id in subs.get(wallet,[]):
                        if is_authorized(chat_id):
                            print(f"[tracker] Envoi notif à {chat_id} pour {wallet} {action}")
                            send_message(chat_id,msg)
                seen.add(sig)
                save_set(SEEN_FILE,seen)
        time.sleep(15)

# === TELEGRAM BOT ===
def bot():
    offset = load_update_id()
    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",params={"offset":offset,"timeout":30}).json()
            updates = resp.get("result",[])
            for update in updates:
                offset = update["update_id"]+1
                save_update_id(offset)
                msg = update.get("message",{})
                chat_id = msg.get("chat",{}).get("id")
                text = msg.get("text","")
                if not chat_id or not text.startswith("/"): continue
                cmd,args=text.split()[0].lower()," ".join(text.split()[1:])
                temp = load_templates()
                if cmd=="/login":
                    if args==PASSWORD: authorize_user(chat_id); send_message(chat_id,temp.get("access_granted"))
                    else: send_message(chat_id,temp.get("access_denied"))
                    continue
                if not is_authorized(chat_id):
                    send_message(chat_id,temp.get("must_login").format(password=PASSWORD))
                    continue
                subs=load_json(SUBSCRIPTIONS_FILE)
                if cmd=="/start": send_message(chat_id,temp.get("access_granted"))
                elif cmd=="/add" and args:
                    wallet=args.strip()
                    if len(wallet)<32: send_message(chat_id,temp.get("wallet_invalid")); continue
                    current=load_list(WALLETS_FILE)
                    if wallet not in current: current.append(wallet); save_list(WALLETS_FILE,current)
                    if wallet not in subs: subs[wallet]=[]
                    if chat_id not in subs[wallet]: subs[wallet].append(chat_id); save_json(SUBSCRIPTIONS_FILE,subs); send_message(chat_id,temp.get("now_following").format(wallet=wallet))
                    else: send_message(chat_id,temp.get("already_followed"))
                elif cmd=="/list":
                    wallets=load_list(WALLETS_FILE)
                    if wallets: txt="<b>Wallets suivis :</b>\n"
                        for w in wallets: txt+=f"• <code>{w}</code> ({len([u for u in subs.get(w,[]) if is_authorized(u)])} abonnés)\n"
                        send_message(chat_id,txt)
                    else: send_message(chat_id,temp.get("no_wallets"))
                elif cmd=="/my":
                    my=[w for w,u in subs.items() if chat_id in u]
                    if my: txt="<b>Tes abonnements :</b>\n"; txt+="\n".join([f"• <code>{w}</code>" for w in my]); send_message(chat_id,txt)
                    else: send_message(chat_id,temp.get("my_subs_none"))
                elif cmd=="/remove" and args:
                    wallet=args.strip()
                    if wallet in subs and chat_id in subs[wallet]: subs[wallet].remove(chat_id); 
                        if not subs[wallet]: del subs[wallet]; save_json(SUBSCRIPTIONS_FILE,subs)
                        send_message(chat_id,f"✅ Plus suivi : <code>{wallet}</code>")
                    else: send_message(chat_id,"❌ Pas suivi.")
        except Exception as e: print(f"[bot] Exception: {e}"); time.sleep(5)

# === FLASK MINI SERVER ===
app = Flask(__name__)
@app.route("/")
def index(): return "Bot Solana en ligne ✅

