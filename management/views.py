from collections import defaultdict
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.utils import timezone

from .decorators import (
    comptable_required,
    eleve_required,
    enseignant_required,
    proviseur_required,
    titulaire_required,
)
from .models import (
    Attribution,
    CentralisationClasse,
    Classe,
    Cotes,
    Cours,
    DecisionJury,
    Eleve,
    Enseignant,
    FraisScolaire,
    Option,
    Paiement,
    Periode,
    PublicationResultats,
)
from .utils import (
    build_deliberation_classe,
    build_dict_cotes,
    build_ligne_bulletin,
    build_suivi_classe,
    calculer_moyenne_semestre,
    get_cours_classe,
    get_situation_financiere,
)


def get_bulletin_title(classe):
    nom_classe = (classe.nomClasse or "").strip()
    option_nom = (getattr(classe.option, "nomOption", "") or "").strip()
    type_label = (
        classe.get_type_bulletin_display()
        if hasattr(classe, "get_type_bulletin_display")
        else ""
    )

    nom_lower = nom_classe.lower()
    if nom_classe:
        if option_nom and option_nom.lower() not in nom_lower:
            return f"Bulletin de {nom_classe} {option_nom}"
        return f"Bulletin de {nom_classe}"

    if option_nom:
        return f"Bulletin de {option_nom}"

    if type_label:
        return f"Bulletin de {type_label}"

    return "Bulletin scolaire"


def home(request):
    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")
        role_choisi = request.POST.get("user_role")

        # 1. Authentification
        user = authenticate(request, username=u, password=p)

        # 2. Vérification si l'utilisateur existe
        if user is not None:
            # 3. Bloc de vérifications des rôles
            if role_choisi in ["eleve", "parent"]:
                if not Eleve.objects.filter(user=user).exists():
                    messages.error(request, "Accès refusé : Aucun profil Élève trouvé.")
                    return redirect("home")

            elif role_choisi == "enseignant":
                if not Enseignant.objects.filter(user=user).exists():
                    messages.error(
                        request, "Accès refusé : Aucun profil Enseignant trouvé."
                    )
                    return redirect("home")

            elif role_choisi == "titulaire":
                enseignant = Enseignant.objects.filter(user=user).first()
                if enseignant and not Classe.objects.filter(idEns=enseignant).exists():
                    messages.error(
                        request, "Accès refusé : Vous n'êtes titulaire d'aucune classe."
                    )
                    return redirect("home")

            elif role_choisi == "comptable":
                is_comptable = (
                    user.groups.filter(name="Comptable").exists()
                    or user.username.lower() == "comptable"
                )
                if not is_comptable:
                    messages.error(
                        request, "Accès refusé : Vous n'avez pas le rôle de Comptable."
                    )
                    return redirect("home")

            elif role_choisi == "admin":
                # Vérification : Est-ce un super-utilisateur OU fait-il partie du groupe 'Proviseur' ?
                # Vous pouvez vérifier le groupe ou simplement le nom d'utilisateur comme pour le comptable
                est_proviseur = (
                    user.is_superuser
                    or user.groups.filter(name="Proviseur").exists()
                    or user.username.lower() == "proviseur"
                )

                if not est_proviseur:
                    messages.error(
                        request,
                        "Accès refusé : Privilèges administratifs du Proviseur insuffisants.",
                    )
                    return redirect("home")

            # 4. Connexion réelle (CRUCIAL)
            login(request, user)
            request.session["role_actif"] = role_choisi

            # 5. Redirections après connexion réussie
            if user.is_superuser:
                return redirect("/admin/")

            if role_choisi in ["eleve", "parent"]:
                return redirect("dashboard_eleve")
            elif role_choisi == "comptable":
                return redirect("espace_comptable")
            elif role_choisi == "titulaire":
                return redirect("espace_titulaire")
            elif role_choisi == "enseignant":
                return redirect("espace_enseignant")
            elif role_choisi == "admin":
                return redirect("dashboard_proviseur")

            return redirect("home")

        else:
            # Si user est None (mot de passe ou username faux)
            messages.error(request, "Matricule ou mot de passe incorrect.")
            return redirect("home")

    return render(request, "management/home.html")


def deconnexion_utilisateur(request):
    logout(request)
    return redirect("home")


