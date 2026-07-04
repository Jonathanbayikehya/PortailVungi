import sqlite3
import time
import os
import sys

# 1. Configuration et initialisation de l'environnement Django
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vungi_portal.settings")

# Sécurisation et forçage de la clé d'application Gmail
os.environ['DJANGO_EMAIL_PASSWORD'] = 'ptowkvqpjyjqumcv'

import django
django.setup()

from django.core.mail import send_mail
from django.conf import settings

# Détection intelligente du chemin absolu de la base de données
if os.path.exists('/home/institutvungi/PortailVungi'):
    DB_PATH = '/home/institutvungi/PortailVungi/sms_queue.db'
else:
    DB_PATH = os.path.join(BASE_DIR, "sms_queue.db")

def envoyer_email_direct(email_dest, contenu_message, sujet="Notification - Institut Vungi"):
    """
    Exécute l'envoi de l'e-mail avec le serveur SMTP configuré dans Django.
    """
    try:
        print(f"[Mail System] Expédition du courriel vers : {email_dest}")
        send_mail(
            subject=sujet,
            message=contenu_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_dest],
            fail_silently=False,
        )
        print("[Mail System] Courriel envoyé avec succès !")
        return True
    except Exception as e:
        print(f"[Erreur SMTP] Échec de l'envoi de l'e-mail : {e}")
        return False

def executer_la_file():
    """
    Vérifie la base SQLite partagée et traite les e-mails en attente.
    """
    if not os.path.exists(DB_PATH):
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Récupération des messages en attente de traitement
        cursor.execute("SELECT id, telephone, message FROM sms_queue WHERE statut = 'EN_ATTENTE'")
        lignes = cursor.fetchall()
        
        for ligne in lignes:
            id_msg, email_parent, message_corps = ligne
            
            # Validation rapide de l'adresse e-mail reçue dans le champ 'telephone'
            if not email_parent or "@" not in str(email_parent):
                print(f"[Worker] ID {id_msg} ignoré : '{email_parent}' n'est pas un e-mail valide.")
                cursor.execute("UPDATE sms_queue SET statut = 'ERREUR' WHERE id = ?", (id_msg,))
                conn.commit()
                continue
                
            print(f"\n[Worker] Prise en charge de la notification ID {id_msg}...")
            
            # Tentative d'envoi
            succes = envoyer_email_direct(email_parent, message_corps)
            
            # Mise à jour du statut selon le résultat de l'envoi
            allocation_statut = 'ENVOYE' if succes else 'ERREUR'
            cursor.execute("UPDATE sms_queue SET statut = ? WHERE id = ?", (allocation_statut, id_msg))
            conn.commit()
            
            print(f"[Worker] Fin de traitement ID {id_msg} avec statut : {allocation_statut}")
            time.sleep(2)  # Pause de sécurité pour respecter les quotas d'envoi
            
    except sqlite3.OperationalError as e:
        print(f"[Erreur Base SQLite] : {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("=========================================================")
    print("=== Worker de Notification E-mail Actif (Portail Vungi) ===")
    print("=========================================================")
    print(f"Base de données ciblée : {DB_PATH}")
    print("En veille... En attente de notifications (Faites Ctrl+C pour quitter)")
    
    while True:
        executer_la_file()
        time.sleep(5)