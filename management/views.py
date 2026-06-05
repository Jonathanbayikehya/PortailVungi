from django.contrib.auth.decorators import login_required
from django import template
register = template.Library()
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q, Count, Sum
from django.template import TemplateDoesNotExist
from django.utils import timezone
from types import SimpleNamespace
from .models import (
    Eleve, Enseignant, Classe, Paiement, FraisScolaire, Option, Cours, Periode, Cotes,
    Attribution, CentralisationClasse, PublicationResultats, DecisionJury,
)
from .utils import (
    get_situation_financiere, get_cours_classe, build_dict_cotes,
    build_ligne_bulletin, build_deliberation_classe, build_suivi_classe,
    calculer_moyenne_semestre,
)

def home(request):
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        role_choisi = request.POST.get('user_role')

        # 1. Authentification
        user = authenticate(request, username=u, password=p)
        
        # 2. Vérification si l'utilisateur existe
        if user is not None:
            
            # 3. Bloc de vérifications des rôles
            if role_choisi in ['eleve', 'parent']:
                if not Eleve.objects.filter(user=user).exists():
                    messages.error(request, "Accès refusé : Aucun profil Élève trouvé.")
                    return redirect('home')

            elif role_choisi == 'enseignant':
                if not Enseignant.objects.filter(user=user).exists():
                    messages.error(request, "Accès refusé : Aucun profil Enseignant trouvé.")
                    return redirect('home')

            elif role_choisi == 'titulaire':
                enseignant = Enseignant.objects.filter(user=user).first()
                if enseignant and not Classe.objects.filter(idEns=enseignant).exists():
                    messages.error(request, "Accès refusé : Vous n'êtes titulaire d'aucune classe.")
                    return redirect('home')

            elif role_choisi == 'comptable':
                is_comptable = user.groups.filter(name='Comptable').exists() or user.username.lower() == 'comptable'
                if not is_comptable:
                    messages.error(request, "Accès refusé : Vous n'avez pas le rôle de Comptable.")
                    return redirect('home')

            elif role_choisi == 'admin':
                # Vérification : Est-ce un super-utilisateur OU fait-il partie du groupe 'Proviseur' ?
                # Vous pouvez vérifier le groupe ou simplement le nom d'utilisateur comme pour le comptable
                est_proviseur = user.is_superuser or user.groups.filter(name='Proviseur').exists() or user.username.lower() == 'proviseur'
                
                if not est_proviseur:
                    messages.error(request, "Accès refusé : Privilèges administratifs du Proviseur insuffisants.")
                    return redirect('home')

            # 4. Connexion réelle (CRUCIAL)
            login(request, user)
            request.session['role_actif'] = role_choisi

            # 5. Redirections après connexion réussie
            if user.is_superuser:
                return redirect('/admin/')
            
            if role_choisi in ['eleve', 'parent']:
                return redirect('dashboard_eleve')
            elif role_choisi == 'comptable':
                return redirect('espace_comptable')
            elif role_choisi == 'titulaire':
                return redirect('espace_titulaire')
            elif role_choisi == 'enseignant':
                return redirect('espace_enseignant')
            elif role_choisi == 'admin':
                return redirect('dashboard_proviseur')
                
            return redirect('home')
            
        else:
            # Si user est None (mot de passe ou username faux)
            messages.error(request, "Matricule ou mot de passe incorrect.")
            return redirect('home')

    return render(request, 'management/home.html')


def deconnexion_utilisateur(request):
    logout(request)
    return redirect('home')