@eleve_required
def dashboard_eleve(request):
    eleve = get_object_or_404(Eleve, user=request.user)
    fin = get_situation_financiere(eleve)
    publication = PublicationResultats.get_instance()
    resultats_publies = publication.est_publiee

    paiements_liste = Paiement.objects.filter(eleve=eleve).order_by("-date")
    paiements_chronologiques = list(
        Paiement.objects.filter(eleve=eleve).order_by("date")
    )
    cumul_tracker = 0
    dict_cumuls = {}
    for p in paiements_chronologiques:
        cumul_tracker += p.montant
        dict_cumuls[p.id] = {
            "cumul_paye": cumul_tracker,
            "reste": max(0, fin["total_du"] - cumul_tracker),
        }

    paiements_avec_cumul = []
    for p in paiements_liste:
        valeurs = dict_cumuls.get(
            p.id, {"cumul_paye": fin["total_paye"], "reste": fin["reste_a_payer"]}
        )
        paiements_avec_cumul.append(
            {
                "instance": p,
                "numRecur": getattr(p, "numRecur", f"REC{p.id:03d}"),
                "date": p.date,
                "montant": p.montant,
                "cumul_paye": valeurs["cumul_paye"],
                "reste_a_payer_instant": valeurs["reste"],
            }
        )

    # On récupère strictement les cours rattachés à cette classe spécifique via la relation ManyToMany
    cours_eleve = Cours.objects.filter(classes=eleve.classe).select_related('max', 'domaine').distinct()
    dict_cotes = build_dict_cotes(eleve)

    # Récupération des statuts des périodes pour filtrer les alertes
    periodes_status = {p.code.upper(): p.statut for p in Periode.objects.all()}

    # Détection du S2 basée sur le dictionnaire déjà normalisé (évite les erreurs de casse DB)
    s2_codes = ["P3", "P4", "EX2"]
    has_notes_s2 = any(k.split('_')[-1] in s2_codes for k in dict_cotes.keys())
    is_s2_active = any(periodes_status.get(p) == 'ACTIVE' for p in s2_codes)
    
    afficher_s2 = has_notes_s2 or is_s2_active

    bulletin_s1 = []
    s1_toutes_cotes = True
    manquants_s1 = []
    bulletin_s2 = []
    s2_toutes_cotes = True
    manquants_s2 = []
    p_stats = {k: {'pts': 0, 'max': 0, 'complet': True} for k in ["P1", "P2", "EX1", "P3", "P4", "EX2"]}

    for c in cours_eleve:
        # --- TRAITEMENT SEMESTRE 1 ---
        p_data_s1, tot_s1, verd_s1, comp_s1 = build_ligne_bulletin(
            c, dict_cotes, fin, ["P1", "P2", "EX1"], resultats_publies
        )
        for p_code in ["P1", "P2", "EX1"]:
            raw_note = dict_cotes.get(f"{c.idCours}_{p_code}")
            if raw_note is not None:
                p_stats[p_code]['pts'] += float(raw_note)
                p_stats[p_code]['max'] += float(c.max.maxima * 2 if p_code.startswith('EX') else c.max.maxima)
            else:
                p_stats[p_code]['complet'] = False
                if periodes_status.get(p_code) == 'ACTIVE':
                    s1_toutes_cotes = False
                    manquants_s1.append(f"Vous manquez une cote sur : {c.libelle} ({p_code})")

        if any(p_data_s1[p]["existe"] for p in ["p1", "p2", "ex1"]):
            bulletin_s1.append({
                "cours": c, "p1": p_data_s1["p1"], "p2": p_data_s1["p2"], "ex1": p_data_s1["ex1"],
                "total_obtenu": tot_s1, "verdict": verd_s1,
            })

        # --- TRAITEMENT SEMESTRE 2 ---
        if afficher_s2:
            p_data_s2, tot_s2, verd_s2, comp_s2 = build_ligne_bulletin(
                c, dict_cotes, fin, ["P3", "P4", "EX2"], resultats_publies
            )
            for p_code in ["P3", "P4", "EX2"]:
                raw_note = dict_cotes.get(f"{c.idCours}_{p_code}")
                if raw_note is not None:
                    p_stats[p_code]['pts'] += float(raw_note)
                    p_stats[p_code]['max'] += float(c.max.maxima * 2 if p_code.startswith('EX') else c.max.maxima)
                else:
                    p_stats[p_code]['complet'] = False
                    if periodes_status.get(p_code) == 'ACTIVE':
                        s2_toutes_cotes = False
                        manquants_s2.append(f"Vous manquez une cote sur : {c.libelle} ({p_code})")

            if any(p_data_s2[p]["existe"] for p in ["p3", "p4", "ex2"]):
                bulletin_s2.append({
                    "cours": c, "p3": p_data_s2["p3"], "p4": p_data_s2["p4"], "ex2": p_data_s2["ex2"],
                    "total_obtenu": tot_s2, "verdict": verd_s2,
                })

    decision_jury = DecisionJury.objects.filter(
        eleve=eleve, classe=eleve.classe
    ).first()

    # Calcul final des pourcentages par période (DOIT ÊTRE FAIT AVANT LA LOGIQUE D'AFFICHAGE DYNAMIQUE)
    for s_info in p_stats.values():
        if s_info['max'] > 0:
            s_info['pct'] = round((s_info['pts'] / s_info['max'] * 100), 1)

    # --- LOGIQUE D'AFFICHAGE DYNAMIQUE (SEMESTRE 1) ---
    pts_s1_total = sum(p_stats[k]['pts'] for k in ["P1", "P2", "EX1"])
    max_s1_total = sum(p_stats[k]['max'] for k in ["P1", "P2", "EX1"])
    
    # Variables par défaut
    moy_s1_disp_pct, moy_s1_disp_pts, moy_s1_disp_max, moy_s1_label = 0, 0, 0, ""

    # Priorité : Moyenne Semestrielle (EX1 fini) -> P2 fini -> P1
    if p_stats['P1']['complet'] and p_stats['P2']['complet'] and p_stats['EX1']['complet'] and p_stats['EX1']['max'] > 0 and fin['acces_ex1']:
        moy_s1_disp_pct = round((pts_s1_total / max_s1_total * 100), 1)
        moy_s1_disp_pts, moy_s1_disp_max = pts_s1_total, max_s1_total
        moy_s1_label = "MOYENNE GÉNÉRALE S1"
    elif p_stats['P2']['complet'] and p_stats['P2']['max'] > 0 and fin['acces_p2']:
        moy_s1_disp_pct = p_stats['P2']['pct']
        moy_s1_disp_pts, moy_s1_disp_max = p_stats['P2']['pts'], p_stats['P2']['max']
        moy_s1_label = "POURCENTAGE P2"
    elif p_stats['P1']['complet'] and p_stats['P1']['max'] > 0 and fin['acces_p1']:
        moy_s1_disp_pct = p_stats['P1']['pct']
        moy_s1_disp_pts, moy_s1_disp_max = p_stats['P1']['pts'], p_stats['P1']['max']
        moy_s1_label = "POURCENTAGE P1"

    # --- LOGIQUE D'AFFICHAGE DYNAMIQUE (SEMESTRE 2) ---
    pts_s2_total = sum(p_stats[k]['pts'] for k in ["P3", "P4", "EX2"])
    max_s2_total = sum(p_stats[k]['max'] for k in ["P3", "P4", "EX2"])
    
    moy_s2_disp_pct, moy_s2_disp_pts, moy_s2_disp_max, moy_s2_label = 0, 0, 0, ""

    if p_stats['P3']['complet'] and p_stats['P4']['complet'] and p_stats['EX2']['complet'] and p_stats['EX2']['max'] > 0 and fin['acces_s2']:
        moy_s2_disp_pct = round((pts_s2_total / max_s2_total * 100), 1)
        moy_s2_disp_pts, moy_s2_disp_max = pts_s2_total, max_s2_total
        moy_s2_label = "MOYENNE GÉNÉRALE S2"
    elif p_stats['P4']['complet'] and p_stats['P4']['max'] > 0 and fin['acces_s2']:
        moy_s2_disp_pct = p_stats['P4']['pct']
        moy_s2_disp_pts, moy_s2_disp_max = p_stats['P4']['pts'], p_stats['P4']['max']
        moy_s2_label = "POURCENTAGE P4"
    elif p_stats['P3']['complet'] and p_stats['P3']['max'] > 0 and fin['acces_s2']:
        moy_s2_disp_pct = p_stats['P3']['pct']
        moy_s2_disp_pts, moy_s2_disp_max = p_stats['P3']['pts'], p_stats['P3']['max']
        moy_s2_label = "POURCENTAGE P3"

    s1_complet = s1_toutes_cotes
    s2_complet = s2_toutes_cotes

    context = {
        "eleve": eleve,
        "paiements": paiements_avec_cumul,
        "total_paye": fin["total_paye"],
        "total_du": fin["total_du"],
        "reste_a_payer": fin["reste_a_payer"],
        "bulletin_s1": bulletin_s1,
        "bulletin_s2": bulletin_s2,
        "afficher_s2": afficher_s2,
        "s1_toutes_cotes": s1_toutes_cotes,
        "s2_toutes_cotes": s2_toutes_cotes,
        "autorise_p1": fin["acces_p1"] and resultats_publies,
        "autorise_p2": fin["acces_p2"] and resultats_publies,
        "autorise_ex1": fin["acces_ex1"] and resultats_publies,
        "autorise_s2": fin["acces_s2"] and resultats_publies,
        "resultats_publies": resultats_publies,
        "decision_jury": decision_jury,
        "moy_s1_pct": moy_s1_disp_pct,
        "moy_s1_pts": moy_s1_disp_pts,
        "moy_s1_max": moy_s1_disp_max,
        "moy_s1_label": moy_s1_label,
        "s1_complet": s1_complet,
        "moy_s2_pct": moy_s2_disp_pct,
        "moy_s2_pts": moy_s2_disp_pts,
        "moy_s2_max": moy_s2_disp_max,
        "moy_s2_label": moy_s2_label,
        "s2_complet": s2_complet,
        "p_stats": p_stats,
        "manquants_s1": manquants_s1,
        "manquants_s2": manquants_s2,
    }
    return render(request, "management/dashboard_eleve.html", context)


