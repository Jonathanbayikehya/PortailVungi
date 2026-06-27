from django.apps import AppConfig

class ManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'management'

    def ready(self):
        # On importe le fichier des signaux pour que l'envoi de SMS s'active
        import management.signals