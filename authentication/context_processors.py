"""
Context processors for authentication app

Provides global template context variables
"""
from django.conf import settings


def google_api_key(request):
    """
    Add Google Maps API key to template context

    Usage in templates:
        {{ GOOGLE_MAPS_API_KEY }}

    Args:
        request: Django HTTP request object

    Returns:
        dict: Context dictionary with GOOGLE_MAPS_API_KEY
    """
    return {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    }