@comptable_required
def espace_comptable(request):
    eleves = (
        Eleve.objects.select_related("classe", "classe__option").all().order_by("nom")
    )
    frais_liste = FraisScolaire.objects.all()
    paiements = Paiement.objects.select_related(
        "eleve", "eleve__classe", "frais_type"
    ).order_by("-date")
    recherche_paiement = request.GET.get("recherche_paiement", "").strip()
    if recherche_paiement:
        paiements = paiements.filter(
            Q(numRecur__icontains=recherche_paiement)
            | Q(eleve__matriculeEleve__icontains=recherche_paiement)
            | Q(eleve__nom__icontains=recherche_paiement)
            | Q(eleve__postnom__icontains=recherche_paiement)
            | Q(eleve__prenom__icontains=recherche_paiement)
        )
    classes_existantes = Classe.objects.all().order_by("nomClasse")
    options_existantes = Option.objects.all().order_by("idOption")

    if request.method == "POST":
        if "configurer_frais" in request.POST:
            typeFrs = request.POST.get("typeFrs")
            montant = request.POST.get("montant_du")
            classe_choisie = request.POST.get("classe")
            option_choisie = request.POST.get("option")

            FraisScolaire.objects.create(
                typeFrs=typeFrs,
                montant=montant,
                classe=classe_choisie if classe_choisie != "" else None,
                option=option_choisie if option_choisie != "" else None,
            )
            messages.success(request, "Nouveau montant dû configuré avec succès !")
            return redirect("espace_comptable")

        elif "modifier_frais" in request.POST:
            frais_id = request.POST.get("frais_id")
            frais = FraisScolaire.objects.get(id=frais_id)
            frais.typeFrs = request.POST.get("typeFrs")
            frais.montant = request.POST.get("montant_du")
            frais.classe = (
                request.POST.get("classe") if request.POST.get("classe") != "" else None
            )
            frais.option = (
                request.POST.get("option") if request.POST.get("option") != "" else None
            )
            frais.save()
            messages.success(request, f"Le tarif '{frais.typeFrs}' a été mis à jour !")
            return redirect("espace_comptable")

        elif "enregistrer_paiement" in request.POST:
            matricule = request.POST.get("matricule")
            frais_id = request.POST.get("frais_id")
            numRecur = request.POST.get("numRecur")
            montant_verse = request.POST.get("montant")

            eleve = Eleve.objects.get(matriculeEleve=matricule)
            frais = FraisScolaire.objects.get(id=frais_id)

            Paiement.objects.create(
                eleve=eleve, frais_type=frais, numRecur=numRecur, montant=montant_verse
            )
            messages.success(
                request,
                f"Versement de {montant_verse}$ enregistré avec succès pour {eleve.nom} !",
            )
            return redirect("espace_comptable")

    context = {
        "eleves": eleves,
        "frais_liste": frais_liste,
        "paiements": paiements,
        "recherche_paiement": recherche_paiement,
        "classes_existantes": classes_existantes,
        "options_existantes": options_existantes,
    }
    return render(request, "management/espace_comptable.html", context)


