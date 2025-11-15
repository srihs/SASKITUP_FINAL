"""
Cin7 API Service for Price Update System

Handles:
- Authentication with Cin7 API
- Rate limiting (3 calls/sec, 60 calls/min, 5000 calls/day)
- Product fetching with pagination
- Price data extraction (cost_price, RRP)
- Error handling and retry logic

Author: Claude Code
Date: 2025-10-10
"""

import logging
import requests
import base64
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation
from decouple import config
from requests.exceptions import RequestException
from django.utils import timezone

logger = logging.getLogger(__name__)


class Cin7ApiService:
    """
    Service for interacting with Cin7 API v1

    Rate Limits:
    - 3 calls per second
    - 60 calls per minute
    - 5000 calls per day

    API Endpoints:
    - GET v1/Products - Get products with filtering
    - GET v1/Products/{id} - Get single product details
    """

    # Rate limiting configuration
    MAX_CALLS_PER_SECOND = 3
    MAX_CALLS_PER_MINUTE = 60
    MAX_CALLS_PER_DAY = 5000

    def __init__(self):
        """Initialize Cin7 API service with credentials from .env"""
        self.api_url = config('CIN7_API_URL', default='https://api.cin7.com/api/v1')
        self.username = config('CIN7_API_USERNAME', default='')
        self.api_key = config('CIN7_API_KEY', default='')

        if not all([self.api_url, self.username, self.api_key]):
            raise ValueError("Cin7 API credentials not configured in .env file")

        # Create Basic Auth header
        credentials = f"{self.username}:{self.api_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        self.headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Rate limiting tracking
        self.call_times = []
        self.daily_calls = 0

        logger.info(f"Cin7ApiService initialized: {self.api_url}")

    def _enforce_rate_limit(self):
        """Enforce rate limits before making API calls"""
        current_time = time.time()

        # Remove calls older than 1 minute
        self.call_times = [t for t in self.call_times if current_time - t < 60]

        # Check per-second limit (3 calls)
        recent_calls = [t for t in self.call_times if current_time - t < 1]
        if len(recent_calls) >= self.MAX_CALLS_PER_SECOND:
            sleep_time = 1.0 - (current_time - recent_calls[0])
            if sleep_time > 0:
                logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)

        # Check per-minute limit (60 calls)
        if len(self.call_times) >= self.MAX_CALLS_PER_MINUTE:
            sleep_time = 60.0 - (current_time - self.call_times[0])
            if sleep_time > 0:
                logger.warning(f"Rate limit: sleeping {sleep_time:.2f}s (per-minute)")
                time.sleep(sleep_time)
                # Remove oldest call after waiting
                self.call_times = [t for t in self.call_times if current_time + sleep_time - t < 60]

        # Check daily limit
        if self.daily_calls >= self.MAX_CALLS_PER_DAY:
            raise Exception("Daily API call limit reached (5000 calls)")

        # Record this call
        self.call_times.append(time.time())
        self.daily_calls += 1

    def _make_request(self, endpoint: str, params: Dict = None, max_retries: int = 3) -> Optional[Dict]:
        """
        Make authenticated API request with retry logic

        Args:
            endpoint: API endpoint (e.g., 'Products' or 'Products/123')
            params: Query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response or None on failure
        """
        if params is None:
            params = {}

        url = f"{self.api_url.rstrip('/')}/{endpoint.lstrip('/')}"

        for attempt in range(max_retries):
            try:
                self._enforce_rate_limit()

                logger.debug(f"Cin7 API request: {url} (params: {params})")
                response = requests.get(url, headers=self.headers, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("Cin7 API authentication failed")
                    return None
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limited (HTTP 429), waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Cin7 API error {response.status_code}: {response.text}")
                    return None

            except RequestException as e:
                logger.error(f"Cin7 API request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)

        return None

    def fetch_all_products(self, price_type: str = None, where_clause: str = None, progress_callback=None) -> Tuple[List[Dict], int, int]:
        """
        Fetch all products from Cin7 with pagination

        Args:
            price_type: One of 'TUS', 'LOTTO', 'SAS', 'Wholesale' (optional filtering)
            where_clause: Optional CIN7 API where clause for filtering (e.g., 'category = "Quotation Base Library"')
            progress_callback: Optional function(current, total, message) for progress updates

        Returns:
            Tuple of (products_list, total_fetched, total_available)
        """
        # Parameter validation to prevent common errors
        if where_clause is not None and not isinstance(where_clause, str):
            raise TypeError(f"where_clause must be a string or None, got {type(where_clause).__name__}")

        if progress_callback is not None and not callable(progress_callback):
            raise TypeError(f"progress_callback must be callable or None, got {type(progress_callback).__name__}")

        all_products = []
        page = 1
        rows_per_page = 100  # Cin7 max is 250, but 100 is safer for rate limiting
        total_available = None

        logger.info(f"Fetching all products from Cin7 (price_type: {price_type}, where: {where_clause})...")
        start_time = timezone.now()

        while True:
            params = {
                'page': page,
                'rows': rows_per_page,
            }

            # Add where clause filtering if provided
            if where_clause:
                params['where'] = where_clause

            response = self._make_request('Products', params)

            if not response:
                logger.error(f"Failed to fetch page {page}")
                break

            # Cin7 may return total count in first response
            if total_available is None:
                # Check for total count in response (format varies by Cin7 version)
                if isinstance(response, list):
                    # Response is directly an array of products
                    products = response
                    total_available = None  # Unknown total
                elif isinstance(response, dict) and 'Items' in response:
                    # Response has Items array and possibly Total
                    products = response.get('Items', [])
                    total_available = response.get('Total')
                else:
                    products = []

                if total_available:
                    logger.info(f"Total products available: {total_available}")
            else:
                # Subsequent pages
                if isinstance(response, list):
                    products = response
                elif isinstance(response, dict) and 'Items' in response:
                    products = response.get('Items', [])
                else:
                    products = []

            if not products:
                logger.info(f"No more products on page {page}")
                break

            all_products.extend(products)
            logger.info(f"Fetched page {page}: {len(products)} products (total: {len(all_products)})")

            # Progress callback
            if progress_callback:
                if total_available:
                    progress_callback(len(all_products), total_available, f"Fetching page {page}...")
                else:
                    progress_callback(len(all_products), len(all_products) + 100, f"Fetching page {page}...")

            # Check if we've reached the end
            if len(products) < rows_per_page:
                logger.info("Last page reached (fewer products than requested)")
                break

            # Safety limit to prevent infinite loops
            if page > 200:
                logger.warning("Safety limit reached (200 pages)")
                break

            page += 1

        elapsed = (timezone.now() - start_time).total_seconds()
        logger.info(f"Fetched {len(all_products)} products from Cin7 in {elapsed:.2f}s")

        return all_products, len(all_products), total_available or len(all_products)

    def extract_product_options(self, product: Dict) -> list:
        """
        Extract all product options (variants) from a Cin7 product.

        Each productOption represents a size/color variant with its own:
        - SKU (code)
        - Barcode
        - Prices (cost, retail, wholesale)

        Args:
            product: Cin7 product dictionary with productOptions array

        Returns:
            List of extracted price data dictionaries, one per productOption
        """
        extracted_options = []
        product_options = product.get('productOptions', [])

        # If no productOptions, treat the product itself as a single option
        if not product_options:
            logger.warning(f"Product {product.get('id')} has no productOptions")
            return []

        for option in product_options:
            # Skip inactive options (only process Active or Primary status)
            option_status = option.get('status', '').lower()
            if option_status not in ['active', 'primary']:
                continue

            # Extract price columns
            price_columns = option.get('priceColumns', {})

            # Extract cost price
            cost_price = None
            cost_price_raw = price_columns.get('costNZD')
            if cost_price_raw:
                try:
                    cost_price = Decimal(str(cost_price_raw))
                    if cost_price < 0:
                        cost_price = None
                except (InvalidOperation, ValueError):
                    pass

            # Extract retail price
            rrp = None
            rrp_raw = price_columns.get('retailNZD') or option.get('retailPrice')
            if rrp_raw:
                try:
                    rrp = Decimal(str(rrp_raw))
                    if rrp < 0:
                        rrp = None
                except (InvalidOperation, ValueError):
                    pass

            # Calculate 75% margin price
            margin_75_price = None
            if cost_price and cost_price > 0:
                try:
                    margin_75_price = cost_price / Decimal('0.25')
                    margin_75_price = margin_75_price.quantize(Decimal('0.01'))
                except (InvalidOperation, ZeroDivisionError):
                    pass

            # Calculate discount percentage
            discount_percentage = None
            if margin_75_price and rrp and margin_75_price > 0:
                try:
                    discount = ((margin_75_price - rrp) / margin_75_price) * 100
                    discount_percentage = max(Decimal('0'), discount)
                    discount_percentage = discount_percentage.quantize(Decimal('0.01'))
                except (InvalidOperation, ZeroDivisionError):
                    pass

            extracted_options.append({
                'cin7_id': option.get('id'),  # Use productOption id, not product id
                'product_id': product.get('id'),  # Parent product id
                'sku': (option.get('code') or '').strip(),
                'barcode': (option.get('barcode') or '').strip(),
                'style_code': (product.get('styleCode') or '').strip(),
                'product_name': f"{product.get('name', '')} - {option.get('option1', '')}".strip(),
                'cost': cost_price,
                'current_retail_nzd_incl': rrp,
                'margin_75_price': margin_75_price,
                'discount_percentage': discount_percentage,
                'category': (product.get('category') or '').strip(),
                'brand': (product.get('brand') or '').strip(),
                'stock_available': option.get('stockAvailable'),
                'product_code': (option.get('code') or '').strip(),
            })

        return extracted_options

    def test_connection(self) -> bool:
        """Test connection to Cin7 API"""
        try:
            logger.info("Testing Cin7 API connection...")
            response = self._make_request('Products', {'rows': 1, 'page': 1})

            if response is not None:
                logger.info("✓ Cin7 API connection test successful")
                return True
            else:
                logger.error("✗ Cin7 API connection test failed")
                return False
        except Exception as e:
            logger.error(f"✗ Cin7 API connection test failed: {e}")
            return False
