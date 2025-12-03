"""
Shipping Calculation Utilities

Provides helper functions and mappings for calculating shipping costs in quotations.
Includes city-to-region mapping and product-to-capacity key mapping.
"""

import logging

logger = logging.getLogger(__name__)

# ===============================================================================
# CITY-TO-REGION MAPPING
# ===============================================================================

# Comprehensive NZ city/town to region mapping
# Based on the 6 shipping rate areas defined in ShippingSettings
CITY_TO_REGION = {
    # Auckland region
    'auckland': 'Auckland',
    'manukau': 'Auckland',
    'north shore': 'Auckland',
    'waitakere': 'Auckland',
    'papakura': 'Auckland',
    'franklin': 'Auckland',
    'rodney': 'Auckland',
    'hibiscus coast': 'Auckland',
    'albany': 'Auckland',
    'takapuna': 'Auckland',
    'devonport': 'Auckland',
    'newmarket': 'Auckland',
    'ponsonby': 'Auckland',
    'parnell': 'Auckland',
    'mt eden': 'Auckland',
    'mount eden': 'Auckland',
    'epsom': 'Auckland',
    'remuera': 'Auckland',
    'greenlane': 'Auckland',
    'ellerslie': 'Auckland',
    'panmure': 'Auckland',
    'howick': 'Auckland',
    'botany': 'Auckland',
    'pakuranga': 'Auckland',
    'half moon bay': 'Auckland',
    'mt wellington': 'Auckland',
    'onehunga': 'Auckland',
    'mt roskill': 'Auckland',
    'avondale': 'Auckland',
    'new lynn': 'Auckland',
    'glen eden': 'Auckland',
    'henderson': 'Auckland',
    'te atatu': 'Auckland',

    # Waikato region (Auckland Rural rate area)
    'hamilton': 'Waikato',
    'cambridge': 'Waikato',
    'te awamutu': 'Waikato',
    'tokoroa': 'Waikato',
    'taupo': 'Waikato',
    'thames': 'Waikato',
    'whitianga': 'Waikato',
    'coromandel': 'Waikato',
    'paeroa': 'Waikato',
    'matamata': 'Waikato',
    'morrinsville': 'Waikato',
    'huntly': 'Waikato',
    'ngaruawahia': 'Waikato',
    'raglan': 'Waikato',
    'te kuiti': 'Waikato',
    'turangi': 'Waikato',

    # Wellington region (North Island rate area)
    'wellington': 'Wellington',
    'lower hutt': 'Wellington',
    'upper hutt': 'Wellington',
    'porirua': 'Wellington',
    'kapiti': 'Wellington',
    'paraparaumu': 'Wellington',
    'waikanae': 'Wellington',
    'otaki': 'Wellington',
    'masterton': 'Wellington',
    'carterton': 'Wellington',
    'featherston': 'Wellington',
    'martinborough': 'Wellington',
    'greytown': 'Wellington',

    # Northland region (North Island rate area)
    'whangarei': 'Northland',
    'kerikeri': 'Northland',
    'kaitaia': 'Northland',
    'dargaville': 'Northland',
    'kaikohe': 'Northland',
    'mangawhai': 'Northland',
    'paihia': 'Northland',
    'russell': 'Northland',

    # Gisborne region (North Island rate area)
    'gisborne': 'Gisborne',

    # Tairāwhiti region (North Island Rural rate area)
    'ruatoria': 'Tairāwhiti',
    'tokomaru bay': 'Tairāwhiti',

    # Hawke's Bay region (North Island Rural rate area)
    'napier': "Hawke's Bay",
    'hastings': "Hawke's Bay",
    'havelock north': "Hawke's Bay",
    'waipukurau': "Hawke's Bay",
    'waipawa': "Hawke's Bay",
    'wairoa': "Hawke's Bay",

    # Taranaki region (North Island Rural rate area)
    'new plymouth': 'Taranaki',
    'hawera': 'Taranaki',
    'stratford': 'Taranaki',
    'waitara': 'Taranaki',
    'inglewood': 'Taranaki',
    'opunake': 'Taranaki',

    # Manawatū-Whanganui region (North Island Rural rate area)
    'palmerston north': 'Manawatū-Whanganui',
    'whanganui': 'Manawatū-Whanganui',
    'wanganui': 'Manawatū-Whanganui',  # Alternative spelling
    'levin': 'Manawatū-Whanganui',
    'feilding': 'Manawatū-Whanganui',
    'dannevirke': 'Manawatū-Whanganui',
    'pahiatua': 'Manawatū-Whanganui',
    'bulls': 'Manawatū-Whanganui',
    'marton': 'Manawatū-Whanganui',
    'taihape': 'Manawatū-Whanganui',

    # Tasman region (South Island rate area)
    'richmond': 'Tasman',
    'motueka': 'Tasman',
    'takaka': 'Tasman',
    'mapua': 'Tasman',

    # Nelson region (South Island rate area)
    'nelson': 'Nelson',
    'stoke': 'Nelson',

    # Marlborough region (South Island rate area)
    'blenheim': 'Marlborough',
    'picton': 'Marlborough',
    'renwick': 'Marlborough',
    'havelock': 'Marlborough',

    # Canterbury region (South Island rate area)
    'christchurch': 'Canterbury',
    'ashburton': 'Canterbury',
    'timaru': 'Canterbury',
    'rangiora': 'Canterbury',
    'kaiapoi': 'Canterbury',
    'rolleston': 'Canterbury',
    'lincoln': 'Canterbury',
    'prebbleton': 'Canterbury',
    'darfield': 'Canterbury',
    'methven': 'Canterbury',
    'geraldine': 'Canterbury',
    'pleasant point': 'Canterbury',
    'temuka': 'Canterbury',
    'waimate': 'Canterbury',

    # Otago region (South Island Rural rate area)
    'dunedin': 'Otago',
    'queenstown': 'Otago',
    'wanaka': 'Otago',
    'oamaru': 'Otago',
    'cromwell': 'Otago',
    'alexandra': 'Otago',
    'clyde': 'Otago',
    'arrowtown': 'Otago',
    'balclutha': 'Otago',
    'milton': 'Otago',

    # Southland region (South Island Rural rate area)
    'invercargill': 'Southland',
    'gore': 'Southland',
    'winton': 'Southland',
    'mataura': 'Southland',
    'bluff': 'Southland',
    'riverton': 'Southland',
    'te anau': 'Southland',

    # West Coast region (South Island Rural rate area)
    'greymouth': 'West Coast',
    'hokitika': 'West Coast',
    'westport': 'West Coast',
    'reefton': 'West Coast',
    'runanga': 'West Coast',
}


