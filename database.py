import sqlite3
import os

# Détection intelligente du chemin absolu pour le serveur en ligne et le PC local
if os.path.exists('/home/institutvungi/PortailVungi'):
    DB_PATH = '/home/institutvungi/PortailVungi/sms_queue.db'
else:
    # Chemin dynamique pour le PC local Windows (remonte d'un niveau si le fichier est dans un sous-dossier)
    CORPS_DIR = os.path.dirname(os.path.abspath(__file__))
    # Si le fichier est dans un sous-dossier de PortailVungi, on remonte d'un cran pour se mettre à la racine
    if "vungi_portal" in CORPS_DIR or "applications" in CORPS_DIR:
        DB_PATH = os.path.join(os.path.dirname(CORPS_DIR), "sms_queue.db")
    else:
        DB_PATH = os.path.join(CORPS_DIR, "sms_queue.db")

def initialiser_bdd():
    """
    Crée la table de file d'attente si elle n'existe pas encore.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telephone TEXT NOT NULL,
            message TEXT NOT NULL,
            statut TEXT DEFAULT 'EN_ATTENTE',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def ajouter_sms_a_la_file(telephone, message):
    """
    Planifie l'envoi d'un e-mail en l'ajoutant à la file d'attente SQLite.
    """
    initialiser_bdd()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sms_queue (telephone, message, statut)
        VALUES (?, ?, 'EN_ATTENTE')
    ''', (telephone, message))
    conn.commit()
    conn.close()
    print(f"[SMS Queue] Message planifié pour {telephone} (Sauvegardé dans {DB_PATH})")