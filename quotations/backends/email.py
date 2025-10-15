"""
Custom email backend that supports SSL context configuration.

This backend extends Django's SMTP backend to use a custom SSL context
for certificate verification, useful for development environments.
"""

from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend
from django.conf import settings


class EmailBackend(DjangoEmailBackend):
    """
    Custom SMTP email backend that uses EMAIL_SSL_CONTEXT from settings.

    This allows us to bypass SSL certificate verification in development
    while maintaining secure connections in production.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use custom SSL context if defined in settings
        if hasattr(settings, 'EMAIL_SSL_CONTEXT'):
            self.ssl_context = settings.EMAIL_SSL_CONTEXT