def get_region_from_city(city):
    """
    Get NZ region from city/town name.

    Args:
        city (str): City or town name

    Returns:
        str: NZ region name, or None if not found
    """
    if not city:
        return None

    # Normalize city name
    city_normalized = city.lower().strip()

    # Direct lookup
    if city_normalized in CITY_TO_REGION:
        return CITY_TO_REGION[city_normalized]

    # Fuzzy match - check if city contains any key
    for city_key, region in CITY_TO_REGION.items():
        if city_key in city_normalized or city_normalized in city_key:
            logger.info(f"Fuzzy matched city '{city}' to region '{region}' via key '{city_key}'")
            return region

    logger.warning(f"Could not find region for city: {city}")
    return None


def get_region_from_address(street_address=None, suburb=None, city=None, postcode=None):
    """
    Extract NZ region from customer address fields.

    Tries in order: city → suburb → None
    Postcode-based lookup not implemented (would require postcode-to-region mapping)

    Args:
        street_address (str): Street address (not used for region)
        suburb (str): Suburb name
        city (str): City/town name
        postcode (str): NZ postcode (not used currently)

    Returns:
        str: NZ region name, or None if not found
    """
    # Try city first
    if city:
        region = get_region_from_city(city)
        if region:
            logger.debug(f"Found region '{region}' from city '{city}'")
            return region

    # Fallback to suburb
    if suburb:
        region = get_region_from_city(suburb)
        if region:
            logger.debug(f"Found region '{region}' from suburb '{suburb}'")
            return region

    logger.warning(f"Could not determine region from address: city={city}, suburb={suburb}")
    return None


# ===============================================================================
# PRODUCT-TO-CAPACITY KEY MAPPING
# ===============================================================================

