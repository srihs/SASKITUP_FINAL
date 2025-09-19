"""
Test suite for CIN7Service

This module contains comprehensive tests for the CIN7Service class:
- Authentication and connection testing
- Product data fetching and parsing
- School organization logic
- Error handling and retry logic
- Rate limiting functionality
- API response mocking
"""

import json
import time
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from requests.exceptions import RequestException, Timeout, ConnectionError
from clubs.services.cin7_service import CIN7Service


class CIN7ServiceInitializationTest(TestCase):
    """Test CIN7Service initialization and configuration"""

    @override_settings(
        CIN7_API_URL='https://test-api.cin7.com',
        CIN7_API_USERNAME='test_user',
        CIN7_API_KEY='test_key',
        CIN7_WHOLE_SALE_ID='190'
    )
    def test_service_initialization_success(self):
        """Test successful service initialization with proper config"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key',
            'CIN7_WHOLE_SALE_ID': '190'
        }):
            service = CIN7Service()

            self.assertEqual(service.api_url, 'https://test-api.cin7.com')
            self.assertEqual(service.username, 'test_user')
            self.assertEqual(service.api_key, 'test_key')
            self.assertEqual(service.wholesale_id, '190')
            self.assertIn('Authorization', service.headers)
            self.assertEqual(service.headers['Content-Type'], 'application/json')

    def test_service_initialization_missing_credentials(self):
        """Test service initialization with missing credentials"""
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError) as context:
                CIN7Service()

            self.assertIn("CIN7 API credentials not found", str(context.exception))

    @patch.dict('os.environ', {
        'CIN7_API_URL': 'https://test-api.cin7.com',
        'CIN7_API_USERNAME': 'test_user',
        'CIN7_API_KEY': 'test_key'
    })
    def test_basic_auth_header_creation(self):
        """Test Basic Auth header is properly created"""
        service = CIN7Service()

        # Decode the auth header to verify
        import base64
        auth_header = service.headers['Authorization']
        self.assertTrue(auth_header.startswith('Basic '))

        encoded_credentials = auth_header.replace('Basic ', '')
        decoded_credentials = base64.b64decode(encoded_credentials).decode()
        self.assertEqual(decoded_credentials, 'test_user:test_key')

    @patch.dict('os.environ', {
        'CIN7_API_URL': 'https://test-api.cin7.com',
        'CIN7_API_USERNAME': 'test_user',
        'CIN7_API_KEY': 'test_key'
    })
    def test_rate_limiting_configuration(self):
        """Test rate limiting configuration"""
        service = CIN7Service()

        self.assertEqual(service.min_request_interval, 0.5)
        self.assertEqual(service.max_retries, 3)
        self.assertEqual(service.retry_delay, 2)
        self.assertEqual(service.last_request_time, 0)


class CIN7ServiceConnectionTest(TestCase):
    """Test connection and basic API functionality"""

    def setUp(self):
        """Set up test service instance"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key'
        }):
            self.service = CIN7Service()

    @patch('clubs.services.cin7_service.requests.get')
    def test_connection_test_success(self, mock_get):
        """Test successful connection test"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'Items': []}
        mock_get.return_value = mock_response

        result = self.service.test_connection()

        self.assertTrue(result)
        mock_get.assert_called_once()

    @patch('clubs.services.cin7_service.requests.get')
    def test_connection_test_failure(self, mock_get):
        """Test connection test failure"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = self.service.test_connection()

        self.assertFalse(result)

    @patch('clubs.services.cin7_service.requests.get')
    def test_connection_test_exception(self, mock_get):
        """Test connection test with exception"""
        mock_get.side_effect = ConnectionError("Connection failed")

        result = self.service.test_connection()

        self.assertFalse(result)

    @patch('clubs.services.cin7_service.time.sleep')
    def test_rate_limiting(self, mock_sleep):
        """Test rate limiting functionality"""
        # Simulate rapid requests
        self.service.last_request_time = time.time()
        self.service._rate_limit()

        # Should sleep if request is too soon
        mock_sleep.assert_called_once()

    @patch('clubs.services.cin7_service.time.sleep')
    def test_rate_limiting_no_sleep_needed(self, mock_sleep):
        """Test rate limiting when no sleep is needed"""
        # Set last request time to long ago
        self.service.last_request_time = time.time() - 10

        self.service._rate_limit()

        # Should not sleep
        mock_sleep.assert_not_called()


