from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings # Importation pour récupérer SITE_URL

# Importation de vos modèles
from .models import Paiement, PublicationResultats, Eleve  
from database import ajouter_sms_a_la_file 

# =====================================================================
# 1. SIGNAL POUR LE PAIEMENT (COMPTABILITÉ)
# =====================================================================
@receiver(post_save, sender=Paiement)
def notifier_paiement_parent(sender, instance, created, **kwargs):
    if created:  
        try:
            eleve = instance.eleve 
            nom_complet_eleve = f"{eleve.nom} {eleve.postnom} {eleve.prenom}".strip()
            email_parent = eleve.adresseMail 
            motif = instance.frais_type.typeFrs if instance.frais_type else "Frais Scolaires"
            
            if email_parent:
                # Intégration du lien dynamique du site
                message = (
                    f"PORTAIL VUNGI : Confirmation de paiement.\n\n"
                    f"Un montant de {instance.montant}$ a été versé pour l'élève {nom_complet_eleve} "
                    f"(Reçu No {instance.numRecur}).\n"
                    f"Motif : {motif}.\n\n"
                    f"Retrouvez l'historique des paiements sur notre plateforme : {settings.SITE_URL}\n\n"
                    f"Merci pour votre confiance."
                )
                
                ajouter_sms_a_la_file(email_parent, message)
                print(f"[Signal Paiement] Mail avec lien planifié pour {email_parent}")
                
        except Exception as e:
            print(f"[Erreur Signal Paiement Mail] : {e}")


# =====================================================================
# 2. SIGNAL POUR LA PUBLICATION DES RÉSULTATS (PROVISEUR)
# =====================================================================
@receiver(post_save, sender=PublicationResultats)
def notifier_publication_global(sender, instance, created, **kwargs):
    try:
        if instance.est_publiee:
            classe_concernee = instance.classe
            periode_concernee = instance.periode
            eleves_classe = Eleve.objects.filter(classe=classe_concernee)
            
            compteur_mails = 0
            for eleve in eleves_classe:
                email_parent = eleve.adresseMail
                
                if email_parent:
                    nom_complet_eleve = f"{eleve.nom} {eleve.postnom} {eleve.prenom}".strip()
                    
                    # Intégration du lien dynamique pour consulter le bulletin
                    message = (
                        f"PORTAIL VUNGI : Publication des résultats.\n\n"
                        f"Les résultats de l'élève {nom_complet_eleve} pour la période "
                        f"'{periode_concernee.nomPeriode}' sont désormais disponibles en ligne.\n\n"
                        f"👉 Cliquez ici pour vous connecter et consulter son bulletin : {settings.SITE_URL}\n\n"
                        f"Direction de l'Établissement."
                    )
                    
                    ajouter_sms_a_la_file(email_parent, message)
                    compteur_mails += 1
                    
            print(f"[Signal Publication] {compteur_mails} mails planifiés avec l'URL du site.")
            
    except Exception as e:
        print(f"[Erreur Signal Publication Mail] : {e}")