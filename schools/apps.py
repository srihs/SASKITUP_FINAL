from django.apps import AppConfig


class SchoolsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'schools'

    def ready(self):
        """Import signal handlers when the app is ready"""
        try:
            from . import signals
            signals.register_audit_signals()
        except ImportError:
            pass
