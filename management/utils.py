from django.db.models import Count, Q, Sum

from .models import Cotes, Cours, Eleve, FraisScolaire, Paiement, Periode

PERIODE_ACCES = {
    'P1': 'acces_p1',
    'P2': 'acces_p2',
    'EX1': 'acces_ex1',
    'P3': 'acces_s2',
    'P4': 'acces_s2',
    'EX2': 'acces_s2',
}


def get_montant_du_eleve(eleve):
    paiements = Paiement.objects.filter(eleve=eleve).order_by('-date')
    premier = paiements.first()
    if premier and premier.frais_type:
        return premier.frais_type.montant

    classe = eleve.classe
    frais = FraisScolaire.objects.filter(classe=classe.nomClasse).first()
    if frais:
        return frais.montant

    frais = FraisScolaire.objects.filter(option=classe.option.nomOption).first()
    if frais:
        return frais.montant

    frais = FraisScolaire.objects.filter(classe__isnull=True, option__isnull=True).first()
    if not frais:
        frais = FraisScolaire.objects.first()
    return frais.montant if frais else 0


def get_situation_financiere(eleve):
    total_paye = Paiement.objects.filter(eleve=eleve).aggregate(Sum('montant'))['montant__sum'] or 0
    total_du = get_montant_du_eleve(eleve)
    reste = max(0, total_du - total_paye)

    if total_du <= 0:
        acces = {'acces_p1': True, 'acces_p2': True, 'acces_ex1': True, 'acces_s2': True}
    else:
        acces = {
            'acces_p1': total_paye >= (total_du / 4),
            'acces_p2': total_paye >= (total_du / 3),
            'acces_ex1': total_paye >= (total_du / 2),
            'acces_s2': total_paye >= total_du,
        }

    return {
        'total_du': total_du,
        'total_paye': total_paye,
        'reste_a_payer': reste,
        **acces,
    }


def get_cours_classe(classe):
    return Cours.objects.filter(classes=classe).select_related('max', 'domaine').order_by(
        'domaine__ordre', 'libelle'
    )


def build_dict_cotes(eleve):
    cotes = Cotes.objects.filter(eleve=eleve).select_related('cours', 'periode')
    return {
        f"{c.cours_id}_{c.periode.code}": c.note
        for c in cotes
        if c.note is not None
    }


def _maxima_periode(code, max_p):
    return max_p * 2 if code.startswith('EX') else max_p


def calculer_bilan_cours(cours, dict_cotes, codes_periodes):
    max_p = cours.max.maxima
    notes = []
    maxima = []

    for code in codes_periodes:
        raw = dict_cotes.get(f"{cours.idCours}_{code}")
        if raw is None:
            return None, None, 'En attente', False
        notes.append(raw)
        maxima.append(_maxima_periode(code, max_p))

    obtenu = sum(notes)
    total_max = sum(maxima)
    verdict = 'Réussi' if obtenu >= (total_max / 2) else 'Échec'
    return obtenu, total_max, verdict, True


def calculer_moyenne_semestre(eleve, codes_periodes):
    dict_cotes = build_dict_cotes(eleve)
    total_obtenu = 0
    total_max = 0
    complet = True

    for cours in get_cours_classe(eleve.classe):
        obtenu, maxima, _, ok = calculer_bilan_cours(cours, dict_cotes, codes_periodes)
        if not ok:
            complet = False
            continue
        total_obtenu += obtenu
        total_max += maxima

    if total_max <= 0:
        return None, 0, 0, complet
    return round(total_obtenu / total_max * 100, 1), total_obtenu, total_max, complet


def _note_affichee(raw, existe, resultats_publies, has_acces_financier):
    if not existe:
        return '-', False
    if not resultats_publies:
        return 'Résultats non disponibles', False
    if not has_acces_financier:
        return 'Veuillez passer à la comptabilité', False
    return raw, True


def build_ligne_bulletin(cours, dict_cotes, fin, codes_periodes, resultats_publies):
    max_p = cours.max.maxima
    max_ex = max_p * 2
    periodes_data = {}

    for code in codes_periodes:
        raw = dict_cotes.get(f"{cours.idCours}_{code}", '-')
        max_val = max_ex if code.startswith('EX') else max_p
        existe = raw != '-'
        acces_key = PERIODE_ACCES[code]
        has_acces = fin.get(acces_key, False)

        note_affichee, autorise = _note_affichee(raw, existe, resultats_publies, has_acces)
        reussi = None
        if autorise and isinstance(raw, (int, float)):
            reussi = raw >= (max_val / 2)

        periodes_data[code.lower()] = {
            'note': note_affichee,
            'max': max_val,
            'reussi': reussi,
            'autorise': autorise,
            'existe': existe,
        }

    obtenu, total_max, verdict, complet = calculer_bilan_cours(cours, dict_cotes, codes_periodes)

    if not complet:
        total_affiche = '-'
        verdict_final = 'En attente'
    elif not resultats_publies:
        total_affiche = 'Masqué'
        verdict_final = 'Masqué'
    elif not all(fin.get(PERIODE_ACCES[c], False) for c in codes_periodes):
        total_affiche = 'Masqué'
        verdict_final = 'Masqué'
    else:
        total_affiche = f"{obtenu} / {total_max}"
        verdict_final = verdict

    return periodes_data, total_affiche, verdict_final, complet