@proviseur_required
def dashboard_proviseur(request):
    # --- 1. TRAITEMENTS POST ---

    # A. Attribution des cours
    if request.method == "POST" and "attribuer_cours" in request.POST:
        enseignant_id = request.POST.get("enseignant_id")
        cours_id = request.POST.get("cours_id")
        classe_id = request.POST.get("classe_id")

        classe_obj = get_object_or_404(Classe, pk=classe_id)
        cours_obj = get_object_or_404(Cours, idCours=cours_id)

        # On récupère ou crée l'attribution pour (Cours + Classe)
        attribution, created = Attribution.objects.get_or_create(
            cours=cours_obj, classe=classe_obj
        )

        if enseignant_id == "retirer":
            attribution.enseignant = None
        else:
            enseignant_obj = get_object_or_404(Enseignant, idEns=enseignant_id)
            attribution.enseignant = enseignant_obj
        attribution.save()

        messages.success(request, f"Attribution mise à jour pour {cours_obj.libelle}")
        return redirect(
            f"/management/proviseur/?classe_id={classe_id}#attribution-panel"
        )

    # B. Gestion des statuts de la Période
    if request.method == "POST" and "action_periode" in request.POST:
        periode_id = request.POST.get("periode_id")
        nouveau_statut = request.POST.get("statut")
        periode_obj = get_object_or_404(Periode, idPeriode=periode_id)
        periode_obj.statut = nouveau_statut
        periode_obj.save()
        messages.success(request, f"Période {periode_obj.nomPeriode} mise à jour.")
        return redirect("/management/proviseur/#periode-panel")

    # C. Publication / retrait des résultats
    if request.method == "POST" and "action_publication" in request.POST:
        publication = PublicationResultats.get_instance()
        if request.POST.get("action_publication") == "publier":
            publication.est_publiee = True
            publication.date_publication = timezone.now()
            publication.publie_par = request.user
            publication.save()
            messages.success(
                request,
                "Les résultats sont maintenant publiés. Les élèves peuvent les consulter selon leur situation financière.",
            )
        else:
            publication.est_publiee = False
            publication.save()
            messages.warning(
                request,
                "Publication des résultats retirée. Les élèves ne peuvent plus voir leurs notes.",
            )
        return redirect("/management/proviseur/#deliberation-panel")

    # D. Décision du jury
    if request.method == "POST" and "decision_jury" in request.POST:
        matricule = request.POST.get("matricule_eleve")
        classe_id = request.POST.get("classe_id")
        decision = request.POST.get("decision")
        commentaire = request.POST.get("commentaire", "")
        eleve_obj = get_object_or_404(Eleve, matriculeEleve=matricule)
        classe_obj = get_object_or_404(Classe, pk=classe_id)
        DecisionJury.objects.update_or_create(
            eleve=eleve_obj,
            classe=classe_obj,
            defaults={"decision": decision, "commentaire": commentaire},
        )
        messages.success(
            request, f"Décision enregistrée pour {eleve_obj.nom} {eleve_obj.postnom}."
        )
        return redirect(
            f"/management/proviseur/?classe_delib={classe_id}#deliberation-panel"
        )

    # --- 2. TRAITEMENT GET (Données) ---
    toutes_les_classes = Classe.objects.all()
    tous_enseignants = Enseignant.objects.all().order_by("nom")
    periodes = Periode.objects.all().order_by("idPeriode")
    publication = PublicationResultats.get_instance()
    fiches_soumises = CentralisationClasse.objects.select_related(
        "classe", "titulaire"
    ).order_by("-date_soumission")
    fiches_avec_suivi = [
        {"fiche": f, "suivi": build_suivi_classe(f.classe)} for f in fiches_soumises
    ]

    classe_id = request.GET.get("classe_id")
    classe_sel = (
        toutes_les_classes.filter(pk=classe_id).first()
        if classe_id
        else toutes_les_classes.first()
    )

    classe_delib_id = request.GET.get("classe_delib")
    classe_delib = (
        toutes_les_classes.filter(pk=classe_delib_id).first()
        if classe_delib_id
        else classe_sel
    )

    deliberation_data = None
    decisions_map = {}
    if classe_delib:
        deliberation_data = build_deliberation_classe(classe_delib)
        decisions = DecisionJury.objects.filter(classe=classe_delib)
        decisions_map = {d.eleve_id: d for d in decisions}
        for ligne in deliberation_data["lignes"]:
            ligne["decision_jury"] = decisions_map.get(ligne["eleve"].matriculeEleve)

    cours_de_la_classe = []
    if classe_sel:
        # On récupère tous les cours
        cours_de_la_classe = Cours.objects.filter(classes=classe_sel)
        # On attache l'enseignant trouvé dans Attribution à chaque cours
        for cours in cours_de_la_classe:
            attr = Attribution.objects.filter(classe=classe_sel, cours=cours).first()
            cours.enseignant_actuel = attr.enseignant if attr else None

    context = {
        "liste_classes_global": toutes_les_classes,
        "liste_enseignants_global": tous_enseignants,
        "classe_selectionnee": classe_sel,
        "classe_delib": classe_delib,
        "cours_de_la_classe": cours_de_la_classe,
        "periodes": periodes,
        "total_eleves": Eleve.objects.count(),
        "total_enseignants": tous_enseignants.count(),
        "total_classes": toutes_les_classes.count(),
        "total_options": Option.objects.count(),
        "fiches_soumises": fiches_soumises,
        "fiches_avec_suivi": fiches_avec_suivi,
        "publication": publication,
        "deliberation_data": deliberation_data,
        "decisions_jury_choices": DecisionJury.DECISION_CHOICES,
    }
    return render(request, "management/dashboard_proviseur.html", context)


