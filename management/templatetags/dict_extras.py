from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    # Retourne la valeur si le dictionnaire existe et la clé est trouvée
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None