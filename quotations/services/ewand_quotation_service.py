"""
eWand Quotation Service

Handles creation of eWand quotations from approved bespoke quotations.

Key Features:
- Transforms quotation data to eWand API format
- Handles bespoke product-specific requirements
- Validates quotation data before sync
- Comprehensive error handling
- Integrates with eWand system for cut & sew production

Author: Claude Code
Date: 2025-11-24
"""

import json
import logging
import requests
from decimal import Decimal
from typing import Dict, List, Optional
from decouple import config
from django.contrib.contenttypes.models import ContentType
from urllib.parse import unquote

logger = logging.getLogger(__name__)


class EwandQuotationService:
    """
    Service for creating eWand quotations from approved bespoke quotations.

    eWand is the system used for managing cut & sew bespoke product orders.
    This service syncs ONLY bespoke products to eWand during quotation approval.
    """

    def __init__(self):
        """Initialize eWand quotation service with credentials from environment"""
        # Extract base URL from the full API URL (remove endpoint path)
        full_api_url = config('EWAND_API_URL', default='')
        if full_api_url:
            # Extract base URL (e.g., https://dev-ewand.it.sas.co.nz)
            parts = full_api_url.split('/quotation')
            self.base_url = parts[0] if parts else full_api_url
            self.api_url = full_api_url
        else:
            self.base_url = ''
            self.api_url = ''

        self.email = config('EWAND_API_USERNAME', default='')  # Changed from username to email
        self.password = config('EWAND_API_PASSWORD', default='')
        self.session = None
        self.authenticated = False

        if not all([self.api_url, self.email, self.password]):
            logger.warning("eWand API credentials not fully configured in .env file")

        logger.info(f"EwandQuotationService initialized - Base URL: {self.base_url}")

    def get_csrf_token(self):
        """
        Step 1: Get CSRF token from Laravel Sanctum.
        Endpoint: /sanctum/csrf-cookie

        Returns:
            str: XSRF-TOKEN value from cookies

        Raises:
            Exception: If CSRF token retrieval fails
        """
        csrf_url = f"{self.base_url}/sanctum/csrf-cookie"

        # Create session to maintain cookies
        self.session = requests.Session()

        try:
            logger.info(f"🔐 Requesting CSRF token from: {csrf_url}")
            response = self.session.get(csrf_url, timeout=30)
            response.raise_for_status()

            # Extract XSRF-TOKEN from cookies
            xsrf_token = self.session.cookies.get('XSRF-TOKEN')

            if not xsrf_token:
                logger.error("XSRF-TOKEN not found in cookies")
                logger.error(f"Available cookies: {list(self.session.cookies.keys())}")
                raise Exception("XSRF-TOKEN not found in response cookies")

            # Decode the URL-encoded token (Laravel encodes it)
            decoded_token = unquote(xsrf_token)

            logger.info(f"✅ CSRF token retrieved successfully")
            logger.debug(f"Encoded token: {xsrf_token[:30]}...")
            logger.debug(f"Decoded token: {decoded_token[:30]}...")

            return decoded_token

        except Exception as e:
            logger.error(f"❌ Failed to get CSRF token: {e}")
            raise

    def login(self, xsrf_token):
        """
        Step 2: Login to eWand with CSRF token.
        Endpoint: /login
        Headers: X-XSRF-TOKEN

        Args:
            xsrf_token: CSRF token from get_csrf_token()

        Raises:
            Exception: If login fails
        """
        login_url = f"{self.base_url}/login"

        payload = {
            "email": self.email,
            "password": self.password,
            "remember": True
        }

        headers = {
            "X-XSRF-TOKEN": xsrf_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": self.base_url,
            "Origin": self.base_url
        }

        try:
            logger.info(f"🔐 Logging in to eWand: {login_url}")
            logger.info(f"Email: {self.email}")
            logger.info(f"Cookies being sent: {self.session.cookies.get_dict()}")
            logger.debug(f"Request headers: {headers}")
            logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

            response = self.session.post(
                login_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            # Log response details immediately (before raising exception)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")

            # Check for 422 validation error - log full details
            if response.status_code == 422:
                logger.error("="*80)
                logger.error("❌ 422 Unprocessable Content - Laravel Validation Error")
                logger.error("="*80)
                logger.error(f"Login URL: {login_url}")
                logger.error(f"Request Headers: {json.dumps(headers, indent=2)}")
                logger.error(f"Request Payload: {json.dumps(payload, indent=2)}")
                logger.error(f"Response Status: {response.status_code}")
                logger.error(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
                logger.error(f"Response Body: {response.text}")

                # Try to parse validation errors
                try:
                    error_data = response.json()
                    logger.error(f"Parsed Validation Errors: {json.dumps(error_data, indent=2)}")

                    # Extract specific error messages
                    if 'errors' in error_data:
                        logger.error("\nField-specific validation errors:")
                        for field, messages in error_data['errors'].items():
                            logger.error(f"  - {field}: {messages}")

                    if 'message' in error_data:
                        logger.error(f"\nError message: {error_data['message']}")

                except ValueError:
                    logger.error("Could not parse response as JSON")
                except Exception as parse_error:
                    logger.error(f"Error parsing validation response: {parse_error}")

                logger.error("="*80)
                raise Exception(f"eWand login validation failed (422): {response.text}")

            # Check if HTML response (login failed)
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                logger.error("❌ Login failed - received HTML response (likely redirected to login page)")
                logger.error(f"Status Code: {response.status_code}")
                logger.error(f"Response preview: {response.text[:500]}")
                raise Exception("eWand login failed - received HTML instead of JSON")

            response.raise_for_status()

            logger.info(f"✅ Login successful - Status: {response.status_code}")
            logger.info(f"Session cookies: {list(self.session.cookies.keys())}")

            self.authenticated = True

            return response

        except requests.HTTPError as e:
            logger.error(f"❌ HTTP Error during login: {e}")
            logger.error(f"Response status: {e.response.status_code if e.response else 'N/A'}")
            logger.error(f"Response body: {e.response.text if e.response else 'N/A'}")
            raise
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            raise

    def authenticate(self):
        """
        Complete eWand authentication flow using Laravel Sanctum:
        1. Get CSRF token from /sanctum/csrf-cookie
        2. Login with CSRF token via /login

        This must be called before making any API requests.
        """
        logger.info("="*80)
        logger.info("🔐 Starting eWand Sanctum authentication...")
        logger.info("="*80)

        try:
            # Step 1: Get CSRF token
            xsrf_token = self.get_csrf_token()

            # Step 2: Login with CSRF token
            self.login(xsrf_token)

            logger.info("="*80)
            logger.info("✅ eWand authentication complete - Ready to make API calls")
            logger.info("="*80)

        except Exception as e:
            logger.error("="*80)
            logger.error(f"❌ eWand authentication failed: {e}")
            logger.error("="*80)
            raise

    def create_quotation(self, quotation) -> Dict:
        """
        Create an eWand quotation from an approved quotation with bespoke items.

        Args:
            quotation: Approved Quotation instance with bespoke products

        Returns:
            dict: Response data with success status and eWand quotation details

        Raises:
            ValueError: If validation fails
            Exception: For API errors
        """
        try:
            # Validate quotation has bespoke items
            if not quotation.has_bespoke_items():
                return {
                    'success': False,
                    'message': 'Quotation has no bespoke items to sync to eWand'
                }

            # Validate quotation
            self._validate_quotation(quotation)

            # Build API payload
            payload = self._build_quotation_payload(quotation)

            # Authenticate first if not already authenticated
            if not self.authenticated:
                self.authenticate()

            # Make API request using authenticated session
            logger.info(f"Creating eWand quotation for quotation {quotation.quotation_number}")
            logger.debug(f"eWand API Request - Full payload: {json.dumps(payload, indent=2)}")

            # Print payload to console for debugging
            print("\n" + "="*80)
            print(f"eWand API REQUEST - Quotation: {quotation.quotation_number}")
            print("="*80)
            print(f"API URL: {self.api_url}")
            print(f"Email: {self.email}")
            print(f"Authenticated: {self.authenticated}")
            print("\nPayload:")
            print(json.dumps(payload, indent=2))
            print("="*80 + "\n")

            # Get current XSRF token from session cookies (URL-encoded)
            xsrf_token_cookie = self.session.cookies.get('XSRF-TOKEN')

            if not xsrf_token_cookie:
                logger.warning("XSRF-TOKEN not found in session - re-authenticating")
                self.authenticate()
                xsrf_token_cookie = self.session.cookies.get('XSRF-TOKEN')

            # CRITICAL: Decode the URL-encoded token (same as in get_csrf_token)
            # Laravel returns a new CSRF token after login in the response cookies
            # This fresh token must be decoded before use in API requests
            xsrf_token = unquote(xsrf_token_cookie)

            logger.info("Making eWand API request with fresh CSRF token")
            logger.debug(f"CSRF token (encoded): {xsrf_token_cookie[:30]}...")
            logger.debug(f"CSRF token (decoded): {xsrf_token[:30]}...")
            logger.debug(f"Session cookies available: {list(self.session.cookies.keys())}")

            # Set proper headers for Laravel Sanctum API
            headers = {
                'X-XSRF-TOKEN': xsrf_token,
                'Content-Type': 'application/json',
                'Accept': 'application/json',  # Critical for Laravel to return JSON instead of HTML
            }

            # Use authenticated session instead of Basic Auth
            response = self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            # Log response details
            logger.info(f"eWand API Response - Status Code: {response.status_code}")
            logger.debug(f"eWand API Response - Headers: {dict(response.headers)}")
            logger.debug(f"eWand API Response - Body (first 500 chars): {response.text[:500]}")

            # Validate response is JSON (not HTML)
            self._validate_json_response(response)

            # Print response to console for debugging
            print("\n" + "="*80)
            print(f"eWand API RESPONSE - Quotation: {quotation.quotation_number}")
            print("="*80)
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print(f"\nResponse Body:")
            print(response.text if response.text else "(Empty response)")
            print("="*80 + "\n")

            # Handle response
            if response.status_code == 200 or response.status_code == 201:
                return self._handle_success_response(quotation, response)
            else:
                return self._handle_error_response(quotation, response)

        except requests.Timeout:
            error_msg = f"eWand API request timeout for quotation {quotation.quotation_number}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error_type': 'timeout'
            }
        except requests.ConnectionError as e:
            error_msg = f"eWand API connection error: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error_type': 'connection_error'
            }
        except Exception as e:
            error_msg = f"Unexpected error creating eWand quotation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg,
                'error_type': 'unexpected_error'
            }

    def _validate_json_response(self, response):
        """
        Validate that the response is JSON and not HTML.

        Args:
            response: Requests response object

        Raises:
            Exception: If response is HTML (indicates authentication failure or redirect)
        """
        content_type = response.headers.get('Content-Type', '').lower()

        # Check if response is HTML (authentication failure)
        if 'text/html' in content_type:
            logger.error(
                f"eWand API returned HTML instead of JSON - Authentication failed or redirected to login page\n"
                f"URL: {response.url}\n"
                f"Status Code: {response.status_code}\n"
                f"Content-Type: {content_type}\n"
                f"Response preview: {response.text[:500]}"
            )
            raise Exception(
                "eWand API authentication failed - received HTML login page instead of JSON response. "
                "Please verify API credentials and endpoint URL."
            )

        # Check for JSON content type
        if 'application/json' not in content_type and response.text.strip():
            logger.warning(
                f"Unexpected Content-Type: {content_type}. "
                f"Expected 'application/json'. Response may not be valid JSON."
            )

        # Try to parse JSON to ensure it's valid
        if response.text.strip():
            try:
                response.json()
            except ValueError as e:
                logger.error(f"Response is not valid JSON: {e}\nResponse: {response.text[:500]}")
                raise Exception(f"eWand API returned invalid JSON: {str(e)}")

        logger.debug("Response validation passed - JSON content confirmed")

    def _validate_quotation(self, quotation):
        """
        Validate quotation before sending to eWand.

        Args:
            quotation: Quotation instance to validate

        Raises:
            ValueError: If validation fails
        """
        # Check quotation has bespoke items
        if not quotation.has_bespoke_items():
            raise ValueError("Quotation must have at least one bespoke item")

        # Validate required fields
        if not quotation.institution:
            raise ValueError("Quotation must have an associated institution")

        # Validate creator
        if not quotation.created_by:
            raise ValueError("Quotation must have a creator (sales agent)")

        # Note: Category validation removed - using default category_id=23 for items without categories
        logger.info(f"eWand validation passed for quotation {quotation.quotation_number}")

    def _build_quotation_payload(self, quotation) -> Dict:
        """
        Build eWand API payload from quotation.

        Args:
            quotation: Quotation instance

        Returns:
            dict: eWand API payload
        """
        # Get bespoke content type
        bespoke_ct = ContentType.objects.get(app_label='bespoke', model='bespokeproduct')

        # Filter ONLY bespoke items - exclude all non-bespoke products
        bespoke_items = quotation.items.filter(product_content_type=bespoke_ct)

        # Log filtering results
        total_items = quotation.items.count()
        bespoke_count = bespoke_items.count()
        non_bespoke_count = total_items - bespoke_count

        logger.info(
            f"eWand payload filtering for {quotation.quotation_number}: "
            f"Total items: {total_items}, Bespoke items: {bespoke_count}, "
            f"Non-bespoke items excluded: {non_bespoke_count}"
        )

        if non_bespoke_count > 0:
            logger.info(
                f"Excluded {non_bespoke_count} non-bespoke items from eWand quotation. "
                f"These items should be synced to CIN7 instead."
            )

        # Get institution details
        institution = quotation.institution

        # Map institution email with priority
        customer_email = (
            getattr(institution, 'cin7_email', None) or
            getattr(institution, 'email', None) or
            quotation.created_by.email or
            'noreply@sascreative.co.nz'
        )

        # Map customer contact information
        attention_person = getattr(institution, 'cin7_first_name', '') or getattr(institution, 'contact_name', '') or 'Customer'
        attention_person_contact = getattr(institution, 'cin7_phone', '') or getattr(institution, 'phone', '') or ''

        # Get sales agent and customer service agent IDs (using creator as sales agent)
        sales_agent_id = quotation.created_by.id if quotation.created_by else 151  # Default fallback
        customer_service_agent_id = quotation.approved_by.id if quotation.approved_by else 115  # Default fallback

        # Build items array - ONLY bespoke products
        items = []
        external_items = []

        logger.info(f"Building eWand items array with {bespoke_count} bespoke products:")

        for item in bespoke_items:
            # Get bespoke product
            bespoke_product = item.product

            # Get category_id from BespokeProduct's category assignments
            # Default to 23 if no category assigned or cin7_id is not a valid integer
            category_id = 23  # Default category_id for eWand
            if bespoke_product and hasattr(bespoke_product, 'category_assignments'):
                first_assignment = bespoke_product.category_assignments.first()
                if first_assignment and first_assignment.category:
                    if first_assignment.category.cin7_id:
                        # Try to convert cin7_id to integer, fall back to default if not numeric
                        try:
                            category_id = int(first_assignment.category.cin7_id)
                            logger.debug(
                                f"Item '{item.product_name}' category: {first_assignment.category.name} "
                                f"(cin7_id: {category_id})"
                            )
                        except ValueError:
                            logger.info(
                                f"Item '{item.product_name}' category cin7_id '{first_assignment.category.cin7_id}' "
                                f"is not a valid integer, using default: {category_id}"
                            )
                    else:
                        logger.info(f"Item '{item.product_name}' category has no cin7_id, using default: {category_id}")
                else:
                    logger.info(f"Item '{item.product_name}' has no category assigned, using default: {category_id}")
            else:
                logger.info(f"Item '{item.product_name}' has no category_assignments attribute, using default: {category_id}")

            # Determine if this is cut & sew or external item based on product type
            # For now, treat all bespoke as cut & sew (can be refined based on product attributes)

            item_data = {
                'style_code': {
                    'id': bespoke_product.cin7_id if hasattr(bespoke_product, 'cin7_id') else item.product_object_id,
                    'code': item.product_sku or bespoke_product.sku if hasattr(bespoke_product, 'sku') else '',
                    'name': item.product_name,
                    'belongs_to': 'internal'  # Bespoke products are internal
                },
                'category_id': category_id,  # REQUIRED: Category ID from BespokeProduct
                'quantity': item.quantity,
                'price_type': 'custom',
                'unit_price': str(item.unit_price),
                'cost_price': str(bespoke_product.cost_price if hasattr(bespoke_product, 'cost_price') else Decimal('0.00')),
                'type': 'cut_and_sew',
                'note': item.notes or None,
                'embellishments': [],  # Can be populated from addon items if needed
                'unit_cost_with_embellishment_unit_costs': float(item.unit_price),
                'embellishment_total': '0.00',
                'gross_price': str(item.line_total),
                'gross_price_without_setup': str(item.line_total),
                'unit_price_total': float(item.line_total),
                'embellishment_cost': '0.00',
                'total_setup_cost': '0.00'
            }

            # Add embellishments from addon items (only for bespoke parent items)
            # Filter addons to ensure they belong to bespoke items only
            addon_items = item.addons.all() if hasattr(item, 'addons') else []
            for addon in addon_items:
                # Additional check: Only include addons for bespoke products
                # Addons are always linked to their parent item, so if parent is bespoke, addon is included
                embellishment = {
                    'id': None,
                    'cost': float(addon.unit_price),
                    'setup_cost': 0,
                    'position': addon.addon_type or 'custom',
                    'quantity': addon.quantity,
                    'total_cost': str(addon.line_total),
                    'setup_quantity': 0,
                    'total_setup_cost': '0.00',
                    'total': str(addon.line_total),
                    'embellishment_id': addon.product_object_id
                }
                item_data['embellishments'].append(embellishment)

                # Update totals
                item_data['embellishment_total'] = str(
                    Decimal(item_data['embellishment_total']) + addon.line_total
                )
                item_data['embellishment_cost'] = str(
                    Decimal(item_data['embellishment_cost']) + addon.unit_price
                )

            items.append(item_data)

            # Log each bespoke item being added
            logger.info(
                f"  - Added bespoke item: {item.product_name} "
                f"(SKU: {item.product_sku}, Qty: {item.quantity}, "
                f"Price: ${item.unit_price}, Category ID: {category_id}, "
                f"Embellishments: {len(item_data['embellishments'])})"
            )

        # Calculate totals
        items_net_price = sum(item.line_total for item in bespoke_items)
        shipping_cost = quotation.shipping_cost or Decimal('0.00')

        # Calculate GST (15%)
        gst_percentage = 15
        gross_without_gst = items_net_price + shipping_cost
        gst_value = gross_without_gst * Decimal(str(gst_percentage / 100))
        gross_price = gross_without_gst + gst_value

        # Build delivery address
        delivery_address = self._build_delivery_address(quotation)

        # Build freight data
        freight = {
            'id': 1,  # Default freight ID
            'region': self._get_region_from_city(quotation.delivery_city) if quotation.delivery_city else 'North Island',
            'amount': float(shipping_cost),
            'gst_included': 1,
            'created_at': quotation.created_at.isoformat() if quotation.created_at else None,
            'updated_at': quotation.updated_at.isoformat() if quotation.updated_at else None
        }

        # Get account_manager_id from environment or use fallback
        # Priority: ENV variable → sales_agent_id → 1 (safe default)
        # eWand's database requires a valid user ID for foreign key constraint
        default_account_manager = sales_agent_id if sales_agent_id else 1
        account_manager_id = config('EWAND_DEFAULT_ACCOUNT_MANAGER_ID', default=default_account_manager, cast=int)
        logger.info(f"Using account_manager_id: {account_manager_id} for quotation {quotation.quotation_number} (fallback: {default_account_manager})")

        # Build payload - CRITICAL: Only contains bespoke items
        payload = {
            'customer_id': institution.id if institution else 4,  # Use institution ID or default
            'customer_email': customer_email,
            'sales_agent_id': sales_agent_id,
            'customer_service_agent_id': customer_service_agent_id,
            'type': 'general',
            'club': institution.name if institution else 'Unknown',
            'attention_person': attention_person,
            'attention_person_contact_no': attention_person_contact,
            'items': items,
            'external_items': external_items,
            'delivery_address': delivery_address,
            'freight': freight,
            'freightBoxesCount': 1,  # Default
            'freightSurchargePercentageAmount': 0,
            'freightSurchargePercentage': 6,
            'freightSurgeAdded': False,
            'totalFreightCost': str(shipping_cost),
            'items_net_price': str(items_net_price),
            'external_items_net_price': '0.00',
            'gst_percentage': gst_percentage,
            'gst_value': str(gst_value),
            'gross_without_gst': str(gross_without_gst),
            'gross_price': float(gross_price),
            'items_net_price_without_setup_charges': str(items_net_price),
            'payment_term_20': False,
            'attachments': [],
            'attachmentsForRemove': [],
            'status': 'DRAFT'  # eWand will manage status transitions
        }

        # Include account_manager_id in payload with valid user ID
        # eWand's database foreign key constraint requires a valid user ID
        payload['account_manager_id'] = account_manager_id
        logger.info(f"Including account_manager_id in payload: {account_manager_id}")

        # Final validation log
        logger.info(
            f"eWand payload ready: {len(items)} bespoke items, "
            f"Total: ${items_net_price}, Shipping: ${shipping_cost}, "
            f"Grand Total (incl GST): ${gross_price}"
        )

        # Verify no non-bespoke items leaked into payload
        if len(items) != bespoke_count:
            logger.error(
                f"CRITICAL: Item count mismatch! Expected {bespoke_count} bespoke items, "
                f"but payload contains {len(items)} items. This should never happen!"
            )

        return payload

    def _build_delivery_address(self, quotation) -> str:
        """
        Build delivery address string from quotation.

        Args:
            quotation: Quotation instance

        Returns:
            str: Formatted delivery address
        """
        address_parts = []

        if quotation.delivery_street_address:
            address_parts.append(quotation.delivery_street_address)
        if quotation.delivery_suburb:
            address_parts.append(quotation.delivery_suburb)
        if quotation.delivery_city:
            address_parts.append(quotation.delivery_city)
        if quotation.delivery_postcode:
            address_parts.append(quotation.delivery_postcode)
        if quotation.delivery_state:
            address_parts.append(quotation.delivery_state)

        return ', '.join(filter(None, address_parts)) or 'Address not provided'

    def _get_region_from_city(self, city: str) -> str:
        """
        Determine NZ region from city name.

        Args:
            city: City name

        Returns:
            str: Region name
        """
        city_lower = city.lower() if city else ''

        # North Island cities
        north_island_cities = [
            'auckland', 'hamilton', 'tauranga', 'rotorua', 'gisborne',
            'napier', 'hastings', 'new plymouth', 'whanganui', 'palmerston north',
            'wellington', 'upper hutt', 'lower hutt', 'porirua'
        ]

        # South Island cities
        south_island_cities = [
            'nelson', 'blenheim', 'christchurch', 'timaru', 'ashburton',
            'dunedin', 'invercargill', 'queenstown'
        ]

        for north_city in north_island_cities:
            if north_city in city_lower:
                return 'North Island'

        for south_city in south_island_cities:
            if south_city in city_lower:
                return 'South Island'

        return 'North Island'  # Default to North Island

    def _handle_success_response(self, quotation, response) -> Dict:
        """
        Handle successful eWand API response.

        Args:
            quotation: Quotation instance
            response: Requests response object

        Returns:
            dict: Success response data
        """
        # Check if response has content
        if not response.text or response.text.strip() == '':
            logger.warning(f"eWand API returned empty response body for quotation {quotation.quotation_number}")
            return {
                'success': True,  # Still consider it success if we got 200/201
                'message': f'eWand quotation created successfully for {quotation.quotation_number} (empty response)',
                'ewand_data': None,
                'quotation_number': quotation.quotation_number,
                'status_code': response.status_code
            }

        try:
            response_data = response.json()
            logger.info(f"eWand quotation created successfully for {quotation.quotation_number}")
            logger.debug(f"eWand Response: {json.dumps(response_data, indent=2)}")

            return {
                'success': True,
                'message': f'eWand quotation created successfully for {quotation.quotation_number}',
                'ewand_data': response_data,
                'quotation_number': quotation.quotation_number,
                'status_code': response.status_code
            }
        except ValueError as e:
            logger.error(f"Failed to parse eWand response JSON: {e}")
            logger.error(f"Response text: {response.text[:1000]}")  # Log first 1000 chars
            return {
                'success': True,  # Still consider it success if we got 200/201
                'message': f'eWand quotation created but response could not be parsed: {str(e)}',
                'quotation_number': quotation.quotation_number,
                'raw_response': response.text[:500],  # Include partial response for debugging
                'status_code': response.status_code
            }

    def _handle_error_response(self, quotation, response) -> Dict:
        """
        Handle error response from eWand API.

        Args:
            quotation: Quotation instance
            response: Requests response object

        Returns:
            dict: Error response data
        """
        try:
            error_data = response.json()
            error_message = error_data.get('message', 'Unknown error')
        except ValueError:
            error_message = response.text or 'Unknown error'

        logger.error(
            f"eWand API error for quotation {quotation.quotation_number}: "
            f"Status {response.status_code}, Message: {error_message}"
        )

        return {
            'success': False,
            'message': f'eWand API error: {error_message}',
            'status_code': response.status_code,
            'error_data': error_message
        }
