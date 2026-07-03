import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sms_queue.db")

def initialiser_bdd():
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
    initialiser_bdd()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sms_queue (telephone, message, statut)
        VALUES (?, ?, 'EN_ATTENTE')
    ''', (telephone, message))
    conn.commit()
    conn.close()
    print(f"[SMS Queue] Message planifié pour {telephone}")