@login_required
def dashboard_eleve(request):
    eleve = get_object_or_404(Eleve, user=request.user)
    fin = get_situation_financiere(eleve)
    publication = PublicationResultats.get_instance()
    resultats_publies = publication.est_publiee

    paiements_liste = Paiement.objects.filter(eleve=eleve).order_by('-date')
    paiements_chronologiques = list(Paiement.objects.filter(eleve=eleve).order_by('date'))
    cumul_tracker = 0
    dict_cumuls = {}
    for p in paiements_chronologiques:
        cumul_tracker += p.montant
        dict_cumuls[p.id] = {
            'cumul_paye': cumul_tracker,
            'reste': max(0, fin['total_du'] - cumul_tracker),
        }

    paiements_avec_cumul = []
    for p in paiements_liste:
        valeurs = dict_cumuls.get(p.id, {'cumul_paye': fin['total_paye'], 'reste': fin['reste_a_payer']})
        paiements_avec_cumul.append({
            'instance': p,
            'numRecur': getattr(p, 'numRecur', f"REC{p.id:03d}"),
            'date': p.date,
            'montant': p.montant,
            'cumul_paye': valeurs['cumul_paye'],
            'reste_a_payer_instant': valeurs['reste'],
        })

    cours_eleve = get_cours_classe(eleve.classe)
    dict_cotes = build_dict_cotes(eleve)
    afficher_s2 = Cotes.objects.filter(
        eleve=eleve, periode__code__in=['P3', 'P4', 'EX2'], note__isnull=False
    ).exists()

    bulletin_s1 = []
    s1_toutes_cotes = True
    for c in cours_eleve:
        periodes_data, total_affiche, verdict, complet = build_ligne_bulletin(
            c, dict_cotes, fin, ['P1', 'P2', 'EX1'], resultats_publies
        )
        if not complet:
            s1_toutes_cotes = False
        if any(periodes_data[p]['existe'] for p in ['p1', 'p2', 'ex1']):
            bulletin_s1.append({
                'cours': c,
                'p1': periodes_data['p1'],
                'p2': periodes_data['p2'],
                'ex1': periodes_data['ex1'],
                'total_obtenu': total_affiche,
                'verdict': verdict,
            })

    bulletin_s2 = []
    s2_toutes_cotes = True
    if afficher_s2:
        for c in cours_eleve:
            periodes_data, total_affiche, verdict, complet = build_ligne_bulletin(
                c, dict_cotes, fin, ['P3', 'P4', 'EX2'], resultats_publies
            )
            if not complet:
                s2_toutes_cotes = False
            if any(periodes_data[p]['existe'] for p in ['p3', 'p4', 'ex2']):
                bulletin_s2.append({
                    'cours': c,
                    'p3': periodes_data['p3'],
                    'p4': periodes_data['p4'],
                    'ex2': periodes_data['ex2'],
                    'total_obtenu': total_affiche,
                    'verdict': verdict,
                })

    decision_jury = DecisionJury.objects.filter(eleve=eleve, classe=eleve.classe).first()

    moy_s1_pct, moy_s1_pts, moy_s1_max, s1_complet = calculer_moyenne_semestre(eleve, ['P1', 'P2', 'EX1'])
    moy_s2_pct, moy_s2_pts, moy_s2_max, s2_complet = calculer_moyenne_semestre(eleve, ['P3', 'P4', 'EX2'])

    context = {
        'eleve': eleve,
        'paiements': paiements_avec_cumul,
        'total_paye': fin['total_paye'],
        'total_du': fin['total_du'],
        'reste_a_payer': fin['reste_a_payer'],
        'bulletin_s1': bulletin_s1,
        'bulletin_s2': bulletin_s2,
        'afficher_s2': afficher_s2,
        's1_toutes_cotes': s1_toutes_cotes,
        's2_toutes_cotes': s2_toutes_cotes,
        'autorise_p1': fin['acces_p1'] and resultats_publies,
        'autorise_p2': fin['acces_p2'] and resultats_publies,
        'autorise_ex1': fin['acces_ex1'] and resultats_publies,
        'autorise_s2': fin['acces_s2'] and resultats_publies,
        'resultats_publies': resultats_publies,
        'decision_jury': decision_jury,
        'moy_s1_pct': moy_s1_pct,
        'moy_s1_pts': moy_s1_pts,
        'moy_s1_max': moy_s1_max,
        's1_complet': s1_complet,
        'moy_s2_pct': moy_s2_pct,
        'moy_s2_pts': moy_s2_pts,
        'moy_s2_max': moy_s2_max,
        's2_complet': s2_complet,
    }
    return render(request, 'management/dashboard_eleve.html', context)


