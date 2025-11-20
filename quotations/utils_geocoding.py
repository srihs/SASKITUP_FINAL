"""
Geocoding Utilities

Provides helper functions for converting postcodes to city names using Google Geocoding API.
Includes caching to minimize API calls and improve performance.
"""

import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def get_city_from_postcode(postcode, country='NZ'):
    """
    Use Google Geocoding API to get city from postcode.

    Args:
        postcode (str): Postal code (e.g., '2121', '7010')
        country (str): Country code (default: 'NZ' for New Zealand)

    Returns:
        dict: {
            'city': str,              # City/locality name
            'formatted_address': str  # Full formatted address
        }
        or None if geocoding fails or API key not configured
    """
    if not postcode:
        logger.warning("get_city_from_postcode called with empty postcode")
        return None

    # Check for API key
    api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
    if not api_key:
        logger.warning("Google Maps API key not configured - geocoding disabled")
        return None

    # Normalize postcode
    postcode = str(postcode).strip()

    # Check cache first (cache for 24 hours)
    cache_key = f'geocode_postcode_{country}_{postcode}'
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.debug(f"Cache hit for postcode {postcode}: {cached_result}")
        return cached_result

    # Google Geocoding API endpoint
    url = 'https://maps.googleapis.com/maps/api/geocode/json'
    params = {
        'address': f"{postcode}, {country}",
        'key': api_key
    }

    try:
        logger.info(f"Geocoding postcode {postcode} for country {country}")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()

        data = response.json()

        if data['status'] == 'OK' and data['results']:
            result = data['results'][0]

            # Extract city/locality from address components
            city = None
            region = None

            for component in result['address_components']:
                # Try to find locality (city/town)
                if 'locality' in component['types']:
                    city = component['long_name']
                # Also capture administrative area (region) as fallback
                elif 'administrative_area_level_1' in component['types']:
                    region = component['long_name']

            # Use region if no locality found (for rural areas)
            if not city and region:
                city = region
                logger.info(f"No locality found for postcode {postcode}, using region: {region}")

            if city:
                geocode_result = {
                    'city': city,
                    'formatted_address': result.get('formatted_address', '')
                }

                # Cache the result for 24 hours (86400 seconds)
                cache.set(cache_key, geocode_result, timeout=86400)

                logger.info(f"Successfully geocoded postcode {postcode} to city: {city}")
                return geocode_result
            else:
                logger.warning(f"No city/locality found in geocoding results for postcode {postcode}")
                return None

        elif data['status'] == 'ZERO_RESULTS':
            logger.warning(f"Google Geocoding returned no results for postcode {postcode}")
            return None

        else:
            logger.error(f"Google Geocoding API error: {data['status']} for postcode {postcode}")
            return None

    except requests.RequestException as e:
        logger.error(f"Network error during geocoding for postcode {postcode}: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error during geocoding for postcode {postcode}: {e}")
        return None
