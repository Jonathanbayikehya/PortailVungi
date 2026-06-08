from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import Classe, Eleve, Enseignant



def _user_is_eleve(user):
    return Eleve.objects.filter(user=user).exists()



def _user_is_enseignant(user):
    return Enseignant.objects.filter(user=user).exists()



def _user_is_titulaire(user):
    enseignant = Enseignant.objects.filter(user=user).first()
    return bool(enseignant and Classe.objects.filter(idEns=enseignant).exists())



def _user_is_comptable(user):
    return user.groups.filter(name='Comptable').exists() or user.username.lower() == 'comptable'



def _user_is_proviseur(user):
    return user.is_superuser or user.groups.filter(name='Proviseur').exists() or user.username.lower() == 'proviseur'



def _role_required(check_func, error_message):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not check_func(request.user):
                messages.error(request, error_message)
                return redirect('home')
            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator



eleve_required = _role_required(
    _user_is_eleve,
    "Accès refusé : Aucun profil Élève trouvé.",
)

enseignant_required = _role_required(
    _user_is_enseignant,
    "Accès refusé : Aucun profil Enseignant trouvé.",
)

titulaire_required = _role_required(
    _user_is_titulaire,
    "Accès refusé : Vous n'êtes titulaire d'aucune classe.",
)

comptable_required = _role_required(
    _user_is_comptable,
    "Accès refusé : Vous n'avez pas le rôle de Comptable.",
)

proviseur_required = _role_required(
    _user_is_proviseur,
    "Accès refusé : Privilèges administratifs du Proviseur insuffisants.",
)
