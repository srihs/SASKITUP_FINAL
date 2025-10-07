"""
URL utility functions for the clubs app
"""
from django.conf import settings
from urllib.parse import urlparse, urlunparse
import logging

logger = logging.getLogger(__name__)


def normalize_lotto_image_url(image_url):
    """
    Normalize LOTTO image URLs to use the configured site URL.
    Handles both production and dev URLs.

    Args:
        image_url: Original image URL (may be production or dev)

    Returns:
        Normalized URL using LOTTO_SITE_URL from settings, or None if invalid
    """
    if not image_url:
        return None

    # Parse the URL
    try:
        parsed = urlparse(image_url)
    except Exception as e:
        logger.warning(f"Could not parse image URL: {image_url}. Error: {e}")
        return None

    # Known LOTTO domains to replace
    lotto_domains = [
        'www.lottosports.co.nz',
        'lottosports.co.nz',
        'dev-lottosports.it.sas.co.nz',
    ]

    # If URL is from a LOTTO domain, replace with configured domain
    if any(domain in parsed.netloc for domain in lotto_domains):
        try:
            configured_url = settings.LOTTO_SITE_URL
            configured_parsed = urlparse(configured_url)

            # Replace scheme and netloc, keep path and other components
            normalized = urlunparse((
                configured_parsed.scheme,
                configured_parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))

            return normalized
        except Exception as e:
            logger.error(f"Error normalizing LOTTO URL {image_url}: {e}")
            return image_url

    # Return original URL if not a LOTTO domain
    return image_url


def get_lotto_domain_list():
    """
    Get list of allowed LOTTO domains including configured domain

    Returns:
        List of allowed domain strings
    """
    # Base list of known LOTTO domains
    domains = [
        'www.lottosports.co.nz',
        'lottosports.co.nz',
        'dev-lottosports.it.sas.co.nz',
    ]

    # Add configured domain if different
    try:
        configured_url = settings.LOTTO_SITE_URL
        configured_domain = urlparse(configured_url).netloc
        if configured_domain and configured_domain not in domains:
            domains.append(configured_domain)
    except Exception:
        pass

    return domains