class CIN7ServiceAPIRequestTest(TestCase):
    """Test API request handling"""

    def setUp(self):
        """Set up test service instance"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key'
        }):
            self.service = CIN7Service()

    @patch('clubs.services.cin7_service.requests.get')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_success(self, mock_rate_limit, mock_get):
        """Test successful API request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True, 'data': 'test'}
        mock_get.return_value = mock_response

        result = self.service._make_request('Products')

        self.assertEqual(result, {'success': True, 'data': 'test'})
        mock_rate_limit.assert_called_once()
        mock_get.assert_called_once()

    @patch('clubs.services.cin7_service.requests.get')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_authentication_failure(self, mock_rate_limit, mock_get):
        """Test API request with authentication failure"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = self.service._make_request('Products')

        self.assertIsNone(result)

    @patch('clubs.services.cin7_service.requests.get')
    @patch('clubs.services.cin7_service.time.sleep')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_rate_limit_retry(self, mock_rate_limit, mock_sleep, mock_get):
        """Test API request with rate limiting and retry"""
        # First call returns 429, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'success': True}

        mock_get.side_effect = [mock_response_429, mock_response_200]

        result = self.service._make_request('Products')

        self.assertEqual(result, {'success': True})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('clubs.services.cin7_service.requests.get')
    @patch('clubs.services.cin7_service.time.sleep')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_max_retries_exceeded(self, mock_rate_limit, mock_sleep, mock_get):
        """Test API request exceeding max retries"""
        mock_get.side_effect = RequestException("Network error")

        result = self.service._make_request('Products')

        self.assertIsNone(result)
        self.assertEqual(mock_get.call_count, 3)  # max_retries = 3

    @patch('clubs.services.cin7_service.requests.get')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_with_params(self, mock_rate_limit, mock_get):
        """Test API request with query parameters"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'Items': []}
        mock_get.return_value = mock_response

        params = {'page': 1, 'rows': 50}
        result = self.service._make_request('Products', params)

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]['params'], params)

    @patch('clubs.services.cin7_service.requests.get')
    @patch.object(CIN7Service, '_rate_limit')
    def test_make_request_timeout(self, mock_rate_limit, mock_get):
        """Test API request timeout handling"""
        mock_get.side_effect = Timeout("Request timed out")

        result = self.service._make_request('Products')

        self.assertIsNone(result)


class CIN7ServiceProductFetchTest(TestCase):
    """Test product fetching functionality"""

    def setUp(self):
        """Set up test service instance"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key'
        }):
            self.service = CIN7Service()

    def test_get_wholesale_products_parameters(self):
        """Test get_wholesale_products parameter handling"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'Items': []}

            self.service.get_wholesale_products(page=2, rows_per_page=50)

            expected_params = {
                'page': 2,
                'rows': 50,
                'where': 'CategoryPath LIKE "%Wholesale Schools%"'
            }
            mock_request.assert_called_once_with('Products', expected_params)

    def test_get_wholesale_products_default_parameters(self):
        """Test get_wholesale_products with default parameters"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'Items': []}

            self.service.get_wholesale_products()

            expected_params = {
                'page': 1,
                'rows': 100,
                'where': 'CategoryPath LIKE "%Wholesale Schools%"'
            }
            mock_request.assert_called_once_with('Products', expected_params)

    def test_get_all_wholesale_products_single_page(self):
        """Test get_all_wholesale_products with single page"""
        with patch.object(self.service, 'get_wholesale_products') as mock_get:
            # Single page with less than rows_per_page items
            mock_get.return_value = {
                'Items': [
                    {'ProductId': '1', 'ProductName': 'Product 1'},
                    {'ProductId': '2', 'ProductName': 'Product 2'}
                ]
            }

            result = self.service.get_all_wholesale_products()

            self.assertEqual(len(result), 2)
            mock_get.assert_called_once_with(1, 100)

    def test_get_all_wholesale_products_multiple_pages(self):
        """Test get_all_wholesale_products with pagination"""
        with patch.object(self.service, 'get_wholesale_products') as mock_get:
            # Mock multiple pages
            def side_effect(page, rows_per_page):
                if page == 1:
                    return {'Items': [{'ProductId': str(i)} for i in range(100)]}
                elif page == 2:
                    return {'Items': [{'ProductId': str(i)} for i in range(100, 150)]}
                else:
                    return {'Items': []}

            mock_get.side_effect = side_effect

            result = self.service.get_all_wholesale_products()

            self.assertEqual(len(result), 150)
            self.assertEqual(mock_get.call_count, 3)  # Pages 1, 2, and 3

    def test_get_all_wholesale_products_no_data(self):
        """Test get_all_wholesale_products with no data"""
        with patch.object(self.service, 'get_wholesale_products') as mock_get:
            mock_get.return_value = None

            result = self.service.get_all_wholesale_products()

            self.assertEqual(len(result), 0)

    def test_get_all_wholesale_products_safety_limit(self):
        """Test get_all_wholesale_products safety limit"""
        with patch.object(self.service, 'get_wholesale_products') as mock_get:
            # Always return full page to trigger safety limit
            mock_get.return_value = {'Items': [{'ProductId': str(i)} for i in range(100)]}

            result = self.service.get_all_wholesale_products()

            # Should stop at safety limit (1000 pages)
            self.assertEqual(mock_get.call_count, 1000)

    def test_get_product_details(self):
        """Test get_product_details method"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'ProductId': '123', 'ProductName': 'Test Product'}

            result = self.service.get_product_details('123')

            mock_request.assert_called_once_with('Products/123')
            self.assertEqual(result['ProductId'], '123')

    def test_get_product_categories(self):
        """Test get_product_categories method"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {
                'Items': [
                    {'CategoryId': '1', 'CategoryName': 'Category 1'},
                    {'CategoryId': '2', 'CategoryName': 'Category 2'}
                ]
            }

            result = self.service.get_product_categories()

            mock_request.assert_called_once_with('ProductCategories')
            self.assertEqual(len(result), 2)

    def test_search_products(self):
        """Test search_products method"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'Items': []}

            self.service.search_products('test search', page=2, rows_per_page=25)

            expected_params = {
                'page': 2,
                'rows': 25,
                'where': '(ProductName LIKE "%test search%" OR SKU LIKE "%test search%") AND CategoryPath LIKE "%Wholesale Schools%"'
            }
            mock_request.assert_called_once_with('Products', expected_params)


