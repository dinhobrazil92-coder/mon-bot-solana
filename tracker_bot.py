#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Solana Wallet Tracker via Helius -> Telegram
- Reçoit webhooks Helius sur /helius (POST)
- Envoie notifications Telegram aux abonnés d'un wallet
- Fichiers data/authorized.json et subscriptions.json pour gestion utilisateurs
- Debug complet pour logs Render
"""

import os
import json
import time
import threading
import requests
from flask import Flask, request, jsonify

# === CONFIG (BOT_TOKEN intégré comme demandé) ===
BOT_TOKEN = "8017958637:AAHGc7Zkw2B63GyR1nbnuckx3Hc8h4eelRY"
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "Business2026$")  # tu peux changer via env sur Render
PORT = int(os.getenv("PORT", "10000"))
DEFAULT_CHAT_ID = os.getenv("DEFAULT_CHAT_ID")  # optionnel: notifications globales

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

AUTHORIZED_FILE = os.path.join(DATA_DIR, "authorized.json")
SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")

# === UTILITAIRES JSON FILES ===
def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[load_json] Erreur lecture {path}: {e}")
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[save_json] Erreur écriture {path}: {e}")

# === TELEGRAM SEND ===
def send_message(chat_id, text, parse_mode="HTML"):
    if not BOT_TOKEN:
        print("[TG] BOT_TOKEN non configuré.")
        return None
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload, timeout=10)
        print(f"[TG] send to {chat_id}: status={r.status_code}, resp={r.text}")
        return r
    except Exception as e:
        print(f"[TG] Exception envoi: {e}")
        return None

def broadcast_to_all(text):
    """Envoyer à tous les users autorisés (authorized.json)."""
    users = load_json(AUTHORIZED_FILE)
    for cid in users.keys():
        send_message(cid, text)
    if DEFAULT_CHAT_ID:
        send_message(DEFAULT_CHAT_ID, text)

# === AUTH HELPERS ===
def is_authorized(chat_id):
    data = load_json(AUTHORIZED_FILE)
    return str(chat_id) in data

def authorize(chat_id):
    data = load_json(AUTHORIZED_FILE)
    data[str(chat_id)] = True
    save_json(AUTHORIZED_FILE, data)

# === FLASK APP ===
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Solana Tracker (Helius -> Telegram) actif"

@app.route("/health")
def health():
    return "OK", 200

# HELIUS WEBHOOK: reçoit POST JSON
@app.route("/helius", methods=["POST"])
def helius_webhook():
    payload = request.get_json(silent=True)
    print("[Helius] Requête reçue:", json.dumps(payload, indent=2)[:4000])

    if not payload:
        # Log complet du corps brut pour debug si JSON non parsable
        try:
            raw = request.get_data(as_text=True)
            print("[Helius] Payload brut:", raw[:4000])
        except:
            pass
        return jsonify({"ok": False, "error": "no json"}), 400

    # --- Normalise events en liste ---
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        # Helius peut envoyer sous "events" ou "tokenTransfers" ou "nftTransfers"
        events = payload.get("events") or payload.get("tokenTransfers") or payload.get("nftTransfers") or []
        # Parfois Helius envoie un top-level event dict (single event), gérer ce cas :
        if not events and ("type" in payload or "signature" in payload):
            events = [payload]
    else:
        events = []

    subs = load_json(SUBSCRIPTIONS_FILE)
    print(f"[Helius] {len(events)} event(s) traités.")

    for event in events:
        try:
            # Multi-champs possibles pour le wallet source/target selon type d'event
            wallet = event.get("account") or event.get("fromUserAccount") or event.get("toUserAccount") or event.get("source") or "inconnu"
            tx_hash = event.get("signature") or event.get("txHash") or event.get("transactionHash") or "inconnu"

            # Montant: lamports -> SOL si présent, sinon tokenAmount
            if "lamports" in event:
                try:
                    amount = round(int(event.get("lamports", 0)) / 1e9, 9)
                    amount_str = f"{amount} SOL"
                except:
                    amount_str = str(event.get("lamports"))
            else:
                amount_str = str(event.get("amount") or event.get("tokenAmount") or "?")

            mint = event.get("mint") or event.get("tokenAddress") or "?"
            name = event.get("name") or (event.get("metadata") or {}).get("name") or mint
            token_standard = event.get("tokenStandard") or (event.get("tokenStandard") if "tokenStandard" in event else "SOL")
            emoji = "💎" if token_standard == "SOL" else "🪙" if token_standard == "SPL" else "🖼️"

            action_type = event.get("type") or event.get("category") or "Transaction"
            if token_standard and token_standard != "SOL":
                action_type += f" ({token_standard})"

            message = (
                f"{emoji} <b>{action_type}</b>\n\n"
                f"👛 Wallet: <code>{wallet}</code>\n"
                f"🪙 Token: <b>{name}</b> (<code>{mint}</code>)\n"
                f"💵 Montant: <code>{amount_str}</code>\n"
                f"🔗 <a href='https://solscan.io/tx/{tx_hash}'>Voir la transaction</a>"
            )

            # Option: si image metadata présent
            image = (event.get("metadata") or {}).get("image")
            if image:
                message += f"\n🖼️ {image}"

            print(f"[Helius] Message préparé pour tx {tx_hash} - wallet {wallet}")

            # Envoie: aux abonnés du wallet (si existants)
            sent_any = False
            for cid in subs.get(wallet, []):
                # subs file may store ints or strings: normalize
                try:
                    cid_key = str(cid)
                except:
                    cid_key = cid
                if is_authorized(cid_key):
                    send_message(cid_key, message)
                    sent_any = True
                else:
                    print(f"[Helius] cid {cid_key} trouvé mais non autorisé")

            # Si aucun abonné, tu peux broadcast global (optionnel)
            if not sent_any and DEFAULT_CHAT_ID:
                print("[Helius] Aucun abonné pour wallet, envoi au DEFAULT_CHAT_ID")
                send_message(DEFAULT_CHAT_ID, message)

        except Exception as e:
            print(f"[Helius] Erreur traitement event: {e}")

    return jsonify({"ok": True}), 200

# === TELEGRAM POLLING (gestion commandes: /login, /add, /remove, /list, /my) ===
def bot_polling():
    print("[Bot] Démarrage polling Telegram...")
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                             params={"offset": offset, "timeout": 30}, timeout=40)
            data = r.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = (msg.get("text") or "").strip()
                print(f"[Bot] update from {chat_id}: {text}")

                # Simple command parsing
                if not text.startswith("/"):
                    continue
                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                subs = load_json(SUBSCRIPTIONS_FILE)

                # /login <password>
                if cmd == "/login":
                    if args == BOT_PASSWORD:
                        authorize(chat_id)
                        send_message(chat_id, "🔓 Accès autorisé !\n\nCommandes :\n/add WALLET\n/remove WALLET\n/list\n/my")
                    else:
                        send_message(chat_id, "❌ Mot de passe incorrect.")
                    continue

                # require login for following commands
                if not is_authorized(chat_id):
                    send_message(chat_id, f"🔐 Connecte-toi : /login <mot_de_passe>")
                    continue

                if cmd == "/add" and args:
                    wallet = args.strip()
                    subs = load_json(SUBSCRIPTIONS_FILE)
                    if wallet not in subs:
                        subs[wallet] = []
                    if chat_id not in subs[wallet]:
                        subs[wallet].append(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"👀 Suivi activé pour <code>{wallet}</code>")
                    else:
                        send_message(chat_id, f"✅ Déjà abonné à <code>{wallet}</code>")

                elif cmd == "/remove" and args:
                    wallet = args.strip()
                    subs = load_json(SUBSCRIPTIONS_FILE)
                    if wallet in subs and chat_id in subs[wallet]:
                        subs[wallet].remove(chat_id)
                        save_json(SUBSCRIPTIONS_FILE, subs)
                        send_message(chat_id, f"❌ Suivi arrêté pour <code>{wallet}</code>")
                    else:
                        send_message(chat_id, "Pas d'abonnement trouvé.")

                elif cmd == "/list":
                    subs = load_json(SUBSCRIPTIONS_FILE)
                    wallets = list(subs.keys())
                    if not wallets:
                        send_message(chat_id, "Aucun wallet suivi.")
                    else:
                        send_message(chat_id, "<b>📜 Wallets suivis :</b>\n" + "\n".join(wallets))

                elif cmd == "/my":
                    subs = load_json(SUBSCRIPTIONS_FILE)
                    my = [w for w, users in subs.items() if chat_id in users]
                    if my:
                        send_message(chat_id, "<b>👤 Tes abonnements :</b>\n" + "\n".join(my))
                    else:
                        send_message(chat_id, "Tu n'es abonné à aucun wallet.")

        except Exception as e:
            print(f"[Bot] Erreur polling: {e}")
            time.sleep(5)

# === MAIN ===
if __name__ == "__main__":
    # Start Telegram polling thread
    if not BOT_TOKEN:
        print("[MAIN] ERREUR: BOT_TOKEN non défini. Mettre BOT_TOKEN en variable d'environnement.")
    else:
        t = threading.Thread(target=bot_polling, daemon=True)
        t.start()
    print("🚀 Démarrage application Flask")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