# Mapping of product category names to ShippingSettings capacity keys
CATEGORY_TO_CAPACITY_KEY = {
    # Wholesale categories → capacity keys
    'sideline jackets': 'sideline_jackets',
    'sideline': 'sideline_jackets',
    'jackets': 'sideline_jackets',
    'jacket': 'sideline_jackets',

    'hoodies': 'hoodies',
    'hooded': 'hoodies',
    'hoodie': 'hoodies',
    'sweatshirt': 'hoodies',

    'pants': 'pants',
    'pant': 'pants',
    'trousers': 'pants',
    'trackpants': 'pants',

    'skorts': 'skorts',
    'skort': 'skorts',
    'skirt': 'skorts',

    'polos': 'polos_tees_singlets_dresses',
    'polo': 'polos_tees_singlets_dresses',
    'polo shirt': 'polos_tees_singlets_dresses',

    'tees': 'polos_tees_singlets_dresses',
    'tee': 'polos_tees_singlets_dresses',
    't-shirt': 'polos_tees_singlets_dresses',
    't-shirts': 'polos_tees_singlets_dresses',
    'tshirt': 'polos_tees_singlets_dresses',
    'singlet': 'polos_tees_singlets_dresses',
    'singlets': 'polos_tees_singlets_dresses',
    'dress': 'polos_tees_singlets_dresses',
    'dresses': 'polos_tees_singlets_dresses',

    'shorts': 'netball_touch_tag_league_skirts_shorts',
    'short': 'netball_touch_tag_league_skirts_shorts',
    'netball': 'netball_touch_tag_league_skirts_shorts',
    'touch': 'netball_touch_tag_league_skirts_shorts',
    'tag': 'netball_touch_tag_league_skirts_shorts',
    'league': 'netball_touch_tag_league_skirts_shorts',

    'bags': 'sideline_jackets',  # Use conservative capacity for bags
    'bag': 'sideline_jackets',
    'backpack': 'sideline_jackets',
    'rucksack': 'sideline_jackets',

    'socks': 'tights_socks_caps_bucket_hats_max',
    'sock': 'tights_socks_caps_bucket_hats_max',
    'tights': 'tights_socks_caps_bucket_hats_max',
    'caps': 'tights_socks_caps_bucket_hats_max',
    'cap': 'tights_socks_caps_bucket_hats_max',
    'bucket hat': 'tights_socks_caps_bucket_hats_max',
    'hat': 'tights_socks_caps_bucket_hats_max',

    'jersey': 'jerseys_softball_tops_pants',
    'jerseys': 'jerseys_softball_tops_pants',
    'softball': 'jerseys_softball_tops_pants',
}

# Mapping of product keywords in names to capacity keys
# Used when category is not available or doesn't match
PRODUCT_NAME_TO_CAPACITY_KEY = {
    # Keywords that might appear in product names
    'jacket': 'sideline_jackets',
    'sideline': 'sideline_jackets',
    'blazer': 'sideline_jackets',

    'hoodie': 'hoodies',
    'hooded': 'hoodies',
    'sweat': 'hoodies',

    'pants': 'pants',
    'trouser': 'pants',
    'trackpants': 'pants',
    'track pants': 'pants',

    'skort': 'skorts',
    'skirt': 'skorts',

    'polo': 'polos_tees_singlets_dresses',

    'tee': 'polos_tees_singlets_dresses',
    't-shirt': 'polos_tees_singlets_dresses',
    'tshirt': 'polos_tees_singlets_dresses',
    'singlet': 'polos_tees_singlets_dresses',
    'dress': 'polos_tees_singlets_dresses',

    'shorts': 'netball_touch_tag_league_skirts_shorts',
    'short': 'netball_touch_tag_league_skirts_shorts',
    'netball': 'netball_touch_tag_league_skirts_shorts',
    'touch': 'netball_touch_tag_league_skirts_shorts',
    'tag': 'netball_touch_tag_league_skirts_shorts',
    'league': 'netball_touch_tag_league_skirts_shorts',

    'bag': 'sideline_jackets',  # Conservative capacity for bags
    'backpack': 'sideline_jackets',
    'rucksack': 'sideline_jackets',

    'sock': 'tights_socks_caps_bucket_hats_max',
    'tight': 'tights_socks_caps_bucket_hats_max',
    'cap': 'tights_socks_caps_bucket_hats_max',
    'hat': 'tights_socks_caps_bucket_hats_max',

    'jersey': 'jerseys_softball_tops_pants',
    'softball': 'jerseys_softball_tops_pants',

    # BallStore specific keywords (sporting goods/equipment)
    # Note: More specific matches should come before generic ones
    'basketball': 'sideline_jackets',  # Basketballs are larger
    'football': 'sideline_jackets',
    'soccer ball': 'sideline_jackets',
    'rugby ball': 'sideline_jackets',
    'volleyball': 'sideline_jackets',
    'table tennis': 'tights_socks_caps_bucket_hats_max',  # Table tennis balls are small
    'ping pong': 'tights_socks_caps_bucket_hats_max',
    'tennis ball': 'tights_socks_caps_bucket_hats_max',
    'cricket ball': 'tights_socks_caps_bucket_hats_max',
    'indoor': 'tights_socks_caps_bucket_hats_max',  # Indoor balls (table tennis, etc.) tend to be small
    'ball': 'tights_socks_caps_bucket_hats_max',  # Generic balls are small items
    'cone': 'tights_socks_caps_bucket_hats_max',  # Cones are stackable/small
    'cones': 'tights_socks_caps_bucket_hats_max',
    'marker': 'tights_socks_caps_bucket_hats_max',
    'markers': 'tights_socks_caps_bucket_hats_max',
    'whistle': 'tights_socks_caps_bucket_hats_max',
    'pump': 'tights_socks_caps_bucket_hats_max',
    'bibs': 'polos_tees_singlets_dresses',  # Training bibs similar to singlets
    'bib': 'polos_tees_singlets_dresses',
}