@login_required
def espace_comptable(request):
    eleves = Eleve.objects.select_related('classe', 'classe__option').all().order_by('nom')
    frais_liste = FraisScolaire.objects.all()
    paiements = Paiement.objects.select_related('eleve', 'eleve__classe', 'frais_type').order_by('-date')
    recherche_paiement = request.GET.get('recherche_paiement', '').strip()
    if recherche_paiement:
        paiements = paiements.filter(
            Q(numRecur__icontains=recherche_paiement) |
            Q(eleve__matriculeEleve__icontains=recherche_paiement) |
            Q(eleve__nom__icontains=recherche_paiement) |
            Q(eleve__postnom__icontains=recherche_paiement) |
            Q(eleve__prenom__icontains=recherche_paiement)
        )
    classes_existantes = Classe.objects.all().order_by('nomClasse')
    options_existantes = Option.objects.all().order_by('idOption')

    if request.method == 'POST':
        if 'configurer_frais' in request.POST:
            typeFrs = request.POST.get('typeFrs')
            montant = request.POST.get('montant_du')
            classe_choisie = request.POST.get('classe')
            option_choisie = request.POST.get('option')
            
            FraisScolaire.objects.create(
                typeFrs=typeFrs,
                montant=montant,
                classe=classe_choisie if classe_choisie != "" else None,
                option=option_choisie if option_choisie != "" else None
            )
            messages.success(request, "Nouveau montant dû configuré avec succès !")
            return redirect('espace_comptable')

        elif 'modifier_frais' in request.POST:
            frais_id = request.POST.get('frais_id')
            frais = FraisScolaire.objects.get(id=frais_id)
            frais.typeFrs = request.POST.get('typeFrs')
            frais.montant = request.POST.get('montant_du')
            frais.classe = request.POST.get('classe') if request.POST.get('classe') != "" else None
            frais.option = request.POST.get('option') if request.POST.get('option') != "" else None
            frais.save()
            messages.success(request, f"Le tarif '{frais.typeFrs}' a été mis à jour !")
            return redirect('espace_comptable')

        elif 'enregistrer_paiement' in request.POST:
            matricule = request.POST.get('matricule')
            frais_id = request.POST.get('frais_id')
            numRecur = request.POST.get('numRecur')
            montant_verse = request.POST.get('montant')

            eleve = Eleve.objects.get(matriculeEleve=matricule)
            frais = FraisScolaire.objects.get(id=frais_id)

            Paiement.objects.create(
                eleve=eleve,
                frais_type=frais,
                numRecur=numRecur,
                montant=montant_verse
            )
            messages.success(request, f"Versement de {montant_verse}$ enregistré avec succès pour {eleve.nom} !")
            return redirect('espace_comptable')

    context = {
        'eleves': eleves,
        'frais_liste': frais_liste,
        'paiements': paiements,
        'recherche_paiement': recherche_paiement,
        'classes_existantes': classes_existantes,
        'options_existantes': options_existantes,
    }
    return render(request, 'management/espace_comptable.html', context)