@proviseur_required
def valider_fiche_proviseur(request, fiche_id):
    fiche = get_object_or_404(CentralisationClasse, pk=fiche_id)
    if request.method == "POST":
        fiche.feedback_proviseur = request.POST.get("feedback_proviseur", "").strip()
        fiche.est_valide = True
        fiche.date_validation = timezone.now()
        fiche.save()
        messages.success(
            request,
            f"La centralisation de {fiche.classe.nomClasse} a été validée. Le titulaire recevra votre retour.",
        )
        return redirect("/management/proviseur/#validation-panel")
    fiche.est_valide = True
    fiche.date_validation = timezone.now()
    fiche.save()
    messages.success(
        request, f"La fiche de cotes de {fiche.classe.nomClasse} a été validée."
    )
    return redirect("dashboard_proviseur")


@titulaire_required
def espace_titulaire(request):
    # 1. Identification de l'enseignant
    enseignant = Enseignant.objects.filter(user=request.user).first()
    if not enseignant:
        messages.error(request, "Erreur : Profil enseignant non trouvé.")
        return redirect("home")

    # 2. Identification de la classe titulaire
    classe_titulaire = Classe.objects.filter(idEns=enseignant).first()
    if not classe_titulaire:
        messages.error(request, f"Vous n'êtes titulaire d'aucune classe.")
        return redirect("home")

    suivi_data = build_suivi_classe(classe_titulaire)
    suivi_eleves = suivi_data["suivi_eleves"]
    nombre_total_cours = suivi_data["nombre_total_cours"]

    centralisation = CentralisationClasse.objects.filter(
        classe=classe_titulaire
    ).first()

    if request.method == "POST" and "valider_et_soumettre" in request.POST:
        obj, _ = CentralisationClasse.objects.update_or_create(
            classe=classe_titulaire,
            defaults={
                "titulaire": enseignant,
                "est_valide": False,
                "feedback_proviseur": "",
                "date_validation": None,
            },
        )
        obj.date_soumission = timezone.now()
        obj.save(update_fields=["date_soumission"])
        messages.success(
            request, "Les points ont été centralisés et soumis au Proviseur."
        )
        return redirect("espace_titulaire")
    cours_classe = get_cours_classe(classe_titulaire)
    attributions_classe = list(
        Attribution.objects.filter(classe=classe_titulaire)
        .select_related("cours", "enseignant")
        .order_by("cours__libelle")
    )
    if not attributions_classe:
        for cours in cours_classe:
            attributions_classe.append(
                SimpleNamespace(cours=cours, enseignant=cours.enseignant)
            )

    context = {
        "enseignant": enseignant,
        "classe": classe_titulaire,
        "suivi_eleves": suivi_eleves,
        "nombre_total_cours": nombre_total_cours,
        "liste_eleves": Eleve.objects.filter(classe=classe_titulaire).order_by(
            "nom", "postnom"
        ),
        "attributions_classe": attributions_classe,
        "centralisation": centralisation,
    }
    return render(request, "management/espace_titulaire.html", context)