def build_suivi_classe(classe):
    nombre_periodes = Periode.objects.count() or 6
    cours_classe = get_cours_classe(classe)
    nombre_total_cours = cours_classe.count()
    cotes_attendues = nombre_total_cours * nombre_periodes

    eleves = Eleve.objects.filter(classe=classe).annotate(
        total_paye=Sum('paiements__montant'),
        nb_cotes=Count('cotes', filter=Q(cotes__note__isnull=False)),
    )

    suivi_eleves = []
    for el in eleves:
        fin = get_situation_financiere(el)
        pct_cotes = round((el.nb_cotes / cotes_attendues) * 100) if cotes_attendues > 0 else 0
        suivi_eleves.append({
            'eleve': el,
            'total_du': fin['total_du'],
            'total_paye': fin['total_paye'],
            'reste_a_payer': fin['reste_a_payer'],
            'cotes_encodees': el.nb_cotes or 0,
            'cotes_attendues': cotes_attendues,
            'pourcentage_cotes': pct_cotes,
            'est_entierement_cote': (el.nb_cotes or 0) >= cotes_attendues if cotes_attendues > 0 else False,
            'en_regle': fin['reste_a_payer'] <= 0,
        })

    return {
        'suivi_eleves': suivi_eleves,
        'nombre_total_cours': nombre_total_cours,
        'cotes_attendues': cotes_attendues,
    }


def build_deliberation_classe(classe):
    cours_list = list(get_cours_classe(classe))
    eleves = list(Eleve.objects.filter(classe=classe).order_by('nom', 'postnom'))

    lignes = []
    nb_reussite = 0
    nb_echec = 0
    nb_attente = 0

    for eleve in eleves:
        dict_cotes = build_dict_cotes(eleve)
        cours_resultats = []
        cours_reussis = 0
        cours_echoues = 0
        cours_attente = 0

        for cours in cours_list:
            _, _, verdict_s1, complet_s1 = calculer_bilan_cours(cours, dict_cotes, ['P1', 'P2', 'EX1'])
            _, _, verdict_s2, complet_s2 = calculer_bilan_cours(cours, dict_cotes, ['P3', 'P4', 'EX2'])
            _, _, verdict_annuel, complet_annuel = calculer_bilan_cours(
                cours, dict_cotes, ['P1', 'P2', 'EX1', 'P3', 'P4', 'EX2']
            )

            cours_resultats.append({
                'cours': cours,
                's1': verdict_s1 if complet_s1 else '—',
                's2': verdict_s2 if complet_s2 else '—',
                'annuel': verdict_annuel if complet_annuel else 'En attente',
            })

            if complet_annuel:
                if verdict_annuel == 'Réussi':
                    cours_reussis += 1
                else:
                    cours_echoues += 1
            else:
                cours_attente += 1

        if cours_list:
            if cours_attente == len(cours_list):
                statut_global = 'En attente'
                nb_attente += 1
            elif cours_echoues == 0 and cours_reussis > 0:
                statut_global = 'Réussi'
                nb_reussite += 1
            elif cours_reussis == 0 and cours_echoues > 0:
                statut_global = 'Échec'
                nb_echec += 1
            else:
                statut_global = 'Partiel'
                nb_attente += 1
        else:
            statut_global = 'En attente'
            nb_attente += 1

        fin = get_situation_financiere(eleve)
        lignes.append({
            'eleve': eleve,
            'cours_resultats': cours_resultats,
            'statut_global': statut_global,
            'total_paye': fin['total_paye'],
            'total_du': fin['total_du'],
            'reste_a_payer': fin['reste_a_payer'],
        })

    total = len(eleves)
    return {
        'cours_list': cours_list,
        'lignes': lignes,
        'stats': {
            'total': total,
            'reussite': nb_reussite,
            'echec': nb_echec,
            'attente': nb_attente,
            'pct_reussite': round(nb_reussite / total * 100, 1) if total else 0,
            'pct_echec': round(nb_echec / total * 100, 1) if total else 0,
        },
    }