def get_capacity_key_from_category(category_name):
    """
    Map product category name to ShippingSettings capacity key.

    Args:
        category_name (str): Product category name

    Returns:
        str: Capacity key, or None if not found
    """
    if not category_name:
        return None

    category_normalized = category_name.lower().strip()

    # Direct lookup
    if category_normalized in CATEGORY_TO_CAPACITY_KEY:
        return CATEGORY_TO_CAPACITY_KEY[category_normalized]

    # Fuzzy match
    for cat_key, capacity_key in CATEGORY_TO_CAPACITY_KEY.items():
        if cat_key in category_normalized or category_normalized in cat_key:
            logger.debug(f"Fuzzy matched category '{category_name}' to capacity key '{capacity_key}'")
            return capacity_key

    return None


def get_capacity_key_from_product_name(product_name):
    """
    Map product name to ShippingSettings capacity key based on keywords.

    Args:
        product_name (str): Product name

    Returns:
        str: Capacity key, or None if not found
    """
    if not product_name:
        return None

    product_normalized = product_name.lower().strip()

    # Check for keywords in product name
    for keyword, capacity_key in PRODUCT_NAME_TO_CAPACITY_KEY.items():
        if keyword in product_normalized:
            logger.debug(f"Matched product '{product_name}' to capacity key '{capacity_key}' via keyword '{keyword}'")
            return capacity_key

    return None


def get_capacity_key_for_product(product):
    """
    Get ShippingSettings capacity key for any product type.

    Tries in order:
    1. Product category (if available)
    2. Product name keywords
    3. Fallback to 'sideline_jackets' (most conservative - smallest capacity)

    Args:
        product: Product instance (WholesaleProduct, LottoProduct, SASProduct, TUSProduct, BallStoreProduct, or BespokeProduct)

    Returns:
        str: Capacity key (always returns a valid key, never None)
    """
    # Try category first (WholesaleProduct has primary_category)
    if hasattr(product, 'primary_category') and product.primary_category:
        category_name = product.primary_category.name
        capacity_key = get_capacity_key_from_category(category_name)
        if capacity_key:
            logger.debug(f"Got capacity key '{capacity_key}' from category '{category_name}' for product {product.id}")
            return capacity_key

    # Try categories for BallStoreProduct (many-to-many relationship)
    if hasattr(product, 'categories') and hasattr(product.categories, 'all'):
        for category in product.categories.all():
            category_name = category.name
            capacity_key = get_capacity_key_from_category(category_name)
            if capacity_key:
                logger.debug(f"Got capacity key '{capacity_key}' from BallStore category '{category_name}' for product {product.id}")
                return capacity_key

    # Try product name keywords
    if hasattr(product, 'name') and product.name:
        capacity_key = get_capacity_key_from_product_name(product.name)
        if capacity_key:
            logger.debug(f"Got capacity key '{capacity_key}' from name '{product.name}' for product {product.id}")
            return capacity_key

    # Fallback to most conservative option
    logger.info(f"No specific capacity key found for product {product.id} ({getattr(product, 'name', 'Unknown')}), using 'sideline_jackets' as fallback")
    return 'sideline_jackets'
