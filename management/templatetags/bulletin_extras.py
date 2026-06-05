from django import template
register = template.Library()

@register.filter
def get_note(cotes, cours):
    """Récupère toutes les cotes pour un cours donné"""
    if hasattr(cotes, 'filter'):
        return cotes.filter(cours=cours)
    return cotes

@register.filter
def get_periode(cotes_cours, p_code):
    """Récupère la note pour une période donnée"""
    if hasattr(cotes_cours, 'filter'):
        cote = cotes_cours.filter(periode__code=p_code).first()
        return cote.note if cote else None
    return None

@register.filter
def calculer_total(cotes, cours):
    """Calcule la somme des notes pour un cours"""
    if hasattr(cotes, 'filter'):
        liste_notes = [c.note for c in cotes.filter(cours=cours) if c.note]
        total = sum(liste_notes)
        return f"{total:.1f}" if total else "-"
    return "-"

@register.filter
def calculer_moyenne(cotes, cours):
    """Calcule la moyenne des notes pour un cours"""
    if hasattr(cotes, 'filter'):
        cotes_cours = [c.note for c in cotes.filter(cours=cours) if c.note]
        if cotes_cours:
            moyenne = sum(cotes_cours) / len(cotes_cours)
            return f"{moyenne:.1f}"
    return "-"
