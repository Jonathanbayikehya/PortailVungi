from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from management.models import Enseignant, Classe, Eleve

class Command(BaseCommand):
    help = 'Create test users (Titulaire, Enseignant) linked to models'

    def handle(self, *args, **options):
        self.stdout.write("Créating test users...")
        
        # 1. Create Titulaire (Titulaire)
        user_titulaire, created = User.objects.get_or_create(
            username='titulaire',
            defaults={'password': 'titulaire123', 'first_name': 'Jean', 'last_name': 'Martin'}
        )
        if created:
            user_titulaire.set_password('titulaire123')
            user_titulaire.save()
            self.stdout.write(self.style.SUCCESS("✓ Created user: titulaire"))
        
        # Create Enseignant for Titulaire
        enseignant_titulaire, created = Enseignant.objects.get_or_create(
            user=user_titulaire,
            defaults={'matriculeEns': 'ENS001', 'nom': 'Martin', 'postnom': 'Jean', 'prenom': 'Jean', 'grade': 'Professeur'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✓ Created Enseignant for titulaire"))
        
        # Link Titulaire to a Classe
        try:
            classe = Classe.objects.first()
            if classe and not classe.idEns:
                classe.idEns = enseignant_titulaire
                classe.save()
                self.stdout.write(self.style.SUCCESS(f"✓ Linked titulaire to classe: {classe.nomClasse}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not link classe: {e}"))
        
        # 2. Create Enseignant user
        user_enseignant, created = User.objects.get_or_create(
            username='enseignant',
            defaults={'password': 'enseignant123', 'first_name': 'Pierre', 'last_name': 'Dupont'}
        )
        if created:
            user_enseignant.set_password('enseignant123')
            user_enseignant.save()
            self.stdout.write(self.style.SUCCESS("✓ Created user: enseignant"))
        
        # Create Enseignant model for enseignant user
        enseignant_obj, created = Enseignant.objects.get_or_create(
            user=user_enseignant,
            defaults={'matriculeEns': 'ENS002', 'nom': 'Dupont', 'postnom': 'Pierre', 'prenom': 'Pierre', 'grade': 'Professeur'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✓ Created Enseignant model for enseignant"))
        
        # 3. Create Eleve user
        user_eleve, created = User.objects.get_or_create(
            username='eleve',
            defaults={'password': 'eleve123', 'first_name': 'Marie', 'last_name': 'Durand'}
        )
        if created:
            user_eleve.set_password('eleve123')
            user_eleve.save()
            self.stdout.write(self.style.SUCCESS("✓ Created user: eleve"))
        
        # Create Eleve model
        try:
            from datetime import date
            eleve_obj, created = Eleve.objects.get_or_create(
                matriculeEleve='EL001',
                defaults={
                    'user': user_eleve,
                    'nom': 'Durand',
                    'postnom': 'Marie',
                    'prenom': 'Marie',
                    'classe': Classe.objects.first(),
                    'sexe': 'F',
                    'date_naissance': date(2008, 5, 15),
                    'lieu_naissance': 'Butembo'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS("✓ Created Eleve model"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not create Eleve: {e}"))
        
        self.stdout.write(self.style.SUCCESS("\n✅ Test data initialization complete!"))
        self.stdout.write("\nAccounts created:")
        self.stdout.write("  Titulaire:  titulaire / titulaire123")
        self.stdout.write("  Enseignant: enseignant / enseignant123")
        self.stdout.write("  Eleve:      eleve / eleve123")
