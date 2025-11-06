# ========================================
# BOT TRACKER SOLANA - MOT DE PASSE + ACHAT/VENTE
# /login MOTDEPASSE → accès
# ========================================

import requests
import time
import threading
import json
import os

# === À REMPLIR (SÉCURITÉ) ===
RPC_URL = os.getenv("RPC_URL",)
BOT_TOKEN = os.getenv("BOT_TOKEN",)
# =============================

# === MOT DE PASSE (CHANGE-LE !) ===
PASSWORD = "Business2026$"  # ← CHANGE ÇA
# ===================================

WALLETS_FILE = "wallets.txt"
SEEN_FILE = "seen.txt"
SUBSCRIPTIONS_FILE = "subscriptions.json"
UPDATE_ID_FILE = "update_id.txt"
AUTHORIZED_FILE = "authorized.json"

# === GESTION FICHIERS ===
def load_json(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

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

def load_list(file):
    try:
        with open(file, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def save_list(file, data):
    with open(file, "w") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_set(file):
    try:
        with open(file, "r") as f:
            return set(f.read().splitlines())
    except:
        return set()

def save_set(file, data):
    with open(file, "w") as f:
        for item in data:
            f.write(str(item) + "\n")

def load_update_id():
    try:
        with open(UPDATE_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def save_update_id(uid):
    with open(UPDATE_ID_FILE, "w") as f:
        f.write(str(uid))

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=10)
    except:
        pass

# === SOLANA RPC ===
def get_signatures(wallet):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": 10}]
    }
    try:
        r = requests.post(RPC_URL, json=payload, timeout=10)
        return r.json().get("result", [])
    except:
        return []

def get_transaction(sig):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        r = requests.post(RPC_URL, json=payload, timeout=10)
        return r.json().get("result")
    except:
        return None

# === DÉTECTION ACHAT / VENTE (TOUT INCLUS) ===
def find_token_transfer(tx, wallet, direction="in"):
    if not tx: return None
    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    token_transfers = []

    # Parcourir toutes les instructions (y compris inner)
    all_instructions = instructions
    for i in instructions:
        if "innerInstructions" in i:
            for inner in i["innerInstructions"]:
                all_instructions.extend(inner.get("instructions", []))

    for i in all_instructions:
        if i.get("programId") == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
            parsed = i.get("parsed", {})
            if parsed.get("type") == "transfer":
                info = parsed.get("info", {})
                source = info.get("source")
                dest = info.get("destination")
                mint = info.get("mint")
                amount = info.get("amount", "0")

                if direction == "in" and dest == wallet:
                    token_transfers.append({"mint": mint, "amount": amount, "type": "ACHAT"})
                elif direction == "out" and source == wallet:
                    token_transfers.append({"mint": mint, "amount": amount, "type": "VENTE"})

    return token_transfers[0] if token_transfers else None

# === TRACKER (ACHAT + VENTE) ===
def tracker():
    seen = load_set(SEEN_FILE)
    while True:
        wallets = load_list(WALLETS_FILE)
        if not wallets:
            time.sleep(20)
            continue

        for wallet in wallets:
            sigs = get_signatures(wallet)
            for s in sigs:
                sig = s["signature"]
                if sig in seen:
                    continue

                tx = get_transaction(sig)
                buy = find_token_transfer(tx, wallet, "in")
                sell = find_token_transfer(tx, wallet, "out")

                if buy or sell:
                    action = buy["type"] if buy else sell["type"]
                    mint = buy["mint"] if buy else sell["mint"]
                    amount_raw = buy["amount"] if buy else sell["amount"]
                    try:
                        amount = int(amount_raw) / 1_000_000
                    except:
                        amount = 0

                    link = f"https://solscan.io/tx/{sig}"
                    message = (
                        f"*{action} DÉTECTÉ !*\n\n"
                        f"Wallet: `{wallet}`\n"
                        f"Token: `{mint}`\n"
                        f"Montant: ~{amount:,.6f}\n"
                        f"[Voir sur Solscan]({link})"
                    )

                    subs = load_json(SUBSCRIPTIONS_FILE)
                    for chat_id in subs.get(wallet, []):
                        if is_authorized(chat_id):
                            send_message(chat_id, message)

                seen.add(sig)
                save_set(SEEN_FILE, seen)
        time.sleep(15)  # Plus rapide

# === BOT TELEGRAM ===
def bot():
    offset = load_update_id()
    while True:
        try:
            updates = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}
            ).json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                save_update_id(offset)
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if not chat_id or not text or not text.startswith("/"):
                    continue

                cmd = text.split()[0].lower()
                args = " ".join(text.split()[1:]).strip()

                # /login
                if cmd == "/login":
                    if args == PASSWORD:
                        authorize_user(chat_id)
                        send_message(chat_id, (
                            "*Accès autorisé !*\n\n"
                            "Tu peux maintenant utiliser le bot.\n\n"
                            "Commandes :\n"
                            "/add WALLET → suivre\n"
                            "/list → voir les wallets\n"
                            "/my → mes abonnements\n"
                            "/remove WALLET → arrêter"
                        ))
                    else:
                        send_message(chat_id, "Mot de passe incorrect.")
                    continue

                # Pas connecté
                if not is_authorized(chat_id):
                    send_message(chat_id, "Tu dois te connecter :\n`/login Business2026$`")
                    continue

                # Commandes
                subs = load_json(SUBSCRIPTIONS_FILE)
                if cmd == "/start":
                    send_message(chat_id, (
                        "*Bot Tracker Solana*\n\n"
                        "Tu es connecté !\n\n"
                        "Commandes :\n"
                        "/add WALLET → suivre\n"
                        "/list → voir les wallets\n"
                        "/my → mes abonnements\n"
                        "/remove WALLET → arrêter"
                    ))
                elif cmd == "/add" and args:
                    wallet = args
                    if len(wallet) < 32:
                        send_message(chat_id, "Wallet invalide.")
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
                        send_message(chat_id, f"Tu suis :\n`{wallet}`")
                    else:
                        send_message(chat_id, "Déjà suivi.")
                elif cmd == "/list":
                    wallets = load_list(WALLETS_FILE)
                    if wallets:
                        txt = "*Wallets suivis :*\n\n"
                        for w in wallets:
                            count = len([u for u in subs.get(w, []) if is_authorized(u)])
                            txt += f"• `{w}` ({count} abonnés)\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, "Aucun wallet.")
                elif cmd == "/my":
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        txt = "*Tes abonnements :*\n\n"
                        for w in my:
                            txt += f"• `{w}`\n"
                        send_message(chat_id, txt)
                    else:
                        send_message(chat_id, "Aucun abonnement.")
                elif cmd == "/remove" and args:
                    wallet = args
                    if wallet in subs and chat_id in subs[wallet]:
                        subs[wallet].remove(chat_id)
                        if not subs[wallet]:
                            del subs[wallet]
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"Plus suivi :\n`{wallet}`")
                    else:
                        send_message(chat_id, "Pas suivi.")

        except Exception as e:
            print(f"[Erreur] {e}")
            time.sleep(5)

# === LANCEMENT ===
if __name__ == "__main__":
    print("Bot SOLANA ACHAT/VENTE + MOT DE PASSE démarré...")
    threading.Thread(target=tracker, daemon=True).start()
    bot()