@enseignant_required
def espace_enseignant(request):
    enseignant_connecte = Enseignant.objects.filter(user=request.user).first()

    if not enseignant_connecte:
        return render(
            request,
            "management/erreur_profil.html",
            {
                "message": "Votre compte utilisateur n'est pas lié à un profil Enseignant."
            },
        )

    # On s'assure de bien récupérer tout ce dont on a besoin
    mes_attributions = Attribution.objects.filter(
        enseignant=enseignant_connecte
    ).select_related("cours", "classe")

    charges_par_cours = {}
    for attr in mes_attributions.order_by("cours__libelle", "classe__nomClasse"):
        cid = attr.cours.idCours
        if cid not in charges_par_cours:
            charges_par_cours[cid] = {
                "cours": attr.cours,
                "attributions": [],
                "classes_labels": [],
            }

        charges_par_cours[cid]["attributions"].append(attr)

        # Label de classe (nom + option si disponible)
        option_nom = ""
        if getattr(attr.classe, "option", None) is not None:
            option_nom = getattr(attr.classe.option, "nomOption", "") or ""

        label = (
            f"{attr.classe.nomClasse}{(' - ' + option_nom) if option_nom else ''}"
        ).strip()

        charges_par_cours[cid]["classes_labels"].append(label)

    # Dédup + tri stable
    for item in charges_par_cours.values():
        item["classes_labels"] = sorted(set(item["classes_labels"]))

    charges_groupees = list(charges_par_cours.values())

    return render(
        request,
        "management/espace_enseignant.html",
        {
            "charges_groupees": charges_groupees,
            "enseignant": enseignant_connecte,
        },
    )
@enseignant_required
def encoder_notes(request, cours_id):
    enseignant_connecte = get_object_or_404(Enseignant, user=request.user)
    cours_obj = get_object_or_404(Cours, idCours=cours_id)

    classe_id = request.GET.get('classe_id')
    classe_selectionnee = None

    if classe_id:
        classe_selectionnee = get_object_or_404(Classe, pk=classe_id)
        get_object_or_404(Attribution, enseignant=enseignant_connecte, cours=cours_obj, classe=classe_selectionnee)
    else:
        attributions = Attribution.objects.filter(enseignant=enseignant_connecte, cours=cours_obj)
        if not attributions.exists():
            return render(request, 'management/erreur_profil.html', 
                          {'message': "Vous n'êtes pas autorisé à accéder à ce cours."})

    periodes_bdd = Periode.objects.all().order_by('idPeriode')
    periodes_actives = {p.code.upper(): p for p in periodes_bdd if p.statut == 'ACTIVE'}

    max_p = getattr(cours_obj.max, 'maxima', 10.0) if cours_obj.max else 10.0
    max_ex = max_p * 2

    eleves_avec_cotes = []
    if classe_selectionnee:
        eleves = Eleve.objects.filter(classe=classe_selectionnee).order_by('nom', 'postnom')
        for eleve in eleves:
            cotes_dict = {}
            for periode in periodes_bdd:
                cote_obj, _ = Cotes.objects.get_or_create(eleve=eleve, cours=cours_obj, periode=periode)
                # Clé normalisée en majuscule
                key = periode.code.upper()
                cotes_dict[key] = cote_obj
            eleves_avec_cotes.append({'eleve': eleve, 'cotes': cotes_dict})

    if request.method == 'POST' and classe_selectionnee:
        # ... (votre code POST est déjà correct, je le garde identique)
        erreurs = []
        sauvegarde_effectuee = False

        for item in eleves_avec_cotes:
            eleve = item['eleve']
            for code, cote_obj in item['cotes'].items():
                if code not in periodes_actives:
                    continue
                input_name = f"{code.lower()}_{eleve.pk}"
                valeur = request.POST.get(input_name)
                max_note = max_ex if 'EX' in code else max_p
                if valeur is None or valeur.strip() == '':
                    if cote_obj.note is not None:
                        cote_obj.note = None
                        cote_obj.save(update_fields=['note'])
                        sauvegarde_effectuee = True
                else:
                    try:
                        note = float(valeur.replace(',', '.'))
                        if 0 <= note <= max_note:
                            if cote_obj.note != note:
                                cote_obj.note = note
                                cote_obj.save(update_fields=['note'])
                                sauvegarde_effectuee = True
                        else:
                            erreurs.append(f"{eleve.nom} {eleve.postnom} - {code} : {note} hors limites (0-{max_note})")
                    except ValueError:
                        erreurs.append(f"{eleve.nom} {eleve.postnom} - {code} : '{valeur}' invalide")
        for err in erreurs:
            messages.error(request, err)
        if sauvegarde_effectuee and not erreurs:
            messages.success(request, "Notes enregistrées avec succès.")
        elif not sauvegarde_effectuee and not erreurs:
            messages.info(request, "Aucune modification détectée.")
        return redirect(f"{request.path}?classe_id={classe_id}")

    classes_concernees = [attr.classe for attr in Attribution.objects.filter(enseignant=enseignant_connecte, cours=cours_obj)]

    context = {
        'cours': cours_obj,
        'classes': classes_concernees,
        'classe_selectionnee': classe_selectionnee,
        'eleves_avec_cotes': eleves_avec_cotes,
        'periodes': periodes_bdd,
        'max_p': max_p,
        'max_ex': max_ex,
    }
    return render(request, 'management/fiche_cote.html', context)

