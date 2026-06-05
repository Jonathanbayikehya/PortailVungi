from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User as DjangoUser

# Importation de tes modèles locaux
from .models import (
    Section, Option, Enseignant, Classe, Eleve, 
    TypeCours, SectionCours, Cours, Periode, 
    Cotes, FraisScolaire, Paiement, Domaine
)

# --- INLINES POUR LA GESTION DES UTILISATEURS ---
class EleveInline(admin.StackedInline):
    model = Eleve
    can_delete = False
    verbose_name_plural = 'Profil Élève / Parent'
    fk_name = 'user'
    extra = 0

class EnseignantInline(admin.StackedInline):
    model = Enseignant
    can_delete = False
    verbose_name_plural = 'Profil Enseignant'
    fk_name = 'user'
    extra = 0

class CustomUserAdmin(UserAdmin):
    inlines = (EleveInline, EnseignantInline)

# Ré-enregistrement de la table User
admin.site.unregister(DjangoUser)
admin.site.register(DjangoUser, CustomUserAdmin)


# --- INLINE POUR LA GESTION DES COURS PAR OPTION ---
# Permet d'afficher et d'ajouter les cours directement dans l'interface de SectionCours
class CoursInline(admin.TabularInline):
    model = Cours
    extra = 3
    fields = ('code_cours', 'libelle', 'ponderation', 'type_cours')
    readonly_fields = ('get_maxima',) # Pour afficher la valeur

    def get_maxima(self, obj):
        return obj.section_cours.maxima
    get_maxima.short_description = 'Maxima actuel' 


# --- CONFIGURATION NETTOYÉE ET ULTRA-SÉCURISÉE DES CLASSES D'ADMIN ---

@admin.register(SectionCours)
class SectionCoursAdmin(admin.ModelAdmin):
    #inlines = [CoursInline]  # Magie : injecte le tableau des cours juste en dessous de l'Option !
    pass  # On laisse la configuration de base pour éviter les erreurs E108

@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    pass  # Plus aucun risque d'erreur E108 ici !

@admin.register(Enseignant)
class EnseignantAdmin(admin.ModelAdmin):
    pass

@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'code_cours', 'max', 'ponderation')
    
    # Rend ces champs directement modifiables dans la liste principale
    list_editable = ('code_cours', 'max', 'ponderation')
    
    # Vous permet de filtrer rapidement par section
    list_filter = ('max',)
    
@admin.register(Domaine)
class DomaineAdmin(admin.ModelAdmin):
    list_display = ('nom', 'ordre')
    ordering = ('ordre',)


# --- ENREGISTREMENT SIMPLE DES AUTRES TABLES ---
admin.site.register(Section)
admin.site.register(Option)
admin.site.register(Eleve)
admin.site.register(TypeCours)
admin.site.register(Periode)
admin.site.register(Cotes)
admin.site.register(FraisScolaire)
admin.site.register(Paiement)