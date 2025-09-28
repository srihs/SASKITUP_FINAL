from django.apps import AppConfig


class ClubsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clubs'
    verbose_name = 'Clubs Management'
    
    def ready(self):
        """
        Initialize app when Django starts
        """
        # Import signals to register them with Django
        try:
            import clubs.signals
        except ImportError:
            pass