@login_required
def dashboard_proviseur(request):
    # --- 1. TRAITEMENTS POST ---
    
    # A. Attribution des cours
    if request.method == 'POST' and 'attribuer_cours' in request.POST:
        enseignant_id = request.POST.get('enseignant_id')
        cours_id = request.POST.get('cours_id')
        classe_id = request.POST.get('classe_id')
        
        classe_obj = get_object_or_404(Classe, pk=classe_id)
        cours_obj = get_object_or_404(Cours, idCours=cours_id)
        
        # On récupère ou crée l'attribution pour (Cours + Classe)
        attribution, created = Attribution.objects.get_or_create(cours=cours_obj, classe=classe_obj)
        
        if enseignant_id == 'retirer':
            attribution.enseignant = None
        else:
            enseignant_obj = get_object_or_404(Enseignant, idEns=enseignant_id)
            attribution.enseignant = enseignant_obj
        attribution.save()
        
        messages.success(request, f"Attribution mise à jour pour {cours_obj.libelle}")
        return redirect(f'/management/proviseur/?classe_id={classe_id}#attribution-panel')

    # B. Gestion des statuts de la Période
    if request.method == 'POST' and 'action_periode' in request.POST:
        periode_id = request.POST.get('periode_id')
        nouveau_statut = request.POST.get('statut')
        periode_obj = get_object_or_404(Periode, idPeriode=periode_id)
        periode_obj.statut = nouveau_statut
        periode_obj.save()
        messages.success(request, f"Période {periode_obj.nomPeriode} mise à jour.")
        return redirect('/management/proviseur/#periode-panel')

    # C. Publication / retrait des résultats
    if request.method == 'POST' and 'action_publication' in request.POST:
        publication = PublicationResultats.get_instance()
        if request.POST.get('action_publication') == 'publier':
            publication.est_publiee = True
            publication.date_publication = timezone.now()
            publication.publie_par = request.user
            publication.save()
            messages.success(request, "Les résultats sont maintenant publiés. Les élèves peuvent les consulter selon leur situation financière.")
        else:
            publication.est_publiee = False
            publication.save()
            messages.warning(request, "Publication des résultats retirée. Les élèves ne peuvent plus voir leurs notes.")
        return redirect('/management/proviseur/#deliberation-panel')

    # D. Décision du jury
    if request.method == 'POST' and 'decision_jury' in request.POST:
        matricule = request.POST.get('matricule_eleve')
        classe_id = request.POST.get('classe_id')
        decision = request.POST.get('decision')
        commentaire = request.POST.get('commentaire', '')
        eleve_obj = get_object_or_404(Eleve, matriculeEleve=matricule)
        classe_obj = get_object_or_404(Classe, pk=classe_id)
        DecisionJury.objects.update_or_create(
            eleve=eleve_obj,
            classe=classe_obj,
            defaults={'decision': decision, 'commentaire': commentaire},
        )
        messages.success(request, f"Décision enregistrée pour {eleve_obj.nom} {eleve_obj.postnom}.")
        return redirect(f'/management/proviseur/?classe_delib={classe_id}#deliberation-panel')

    # --- 2. TRAITEMENT GET (Données) ---
    toutes_les_classes = Classe.objects.all()
    tous_enseignants = Enseignant.objects.all().order_by('nom')
    periodes = Periode.objects.all().order_by('idPeriode')
    publication = PublicationResultats.get_instance()
    fiches_soumises = CentralisationClasse.objects.select_related('classe', 'titulaire').order_by('-date_soumission')
    fiches_avec_suivi = [
        {'fiche': f, 'suivi': build_suivi_classe(f.classe)}
        for f in fiches_soumises
    ]
    
    classe_id = request.GET.get('classe_id')
    classe_sel = toutes_les_classes.filter(pk=classe_id).first() if classe_id else toutes_les_classes.first()

    classe_delib_id = request.GET.get('classe_delib')
    classe_delib = toutes_les_classes.filter(pk=classe_delib_id).first() if classe_delib_id else classe_sel

    deliberation_data = None
    decisions_map = {}
    if classe_delib:
        deliberation_data = build_deliberation_classe(classe_delib)
        decisions = DecisionJury.objects.filter(classe=classe_delib)
        decisions_map = {d.eleve_id: d for d in decisions}
        for ligne in deliberation_data['lignes']:
            ligne['decision_jury'] = decisions_map.get(ligne['eleve'].matriculeEleve)
    
    cours_de_la_classe = []
    if classe_sel:
        # On récupère tous les cours
        cours_de_la_classe = Cours.objects.filter(classes=classe_sel)
        # On attache l'enseignant trouvé dans Attribution à chaque cours
        for cours in cours_de_la_classe:
            attr = Attribution.objects.filter(classe=classe_sel, cours=cours).first()
            cours.enseignant_actuel = attr.enseignant if attr else None

    context = {
        'liste_classes_global': toutes_les_classes,
        'liste_enseignants_global': tous_enseignants,
        'classe_selectionnee': classe_sel,
        'classe_delib': classe_delib,
        'cours_de_la_classe': cours_de_la_classe,
        'periodes': periodes,
        'total_eleves': Eleve.objects.count(),
        'total_enseignants': tous_enseignants.count(),
        'total_classes': toutes_les_classes.count(),
        'total_options': Option.objects.count(),
        'fiches_soumises': fiches_soumises,
        'fiches_avec_suivi': fiches_avec_suivi,
        'publication': publication,
        'deliberation_data': deliberation_data,
        'decisions_jury_choices': DecisionJury.DECISION_CHOICES,
    }
    return render(request, 'management/dashboard_proviseur.html', context)

