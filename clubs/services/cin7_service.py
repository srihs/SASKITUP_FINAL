"""
CIN7 API Service for Wholesale Schools Integration

This service handles all API communication with CIN7 for wholesale schools data.
It fetches products from the "Wholesale Schools" category and organizes them by school.
"""

import logging
import requests
import base64
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.conf import settings
from requests.exceptions import RequestException
import time
from decouple import config

logger = logging.getLogger(__name__)


class CIN7Service:
    """
    Service class for interacting with CIN7 API
    Handles authentication and data retrieval for wholesale schools
    """

    def __init__(self):
        """Initialize the CIN7 API client"""
        self.api_url = config('CIN7_API_URL', default='')
        self.username = config('CIN7_API_USERNAME', default='')
        self.api_key = config('CIN7_API_KEY', default='')
        self.wholesale_id = config('CIN7_WHOLE_SALE_ID', default='190')

        if not all([self.api_url, self.username, self.api_key]):
            raise ValueError("CIN7 API credentials not found in environment variables")

        # Create Basic Auth header
        credentials = f"{self.username}:{self.api_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        self.headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Minimum seconds between requests

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2

        logger.info(f"Initialized CIN7 service for: {self.api_url}")

    def _rate_limit(self):
        """Implement rate limiting to avoid overwhelming the API"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """
        Make authenticated API request with retry logic

        Args:
            endpoint: API endpoint (e.g., 'Products')
            params: Query parameters

        Returns:
            API response data or None on failure
        """
        if params is None:
            params = {}

        url = f"{self.api_url.rstrip('/')}/{endpoint.lstrip('/')}"

        for attempt in range(self.max_retries):
            try:
                self._rate_limit()

                logger.debug(f"Making CIN7 API request to: {url} with params: {params}")
                response = requests.get(url, headers=self.headers, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("CIN7 API authentication failed - check credentials")
                    return None
                elif response.status_code == 429:
                    # Rate limited - wait longer and retry
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(f"CIN7 API rate limited. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"CIN7 API request failed with status {response.status_code}: {response.text}")

            except RequestException as e:
                logger.error(f"CIN7 API request failed (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached for CIN7 API request")

        return None

    def test_connection(self) -> bool:
        """Test connection to CIN7 API"""
        try:
            response = self._make_request('Products', {'rows': 1})
            if response is not None:
                logger.info("CIN7 API connection test successful")
                return True
            else:
                logger.error("CIN7 API connection test failed")
                return False
        except Exception as e:
            logger.error(f"CIN7 API connection test failed: {e}")
            return False

    def get_wholesale_products(self, page: int = 1, rows_per_page: int = 100) -> Optional[Dict]:
        """
        Get products from the Wholesale Schools category

        Args:
            page: Page number (1-based)
            rows_per_page: Number of products per page

        Returns:
            API response with products data
        """
        params = {
            'page': page,
            'rows': rows_per_page,
            'where': f'Category = "Wholesale Schools"'  # Filter by Wholesale Schools category
        }

        logger.info(f"Fetching wholesale products - page {page}, rows {rows_per_page}")
        response = self._make_request('Products', params)

        if response:
            logger.info(f"Retrieved {len(response.get('Items', []))} wholesale products from page {page}")

        return response

    def get_all_wholesale_products(self) -> List[Dict]:
        """
        Get all products from Wholesale Schools category with pagination

        Returns:
            List of all wholesale products
        """
        all_products = []
        page = 1
        rows_per_page = 100

        logger.info("Starting to fetch all wholesale products...")

        while True:
            response = self.get_wholesale_products(page, rows_per_page)

            if not response or 'Items' not in response:
                logger.error(f"No data received from CIN7 API on page {page}")
                break

            products = response['Items']

            if not products:
                logger.info(f"No more products found on page {page}. Finished pagination.")
                break

            all_products.extend(products)
            logger.info(f"Retrieved {len(products)} products from page {page}. Total: {len(all_products)}")

            # Check if we've reached the end
            if len(products) < rows_per_page:
                logger.info("Last page reached (fewer products than requested)")
                break

            page += 1

            # Safety check to prevent infinite loops
            if page > 1000:  # Arbitrary large number
                logger.warning("Safety limit reached (1000 pages). Stopping pagination.")
                break

        logger.info(f"Total wholesale products retrieved: {len(all_products)}")
        return all_products

    def get_product_details(self, product_id: str) -> Optional[Dict]:
        """
        Get detailed information for a specific product

        Args:
            product_id: CIN7 product ID

        Returns:
            Product details or None
        """
        endpoint = f'Products/{product_id}'
        return self._make_request(endpoint)

    def get_product_categories(self) -> Optional[List[Dict]]:
        """
        Get all product categories from CIN7

        Returns:
            List of categories or None
        """
        logger.info("Fetching product categories from CIN7...")
        response = self._make_request('ProductCategories')

        if response and 'Items' in response:
            categories = response['Items']
            logger.info(f"Retrieved {len(categories)} categories")
            return categories

        return None

    def extract_school_info_from_product(self, product: Dict) -> Dict:
        """
        Extract school information from a CIN7 product

        Args:
            product: CIN7 product data

        Returns:
            Extracted school information
        """
        # The school name might be in different fields depending on CIN7 setup
        # Common places: Product name, Brand, Category path, or custom fields

        school_name = ""
        school_code = ""

        # Try to extract school name from product name or brand
        product_name = product.get('ProductName', '')
        brand = product.get('Brand', '')
        category_path = product.get('CategoryPath', '')

        # Look for school indicators in the category path
        # Expected format: "Wholesale Schools > School Name > Sub Category"
        if 'Wholesale Schools' in category_path:
            parts = [part.strip() for part in category_path.split('>')]
            if len(parts) >= 2:
                school_name = parts[1]  # School name should be the second part

        # If no school name found in category, try other fields
        if not school_name:
            school_name = brand or product_name

        # Try to extract school code from SKU or other fields
        sku = product.get('SKU', '')
        if sku:
            # Assuming school code might be a prefix in SKU
            school_code = sku.split('-')[0] if '-' in sku else sku[:4]

        return {
            'name': school_name,
            'code': school_code,
            'description': product.get('ProductDescription', ''),
            'brand': brand,
            'category_path': category_path
        }

    def parse_product_data(self, product: Dict) -> Dict:
        """
        Parse CIN7 product data into our model format

        Args:
            product: Raw CIN7 product data

        Returns:
            Parsed product data
        """
        # Extract pricing information
        wholesale_price = None
        retail_price = None
        cost_price = None

        # CIN7 might have different price fields
        if 'WholesalePrice' in product:
            wholesale_price = Decimal(str(product['WholesalePrice']))
        elif 'SellPrice1' in product:
            wholesale_price = Decimal(str(product['SellPrice1']))

        if 'RetailPrice' in product:
            retail_price = Decimal(str(product['RetailPrice']))
        elif 'SellPrice2' in product:
            retail_price = Decimal(str(product['SellPrice2']))

        if 'CostPrice' in product:
            cost_price = Decimal(str(product['CostPrice']))
        elif 'AvgCost' in product:
            cost_price = Decimal(str(product['AvgCost']))

        # Extract stock information
        quantity_available = product.get('QtyAvailable', 0)
        quantity_on_hand = product.get('QtyOnHand', 0)
        quantity_committed = product.get('QtyCommitted', 0)

        # Determine stock status
        stock_status = 'in_stock'
        if quantity_available <= 0:
            stock_status = 'out_of_stock'
        elif product.get('Discontinued', False):
            stock_status = 'discontinued'

        # Extract dimensions and attributes
        dimensions = {}
        if 'Length' in product:
            dimensions['length'] = product['Length']
        if 'Width' in product:
            dimensions['width'] = product['Width']
        if 'Height' in product:
            dimensions['height'] = product['Height']

        attributes = {
            'supplier': product.get('Supplier', ''),
            'brand': product.get('Brand', ''),
            'unit_of_measure': product.get('UnitOfMeasure', ''),
            'barcode': product.get('Barcode', ''),
            'discontinued': product.get('Discontinued', False)
        }

        return {
            'cin7_id': str(product.get('ProductId', '')),
            'name': product.get('ProductName', ''),
            'description': product.get('ProductDescription', ''),
            'short_description': product.get('ShortDescription', ''),
            'cin7_sku': product.get('SKU', ''),
            'cin7_barcode': product.get('Barcode', ''),
            'cin7_brand': product.get('Brand', ''),
            'cin7_supplier': product.get('Supplier', ''),
            'cin7_unit_of_measure': product.get('UnitOfMeasure', ''),
            'wholesale_price': wholesale_price,
            'retail_price': retail_price,
            'cost_price': cost_price,
            'stock_status': stock_status,
            'quantity_available': int(quantity_available),
            'quantity_on_hand': int(quantity_on_hand),
            'quantity_committed': int(quantity_committed),
            'weight': product.get('Weight'),
            'dimensions': dimensions,
            'attributes': attributes,
            'image_url': product.get('ImageUrl', ''),
            'category_path': product.get('CategoryPath', '')
        }

    def organize_products_by_school(self, products: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Organize products by school

        Args:
            products: List of CIN7 products

        Returns:
            Dictionary with school names as keys and lists of products as values
        """
        schools = {}

        for product in products:
            school_info = self.extract_school_info_from_product(product)
            school_name = school_info['name']

            if school_name not in schools:
                schools[school_name] = {
                    'info': school_info,
                    'products': []
                }

            # Parse product data
            parsed_product = self.parse_product_data(product)
            schools[school_name]['products'].append(parsed_product)

        logger.info(f"Organized {len(products)} products into {len(schools)} schools")

        # Log school summary
        for school_name, school_data in schools.items():
            logger.info(f"School: {school_name} - {len(school_data['products'])} products")

        return schools

    def get_product_stock_levels(self, product_id: str) -> Optional[Dict]:
        """
        Get detailed stock levels for a product

        Args:
            product_id: CIN7 product ID

        Returns:
            Stock level information
        """
        endpoint = f'Products/{product_id}/StockLevels'
        return self._make_request(endpoint)

    def search_products(self, search_term: str, page: int = 1, rows_per_page: int = 50) -> Optional[Dict]:
        """
        Search for products by name or SKU

        Args:
            search_term: Term to search for
            page: Page number
            rows_per_page: Results per page

        Returns:
            Search results
        """
        params = {
            'page': page,
            'rows': rows_per_page,
            'where': f'(ProductName like "%{search_term}%" or SKU like "%{search_term}%") and Category = "Wholesale Schools"'
        }

        return self._make_request('Products', params)