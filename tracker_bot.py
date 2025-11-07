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

# === DATA ===
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
AUTHORIZED_FILE = DATA_DIR + "/authorized.json"
SUBSCRIPTIONS_FILE = DATA_DIR + "/subscriptions.json"
WALLETS_FILE = DATA_DIR + "/wallets.txt"
SEEN_FILE = DATA_DIR + "/seen.txt"
UPDATE_ID_FILE = DATA_DIR + "/update_id.txt"

# === FICHIERS ===
def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

def load_list(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_list(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
    except:
        pass

def load_set(path):
    return set(load_list(path))

def save_set(path, data):
    save_list(path, list(data))

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
def is_authorized(cid):
    return str(cid) == MY_CHAT_ID or str(cid) in load_json(AUTHORIZED_FILE)

def pre_authorize():
    data = load_json(AUTHORIZED_FILE)
    data[MY_CHAT_ID] = True
    save_json(AUTHORIZED_FILE, data)
    print("[OK] Pré-autorisé: " + MY_CHAT_ID)

# === TELEGRAM ===
def send(cid, text):
    try:
        r = requests.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            data={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        if r.status_code == 200:
            print("[OK] Envoyé à " + str(cid))
        else:
            print("[ERR] TG " + str(r.status_code))
    except Exception as e:
        print("[ERR] TG: " + str(e))

def test_force():
    time.sleep(15)
    send(MY_CHAT_ID, "BOT VIVANT !\n\nTest OK.\nEnvoie /add <wallet>")

# === RPC SOLANA ===
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

def rpc(method, params=None):
    if params is None:
        params = []
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        r = requests.post(SOLANA_RPC, json=payload, timeout=15)
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
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    for i in instructions:
        if i.get("programId") == MINT_PROGRAM:
            parsed = i.get("parsed", {})
            if parsed.get("type") == "initializeMint":
                info = parsed.get("info", {})
                if info.get("mintAuthority") == wallet:
                    return info.get("mint")
    return None

def detect_transfer(tx, wallet):
    if not tx:
        return None
    all_i = tx.get("transaction", {}).get("message", {}).get("instructions", [])[:]
    inner_list = tx.get("meta", {}).get("innerInstructions", [])
    for inner in inner_list:
        all_i.extend(inner.get("instructions", []))
    for i in all_i:
        if i.get("programId") == TOKEN_PROGRAM:
            parsed = i.get("parsed", {})
            if parsed.get("type") in ("transfer", "transferChecked"):
                info = parsed.get("info", {})
                src = info.get("source")
                dst = info.get("destination")
                mint = info.get("mint") or "?"
                amount = info.get("amount")
                decimals = info.get("tokenAmount", {}).get("decimals") if "tokenAmount" in info else None
                if dst == wallet:
                    return "ACHAT", mint, amount, decimals
                if src == wallet:
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
                        continue

                    # Création
                    mint = detect_creation(tx, wallet)
                    if mint:
                        msg = "NOUVEAU TOKEN !\n<a href=\"https://solscan.io/tx/" + sig + "\">Voir</a>\n<code>" + wallet[:8] + "..." + wallet[-6:] + "</code>"
                        send(MY_CHAT_ID, msg)

                    # Transfert
                    transfer = detect_transfer(tx, wallet)
                    if transfer:
                        action, mint, amount, decimals = transfer
                        try:
                            if decimals is not None:
                                amt = int(amount) / (10 ** int(decimals))
                            else:
                                amt = int(amount) / 1000000000
                            amount_str = "{:,.8f}".format(amt).rstrip("0").rstrip(".")
                        except:
                            amount_str = str(amount)
                        msg = "<b>" + action + "</b>\n<a href=\"https://solscan.io/tx/" + sig + "\">Voir</a>\n<code>" + wallet[:8] + "..." + wallet[-6:] + "</code>\n<code>" + amount_str + "</code>"
                        send(MY_CHAT_ID, msg)

                    seen.add(sig)
                    save_set(SEEN_FILE, seen)
            time.sleep(18)
        except Exception as e:
            print("[ERR] Tracker: " + str(e))
            time.sleep(10)

# === BOT ===
def bot():
    print("[OK] Bot démarré")
    offset = load_update_id()
    while True:
        try:
            url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates"
            params = {"offset": offset, "timeout": 30}
            response = requests.get(url, params=params, timeout=40).json()
            for update in response.get("result", []):
                offset = update["update_id"] + 1
                save_update_id(offset)
                message = update.get("message") or {}
                cid = message.get("chat", {}).get("id")
                text = (message.get("text") or "").strip()
                if not text.startswith("/"):
                    continue
                parts = text.split(" ", 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "/login" and args == SECRET_PASSWORD:
                    data = load_json(AUTHORIZED_FILE)
                    data[str(cid)] = True
                    save_json(AUTHORIZED_FILE, data)
                    send(cid, "Accès OK !\n/add <wallet>")
                    continue

                if not is_authorized(cid):
                    send(cid, "Connecte-toi : /login [mdp]")
                    continue

                subs = load_json(SUBSCRIPTIONS_FILE)

                if cmd == "/add" and args:
                    w = args.strip()
                    if len(w) < 32:
                        send(cid, "Invalide")
                        continue
                    current = load_list(WALLETS_FILE)
                    if w not in current:
                        current.append(w)
                        save_list(WALLETS_FILE, current)
                    if w not in subs:
                        subs[w] = []
                    if cid not in subs[w]:
                        subs[w].append(cid)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send(cid, "Suivi : <code>" + w + "</code>")
                elif cmd == "/my":
                    mine = []
                    for wallet_key, users in subs.items():
                        if cid in users:
                            mine.append(wallet_key)
                    if mine:
                        msg = ""
                        for w in mine:
                            msg += "• <code>" + w + "</code>\n"
                        send(cid, msg)
                    else:
                        send(cid, "Aucun")
        except Exception as e:
            print("[ERR] Bot: " + str(e))
            time.sleep(5)

# === FLASK ===
app = Flask(__name__)
@app.route("/")
def index():
    return "ON"

@app.route("/health")
def health():
    return "OK", 200

# === LANCEMENT ===
if __name__ == "__main__":
    pre_authorize()
    threading.Thread(target=test_force, daemon=True).start()
    threading.Thread(target=tracker, daemon=True).start()
    threading.Thread(target=bot, daemon=True).start()
    print("[OK] Démarré")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