@login_required
def valider_fiche_proviseur(request, fiche_id):
    fiche = get_object_or_404(CentralisationClasse, pk=fiche_id)
    if request.method == 'POST':
        fiche.feedback_proviseur = request.POST.get('feedback_proviseur', '').strip()
        fiche.est_valide = True
        fiche.date_validation = timezone.now()
        fiche.save()
        messages.success(request, f"La centralisation de {fiche.classe.nomClasse} a été validée. Le titulaire recevra votre retour.")
        return redirect('/management/proviseur/#validation-panel')
    fiche.est_valide = True
    fiche.date_validation = timezone.now()
    fiche.save()
    messages.success(request, f"La fiche de cotes de {fiche.classe.nomClasse} a été validée.")
    return redirect('dashboard_proviseur')

@login_required
def espace_titulaire(request):
    # 1. Identification de l'enseignant
    enseignant = Enseignant.objects.filter(user=request.user).first()
    if not enseignant:
        messages.error(request, "Erreur : Profil enseignant non trouvé.")
        return redirect('home')
    
    # 2. Identification de la classe titulaire
    classe_titulaire = Classe.objects.filter(idEns=enseignant).first()
    if not classe_titulaire:
        messages.error(request, f"Vous n'êtes titulaire d'aucune classe.")
        return redirect('home')

    suivi_data = build_suivi_classe(classe_titulaire)
    suivi_eleves = suivi_data['suivi_eleves']
    nombre_total_cours = suivi_data['nombre_total_cours']

    centralisation = CentralisationClasse.objects.filter(classe=classe_titulaire).first()

    if request.method == 'POST' and 'valider_et_soumettre' in request.POST:
        obj, _ = CentralisationClasse.objects.update_or_create(
            classe=classe_titulaire,
            defaults={
                'titulaire': enseignant,
                'est_valide': False,
                'feedback_proviseur': '',
                'date_validation': None,
            },
        )
        obj.date_soumission = timezone.now()
        obj.save(update_fields=['date_soumission'])
        messages.success(request, "Les points ont été centralisés et soumis au Proviseur.")
        return redirect('espace_titulaire')
    cours_classe = get_cours_classe(classe_titulaire)
    attributions_classe = list(
        Attribution.objects.filter(classe=classe_titulaire)
        .select_related('cours', 'enseignant')
        .order_by('cours__libelle')
    )
    if not attributions_classe:
        for cours in cours_classe:
            attributions_classe.append(SimpleNamespace(cours=cours, enseignant=cours.enseignant))

    context = {
        'enseignant': enseignant,
        'classe': classe_titulaire,
        'suivi_eleves': suivi_eleves,
        'nombre_total_cours': nombre_total_cours,
        'liste_eleves': Eleve.objects.filter(classe=classe_titulaire).order_by('nom', 'postnom'),
        'attributions_classe': attributions_classe,
        'centralisation': centralisation,
    }
    return render(request, 'management/espace_titulaire.html', context)


