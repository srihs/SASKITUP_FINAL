"""
Custom template tags for image proxy functionality.

Provides filters to generate proxied image URLs for password-protected images.
"""

from django import template
from django.urls import reverse
from urllib.parse import urlencode

register = template.Library()


@register.filter
def proxy_image_url(image_url):
    """
    Generate a proxy URL for password-protected images.

    This filter checks if the image URL is from a protected domain
    and generates a proxy URL if needed.

    Args:
        image_url: Original image URL

    Returns:
        Proxied URL or original URL if not from protected domain

    Usage:
        {{ product.image_url|proxy_image_url }}
    """
    if not image_url:
        return ''

    # Check if image is from a password-protected domain
    protected_domains = ['dev-lottosports.it.sas.co.nz', 'theballstore.co.nz']

    if any(domain in image_url for domain in protected_domains):
        # Generate proxy URL
        proxy_url = reverse('quotations:proxy-image')
        params = urlencode({'url': image_url})
        return f"{proxy_url}?{params}"

    # Return original URL if not from protected domain
    return image_url
