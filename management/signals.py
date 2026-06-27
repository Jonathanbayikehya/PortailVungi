import os
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum

# Importation de tes modèles selon ton fichier models.py
from management.models import Paiement, PublicationResultats

# --- CONFIGURATION DE TES IDENTIFIANTS GREEN-API (WHATSAPP) ---
# Inscris-toi sur green-api.com, choisis l'instance gratuite "Developer" et colle tes clés ici :
GREEN_API_ID_INSTANCE = "7107665628"  # Remplace par ton ID d'instance exact
GREEN_API_API_TOKEN = "fb7864ef65574ced8e30361d61f6079b179dcbb411544d0886"  # Remplace par ton Token exact


def envoyer_whatsapp_green(numero_parent, message_corps):
    """Fonction utilitaire pour centraliser l'envoi des messages via WhatsApp"""
    if not numero_parent:
        return

    # Nettoyage du numéro : Green-API requiert uniquement les chiffres (ex: 243XXXXXXXXX)
    numero_propre = numero_parent.replace("+", "").replace(" ", "").strip()

    url = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"

    payload = {
        "chatId": f"{numero_propre}@c.us",
        "message": message_corps
    }

    try:
        reponse = requests.post(url, json=payload, timeout=8)
        if reponse.status_code == 200:
            print(f"✅ Message WhatsApp envoyé avec succès au numéro {numero_parent}")
        else:
            print(f"⚠️ Erreur Green-API (Code {reponse.status_code}) : {reponse.text}")
    except Exception as e:
        print(f"❌ Impossible de joindre Green-API : {e}")


# =========================================================================
# SIGNAL 1 : DÉCLENCHÉ LORS D'UN NOUVEAU PAIEMENT (AVEC CALCUL DU RESTE)
# =========================================================================
@receiver(post_save, sender=Paiement)
def envoyer_sms_paiementt(sender, instance, created, **kwargs):
    """
    Ce signal se déclenche automatiquement juste après l'enregistrement d'un versement.
    """
    if created:
        try:
            # Récupération de l'élève lié au paiement et du téléphone du parent
            eleve = instance.eleve 
            telephone_parent = eleve.telephone_parent
            frais = instance.frais_type

            if not telephone_parent:
                print(f"⚠️ Aucun numéro de téléphone pour le parent de {eleve.nom} {eleve.postnom}")
                return

            if not frais:
                print(f"⚠️ Aucun type de frais associé à ce paiement.")
                return

            # 1. Calcul du montant TOTAL déjà payé par cet élève pour ce type de frais spécifique
            total_deja_paye = Paiement.objects.filter(
                eleve=eleve, 
                frais_type=frais
            ).aggregate(Sum('montant'))['montant__sum'] or 0.0

            # 2. Calcul du reste à payer
            montant_du = frais.montant
            reste_a_payer = montant_du - total_deja_paye

            # 3. Rédaction du message personnalisé avec le reste à payer
            message_corps = (
                f"Institut Vungi\n"
                f"Cher Parent, un versement de {instance.montant} USD (Reçu n°{instance.numRecur}) vient d'être enregistré "
                f"pour l'élève {eleve.nom} {eleve.postnom}.\n"
                f"Total payé: {total_deja_paye} USD sur {montant_du} USD.\n"
                f"Reste à payer: {max(0, reste_a_payer)} USD."
            )

            # 4. Envoi via WhatsApp
            envoyer_whatsapp_green(telephone_parent, message_corps)

        except Exception as e:
            print(f"❌ Erreur lors de l'exécution du signal Paiement : {e}")


# =========================================================================
# SIGNAL 2 : DÉCLENCHÉ LORSQUE LE PROVISEUR PUBLIE LES RÉSULTATS
# =========================================================================
@receiver(post_save, sender=PublicationResultats)
def alerte_sms_publication(sender, instance, created, **kwargs):
    """
    Ce signal se déclenche automatiquement quand le proviseur active la publication.
    """
    # On vérifie si le proviseur a coché la case "est_publiee" (True)
    if instance.est_publiee:
        try:
            classe = instance.classe
            periode = instance.periode

            # Récupérer automatiquement tous les élèves inscrits dans cette classe
            eleves = classe.eleve_set.all()

            for eleve in eleves:
                if eleve.telephone_parent:
                    # Message personnalisé pour chaque parent de la classe
                    message_corps = (
                        f"Institut Vungi\n"
                        f"Cher Parent, les résultats de la période [{periode.nomPeriode}] pour la classe de "
                        f"{classe.nomClasse} sont officiellement publiés en ligne.\n"
                        f"Veuillez vous connecter sur le portail avec le matricule de l'élève "
                        f"{eleve.nom} {eleve.postnom} pour consulter son bulletin."
                    )
                    
                    # Envoi individuel par WhatsApp
                    envoyer_whatsapp_green(eleve.telephone_parent, message_corps)

        except Exception as e:
            print(f"❌ Erreur lors de l'exécution du signal Publication : {e}")