@login_required
def espace_enseignant(request):
    # 1. On cherche l'enseignant lié au compte connecté
    enseignant_connecte = Enseignant.objects.filter(user=request.user).first()
    
    if not enseignant_connecte:
        # DEBUG : Afficher tous les utilisateurs et leurs profils liés pour voir s'il y a un décalage
        print(f"DEBUG: Utilisateur {request.user.username} n'est pas lié à un objet Enseignant.")
        return render(request, 'management/erreur_profil.html', {'message': "Votre compte utilisateur n'est pas lié à un profil Enseignant."})

    # 2. On récupère les attributions réelles en base
    # Assurez-vous que votre modèle Attribution possède bien un champ 'enseignant'
    mes_attributions = Attribution.objects.filter(enseignant=enseignant_connecte).select_related('cours', 'classe', 'cours__max')

    charges_par_cours = {}
    for attr in mes_attributions.order_by('cours__libelle', 'classe__nomClasse'):
        cid = attr.cours.idCours
        if cid not in charges_par_cours:
            charges_par_cours[cid] = {'cours': attr.cours, 'attributions': []}
        charges_par_cours[cid]['attributions'].append(attr)

    charges_groupees = list(charges_par_cours.values())

    return render(request, 'management/espace_enseignant.html', {
        'mes_attributions': mes_attributions,
        'charges_groupees': charges_groupees,
        'enseignant': enseignant_connecte,
    })