class CIN7ServiceDataParsingTest(TestCase):
    """Test data parsing and organization functionality"""

    def setUp(self):
        """Set up test service instance"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key'
        }):
            self.service = CIN7Service()

        self.sample_product = {
            'ProductId': '12345',
            'ProductName': 'Test Sports Jersey',
            'ProductDescription': 'A high-quality sports jersey',
            'ShortDescription': 'Sports jersey',
            'SKU': 'TSJ-001',
            'Barcode': '1234567890123',
            'Brand': 'SportsBrand',
            'Supplier': 'SportsSupplier',
            'UnitOfMeasure': 'Each',
            'SellPrice1': '50.00',
            'SellPrice2': '75.00',
            'CostPrice': '30.00',
            'QtyAvailable': 100,
            'QtyOnHand': 120,
            'QtyCommitted': 20,
            'Weight': '0.5',
            'Length': '10',
            'Width': '8',
            'Height': '2',
            'ImageUrl': 'https://example.com/image.jpg',
            'CategoryPath': 'Wholesale Schools > Test High School > Sports Equipment',
            'Discontinued': False
        }

    def test_extract_school_info_from_product(self):
        """Test school information extraction from product"""
        school_info = self.service.extract_school_info_from_product(self.sample_product)

        expected_info = {
            'name': 'Test High School',
            'code': 'TSJ',  # From SKU prefix
            'description': 'A high-quality sports jersey',
            'brand': 'SportsBrand',
            'category_path': 'Wholesale Schools > Test High School > Sports Equipment'
        }

        self.assertEqual(school_info['name'], expected_info['name'])
        self.assertEqual(school_info['code'], expected_info['code'])
        self.assertEqual(school_info['description'], expected_info['description'])
        self.assertEqual(school_info['brand'], expected_info['brand'])

    def test_extract_school_info_no_category_path(self):
        """Test school info extraction with missing category path"""
        product_no_path = self.sample_product.copy()
        product_no_path['CategoryPath'] = ''

        school_info = self.service.extract_school_info_from_product(product_no_path)

        # Should fall back to brand
        self.assertEqual(school_info['name'], 'SportsBrand')

    def test_extract_school_info_invalid_category_path(self):
        """Test school info extraction with invalid category path"""
        product_invalid_path = self.sample_product.copy()
        product_invalid_path['CategoryPath'] = 'Just One Level'

        school_info = self.service.extract_school_info_from_product(product_invalid_path)

        # Should fall back to brand
        self.assertEqual(school_info['name'], 'SportsBrand')

    def test_parse_product_data_complete(self):
        """Test complete product data parsing"""
        parsed = self.service.parse_product_data(self.sample_product)

        expected_parsed = {
            'cin7_id': '12345',
            'name': 'Test Sports Jersey',
            'description': 'A high-quality sports jersey',
            'short_description': 'Sports jersey',
            'cin7_sku': 'TSJ-001',
            'cin7_barcode': '1234567890123',
            'cin7_brand': 'SportsBrand',
            'cin7_supplier': 'SportsSupplier',
            'cin7_unit_of_measure': 'Each',
            'wholesale_price': Decimal('50.00'),
            'retail_price': Decimal('75.00'),
            'cost_price': Decimal('30.00'),
            'stock_status': 'in_stock',
            'quantity_available': 100,
            'quantity_on_hand': 120,
            'quantity_committed': 20,
            'weight': '0.5',
            'dimensions': {'length': '10', 'width': '8', 'height': '2'},
            'attributes': {
                'supplier': 'SportsSupplier',
                'brand': 'SportsBrand',
                'unit_of_measure': 'Each',
                'barcode': '1234567890123',
                'discontinued': False
            },
            'image_url': 'https://example.com/image.jpg',
            'category_path': 'Wholesale Schools > Test High School > Sports Equipment'
        }

        self.assertEqual(parsed['cin7_id'], expected_parsed['cin7_id'])
        self.assertEqual(parsed['name'], expected_parsed['name'])
        self.assertEqual(parsed['wholesale_price'], expected_parsed['wholesale_price'])
        self.assertEqual(parsed['stock_status'], expected_parsed['stock_status'])
        self.assertEqual(parsed['dimensions'], expected_parsed['dimensions'])

    def test_parse_product_data_out_of_stock(self):
        """Test product parsing for out of stock item"""
        out_of_stock_product = self.sample_product.copy()
        out_of_stock_product['QtyAvailable'] = 0

        parsed = self.service.parse_product_data(out_of_stock_product)

        self.assertEqual(parsed['stock_status'], 'out_of_stock')
        self.assertEqual(parsed['quantity_available'], 0)

    def test_parse_product_data_discontinued(self):
        """Test product parsing for discontinued item"""
        discontinued_product = self.sample_product.copy()
        discontinued_product['Discontinued'] = True

        parsed = self.service.parse_product_data(discontinued_product)

        self.assertEqual(parsed['stock_status'], 'discontinued')

    def test_parse_product_data_missing_prices(self):
        """Test product parsing with missing price data"""
        no_price_product = self.sample_product.copy()
        del no_price_product['SellPrice1']
        del no_price_product['CostPrice']

        parsed = self.service.parse_product_data(no_price_product)

        self.assertIsNone(parsed['wholesale_price'])
        self.assertIsNone(parsed['cost_price'])
        self.assertEqual(parsed['retail_price'], Decimal('75.00'))

    def test_parse_product_data_alternative_price_fields(self):
        """Test product parsing with alternative price field names"""
        alt_price_product = self.sample_product.copy()
        alt_price_product['WholesalePrice'] = '45.00'
        alt_price_product['RetailPrice'] = '70.00'
        alt_price_product['AvgCost'] = '25.00'

        parsed = self.service.parse_product_data(alt_price_product)

        self.assertEqual(parsed['wholesale_price'], Decimal('45.00'))
        self.assertEqual(parsed['retail_price'], Decimal('70.00'))
        self.assertEqual(parsed['cost_price'], Decimal('25.00'))

    def test_organize_products_by_school(self):
        """Test product organization by school"""
        products = [
            {
                'ProductId': '1',
                'CategoryPath': 'Wholesale Schools > School A > Category 1',
                'ProductName': 'Product 1',
                'Brand': 'Brand A'
            },
            {
                'ProductId': '2',
                'CategoryPath': 'Wholesale Schools > School A > Category 2',
                'ProductName': 'Product 2',
                'Brand': 'Brand A'
            },
            {
                'ProductId': '3',
                'CategoryPath': 'Wholesale Schools > School B > Category 1',
                'ProductName': 'Product 3',
                'Brand': 'Brand B'
            }
        ]

        with patch.object(self.service, 'parse_product_data') as mock_parse:
            mock_parse.side_effect = lambda p: {'name': p['ProductName'], 'cin7_id': p['ProductId']}

            organized = self.service.organize_products_by_school(products)

            self.assertEqual(len(organized), 2)  # Two schools
            self.assertIn('School A', organized)
            self.assertIn('School B', organized)
            self.assertEqual(len(organized['School A']['products']), 2)
            self.assertEqual(len(organized['School B']['products']), 1)

    def test_organize_products_by_school_no_category_path(self):
        """Test product organization with missing category paths"""
        products = [
            {
                'ProductId': '1',
                'CategoryPath': '',
                'ProductName': 'Product 1',
                'Brand': 'Brand A'
            }
        ]

        with patch.object(self.service, 'parse_product_data') as mock_parse:
            mock_parse.return_value = {'name': 'Product 1', 'cin7_id': '1'}

            organized = self.service.organize_products_by_school(products)

            # Should fall back to brand name
            self.assertIn('Brand A', organized)

    def test_get_product_stock_levels(self):
        """Test get_product_stock_levels method"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'StockLevels': []}

            result = self.service.get_product_stock_levels('123')

            mock_request.assert_called_once_with('Products/123/StockLevels')


