import os
import logging
import requests
import json
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
from django.conf import settings
from django.utils.text import slugify
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from decimal import Decimal, InvalidOperation
import urllib3

# Enhanced image downloader is no longer needed since we store URLs directly
ENHANCED_DOWNLOADER_AVAILABLE = False

# Disable SSL warnings for image downloads
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


logger = logging.getLogger(__name__)


class WooCommerceService:
    """
    Service class for integrating with WooCommerce REST API
    """
    
    def __init__(self, store_type: str = 'LOTTO'):
        """
        Initialize WooCommerce service
        
        Args:
            store_type: 'LOTTO' or 'SAS'
        """
        self.store_type = store_type.upper()
        
        # Validate and get settings with proper error handling
        try:
            if self.store_type == 'LOTTO':
                self.api_url = getattr(settings, 'LOTTO_WOO_URL', None)
                self.consumer_key = getattr(settings, 'LOTTO_WOO_KEY', None)
                self.consumer_secret = getattr(settings, 'LOTTO_WOO_SECRET', None)
                required_settings = ['LOTTO_WOO_URL', 'LOTTO_WOO_KEY', 'LOTTO_WOO_SECRET']
            elif self.store_type == 'SAS':
                self.api_url = getattr(settings, 'SAS_WOO_URL', None)
                self.consumer_key = getattr(settings, 'SAS_WOO_KEY', None)
                self.consumer_secret = getattr(settings, 'SAS_WOO_SECRET', None)
                required_settings = ['SAS_WOO_URL', 'SAS_WOO_KEY', 'SAS_WOO_SECRET']
            else:
                raise ValueError("Store type must be 'LOTTO' or 'SAS'")
            
            # Check for missing settings
            missing_settings = []
            if not self.api_url:
                missing_settings.append(required_settings[0])
            if not self.consumer_key:
                missing_settings.append(required_settings[1])
            if not self.consumer_secret:
                missing_settings.append(required_settings[2])
            
            if missing_settings:
                raise ValueError(f"Missing required WooCommerce settings: {', '.join(missing_settings)}")
            
        except AttributeError as e:
            raise ValueError(f"WooCommerce settings not configured properly: {str(e)}")
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set authentication
        self.session.auth = (self.consumer_key, self.consumer_secret)
        
        # Image downloading is no longer needed since we store URLs directly
        logger.info(f"Using URL-based image storage for {self.store_type} - no download required")
        
        logger.info(f"Initialized WooCommerce service for {self.store_type}")
    
    def _make_request(self, endpoint: str, params: Dict = None, method: str = 'GET', retry_count: int = 0) -> Optional[Dict]:
        """
        Make authenticated request to WooCommerce API with enhanced error handling
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            method: HTTP method
            retry_count: Current retry attempt (internal use)
            
        Returns:
            Response data or None if failed
        """
        url = urljoin(self.api_url, endpoint)
        max_retries = 3
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            else:
                response = self.session.request(method, url, json=params, timeout=30)
            
            # Handle rate limiting before checking status
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited (429), waiting {retry_after} seconds...")
                time.sleep(retry_after)
                
                # Retry the request if we haven't exceeded max retries
                if retry_count < max_retries:
                    return self._make_request(endpoint, params, method, retry_count + 1)
                else:
                    logger.error(f"Max retries exceeded for rate limited request: {url}")
                    return None
            
            response.raise_for_status()
            
            # Log response details for debugging
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            logger.debug(f"Response content length: {len(response.content)}")
            
            # Check if response has content
            if not response.content.strip():
                logger.warning(f"Empty response from {url}")
                return []
            
            try:
                return response.json()
            except ValueError as json_err:
                # Handle the specific case of PHP warnings in WooCommerce responses
                content_str = response.content.decode('utf-8', errors='ignore')
                
                # Look for JSON content after PHP warnings
                json_start = content_str.find('[')
                if json_start == -1:
                    json_start = content_str.find('{')
                
                if json_start > 0:
                    logger.warning(f"Found PHP warnings in response, attempting to extract JSON from position {json_start}")
                    try:
                        clean_json = content_str[json_start:]
                        return json.loads(clean_json)
                    except:
                        pass
                
                logger.error(f"JSON parsing failed for {url}: {json_err}")
                logger.error(f"Response content: {response.content[:500]}...")  # First 500 chars
                return None
                
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout for {url}: {str(e)}")
            if retry_count < max_retries:
                logger.info(f"Retrying request (attempt {retry_count + 1}/{max_retries})")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(endpoint, params, method, retry_count + 1)
            return None
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error for {url}: {str(e)}")
            if retry_count < max_retries:
                logger.info(f"Retrying connection (attempt {retry_count + 1}/{max_retries})")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(endpoint, params, method, retry_count + 1)
            return None
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {url}: {str(e)} - Status: {response.status_code}")
            
            # Don't retry client errors (4xx), but do retry server errors (5xx)
            if 500 <= response.status_code < 600 and retry_count < max_retries:
                logger.info(f"Retrying server error (attempt {retry_count + 1}/{max_retries})")
                time.sleep(2 ** retry_count)
                return self._make_request(endpoint, params, method, retry_count + 1)
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during API request: {str(e)}")
            return None
    
    def get_categories(self, parent_id: int = None, per_page: int = 100) -> List[Dict]:
        """
        Fetch categories from WooCommerce
        
        Args:
            parent_id: Parent category ID to filter by
            per_page: Number of items per page
            
        Returns:
            List of category dictionaries
        """
        categories = []
        page = 1
        
        while True:
            # Use the parameters that work reliably
            params = {
                'per_page': min(per_page, 100),
                'page': page,
                'orderby': 'name',
                'order': 'asc'
            }
            
            logger.info(f"Fetching categories page {page}")
            data = self._make_request('products/categories', params)
            
            if not data:
                logger.error(f"Failed to fetch categories page {page}")
                break
            
            if not data:  # Empty response means no more pages
                break
            
            categories.extend(data)
            
            # Check if there are more pages
            if len(data) < min(per_page, 100):
                break
            
            page += 1
            time.sleep(0.5)  # Rate limiting
        
        # Filter by parent_id client-side if specified
        if parent_id is not None:
            categories = [cat for cat in categories if cat.get('parent', 0) == parent_id]
            logger.info(f"Filtered to {len(categories)} categories with parent_id={parent_id}")
        
        logger.info(f"Fetched {len(categories)} categories total")
        return categories
    
    def get_categories_with_products(self, parent_id: int = 23) -> List[Dict]:
        """
        Fetch categories that have products (product_count > 0)
        
        Args:
            parent_id: Parent category ID (default: 23 for Club Shops)
            
        Returns:
            List of categories with products
        """
        all_categories = self.get_categories(parent_id=parent_id)
        
        # Filter categories with products
        categories_with_products = [
            category for category in all_categories 
            if category.get('count', 0) > 0
        ]
        
        logger.info(f"Found {len(categories_with_products)} categories with products")
        return categories_with_products
    
    def get_products_by_category(self, category_id: int, per_page: int = 100) -> List[Dict]:
        """
        Fetch products for a specific category
        
        Args:
            category_id: Category ID
            per_page: Number of items per page
            
        Returns:
            List of product dictionaries
        """
        products = []
        page = 1
        
        while True:
            params = {
                'category': category_id,
                'per_page': per_page,
                'page': page,
                'status': 'publish',
                'orderby': 'title',
                'order': 'asc'
            }
            
            logger.info(f"Fetching products page {page} for category {category_id}")
            data = self._make_request('products', params)
            
            if not data:
                logger.error(f"Failed to fetch products page {page} for category {category_id}")
                break
            
            if not data:  # Empty response
                break
            
            products.extend(data)
            
            # Check if there are more pages
            if len(data) < per_page:
                break
            
            page += 1
            time.sleep(0.5)  # Rate limiting
        
        logger.info(f"Fetched {len(products)} products for category {category_id}")
        return products
    
    def get_product_variations(self, product_id: int) -> List[Dict]:
        """
        Fetch variations for a specific variable product
        
        Args:
            product_id: WooCommerce product ID
            
        Returns:
            List of variation dictionaries
        """
        variations = []
        page = 1
        per_page = 100
        
        while True:
            params = {
                'per_page': per_page,
                'page': page,
                'status': 'publish'
            }
            
            logger.info(f"Fetching variations page {page} for product {product_id}")
            data = self._make_request(f'products/{product_id}/variations', params)
            
            if not data:
                logger.error(f"Failed to fetch variations page {page} for product {product_id}")
                break
            
            if not data:  # Empty response
                break
            
            # Debug logging to understand what type of data we're getting
            if data:
                first_item = data[0] if len(data) > 0 else None
                if first_item:
                    logger.debug(f"First variation data type: {type(first_item)}, content: {str(first_item)[:200]}")
                    if not isinstance(first_item, dict):
                        logger.error(f"Expected dict but got {type(first_item)} for variations in product {product_id}")
            
            variations.extend(data)
            
            # Check if there are more pages
            if len(data) < per_page:
                break
            
            page += 1
            time.sleep(0.3)  # Rate limiting for variations
        
        logger.info(f"Fetched {len(variations)} variations for product {product_id}")
        return variations
    
    def is_variable_product(self, product_data: Dict) -> bool:
        """
        Check if a product is a variable product
        
        Args:
            product_data: Product data from WooCommerce API
            
        Returns:
            True if product is variable
        """
        product_type = product_data.get('type', 'simple')
        return product_type == 'variable'
    
    def get_variable_products_by_category(self, category_id: int) -> List[Dict]:
        """
        Fetch only variable products for a specific category
        
        Args:
            category_id: Category ID
            
        Returns:
            List of variable product dictionaries
        """
        all_products = self.get_products_by_category(category_id)
        variable_products = [
            product for product in all_products 
            if self.is_variable_product(product)
        ]
        
        logger.info(f"Found {len(variable_products)} variable products in category {category_id}")
        return variable_products
    
    def get_variation_attributes(self, variation_data: Dict) -> Dict[str, str]:
        """
        Extract and normalize variation attributes from WooCommerce data
        
        Args:
            variation_data: Variation data from WooCommerce API
            
        Returns:
            Dictionary mapping attribute types to values
        """
        attributes = {}
        
        # Get attributes from the variation data
        variation_attributes = variation_data.get('attributes', [])
        
        for attr in variation_attributes:
            # Extract attribute name and value
            attr_name = attr.get('name', '').lower()
            attr_value = attr.get('option', '')
            
            # Normalize common attribute names
            if 'size' in attr_name or attr_name.startswith('pa_size'):
                attributes['size'] = attr_value
            elif 'color' in attr_name or attr_name.startswith('pa_color'):
                attributes['color'] = attr_value
            elif 'material' in attr_name or attr_name.startswith('pa_material'):
                attributes['material'] = attr_value
            elif 'style' in attr_name or attr_name.startswith('pa_style'):
                attributes['style'] = attr_value
            else:
                # For custom attributes, use the name as-is
                clean_name = attr_name.replace('pa_', '').replace('-', '_')
                attributes[clean_name] = attr_value
        
        return attributes
    
    def extract_variation_data(self, variation_data: Dict, product_data: Dict = None) -> Dict:
        """
        Extract variation data for database storage
        
        Args:
            variation_data: Variation data from WooCommerce API
            product_data: Parent product data (optional, for context)
            
        Returns:
            Dictionary with extracted variation information
        """
        # Handle case where variation_data is a string instead of dict
        if isinstance(variation_data, str):
            logger.error(f"Received string variation data instead of dict: {variation_data}")
            # Return a minimal valid response
            return {
                'woo_variation_id': 0,
                'variation_type': 'unknown',
                'variation_value': 'unknown',
                'price_modifier': 0,
                'stock_quantity': 0,
                'sku_suffix': '',
                'is_active': False,
                'attributes': {},
                'weight': '',
                'dimensions': {},
                'image_data': None,
                'raw_data': {}
            }
        
        # Ensure variation_data is a dict
        if not isinstance(variation_data, dict):
            logger.error(f"Invalid variation data type: {type(variation_data)}")
            return {
                'woo_variation_id': 0,
                'variation_type': 'unknown',
                'variation_value': 'unknown',
                'price_modifier': 0,
                'stock_quantity': 0,
                'sku_suffix': '',
                'is_active': False,
                'attributes': {},
                'weight': '',
                'dimensions': {},
                'image_data': None,
                'raw_data': {}
            }
        
        # Get variation attributes
        attributes = self.get_variation_attributes(variation_data)
        
        # Determine primary variation type and value
        variation_type = 'other'
        variation_value = 'Default'
        
        # Priority order for variation types
        type_priority = ['size', 'color', 'material', 'style', 'gender']
        
        for priority_type in type_priority:
            if priority_type in attributes and attributes[priority_type]:
                variation_type = priority_type
                variation_value = attributes[priority_type]
                break
        
        # If no priority type found, use the first available attribute
        if variation_type == 'other' and attributes:
            first_attr = list(attributes.items())[0]
            variation_type = first_attr[0]
            variation_value = first_attr[1]
        
        # Parse prices
        variation_price = self._parse_decimal(variation_data.get('price', '0'))
        regular_price = self._parse_decimal(variation_data.get('regular_price', '0'))
        sale_price = self._parse_decimal(variation_data.get('sale_price', ''))
        
        # Calculate price modifier compared to parent product
        price_modifier = 0
        if product_data:
            parent_price = self._parse_decimal(product_data.get('price', '0'))
            if parent_price > 0 and variation_price > 0:
                price_modifier = variation_price - parent_price
        
        # Extract stock information
        stock_quantity = max(0, int(variation_data.get('stock_quantity', 0) or 0))
        manage_stock = variation_data.get('manage_stock', False)
        stock_status = variation_data.get('stock_status', 'instock')
        
        # If stock is not managed, set a default quantity based on status
        if not manage_stock:
            stock_quantity = 100 if stock_status == 'instock' else 0
        
        # Determine image strategy based on variation type and available images
        image_data = self._extract_variation_image_data(variation_data, product_data, variation_type)
        
        return {
            'woo_variation_id': variation_data['id'],
            'variation_type': variation_type,
            'variation_value': variation_value,
            'price_modifier': price_modifier,
            'stock_quantity': stock_quantity,
            'sku_suffix': variation_data.get('sku', ''),
            'is_active': stock_status in ['instock', 'onbackorder'],
            'attributes': attributes,
            'weight': variation_data.get('weight', ''),
            'dimensions': variation_data.get('dimensions', {}),
            # Image data with fallback strategy
            'image_data': image_data,
            # Additional WooCommerce data
            'raw_data': {
                'price': str(variation_price),
                'regular_price': str(regular_price),
                'sale_price': str(sale_price) if sale_price else None,
                'stock_status': stock_status,
                'manage_stock': manage_stock,
            }
        }
    
    def _parse_decimal(self, value):
        """Parse decimal value from string or number"""
        if not value or value == '':
            return Decimal('0')
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal('0')
    
    def get_image_url(self, image_url: str) -> Optional[str]:
        """
        Extract and validate image URL for direct storage
        
        Args:
            image_url: URL of the image
            
        Returns:
            Validated image URL or None if invalid
        """
        if not image_url:
            return None
        
        # Clean the URL and remove parameters that might cause issues
        clean_url = image_url.split('?')[0]
        
        # Basic URL validation
        if not clean_url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid image URL format: {clean_url}")
            return None
        
        logger.debug(f"Validated image URL: {clean_url}")
        return clean_url
    
    def _download_image_basic_deprecated(self, image_url: str, folder: str, filename: str = None):
        """
        Basic image download method (original implementation as fallback)
        """
        if not image_url:
            return None
        
        # Clean the URL and remove parameters that might cause issues
        clean_url = image_url.split('?')[0]
        
        # Get configured LOTTO site URL for Referer/Origin headers
        lotto_site_url = getattr(settings, 'LOTTO_SITE_URL', 'https://dev-lottosports.it.sas.co.nz')

        # Try multiple strategies to bypass bot detection
        strategies = [
            # Strategy 1: Advanced browser simulation
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Referer': f'{lotto_site_url}/',
                    'Origin': lotto_site_url,
                    'Sec-Fetch-Dest': 'image',
                    'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'same-origin',
                    'DNT': '1',
                    'Upgrade-Insecure-Requests': '1',
                },
                'name': 'Advanced browser simulation'
            },
            # Strategy 2: Simple browser-like request
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Referer': f'{lotto_site_url}/',
                },
                'name': 'Simple browser simulation'
            },
            # Strategy 3: Mobile browser simulation
            {
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Referer': f'{lotto_site_url}/',
                },
                'name': 'Mobile browser simulation'
            }
        ]
        
        logger.info(f"Attempting basic image download from: {clean_url}")
        
        for i, strategy in enumerate(strategies, 1):
            try:
                logger.debug(f"Trying strategy {i}: {strategy['name']}")
                
                # First establish a session by visiting the main site
                if i == 1:  # Only do this for the first strategy to save time
                    try:
                        lotto_site_url = getattr(settings, 'LOTTO_SITE_URL', 'https://dev-lottosports.it.sas.co.nz')
                        self.session.get(
                            lotto_site_url,
                            headers=strategy['headers'],
                            timeout=15,
                            verify=False
                        )
                        logger.debug("Established session with main site")
                    except:
                        pass  # Continue even if session establishment fails
                
                # Make request with current strategy
                response = self.session.get(
                    clean_url, 
                    headers=strategy['headers'], 
                    timeout=30, 
                    stream=True,
                    allow_redirects=True,
                    verify=False
                )
                
                response.raise_for_status()
                
                # Check if we got HTML (bot detection) or actual image
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    logger.warning(f"Strategy {i} failed: received HTML instead of image (bot detection)")
                    continue
                
                if 'image' not in content_type:
                    logger.warning(f"Strategy {i} failed: unexpected content type {content_type}")
                    continue
                
                # Success! Process the image
                logger.info(f"Strategy {i} ({strategy['name']}) successful!")
                return self._process_image_response(response, clean_url, folder, filename)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Strategy {i} failed with request error: {str(e)}")
                continue
            except Exception as e:
                logger.warning(f"Strategy {i} failed with unexpected error: {str(e)}")
                continue
        
        # All strategies failed
        logger.error(f"All basic image download strategies failed for {clean_url}")
        logger.info(f"Image download blocked by bot detection system - skipping image for {clean_url}")
        return None
    
    def _image_exists_locally_deprecated(self, filename: str, folder: str) -> bool:
        """Deprecated: No longer needed since we store URLs directly"""
        return False
    
    def _ensure_media_directories_deprecated(self):
        """Deprecated: No longer needed since we store URLs directly"""
        pass
    
    
    
    
    # Image processing methods removed - we now store URLs directly
    
    
    def get_category_hierarchy(self, parent_id: int = 23) -> Dict[int, Dict]:
        """
        Get category hierarchy starting from parent_id
        
        Args:
            parent_id: Root parent category ID
            
        Returns:
            Dictionary mapping category IDs to category data with children
        """
        all_categories = self.get_categories()
        
        # Build hierarchy
        category_map = {}
        root_categories = []
        
        for category in all_categories:
            category_id = category['id']
            parent = category.get('parent', 0)
            
            category_map[category_id] = {
                **category,
                'children': []
            }
            
            if parent == parent_id:
                root_categories.append(category_id)
        
        # Build parent-child relationships
        for category in all_categories:
            parent = category.get('parent', 0)
            if parent != 0 and parent in category_map:
                category_map[parent]['children'].append(category['id'])
        
        logger.info(f"Built category hierarchy with {len(category_map)} categories")
        return category_map
    
    def test_connection(self) -> bool:
        """
        Test API connection
        
        Returns:
            True if connection successful
        """
        try:
            data = self._make_request('system_status')
            if data:
                logger.info(f"Successfully connected to {self.store_type} WooCommerce API")
                return True
            else:
                logger.error(f"Failed to connect to {self.store_type} WooCommerce API")
                return False
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False
    
    def get_store_info(self) -> Optional[Dict]:
        """
        Get store information
        
        Returns:
            Store information dictionary
        """
        return self._make_request('system_status')
    
    def _calculate_category_depth(self, category_id: int, hierarchy: Dict = None, visited: set = None) -> int:
        """
        Calculate category hierarchy depth to avoid infinite loops
        
        Args:
            category_id: Category ID to check
            hierarchy: Category hierarchy data
            visited: Set of visited category IDs to avoid loops
            
        Returns:
            Depth level (0 = root, 1 = first level, etc.)
        """
        if visited is None:
            visited = set()
        
        if category_id in visited:
            logger.warning(f"Circular reference detected in category hierarchy at {category_id}")
            return 0
        
        visited.add(category_id)
        
        if hierarchy is None:
            # Build minimal hierarchy if not provided
            categories = self.get_categories()
            hierarchy = {cat['id']: cat for cat in categories}
        
        if category_id not in hierarchy:
            return 0
        
        parent_id = hierarchy[category_id].get('parent', 0)
        if parent_id == 0:
            return 0  # Root category
        
        return 1 + self._calculate_category_depth(parent_id, hierarchy, visited)
    
    def _extract_variation_image_data(self, variation_data: Dict, product_data: Dict = None, variation_type: str = 'other') -> Dict:
        """
        Extract variation image data with intelligent fallback logic
        
        Args:
            variation_data: Variation data from WooCommerce API
            product_data: Parent product data (optional)
            variation_type: Type of variation (color, size, material, etc.)
            
        Returns:
            Dictionary with image URL and fallback strategy
        """
        image_data = {
            'variation_image_url': None,
            'fallback_image_url': None,
            'should_use_variation_image': False,
            'image_strategy': 'none'
        }
        
        # Get variation-specific image
        variation_image = variation_data.get('image')
        if variation_image and variation_image.get('src'):
            image_data['variation_image_url'] = variation_image['src']
        
        # Get parent product image as fallback
        if product_data and product_data.get('images'):
            parent_images = product_data['images']
            if parent_images:
                image_data['fallback_image_url'] = parent_images[0].get('src')
        
        # Determine image strategy based on variation type
        if image_data['variation_image_url']:
            # We have a variation-specific image
            if self._should_use_variation_image(variation_type):
                image_data['should_use_variation_image'] = True
                image_data['image_strategy'] = 'variation_primary'
            else:
                # For size variations, only use if significantly different from parent
                if self._is_variation_image_significantly_different(
                    image_data['variation_image_url'], 
                    image_data['fallback_image_url']
                ):
                    image_data['should_use_variation_image'] = True
                    image_data['image_strategy'] = 'variation_different'
                else:
                    image_data['image_strategy'] = 'fallback_preferred'
        else:
            # No variation image, use fallback
            image_data['image_strategy'] = 'fallback_only'
        
        return image_data
    
    def _should_use_variation_image(self, variation_type: str) -> bool:
        """
        Determine if variation type typically has different images
        
        Args:
            variation_type: Type of variation
            
        Returns:
            True if variation type typically has unique images
        """
        # Variation types that typically have different images
        image_variant_types = {
            'color': True,      # Colors almost always have different images
            'style': True,      # Different styles need different images
            'material': True,   # Material changes often affect appearance
            'gender': False,    # Gender variations usually same product, different sizes
            'size': False,      # Size variations typically same image
            'age_group': False, # Age groups usually same design, different sizes
            'other': False      # Conservative default
        }
        
        return image_variant_types.get(variation_type, False)
    
    def _is_variation_image_significantly_different(self, variation_url: str, parent_url: str) -> bool:
        """
        Check if variation image is significantly different from parent image
        
        Args:
            variation_url: Variation image URL
            parent_url: Parent product image URL
            
        Returns:
            True if images appear to be different
        """
        if not variation_url or not parent_url:
            return True
        
        # Simple heuristic: compare filenames
        # If filenames are very similar, assume same image
        import os
        from urllib.parse import urlparse
        
        try:
            variation_filename = os.path.basename(urlparse(variation_url).path)
            parent_filename = os.path.basename(urlparse(parent_url).path)
            
            # Remove file extensions for comparison
            variation_base = os.path.splitext(variation_filename)[0]
            parent_base = os.path.splitext(parent_filename)[0]
            
            # If one filename contains the other, they're likely the same
            if variation_base in parent_base or parent_base in variation_base:
                return False
            
            # If filenames are very similar (e.g., only size suffix difference)
            # This is a simple heuristic and could be improved with actual image analysis
            return True
            
        except Exception:
            # If we can't parse URLs, assume they're different
            return True
    
    def get_effective_variation_image_url(self, variation_data: Dict, product_data: Dict = None) -> Optional[str]:
        """
        Get the effective image URL for a variation using intelligent logic
        
        Args:
            variation_data: Variation data from WooCommerce API
            product_data: Parent product data (optional)
            
        Returns:
            URL of image to use for this variation, or None
        """
        # Extract variation attributes to determine type
        attributes = self.get_variation_attributes(variation_data)
        
        # Determine variation type
        variation_type = 'other'
        type_priority = ['color', 'style', 'material', 'size', 'gender']
        
        for priority_type in type_priority:
            if priority_type in attributes and attributes[priority_type]:
                variation_type = priority_type
                break
        
        # Get image data with strategy
        image_data = self._extract_variation_image_data(variation_data, product_data, variation_type)
        
        # Return appropriate image URL based on strategy
        if image_data['should_use_variation_image'] and image_data['variation_image_url']:
            return image_data['variation_image_url']
        else:
            return image_data['fallback_image_url']
    
    def get_variation_image_url(self, variation_data: Dict, product_data: Dict) -> Optional[str]:
        """
        Get variation image URL with intelligent fallback logic
        
        Args:
            variation_data: Variation data from WooCommerce API
            product_data: Parent product data
            
        Returns:
            Image URL or None if no image available
        """
        # Get the effective image URL
        image_url = self.get_effective_variation_image_url(variation_data, product_data)
        
        if not image_url:
            return None
        
        # Return the validated URL
        return self.get_image_url(image_url)
    
    def get_single_product(self, product_id: int) -> Optional[Dict]:
        """
        Fetch a single product by ID
        
        Args:
            product_id: WooCommerce product ID
            
        Returns:
            Product data dictionary or None if not found
        """
        logger.info(f"Fetching single product {product_id}")
        return self._make_request(f'products/{product_id}')
    
    def get_category_by_id(self, category_id: int) -> Optional[Dict]:
        """
        Fetch a single category by ID
        
        Args:
            category_id: WooCommerce category ID
            
        Returns:
            Category data dictionary or None if not found
        """
        logger.info(f"Fetching single category {category_id}")
        return self._make_request(f'products/categories/{category_id}')
    
    def validate_api_credentials(self) -> Dict[str, any]:
        """
        Validate API credentials and return connection status
        
        Returns:
            Dictionary with validation results and store information
        """
        validation_result = {
            'is_valid': False,
            'store_type': self.store_type,
            'api_url': self.api_url,
            'error': None,
            'store_info': None,
            'connection_time': None
        }
        
        try:
            import time
            start_time = time.time()
            
            # Test basic connection
            data = self._make_request('system_status')
            
            connection_time = time.time() - start_time
            validation_result['connection_time'] = connection_time
            
            if data:
                validation_result['is_valid'] = True
                validation_result['store_info'] = {
                    'version': data.get('version'),
                    'environment': data.get('environment', {}),
                    'database': data.get('database', {}),
                    'api_enabled': True
                }
                logger.info(f"API credentials validated for {self.store_type} store in {connection_time:.2f}s")
            else:
                validation_result['error'] = "No data returned from API"
                logger.error(f"API credentials validation failed for {self.store_type}: No data returned")
                
        except Exception as e:
            validation_result['error'] = str(e)
            logger.error(f"API credentials validation failed for {self.store_type}: {str(e)}")
        
        return validation_result
    
    def get_products_with_variations_by_category(self, category_id: int) -> List[Dict]:
        """
        Fetch products and their variations for a specific category
        
        Args:
            category_id: Category ID
            
        Returns:
            List of products with embedded variation data
        """
        products = self.get_products_by_category(category_id)
        products_with_variations = []
        
        for product in products:
            if self.is_variable_product(product):
                # Fetch variations for variable products
                variations = self.get_product_variations(product['id'])
                product['variations'] = variations
                logger.info(f"Product {product['id']} has {len(variations)} variations")
            else:
                product['variations'] = []
            
            products_with_variations.append(product)
        
        logger.info(f"Fetched {len(products_with_variations)} products with variations for category {category_id}")
        return products_with_variations
    
    def get_batch_products(self, product_ids: List[int]) -> List[Dict]:
        """
        Fetch multiple products by their IDs
        
        Args:
            product_ids: List of WooCommerce product IDs
            
        Returns:
            List of product dictionaries
        """
        products = []
        
        # WooCommerce API supports comma-separated IDs in include parameter
        if product_ids:
            # Process in batches to avoid URL length limits
            batch_size = 100
            for i in range(0, len(product_ids), batch_size):
                batch_ids = product_ids[i:i + batch_size]
                params = {
                    'include': ','.join(map(str, batch_ids)),
                    'per_page': batch_size
                }
                
                logger.info(f"Fetching batch of {len(batch_ids)} products")
                batch_data = self._make_request('products', params)
                
                if batch_data:
                    products.extend(batch_data)
                else:
                    logger.error(f"Failed to fetch product batch: {batch_ids}")
                
                time.sleep(0.3)  # Rate limiting
        
        logger.info(f"Fetched {len(products)} products in batch request")
        return products
    
    def search_products(self, search_term: str, category_id: int = None, per_page: int = 20) -> List[Dict]:
        """
        Search for products by name/description
        
        Args:
            search_term: Search term
            category_id: Optional category filter
            per_page: Number of results per page
            
        Returns:
            List of matching products
        """
        params = {
            'search': search_term,
            'per_page': per_page,
            'status': 'publish'
        }
        
        if category_id:
            params['category'] = category_id
        
        logger.info(f"Searching products for term: {search_term}")
        data = self._make_request('products', params)
        
        if data:
            logger.info(f"Found {len(data)} products matching '{search_term}'")
            return data
        else:
            logger.warning(f"No products found for search term: {search_term}")
            return []
    
    def get_api_stats(self) -> Dict[str, any]:
        """
        Get API usage statistics and performance metrics
        
        Returns:
            Dictionary with API statistics
        """
        # This would require tracking API calls, which could be added as middleware
        # For now, return basic connection test results
        connection_test = self.validate_api_credentials()
        
        return {
            'store_type': self.store_type,
            'api_url': self.api_url,
            'connection_status': connection_test['is_valid'],
            'connection_time': connection_test.get('connection_time'),
            'last_test': time.time(),
            'features_available': {
                'categories': True,
                'products': True,
                'variations': True,
                'image_urls': True,
                'system_status': True
            }
        }
    
    def bulk_update_product_status(self, product_ids: List[int], status: str = 'publish') -> Dict[str, any]:
        """
        Bulk update product status (if write permissions are available)
        
        Args:
            product_ids: List of product IDs to update
            status: New status ('publish', 'draft', 'private')
            
        Returns:
            Dictionary with update results
        """
        logger.warning("Bulk update operations require write permissions - current implementation is read-only")
        
        # This would be implemented if write permissions were available
        # For now, return a placeholder response
        return {
            'success': False,
            'message': 'Write operations not implemented - service is read-only',
            'product_ids': product_ids,
            'requested_status': status
        }