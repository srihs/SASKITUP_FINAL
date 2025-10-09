import logging
import requests
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from django.conf import settings
from requests.exceptions import RequestException
import time
import os
from woocommerce import API
from decouple import config
import concurrent.futures

logger = logging.getLogger(__name__)


class TUSWooCommerceService:
    """
    Service class for interacting with TUS WooCommerce API
    Handles all API communication for school uniform synchronization
    """

    def __init__(self):
        """Initialize the TUS WooCommerce API client"""
        self.base_url = config('TUS_WOOCOMMERCE_API_URL', default='')
        self.consumer_key = config('TUS_WOOCOMMERCE_API_CONSUMER_KEY', default='')
        self.consumer_secret = config('TUS_WOOCOMMERCE_API_SECRET', default='')

        if not all([self.base_url, self.consumer_key, self.consumer_secret]):
            raise ValueError("TUS WooCommerce API credentials not found in environment variables")

        # Initialize WooCommerce API client
        self.wcapi = API(
            url=self.base_url.replace('/wp-json/wc/v3/', ''),  # Remove the API path as the library adds it
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            version="wc/v3",
            timeout=30
        )

        # Rate limiting (reduced for parallel requests)
        self.last_request_time = 0
        self.min_request_interval = 0.2  # Reduced from 0.5s to 0.2s for parallel requests

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2

        logger.info(f"Initialized TUS WooCommerce service for: {self.base_url}")

    def _rate_limit(self):
        """Implement rate limiting to avoid overwhelming the API"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict = None, method: str = 'GET') -> Optional[Dict]:
        """
        Make a request to the WooCommerce API with retry logic

        Args:
            endpoint: API endpoint (e.g., 'products/categories')
            params: Query parameters
            method: HTTP method (GET, POST, PUT, DELETE)

        Returns:
            Response data or None if failed
        """
        self._rate_limit()

        for attempt in range(self.max_retries):
            try:
                if method == 'GET':
                    response = self.wcapi.get(endpoint, params=params)
                elif method == 'POST':
                    response = self.wcapi.post(endpoint, data=params)
                elif method == 'PUT':
                    response = self.wcapi.put(endpoint, data=params)
                elif method == 'DELETE':
                    response = self.wcapi.delete(endpoint)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Resource not found: {endpoint}")
                    return None
                else:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")

            except RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue

            except Exception as e:
                logger.error(f"Unexpected error making request: {e}")
                return None

        return None

    def test_connection(self) -> bool:
        """Test the connection to the WooCommerce API"""
        try:
            response = self._make_request('system_status')
            if response:
                logger.info("Successfully connected to TUS WooCommerce API")
                return True
            else:
                logger.error("Failed to connect to TUS WooCommerce API")
                return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_all_categories(self, per_page: int = 100) -> List[Dict]:
        """
        Fetch all product categories from WooCommerce

        Args:
            per_page: Number of categories per page

        Returns:
            List of category dictionaries
        """
        all_categories = []
        page = 1

        while True:
            params = {
                'per_page': per_page,
                'page': page,
                'orderby': 'name',
                'order': 'asc'
            }

            logger.info(f"Fetching categories page {page}")
            categories = self._make_request('products/categories', params)

            if not categories:
                break

            all_categories.extend(categories)

            if len(categories) < per_page:
                break

            page += 1

        logger.info(f"Fetched {len(all_categories)} total categories")
        return all_categories

    def get_categories_by_parent(self, parent_id: int, per_page: int = 100) -> List[Dict]:
        """
        Fetch categories that have a specific parent

        Args:
            parent_id: Parent category ID
            per_page: Number of categories per page

        Returns:
            List of category dictionaries
        """
        all_categories = []
        page = 1

        while True:
            params = {
                'parent': parent_id,
                'per_page': per_page,
                'page': page,
                'orderby': 'name',
                'order': 'asc'
            }

            logger.info(f"Fetching categories with parent {parent_id}, page {page}")
            categories = self._make_request('products/categories', params)

            if not categories:
                break

            all_categories.extend(categories)

            if len(categories) < per_page:
                break

            page += 1

        logger.info(f"Fetched {len(all_categories)} categories for parent {parent_id}")
        return all_categories

    def get_category(self, category_id: int) -> Optional[Dict]:
        """
        Fetch a single category by ID

        Args:
            category_id: WooCommerce category ID

        Returns:
            Category dictionary or None
        """
        return self._make_request(f'products/categories/{category_id}')

    def get_products_by_category(self, category_id: int, per_page: int = 100) -> List[Dict]:
        """
        Fetch all products in a specific category

        Args:
            category_id: WooCommerce category ID
            per_page: Number of products per page

        Returns:
            List of product dictionaries
        """
        all_products = []
        page = 1

        while True:
            params = {
                'category': category_id,
                'per_page': per_page,
                'page': page,
                'status': 'publish'
            }

            logger.info(f"Fetching products for category {category_id}, page {page}")
            products = self._make_request('products', params)

            if not products:
                break

            all_products.extend(products)

            if len(products) < per_page:
                break

            page += 1

        logger.info(f"Fetched {len(all_products)} products for category {category_id}")
        return all_products

    def get_product(self, product_id: int) -> Optional[Dict]:
        """
        Fetch a single product by ID

        Args:
            product_id: WooCommerce product ID

        Returns:
            Product dictionary or None
        """
        return self._make_request(f'products/{product_id}')

    def get_product_variations(self, product_id: int, per_page: int = 100) -> List[Dict]:
        """
        Fetch all variations for a variable product

        Args:
            product_id: WooCommerce product ID
            per_page: Number of variations per page

        Returns:
            List of variation dictionaries
        """
        all_variations = []
        page = 1

        while True:
            params = {
                'per_page': per_page,
                'page': page
            }

            logger.debug(f"Fetching variations for product {product_id}, page {page}")
            variations = self._make_request(f'products/{product_id}/variations', params)

            if not variations:
                break

            all_variations.extend(variations)

            if len(variations) < per_page:
                break

            page += 1

        logger.debug(f"Fetched {len(all_variations)} variations for product {product_id}")
        return all_variations

    def analyze_category_hierarchy(self) -> Dict:
        """
        Analyze the category hierarchy to understand locations and schools structure

        Returns:
            Dictionary with hierarchy analysis
        """
        all_categories = self.get_all_categories()

        analysis = {
            'total_categories': len(all_categories),
            'root_categories': [],
            'location_categories': [],
            'school_categories': [],
            'general_categories': [],
            'product_categories': [],
            'hierarchy': {}
        }

        # Build hierarchy map
        category_map = {cat['id']: cat for cat in all_categories}

        for category in all_categories:
            # Root level categories (no parent)
            if category['parent'] == 0:
                analysis['root_categories'].append({
                    'id': category['id'],
                    'name': category['name'],
                    'slug': category['slug'],
                    'count': category['count']
                })

                # Analyze category name to determine type
                name_lower = category['name'].lower()
                slug_lower = category['slug'].lower()

                # Check if it's a location (common NZ location names)
                location_indicators = [
                    # Actual TUS store locations
                    'manukau', 'papakura', 'pukekohe', 'avondale', 'penrose',
                    'kerikeri', 'pakuranga', 'rotorua', 'cambridge', 'helensville',
                    'kaitaia', 'long bay', 'matamata', 'mt albert', 'north harbour'
                ]
                is_location = any(loc in name_lower or loc in slug_lower for loc in location_indicators)

                if is_location or 'location' in slug_lower:
                    analysis['location_categories'].append(category)

        # Find schools (categories under locations)
        for category in all_categories:
            if category['parent'] != 0:
                parent_cat = category_map.get(category['parent'])
                if parent_cat:
                    # Check if parent is a location
                    parent_name_lower = parent_cat['name'].lower()
                    parent_slug_lower = parent_cat['slug'].lower()

                    # School indicators
                    school_indicators = [
                        'college', 'school', 'high', 'primary', 'intermediate',
                        'academy', 'grammar', 'preparatory', 'kindergarten'
                    ]
                    is_school = any(indicator in category['name'].lower() for indicator in school_indicators)

                    if is_school:
                        analysis['school_categories'].append({
                            'id': category['id'],
                            'name': category['name'],
                            'slug': category['slug'],
                            'parent_id': category['parent'],
                            'parent_name': parent_cat['name'],
                            'count': category['count']
                        })

        # Log analysis summary
        logger.info("TUS Category Hierarchy Analysis:")
        logger.info(f"Total categories: {analysis['total_categories']}")
        logger.info(f"Root categories: {len(analysis['root_categories'])}")
        logger.info(f"Location categories: {len(analysis['location_categories'])}")
        logger.info(f"School categories: {len(analysis['school_categories'])}")

        return analysis

    def identify_locations_and_schools(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Identify location and school categories in the WooCommerce structure

        Returns:
            Tuple of (locations, schools) lists
        """
        all_categories = self.get_all_categories()
        category_map = {cat['id']: cat for cat in all_categories}

        locations = []
        schools = []

        # Common NZ location names
        location_keywords = [
            # Actual TUS store locations
            'manukau', 'papakura', 'pukekohe', 'avondale', 'penrose',
            'kerikeri', 'pakuranga', 'rotorua', 'cambridge', 'helensville',
            'kaitaia', 'long bay', 'matamata', 'mt albert', 'north harbour'
        ]

        # School type keywords
        school_keywords = [
            'college', 'school', 'high', 'primary', 'intermediate',
            'academy', 'grammar', 'preparatory', 'kindergarten', 'kura'
        ]

        for category in all_categories:
            name_lower = category['name'].lower()
            slug_lower = category['slug'].lower()

            # Check if it's a location
            is_location = any(keyword in name_lower or keyword in slug_lower for keyword in location_keywords)

            # Check if it's a school
            is_school = any(keyword in name_lower for keyword in school_keywords)

            if is_location and category['parent'] == 0:
                # Root level location
                locations.append(category)
            elif is_school:
                # School category
                parent_id = category['parent']
                if parent_id in category_map:
                    parent = category_map[parent_id]
                    school_info = {
                        **category,
                        'location_id': parent_id,
                        'location_name': parent['name']
                    }
                    schools.append(school_info)
                else:
                    schools.append(category)

        logger.info(f"Identified {len(locations)} locations and {len(schools)} schools")
        return locations, schools

    def parse_price(self, price_value) -> Decimal:
        """
        Parse price value to Decimal

        Args:
            price_value: Price value from API (can be string or number)

        Returns:
            Decimal price value
        """
        if price_value is None or price_value == '':
            return Decimal('0.00')

        try:
            # Remove any currency symbols and whitespace
            if isinstance(price_value, str):
                price_value = price_value.replace('$', '').replace(',', '').strip()
            return Decimal(str(price_value))
        except:
            logger.warning(f"Could not parse price: {price_value}")
            return Decimal('0.00')

    def get_products_by_categories_parallel(self, category_ids: List[int], max_workers: int = 5) -> Dict[int, List[Dict]]:
        """
        Fetch products for multiple categories in parallel.

        Args:
            category_ids: List of WooCommerce category IDs
            max_workers: Number of concurrent API requests (default: 5)

        Returns:
            Dictionary mapping category_id to list of products
        """
        all_products = {}

        def fetch_category_products(cat_id: int) -> tuple:
            """Fetch products for a single category"""
            try:
                products = self.get_products_by_category(cat_id)
                return (cat_id, products)
            except Exception as e:
                logger.error(f"Failed to fetch products for category {cat_id}: {e}")
                return (cat_id, [])

        # Use ThreadPoolExecutor for parallel requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all category fetch tasks
            future_to_category = {
                executor.submit(fetch_category_products, cat_id): cat_id
                for cat_id in category_ids
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_category):
                cat_id, products = future.result()
                all_products[cat_id] = products
                logger.info(f"✓ Fetched {len(products)} products for category {cat_id}")

        return all_products

    def get_variations_parallel(self, product_ids: List[int], max_workers: int = 5) -> Dict[int, List[Dict]]:
        """
        Fetch variations for multiple products in parallel.

        Args:
            product_ids: List of WooCommerce product IDs
            max_workers: Number of concurrent API requests (default: 5)

        Returns:
            Dictionary mapping product_id to list of variations
        """
        all_variations = {}

        def fetch_product_variations(prod_id: int) -> tuple:
            """Fetch variations for a single product"""
            try:
                variations = self.get_product_variations(prod_id)
                return (prod_id, variations)
            except Exception as e:
                logger.error(f"Failed to fetch variations for product {prod_id}: {e}")
                return (prod_id, [])

        # Use ThreadPoolExecutor for parallel requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all variation fetch tasks
            future_to_product = {
                executor.submit(fetch_product_variations, prod_id): prod_id
                for prod_id in product_ids
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_product):
                prod_id, variations = future.result()
                all_variations[prod_id] = variations

        return all_variations

    def get_all_products_parallel(self, per_page: int = 100, max_workers: int = 5) -> List[Dict]:
        """
        Fetch all products using parallel pagination.

        Args:
            per_page: Items per page
            max_workers: Number of concurrent requests

        Returns:
            List of all products
        """
        # First request to get total pages
        params = {'per_page': per_page, 'page': 1}
        first_page = self._make_request('products', params)

        if not first_page:
            return []

        # Get total pages from headers (WooCommerce returns this)
        total_pages = 1  # Default to 1 if header not available

        all_products = first_page.copy()

        if total_pages > 1:
            # Fetch remaining pages in parallel
            page_numbers = range(2, total_pages + 1)

            def fetch_page(page_num: int) -> List[Dict]:
                """Fetch a single page"""
                try:
                    params = {'per_page': per_page, 'page': page_num}
                    return self._make_request('products', params)
                except Exception as e:
                    logger.error(f"Failed to fetch page {page_num}: {e}")
                    return []

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_page = {
                    executor.submit(fetch_page, page_num): page_num
                    for page_num in page_numbers
                }

                for future in concurrent.futures.as_completed(future_to_page):
                    page_products = future.result()
                    all_products.extend(page_products)

        logger.info(f"✓ Fetched total of {len(all_products)} products across {total_pages} pages")
        return all_products