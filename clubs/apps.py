from django.apps import AppConfig


class ClubsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clubs'
    verbose_name = 'Clubs Management'
    
    def ready(self):
        """
        Initialize app when Django starts
        """
        pass  # Import signals if we create any later
