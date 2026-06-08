from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from management.models import (
    Attribution,
    Classe,
    Cotes,
    Domaine,
    Eleve,
    Enseignant,
    Option,
    Periode,
    Section,
    SectionCours,
    TypeCours,
    Cours,
)


class WorkflowViewsTest(TestCase):
    def setUp(self):
        self.client = Client()

        self.section = Section.objects.create(description="Section test")
        self.option = Option.objects.create(nomOption="Commerciale", section=self.section)
        self.titulaire_user = User.objects.create_user(username="titulaire_test", password="pass1234")
        self.enseignant_user = User.objects.create_user(username="enseignant_test", password="pass1234")

        self.titulaire = Enseignant.objects.create(
            matriculeEns="ENS-TIT-01",
            nom="Titulaire",
            postnom="Test",
            prenom="Jean",
            grade="Licencié",
            user=self.titulaire_user,
        )
        self.enseignant = Enseignant.objects.create(
            matriculeEns="ENS-ENS-01",
            nom="Enseignant",
            postnom="Test",
            prenom="Paul",
            grade="Gradué",
            user=self.enseignant_user,
        )

        self.classe = Classe.objects.create(
            nomClasse="1ère",
            annee="2025-2026",
            option=self.option,
            idEns=self.titulaire,
            type_bulletin="cg",
        )

        self.eleve = Eleve.objects.create(
            matriculeEleve="EL001",
            nom="Eleve",
            postnom="Test",
            prenom="Marie",
            sexe="F",
            date_naissance=date(2008, 1, 1),
            lieu_naissance="Butembo",
            classe=self.classe,
        )

        self.type_cours = TypeCours.objects.create(libelle="Général")
        self.section_cours = SectionCours.objects.create(maxima=10)
        self.domaine = Domaine.objects.create(nom="Langues", ordre=1)
        self.cours = Cours.objects.create(
            code_cours="FR001",
            libelle="Français",
            max=self.section_cours,
            ponderation=1,
            type_cours=self.type_cours,
            domaine=self.domaine,
        )
        self.cours.classes.add(self.classe)

        self.attribution = Attribution.objects.create(
            cours=self.cours,
            classe=self.classe,
            enseignant=self.enseignant,
            max_tj=10,
            max_examen=20,
        )

        for code, nom, statut in [
            ("P1", "Période 1", "ACTIVE"),
            ("P2", "Période 2", "ACTIVE"),
            ("EX1", "Examen 1", "ACTIVE"),
            ("P3", "Période 3", "VERROUILLE"),
            ("P4", "Période 4", "VERROUILLE"),
            ("EX2", "Examen 2", "VERROUILLE"),
        ]:
            Periode.objects.create(code=code, nomPeriode=nom, statut=statut)

    def test_enseignant_can_open_encoder_notes(self):
        self.client.login(username="enseignant_test", password="pass1234")
        response = self.client.get(
            reverse("encoder_notes", args=[self.cours.idCours]),
            {"classe_id": self.classe.idClasse},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Français")
        self.assertContains(response, "EL001")

    def test_enseignant_can_save_notes(self):
        self.client.login(username="enseignant_test", password="pass1234")
        response = self.client.post(
            reverse("encoder_notes", args=[self.cours.idCours]) + f"?classe_id={self.classe.idClasse}",
            {
                "p1_EL001": "8",
                "p2_EL001": "7.5",
                "ex1_EL001": "15",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Cotes.objects.filter(eleve=self.eleve, cours=self.cours, periode__code="P1", note=8).exists())
        self.assertTrue(Cotes.objects.filter(eleve=self.eleve, cours=self.cours, periode__code="P2", note=7.5).exists())
        self.assertTrue(Cotes.objects.filter(eleve=self.eleve, cours=self.cours, periode__code="EX1", note=15).exists())

    def test_titulaire_can_open_print_bulletins(self):
        Cotes.objects.create(eleve=self.eleve, cours=self.cours, periode=Periode.objects.get(code="P1"), note=8)
        Cotes.objects.create(eleve=self.eleve, cours=self.cours, periode=Periode.objects.get(code="P2"), note=7)
        Cotes.objects.create(eleve=self.eleve, cours=self.cours, periode=Periode.objects.get(code="EX1"), note=14)

        self.client.login(username="titulaire_test", password="pass1234")
        response = self.client.post(
            reverse("imprimer_bulletins", args=[self.classe.idClasse]),
            {"eleves_selectionnes": [self.eleve.matriculeEleve]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulletin de")
        self.assertContains(response, "Français")
        self.assertContains(response, self.eleve.matriculeEleve)