@titulaire_required
def imprimer_bulletins(request, classe_id):
    """
    Génère les bulletins scolaires avec calculs automatiques des totaux, moyennes et appréciations.
    """
    enseignant = get_object_or_404(Enseignant, user=request.user)
    classe = get_object_or_404(Classe, pk=classe_id, idEns=enseignant)

    eleve_ids = request.POST.getlist("eleves_selectionnes")

    if eleve_ids:
        eleves = Eleve.objects.filter(
            classe=classe, matriculeEleve__in=eleve_ids
        ).order_by("nom", "postnom")
    else:
        eleves = Eleve.objects.filter(classe=classe).order_by("nom", "postnom")

    cours_de_la_classe = list(
        Cours.objects.filter(classes=classe)
        .select_related("max", "domaine")
        .order_by("domaine__ordre", "domaine__nom", "libelle")
    )

    bulletin_structure = []
    domaine_groups = defaultdict(list)
    for cours in cours_de_la_classe:
        domaine_nom = cours.domaine.nom if cours.domaine else "AUTRES"
        domaine_groups[domaine_nom].append(cours)

    for domaine_nom, cours_items in domaine_groups.items():
        bulletin_structure.append(
            {
                "type": "domaine",
                "label": domaine_nom.upper(),
                "cours": cours_items,
            }
        )

    ranking_data = []
    bulletins = []

    for eleve in eleves:
        cotes_elev = Cotes.objects.filter(eleve=eleve).select_related(
            "cours", "periode"
        )
        dict_cotes = {}
        for cote in cotes_elev:
            if cote.note is not None:
                dict_cotes[(cote.cours.idCours, cote.periode.code)] = cote.note

        lignes = []
        total_s1_points = 0
        total_s1_max = 0
        total_s2_points = 0
        total_s2_max = 0
        total_general_points = 0
        total_general_max = 0

        for bloc in bulletin_structure:
            lignes.append({"type": "domaine", "label": bloc["label"]})
            sous_total = {
                "max_p": 0,
                "max_ex": 0,
                "s1_total_max": 0,
                "s2_total_max": 0,
                "total_general_max": 0,
                "p1_points": 0,
                "p2_points": 0,
                "ex1_points": 0,
                "p3_points": 0,
                "p4_points": 0,
                "ex2_points": 0,
                "s1_points": 0,
                "s2_points": 0,
                "total_points": 0,
            }

            for cours in bloc["cours"]:
                max_p = cours.max.maxima
                max_ex = max_p * 2

                p1 = dict_cotes.get((cours.idCours, "P1"))
                p2 = dict_cotes.get((cours.idCours, "P2"))
                ex1 = dict_cotes.get((cours.idCours, "EX1"))
                p3 = dict_cotes.get((cours.idCours, "P3"))
                p4 = dict_cotes.get((cours.idCours, "P4"))
                ex2 = dict_cotes.get((cours.idCours, "EX2"))

                p1_points = p1 if p1 is not None else 0
                p2_points = p2 if p2 is not None else 0
                ex1_points = ex1 if ex1 is not None else 0
                p3_points = p3 if p3 is not None else 0
                p4_points = p4 if p4 is not None else 0
                ex2_points = ex2 if ex2 is not None else 0

                s1_points = p1_points + p2_points + ex1_points
                s2_points = p3_points + p4_points + ex2_points
                total_points = s1_points + s2_points

                s1_total_max = (max_p * 2) + max_ex
                s2_total_max = (max_p * 2) + max_ex
                total_cours_max = s1_total_max + s2_total_max

                total_s1_points += s1_points
                total_s1_max += s1_total_max
                total_s2_points += s2_points
                total_s2_max += s2_total_max
                total_general_points += total_points
                total_general_max += total_cours_max

                sous_total["max_p"] += max_p
                sous_total["max_ex"] += max_ex
                sous_total["s1_total_max"] += s1_total_max
                sous_total["s2_total_max"] += s2_total_max
                sous_total["total_general_max"] += total_cours_max
                sous_total["p1_points"] += p1_points
                sous_total["p2_points"] += p2_points
                sous_total["ex1_points"] += ex1_points
                sous_total["p3_points"] += p3_points
                sous_total["p4_points"] += p4_points
                sous_total["ex2_points"] += ex2_points
                sous_total["s1_points"] += s1_points
                sous_total["s2_points"] += s2_points
                sous_total["total_points"] += total_points

                lignes.append(
                    {
                        "type": "cours",
                        "label": cours.libelle,
                        "max_p": max_p,
                        "max_ex": max_ex,
                        "s1_total_max": s1_total_max,
                        "s2_total_max": s2_total_max,
                        "total_general_max": total_cours_max,
                        "p1": p1,
                        "p2": p2,
                        "ex1": ex1,
                        "p3": p3,
                        "p4": p4,
                        "ex2": ex2,
                        "p1_points": p1_points,
                        "p2_points": p2_points,
                        "ex1_points": ex1_points,
                        "p3_points": p3_points,
                        "p4_points": p4_points,
                        "ex2_points": ex2_points,
                        "s1_points": s1_points,
                        "s2_points": s2_points,
                        "total_points": total_points,
                        "pct_p1": round((p1_points / max_p) * 100, 1)
                        if p1 is not None and max_p
                        else None,
                        "pct_p2": round((p2_points / max_p) * 100, 1)
                        if p2 is not None and max_p
                        else None,
                        "pct_ex1": round((ex1_points / max_ex) * 100, 1)
                        if ex1 is not None and max_ex
                        else None,
                        "pct_p3": round((p3_points / max_p) * 100, 1)
                        if p3 is not None and max_p
                        else None,
                        "pct_p4": round((p4_points / max_p) * 100, 1)
                        if p4 is not None and max_p
                        else None,
                        "pct_ex2": round((ex2_points / max_ex) * 100, 1)
                        if ex2 is not None and max_ex
                        else None,
                        "pct_s1": round((s1_points / s1_total_max) * 100, 1)
                        if s1_total_max
                        else None,
                        "pct_s2": round((s2_points / s2_total_max) * 100, 1)
                        if s2_total_max
                        else None,
                    }
                )

            lignes.append(
                {
                    "type": "subtotal",
                    "label": "Sous - Total",
                    **sous_total,
                    "pct_s1": round(
                        (sous_total["s1_points"] / sous_total["s1_total_max"]) * 100, 1
                    )
                    if sous_total["s1_total_max"]
                    else None,
                    "pct_s2": round(
                        (sous_total["s2_points"] / sous_total["s2_total_max"]) * 100, 1
                    )
                    if sous_total["s2_total_max"]
                    else None,
                }
            )

        moyenne_generale = (
            round((total_general_points / total_general_max) * 100, 1)
            if total_general_max
            else None
        )
        ranking_data.append(
            {
                "eleve_id": eleve.matriculeEleve,
                "points": total_general_points,
                "moyenne": moyenne_generale or 0,
            }
        )

        decision = DecisionJury.objects.filter(eleve=eleve, classe=classe).first()
        decision_label = (
            decision.get_decision_display()
            if decision and decision.decision != "EN_ATTENTE"
            else ""
        )
        apprec_general = ""
        if moyenne_generale is not None:
            if moyenne_generale >= 80:
                apprec_general = "Félicitations du Jury"
            elif moyenne_generale >= 70:
                apprec_general = "Grande Distinction"
            elif moyenne_generale >= 60:
                apprec_general = "Distinction"
            elif moyenne_generale >= 50:
                apprec_general = "Satisfaction"
            elif moyenne_generale >= 40:
                apprec_general = "Réservé"
            else:
                apprec_general = "Échec"

        bulletins.append(
            {
                "eleve": eleve,
                "lignes": lignes,
                "total_s1_points": total_s1_points,
                "total_s1_max": total_s1_max,
                "total_s2_points": total_s2_points,
                "total_s2_max": total_s2_max,
                "total_points": total_general_points,
                "total_max": total_general_max,
                "pct_s1": round((total_s1_points / total_s1_max) * 100, 1)
                if total_s1_max
                else None,
                "pct_s2": round((total_s2_points / total_s2_max) * 100, 1)
                if total_s2_max
                else None,
                "moy_general": f"{moyenne_generale:.1f}%"
                if moyenne_generale is not None
                else "-",
                "moy_general_value": moyenne_generale,
                "apprec_general": apprec_general,
                "decision_jury": decision_label,
            }
        )

    ranking_sorted = sorted(
        ranking_data,
        key=lambda item: (-item["points"], -item["moyenne"], item["eleve_id"]),
    )
    rank_map = {
        item["eleve_id"]: index + 1 for index, item in enumerate(ranking_sorted)
    }
    total_eleves = len(ranking_sorted)

    for bulletin in bulletins:
        bulletin["rang"] = rank_map.get(bulletin["eleve"].matriculeEleve)
        bulletin["effectif"] = total_eleves

    context = {
        "bulletins": bulletins,
        "classe": classe,
        "annee_scolaire": classe.annee,
        "bulletin_title": get_bulletin_title(classe),
    }

    template_names = [
        f"bulletins/bulletin_{classe.type_bulletin}.html",
        "bulletins/bulletin_co.html",
    ]

    for template_name in template_names:
        try:
            return render(request, template_name, context)
        except TemplateDoesNotExist:
            continue

    return render(request, "bulletins/bulletin_co.html", context)
