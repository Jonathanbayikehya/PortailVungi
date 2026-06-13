from django.db import models
from django.conf import settings # <--- Ajoute ceci
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
import string
import random
from django.apps import apps # Pour charger le modèle de manière sécurisée


# 1. SECTION (Celle liée à l'Option)
class Section(models.Model):
    idSection = models.AutoField(primary_key=True)
    description = models.CharField(max_length=255)
    def __str__(self): return self.description

# 2. OPTION
class Option(models.Model):
    idOption = models.AutoField(primary_key=True)
    nomOption = models.CharField(max_length=100)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    def __str__(self): return self.nomOption

# 3. ENSEIGNANT
class Enseignant(models.Model):
    idEns = models.AutoField(primary_key=True)
    matriculeEns = models.CharField(max_length=50, unique=True, verbose_name="Matricule Enseignant") # REMIS ICI
    nom = models.CharField(max_length=50)
    postnom = models.CharField(max_length=50)
    prenom = models.CharField(max_length=50)
    grade = models.CharField(max_length=50)
    telephone = models.CharField(max_length=15)
    
    # Liaison One-to-One avec le compte de connexion Django
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='enseignant_profile')

    def __str__(self):
        return f"{self.matriculeEns} - {self.nom} {self.prenom}"

# 4. CLASSE
class Classe(models.Model):
    idClasse = models.AutoField(primary_key=True)
    nomClasse = models.CharField(max_length=50)
    annee = models.CharField(max_length=20) # Ex: "2025-2026"
    option = models.ForeignKey('Option', on_delete=models.CASCADE, db_column='idOption')
    
    # C'est cette ligne qui définit le Titulaire de la classe (#idEns) !
    idEns = models.ForeignKey(
        'Enseignant', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='idEns',
        related_name='classe_titulaire'
    )
    
    TYPE_BULLETIN_CHOICES = [
        ('co', 'Cycle d\'Orientation'),
        ('sci', 'Scientifique'),
        ('elec', 'Electricité'),
        ('peda', 'Pédagogie'),
        ('cg', 'Commerciale & Gestion'),
    ]
    type_bulletin = models.CharField(max_length=10, choices=TYPE_BULLETIN_CHOICES, default='co')

    def __str__(self):
        return f"{self.nomClasse} - {self.option} - {self.annee}"


# 5. ELEVE
class Eleve(models.Model):
    # Utilise settings.AUTH_USER_MODEL au lieu de User
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    matriculeEleve = models.CharField(max_length=50, unique=True, primary_key=True)
    nom = models.CharField(max_length=100)
    postnom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    sexe = models.CharField(max_length=10)
    date_naissance = models.DateField()
    lieu_naissance = models.CharField(max_length=100)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE)
    def __str__(self): return f"{self.nom} {self.postnom} ({self.matriculeEleve})"

# 6. TYPECOURS
class TypeCours(models.Model):
    idType = models.AutoField(primary_key=True)
    libelle = models.CharField(max_length=100)
    def __str__(self): return self.libelle

# 7. SECTION COURS (Entité distincte dans ton diagramme)
class SectionCours(models.Model):
    maxima = models.FloatField(unique=True)

    def __str__(self):
        return f"Max {self.maxima}"
    
class Domaine(models.Model):
    nom = models.CharField(max_length=100)
    # Pour gérer le tri sur le bulletin (ex: Sciences = 1, Arts = 2)
    ordre = models.IntegerField(default=0) 

    def __str__(self):
        return self.nom

# 8. COURS
class Cours(models.Model):
    idCours = models.AutoField(primary_key=True)
    code_cours = models.CharField(max_length=20)
    libelle = models.CharField(max_length=150)
    max = models.ForeignKey(SectionCours, on_delete=models.CASCADE)
    ponderation = models.FloatField()
    type_cours = models.ForeignKey(TypeCours, on_delete=models.CASCADE)
    enseignant = models.ForeignKey(Enseignant, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Enseignant Attribué")
    domaine = models.ForeignKey(Domaine, on_delete=models.SET_NULL, null=True, blank=True)
    classes = models.ManyToManyField(
        'Classe', 
        related_name='cours_etudies',
        help_text="Sélectionnez la ou les classes spécifiques qui suivent ce cours."
    )
    
    def __str__(self):
        return self.libelle

# 9. PERIODE
class Periode(models.Model):
    STATUT_CHOICES = [
        ('VERROUILLE', 'Pas encore ouverte'),
        ('ACTIVE', 'En cours d\'encodage'),
        ('CLOTURE', 'Clôturée (Résultats publiés)'),
    ]

    idPeriode = models.AutoField(primary_key=True)
    nomPeriode = models.CharField(max_length=50)
    code = models.CharField(max_length=10, unique=True)
    # AJOUTE CE CHAMP :
    statut = models.CharField(
        max_length=15, 
        choices=STATUT_CHOICES, 
        default='VERROUILLE'
    )

    def __str__(self):
        return f"{self.nomPeriode} ({self.get_statut_display()})"

# 10. COTES
class Cotes(models.Model):
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='cotes')
    cours = models.ForeignKey('Cours', on_delete=models.CASCADE, related_name='cotes_cours')
    periode = models.ForeignKey(Periode, on_delete=models.CASCADE, related_name='cotes_periode')
    note = models.FloatField(null=True, blank=True)

    class Meta:
        # Un élève a une seule note par cours pour une période donnée
        unique_together = ('eleve', 'cours', 'periode') 

    def __str__(self):
        return f"{self.eleve} - {self.cours.libelle} - {self.periode.code} : {self.note}"

