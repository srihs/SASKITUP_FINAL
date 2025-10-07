from django import template
from django.urls import reverse
from urllib.parse import urlencode
from clubs.utils import get_lotto_domain_list
import logging

logger = logging.getLogger(__name__)

register = template.Library()


@register.filter
def proxy_image_url(image_url):
    """
    Convert external image URL to use the internal image proxy

    Args:
        image_url: External image URL

    Returns:
        Proxied image URL or None if invalid
    """
    if not image_url:
        return None

    # Check if this is a URL that needs proxying - use dynamic domain list
    domains_to_proxy = get_lotto_domain_list()
    
    # If URL doesn't need proxying, return as-is
    from urllib.parse import urlparse
    try:
        domain = urlparse(image_url).netloc.lower()
        if domain not in domains_to_proxy:
            return image_url
    except Exception:
        logger.warning(f"Could not parse image URL: {image_url}")
        return image_url
    
    # Generate proxy URL
    try:
        proxy_url = reverse('clubs:proxy-image')
        params = urlencode({'url': image_url})
        return f"{proxy_url}?{params}"
    except Exception as e:
        logger.error(f"Error generating proxy URL for {image_url}: {str(e)}")
        return image_url


@register.simple_tag
def club_image_or_placeholder(club):
    """
    Get club logo image URL with fallback to placeholder
    
    Args:
        club: Club object
        
    Returns:
        Image URL (proxied if needed) or placeholder class
    """
    if club.logo:
        proxied_url = proxy_image_url(club.logo)
        return {'type': 'image', 'url': proxied_url}
    else:
        return {'type': 'placeholder', 'text': club.name[0].upper() if club.name else 'C'}


@register.simple_tag
def product_image_or_placeholder(product):
    """
    Get product image URL with fallback to placeholder
    
    Args:
        product: Product object
        
    Returns:
        Image URL (proxied if needed) or placeholder class
    """
    if product.image:
        proxied_url = proxy_image_url(product.image)
        return {'type': 'image', 'url': proxied_url}
    else:
        return {'type': 'placeholder', 'text': product.name[0].upper() if product.name else 'P'}