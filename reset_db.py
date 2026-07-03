import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sms_queue.db")

if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE sms_queue SET statut = 'EN_ATTENTE'")
    conn.commit()
    conn.close()
    print("🚀 Base de données réinitialisée avec succès ! Tous les SMS sont en attente.")
else:
    print("❌ Fichier sms_queue.db introuvable au bon emplacement.")