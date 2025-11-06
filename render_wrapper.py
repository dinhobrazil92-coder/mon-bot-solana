#!/usr/bin/env python3
# render_wrapper.py
# Wrapper pour Render : lance un mini-serveur HTTP + démarre tracker() et bot()
# Utilisation : place ce fichier à la racine du repo, à côté de ton script principal (ex: tracker_bot.py)

import os
import threading
import time
import importlib
import sys
from flask import Flask, jsonify

# Nom du module de ton bot (modifie si ton fichier s'appelle autrement)
# Si ton script principal s'appelle "tracker_bot.py" -> module_name = "tracker_bot"
# Si ton script principal s'appelle "bot_sol.py" -> module_name = "bot_sol"
module_name = "tracker_bot"  # <-- CHANGE ce nom si besoin (sans .py)

# Vérification simple : ton module doit exposer les fonctions `tracker()` et `bot()`.
# Si elles ont d'autres noms dans ton script, adapte module_name et/ou les noms below.
tracker_func_name = "tracker"
bot_func_name = "bot"

# --- Flask health server ---
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Bot Solana en ligne (Render wrapper)."

@app.route("/healthz")
def healthz():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    # host 0.0.0.0 pour accepter connexions externes
    app.run(host="0.0.0.0", port=port)

# --- Charger et lancer le module du bot ---
def start_bot_threads():
    # tenter d'importer le module du bot
    try:
        if module_name in sys.modules:
            mod = sys.modules[module_name]
        else:
            mod = importlib.import_module(module_name)
    except Exception as e:
        print(f"[wrapper] Erreur import du module '{module_name}': {e}")
        return

    # récupérer les fonctions tracker() et bot() depuis le module
    tracker = getattr(mod, tracker_func_name, None)
    bot = getattr(mod, bot_func_name, None)

    if not callable(tracker):
        print(f"[wrapper] Fonction '{tracker_func_name}' introuvable dans {module_name}. Aborting threads.")
    else:
        try:
            t = threading.Thread(target=tracker, daemon=True)
            t.start()
            print("[wrapper] tracker() lancé en thread.")
        except Exception as e:
            print(f"[wrapper] Erreur démarrage tracker thread: {e}")

    if not callable(bot):
        print(f"[wrapper] Fonction '{bot_func_name}' introuvable dans {module_name}. Le bot principal peut ne pas être démarré.")
    else:
        try:
            t2 = threading.Thread(target=bot, daemon=True)
            t2.start()
            print("[wrapper] bot() lancé en thread.")
        except Exception as e:
            print(f"[wrapper] Erreur démarrage bot thread: {e}")

    # garder le process principal alive (Flask tourne dans un thread séparé)
    # Si tu préfères que bot() soit bloquant, modifie l'approche (ici tout est en threads).
    while True:
        time.sleep(60)

# --- MAIN ---
if __name__ == "__main__":
    print("[wrapper] Démarrage Render wrapper...")
    # Lancer Flask en thread non bloquant
    threading.Thread(target=run_web, daemon=True).start()
    print("[wrapper] Serveur web démarré (thread).")

    # Démarrer les threads tracker et bot (import du module utilisateur)
    start_bot_threads()