class CIN7ServiceErrorHandlingTest(TestCase):
    """Test error handling and edge cases"""

    def setUp(self):
        """Set up test service instance"""
        with patch.dict('os.environ', {
            'CIN7_API_URL': 'https://test-api.cin7.com',
            'CIN7_API_USERNAME': 'test_user',
            'CIN7_API_KEY': 'test_key'
        }):
            self.service = CIN7Service()

    def test_parse_product_data_empty_product(self):
        """Test product parsing with empty product data"""
        empty_product = {}
        parsed = self.service.parse_product_data(empty_product)

        self.assertEqual(parsed['cin7_id'], '')
        self.assertEqual(parsed['name'], '')
        self.assertIsNone(parsed['wholesale_price'])
        self.assertEqual(parsed['stock_status'], 'in_stock')  # Default

    def test_parse_product_data_invalid_numbers(self):
        """Test product parsing with invalid numeric data"""
        invalid_product = {
            'ProductId': '123',
            'SellPrice1': 'invalid_price',
            'QtyAvailable': 'invalid_qty'
        }

        # Should handle gracefully without crashing
        try:
            parsed = self.service.parse_product_data(invalid_product)
            # If it doesn't crash, that's good
            self.assertEqual(parsed['cin7_id'], '123')
        except (ValueError, TypeError):
            # Acceptable to raise these for invalid data
            pass

    def test_extract_school_info_minimal_data(self):
        """Test school info extraction with minimal product data"""
        minimal_product = {
            'ProductId': '123'
        }

        school_info = self.service.extract_school_info_from_product(minimal_product)

        self.assertEqual(school_info['name'], '')
        self.assertEqual(school_info['code'], '')
        self.assertEqual(school_info['description'], '')

    @patch('clubs.services.cin7_service.logger')
    def test_logging_functionality(self, mock_logger):
        """Test that logging is working properly"""
        with patch.object(self.service, '_make_request') as mock_request:
            mock_request.return_value = {'Items': []}

            self.service.get_wholesale_products()

            # Verify logging was called
            mock_logger.info.assert_called()

    def test_url_construction(self):
        """Test proper URL construction for API calls"""
        with patch.object(self.service, '_rate_limit'):
            with patch('clubs.services.cin7_service.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {}
                mock_get.return_value = mock_response

                self.service._make_request('Products')

                # Verify URL construction
                call_args = mock_get.call_args
                expected_url = f"{self.service.api_url}/Products"
                self.assertEqual(call_args[0][0], expected_url)

    def test_url_construction_with_leading_slash(self):
        """Test URL construction with endpoint having leading slash"""
        with patch.object(self.service, '_rate_limit'):
            with patch('clubs.services.cin7_service.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {}
                mock_get.return_value = mock_response

                self.service._make_request('/Products')

                # Should handle leading slash properly
                call_args = mock_get.call_args
                expected_url = f"{self.service.api_url}/Products"
                self.assertEqual(call_args[0][0], expected_url)

    def test_timeout_configuration(self):
        """Test that requests are made with proper timeout"""
        with patch.object(self.service, '_rate_limit'):
            with patch('clubs.services.cin7_service.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {}
                mock_get.return_value = mock_response

                self.service._make_request('Products')

                # Verify timeout is set
                call_args = mock_get.call_args
                self.assertEqual(call_args[1]['timeout'], 30)