# 11. FRAISSCOLAIRE
class FraisScolaire(models.Model):
    typeFrs = models.CharField(max_length=100) # Ex: "Frais Scolaires Annuels"
    montant = models.FloatField() # Le montant DU (Total à payer)
    
    # Correction ici : on retire 'placeholder=' qui faisait planter Django
    classe = models.CharField(max_length=50, blank=True, null=True)
    option = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        cible = f" - {self.classe} {self.option}" if (self.classe or self.option) else " - Général"
        return f"{self.typeFrs}{cible} ({self.montant}$)"

# 12. PAIEMENT
class Paiement(models.Model):
    # idPaiement est automatique
    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='paiements')
    # Lien vers FraisScolaire comme sur le diagramme
    frais_type = models.ForeignKey(FraisScolaire, on_delete=models.CASCADE, null=True) 
    numRecur = models.CharField(max_length=50) # Numéro de reçu
    montant = models.FloatField()
    date = models.DateField(auto_now_add=True) # Ton diagramme dit int, mais Date est plus logique pour le reçu

    def __str__(self):
        return f"Reçu {self.numRecur} - {self.eleve.nom}"

# 13. USER (Utilisateur du portail)


@receiver(post_save, sender="management.Eleve")
def create_user_for_eleve(sender, instance, created, **kwargs):
    if created:
        UserAccount = get_user_model()
        username = str(instance.matriculeEleve).replace(" ", "")
        
        if not UserAccount.objects.filter(username=username).exists():
            new_user = UserAccount.objects.create_user(
                username=username,
                password=str(instance.matriculeEleve)
            )
            # Lien avec l'élève
            sender.objects.filter(pk=instance.pk).update(user=new_user)
            
@receiver(post_save, sender=Enseignant)
def creer_utilisateur_pour_enseignant(sender, instance, created, **kwargs):
    """
    Ce signal génère automatiquement un compte User Django avec le matricule
    comme identifiant dès qu'un Enseignant est enregistré.
    """
    if created and not instance.user:
        # On nettoie le matricule pour en faire un identifiant valide (sans espaces)
        username_val = instance.matriculeEns.lower().replace(' ', '')
        
        # TECHNIQUE SÉCURISÉE : On récupère le vrai modèle User de Django de manière explicite
        VraiModeleUser = apps.get_model('auth', 'User')
        
        # On vérifie si cet identifiant n'existe pas déjà
        if not VraiModeleUser.objects.filter(username=username_val).exists():
            
            # Ici, .objects.create_user fonctionnera à 100% car on cible le bon modèle
            nouvel_user = VraiModeleUser.objects.create_user(
                username=username_val,
                first_name=instance.prenom,
                last_name=instance.nom,
                password="vungi2026" # Mot de passe par défaut pour l'Institut Vungi
            )
            
            # Liaison physique et sauvegarde
            instance.user = nouvel_user
            instance.save()

class CentralisationClasse(models.Model):
    classe = models.OneToOneField(Classe, on_delete=models.CASCADE, verbose_name="Classe concernée")
    titulaire = models.ForeignKey(Enseignant, on_delete=models.CASCADE, verbose_name="Titulaire")
    date_soumission = models.DateTimeField(auto_now_add=True, verbose_name="Date de soumission")
    est_valide = models.BooleanField(default=False, verbose_name="Validé par le Proviseur")
    feedback_proviseur = models.TextField(blank=True, default='', verbose_name="Retour du proviseur")
    date_validation = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation")

    def __str__(self):
        return f"Centralisation {self.classe.nomClasse} - {self.titulaire.nom}"
    
class Attribution(models.Model):
    cours = models.ForeignKey('Cours', on_delete=models.CASCADE)
    classe = models.ForeignKey('Classe', on_delete=models.CASCADE)
    enseignant = models.ForeignKey('Enseignant', on_delete=models.SET_NULL, null=True, blank=True)
    
    # AJOUTEZ CES CHAMPS ICI :
    max_tj = models.FloatField(default=20, verbose_name="Max Travaux Journaliers")
    max_examen = models.FloatField(default=40, verbose_name="Max Examen")

    class Meta:
        unique_together = ('cours', 'classe')

    def __str__(self):
        return f"{self.cours.libelle} - {self.classe.nomClasse}"


class PublicationResultats(models.Model):
    """Publication globale des résultats par le proviseur."""
    est_publiee = models.BooleanField(default=False, verbose_name="Résultats publiés")
    date_publication = models.DateTimeField(null=True, blank=True)
    publie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='publications_resultats',
    )

    class Meta:
        verbose_name = "Publication des résultats"
        verbose_name_plural = "Publications des résultats"

    @classmethod
    def get_instance(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Publiés" if self.est_publiee else "Non publiés"


class DecisionJury(models.Model):
    DECISION_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('ADMIS', 'Admis'),
        ('AJOURNE', 'Ajourné'),
        ('REDOUBLE', 'Redouble'),
        ('EXCLU', 'Exclu'),
    ]

    eleve = models.ForeignKey(Eleve, on_delete=models.CASCADE, related_name='decisions_jury')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='decisions_jury')
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default='EN_ATTENTE')
    commentaire = models.TextField(blank=True, default='')
    date_decision = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('eleve', 'classe')
        verbose_name = "Décision du jury"
        verbose_name_plural = "Décisions du jury"

    def __str__(self):
        return f"{self.eleve} — {self.get_decision_display()}"