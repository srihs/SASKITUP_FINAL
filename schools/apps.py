from django.apps import AppConfig


class SchoolsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'schools'

    def ready(self):
        """Import signal handlers when the app is ready"""
        # Prevent duplicate signal registration on auto-reload
        if hasattr(self.__class__, '_signals_registered'):
            return

        try:
            from . import signals
            signals.register_audit_signals()
            self.__class__._signals_registered = True
        except ImportError:
            pass
