from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('mon-espace/', views.dashboard_eleve, name='dashboard_eleve'),
    path('gestion-comptable/', views.espace_comptable, name='espace_comptable'),
    path('management/proviseur/', views.dashboard_proviseur, name='dashboard_proviseur'),
    path('espace-titulaire/', views.espace_titulaire, name='espace_titulaire'),
    path('espace-enseignant/', views.espace_enseignant, name='espace_enseignant'),
    path('cours/<int:cours_id>/encoder/', views.encoder_notes, name='encoder_notes'),
    path('deconnexion/', LogoutView.as_view(next_page='home'), name='logout'),
    path('logout/', views.deconnexion_utilisateur, name='logout'),# Nouvelle route pour la signature du Proviseur (prend l'ID de la fiche en paramètre)
    path('proviseur/valider/<int:fiche_id>/', views.valider_fiche_proviseur, name='valider_fiche_proviseur'),
    path('imprimer_bulletins/<int:classe_id>/', views.imprimer_bulletins, name='imprimer_bulletins'),
    
]