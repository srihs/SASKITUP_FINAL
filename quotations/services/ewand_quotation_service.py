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

logger = logging.getLogger(__name__)


class EwandQuotationService:
    """
    Service for creating eWand quotations from approved bespoke quotations.

    eWand is the system used for managing cut & sew bespoke product orders.
    This service syncs ONLY bespoke products to eWand during quotation approval.
    """

    def __init__(self):
        """Initialize eWand quotation service with credentials from environment"""
        self.api_url = config('EWAND_API_URL', default='')
        self.username = config('EWAND_API_USERNAME', default='')
        self.password = config('EWAND_API_PASSWORD', default='')

        if not all([self.api_url, self.username, self.password]):
            logger.warning("eWand API credentials not fully configured in .env file")

        logger.info("EwandQuotationService initialized")

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

            # Make API request
            logger.info(f"Creating eWand quotation for quotation {quotation.quotation_number}")
            logger.debug(f"eWand API Request - Full payload: {json.dumps(payload, indent=2)}")

            # Print payload to console for debugging
            print("\n" + "="*80)
            print(f"eWand API REQUEST - Quotation: {quotation.quotation_number}")
            print("="*80)
            print(f"API URL: {self.api_url}")
            print(f"Username: {self.username}")
            print("\nPayload:")
            print(json.dumps(payload, indent=2))
            print("="*80 + "\n")

            response = requests.post(
                self.api_url,
                json=payload,
                auth=(self.username, self.password),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            # Log response details
            logger.info(f"eWand API Response - Status Code: {response.status_code}")
            logger.debug(f"eWand API Response - Headers: {dict(response.headers)}")
            logger.debug(f"eWand API Response - Body (first 500 chars): {response.text[:500]}")

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

            # Determine if this is cut & sew or external item based on product type
            # For now, treat all bespoke as cut & sew (can be refined based on product attributes)

            item_data = {
                'style_code': {
                    'id': bespoke_product.cin7_id if hasattr(bespoke_product, 'cin7_id') else item.product_object_id,
                    'code': item.product_sku or bespoke_product.sku if hasattr(bespoke_product, 'sku') else '',
                    'name': item.product_name,
                    'belongs_to': 'internal'  # Bespoke products are internal
                },
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
                f"Price: ${item.unit_price}, Embellishments: {len(item_data['embellishments'])})"
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
            'account_manager_id': quotation.approved_by.id if quotation.approved_by else None,
            'status': 'DRAFT'  # eWand will manage status transitions
        }

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