@login_required
def encoder_notes(request, cours_id):
    enseignant_connecte = get_object_or_404(Enseignant, user=request.user)
    
    # On vérifie que le cours existe
    cours_obj = get_object_or_404(Cours, idCours=cours_id)
    
    classe_id = request.GET.get('classe_id')
    classe_selectionnee = None
    
    # Vérification que l'enseignant a une Attribution pour ce cours et cette classe
    if classe_id:
        classe_selectionnee = get_object_or_404(Classe, pk=classe_id)
        attribution = get_object_or_404(Attribution, enseignant=enseignant_connecte, cours=cours_obj, classe=classe_selectionnee)
    else:
        # Si pas de classe, on récupère les attributions de cet enseignant pour ce cours
        attributions = Attribution.objects.filter(enseignant=enseignant_connecte, cours=cours_obj)
        if not attributions.exists():
            return render(request, 'management/erreur_profil.html', {'message': "Vous n'êtes pas autorisé à accéder à ce cours."})
    
    eleves_avec_cotes = []
    
    # CORRECTION ICI : Remplacement de id par idPeriode
    periodes_bdd = Periode.objects.all().order_by('idPeriode')

    if classe_selectionnee:
        eleves = Eleve.objects.filter(classe=classe_selectionnee).order_by('nom', 'postnom')
        
        for el in eleves:
            cotes_par_periode = {}
            for p in periodes_bdd:
                cote_obj, _ = Cotes.objects.get_or_create(eleve=el, cours=cours_obj, periode=p)
                cotes_par_periode[p.code] = cote_obj
                
            eleves_avec_cotes.append({
                'eleve': el,
                'cotes': cotes_par_periode
            })

    try:
        max_p = cours_obj.max.maxima # Remplace 'points_max' par le nom du champ dans SectionCours
    except:
        max_p = 10 # Valeur par défaut si la relation est vide
        
    max_ex = max_p * 2

    if request.method == 'POST' and classe_selectionnee:
        periodes_actives = [p for p in periodes_bdd if p.statut == 'ACTIVE']
        if not periodes_actives:
            messages.warning(request, "Impossible d'enregistrer : l'encodage est verrouillé.")
            return redirect(f"{request.path}?classe_id={classe_id}")

        for item in eleves_avec_cotes:
            el = item['eleve']
            for code, cote_obj in item['cotes'].items():
                if cote_obj.periode.statut != 'ACTIVE':
                    continue
                
                input_name = f"{code.lower()}_{el.pk}"
                val_saisie = request.POST.get(input_name)
                
                if val_saisie and val_saisie.strip() != "":
                    cote_obj.note = float(val_saisie)
                else:
                    cote_obj.note = None 
                cote_obj.save()
            
        messages.success(request, f"Les notes ont été enregistrées avec succès !")
        return redirect(f"{request.path}?classe_id={classe_id}")

    # Récupérer les classes pour lesquelles cet enseignant a ce cours attribué
    attributions_enseignant = Attribution.objects.filter(enseignant=enseignant_connecte, cours=cours_obj)
    classes_concernees = [attr.classe for attr in attributions_enseignant]

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

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@login_required
def imprimer_bulletins(request, classe_id):
    """
    Génère les bulletins scolaires avec calculs automatiques des totaux, moyennes et appréciations.
    """
    enseignant = get_object_or_404(Enseignant, user=request.user)
    classe = get_object_or_404(Classe, pk=classe_id, idEns=enseignant)

    # Récupère la liste des matricules cochés dans le formulaire
    eleve_ids = request.POST.getlist('eleves_selectionnes')

    if eleve_ids:
        eleves = Eleve.objects.filter(classe=classe, matriculeEleve__in=eleve_ids)
    else:
        eleves = Eleve.objects.filter(classe=classe).order_by('nom', 'postnom')

    # Récupérer tous les cours de la classe, triés par domaine
    cours_de_la_classe = Cours.objects.filter(classes=classe).select_related('max', 'domaine').order_by('domaine__ordre', 'domaine__nom', 'libelle')

    # Récupérer toutes les périodes
    periodes = Periode.objects.all().order_by('idPeriode')

    # Préparer les bulletins avec tous les calculs
    bulletins = []
    for eleve in eleves:
        # Récupérer toutes les cotes de l'élève
        cotes_elev = Cotes.objects.filter(eleve=eleve).select_related('cours', 'periode')
        
        # Créer un dictionnaire pour accès rapide: {(id_cours, code_periode): note}
        dict_cotes = {}
        for cote in cotes_elev:
            if cote.note is not None:
                dict_cotes[(cote.cours.idCours, cote.periode.code)] = cote.note
        
        # Calculer les totaux et moyennes pour chaque cours
        cours_avec_calculs = []
        total_general_points = 0
        total_general_max = 0
        
        for cours in cours_de_la_classe:
            max_p = cours.max.maxima  # Maximum pour une période
            max_ex = max_p * 2  # Maximum pour l'examen
            
            # Récupérer les notes
            p1 = dict_cotes.get((cours.idCours, 'P1'))
            p2 = dict_cotes.get((cours.idCours, 'P2'))
            ex1 = dict_cotes.get((cours.idCours, 'EX1'))
            p3 = dict_cotes.get((cours.idCours, 'P3'))
            p4 = dict_cotes.get((cours.idCours, 'P4'))
            ex2 = dict_cotes.get((cours.idCours, 'EX2'))
            
            # Calculs Semestre 1
            s1_notes = [p1, p2, ex1]
            s1_obtenu = sum([n for n in s1_notes if n is not None])
            s1_max = 0
            if p1 is not None: s1_max += max_p
            if p2 is not None: s1_max += max_p
            if ex1 is not None: s1_max += max_ex
            
            s1_moy = (s1_obtenu / s1_max * 100) if s1_max > 0 else None
            s1_apprec = ""
            if s1_moy is not None:
                if s1_moy >= 80: s1_apprec = "FD"  # Félicitations
                elif s1_moy >= 70: s1_apprec = "FD"  # Grande Distinction
                elif s1_moy >= 60: s1_apprec = "D"   # Distinction
                elif s1_moy >= 50: s1_apprec = "S"   # Satisfaction
                elif s1_moy >= 40: s1_apprec = "R"   # Réservé
                else: s1_apprec = "E"  # Échec
            
            # Calculs Semestre 2
            s2_notes = [p3, p4, ex2]
            s2_obtenu = sum([n for n in s2_notes if n is not None])
            s2_max = 0
            if p3 is not None: s2_max += max_p
            if p4 is not None: s2_max += max_p
            if ex2 is not None: s2_max += max_ex
            
            s2_moy = (s2_obtenu / s2_max * 100) if s2_max > 0 else None
            s2_apprec = ""
            if s2_moy is not None:
                if s2_moy >= 80: s2_apprec = "FD"
                elif s2_moy >= 70: s2_apprec = "FD"
                elif s2_moy >= 60: s2_apprec = "D"
                elif s2_moy >= 50: s2_apprec = "S"
                elif s2_moy >= 40: s2_apprec = "R"
                else: s2_apprec = "E"
            
            # Total général pour ce cours
            cours_total_obtenu = s1_obtenu + s2_obtenu
            cours_total_max = s1_max + s2_max
            cours_moy = (cours_total_obtenu / cours_total_max * 100) if cours_total_max > 0 else None
            
            total_general_points += s1_obtenu + s2_obtenu
            total_general_max += s1_max + s2_max
            
            cours_avec_calculs.append({
                'cours': cours,
                'p1': p1 if p1 is not None else '-',
                'p2': p2 if p2 is not None else '-',
                'ex1': ex1 if ex1 is not None else '-',
                's1_total': s1_obtenu if s1_obtenu > 0 else '-',
                's1_moy': f"{s1_moy:.1f}%" if s1_moy is not None else '-',
                's1_apprec': s1_apprec,
                'p3': p3 if p3 is not None else '-',
                'p4': p4 if p4 is not None else '-',
                'ex2': ex2 if ex2 is not None else '-',
                's2_total': s2_obtenu if s2_obtenu > 0 else '-',
                's2_moy': f"{s2_moy:.1f}%" if s2_moy is not None else '-',
                's2_apprec': s2_apprec,
                'total': cours_total_obtenu if cours_total_obtenu > 0 else '-',
                'moy': f"{cours_moy:.1f}%" if cours_moy is not None else '-',
            })
        
        # Moyenne générale
        moy_general = (total_general_points / total_general_max * 100) if total_general_max > 0 else None
        apprec_general = ""
        if moy_general is not None:
            if moy_general >= 80: apprec_general = "Félicitations du Jury"
            elif moy_general >= 70: apprec_general = "Grande Distinction"
            elif moy_general >= 60: apprec_general = "Distinction"
            elif moy_general >= 50: apprec_general = "Satisfaction"
            elif moy_general >= 40: apprec_general = "Réservé"
            else: apprec_general = "Échec"
        
        # Décompte des domaines
        domaines_stats = {}
        for cours_data in cours_avec_calculs:
            domaine_nom = cours_data['cours'].domaine.nom if cours_data['cours'].domaine else 'Autres'
            if domaine_nom not in domaines_stats:
                domaines_stats[domaine_nom] = {'points': 0, 'max': 0, 'cours': 0}
            # Calculer le total pour ce cours
            c = cours_data['cours']
            max_p = c.max.maxima
            notes = []
            for code in ['P1', 'P2', 'EX1', 'P3', 'P4', 'EX2']:
                n = dict_cotes.get((c.idCours, code))
                if n is not None:
                    notes.append(n)
            domaines_stats[domaine_nom]['points'] += sum(notes)
            domaines_stats[domaine_nom]['max'] += len(notes) * (max_p if len(notes) <= 4 else max_p * 2)
            domaines_stats[domaine_nom]['cours'] += 1
        
        decision = DecisionJury.objects.filter(eleve=eleve, classe=classe).first()
        decision_label = decision.get_decision_display() if decision and decision.decision != 'EN_ATTENTE' else ''

        bulletins.append({
            'eleve': eleve,
            'cours': cours_avec_calculs,
            'moy_general': f"{moy_general:.1f}%" if moy_general is not None else '-',
            'apprec_general': apprec_general,
            'total_points': total_general_points,
            'total_max': total_general_max,
            'domaines_stats': domaines_stats,
            'decision_jury': decision_label,
        })

    context = {
        'bulletins': bulletins,
        'classe': classe,
    }

    template_names = [
        f'bulletins/bulletin_{classe.type_bulletin}.html',
        'bulletins/bulletin_co.html',
    ]

    for template_name in template_names:
        try:
            return render(request, template_name, context)
        except TemplateDoesNotExist:
            continue

    return render(request, 'bulletins/bulletin_co.html', context)