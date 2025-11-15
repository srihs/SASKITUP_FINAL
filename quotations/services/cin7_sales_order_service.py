"""
CIN7 Sales Order Service

Handles creation of CIN7 Sales Orders from approved quotations.

Key Features:
- Transforms quotation data to CIN7 API format
- Handles Bespoke product filtering (excludes from sync)
- Validates quotation data before sync
- Implements rate limiting
- Comprehensive error handling
- Integrates with CIN7OrderMapping model

Author: Claude Code
Date: 2025-11-15
"""

import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from decouple import config
from django.core.cache import cache
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from schools.services.cin7_api_service import Cin7ApiService
from quotations.models import Quotation, CIN7OrderMapping

logger = logging.getLogger(__name__)


class Cin7SalesOrderService:
    """
    Service for creating CIN7 Sales Orders from approved quotations.

    CRITICAL: Bespoke products are EXCLUDED from CIN7 sync.
    Only Wholesale products with valid cin7_id are synced.
    """

    # Rate limiting configuration (inherited from Cin7ApiService)
    MAX_CALLS_PER_SECOND = 3
    MAX_CALLS_PER_MINUTE = 60
    MAX_CALLS_PER_DAY = 5000

    def __init__(self):
        """Initialize CIN7 Sales Order service"""
        self.api_service = Cin7ApiService()
        self.api_url = self.api_service.api_url
        self.headers = self.api_service.headers

        logger.info("Cin7SalesOrderService initialized")

    def create_sales_order(self, quotation: Quotation) -> Dict:
        """
        Create a CIN7 Sales Order from an approved quotation.

        Args:
            quotation: Approved Quotation instance

        Returns:
            dict: Response data with CIN7 order details

        Raises:
            ValueError: If validation fails
            Exception: For API errors
        """
        # Validate quotation
        self._validate_quotation(quotation)

        # Check rate limit
        self._check_rate_limit()

        # Build API payload
        payload = self._build_sales_order_payload(quotation)

        # Make API request
        import requests
        url = f"{self.api_url.rstrip('/')}/v1/SalesOrders"

        try:
            logger.info(f"Creating CIN7 sales order for quotation {quotation.quotation_number}")

            response = requests.post(
                url,
                json=[payload],  # API expects array of orders
                headers=self.headers,
                timeout=30
            )

            # Handle response
            if response.status_code == 200:
                return self._handle_success_response(quotation, response)
            elif response.status_code == 400:
                return self._handle_validation_error(quotation, response)
            elif response.status_code == 401:
                return self._handle_auth_error(response)
            elif response.status_code == 429:
                return self._handle_rate_limit_error(quotation, response)
            elif response.status_code in [500, 503]:
                return self._handle_server_error(quotation, response)
            else:
                error_msg = f"Unexpected CIN7 response: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except requests.exceptions.RequestException as e:
            logger.error(f"CIN7 API request failed: {e}")
            raise Exception(f"CIN7 API request failed: {str(e)}")

    def _validate_quotation(self, quotation: Quotation):
        """
        Validate quotation before creating CIN7 sales order.

        Args:
            quotation: Quotation instance

        Raises:
            ValueError: If validation fails
        """
        errors = []

        # Check quotation status
        if quotation.status not in ['approved', 'confirmed']:
            errors.append(f"Quotation status must be approved or confirmed, got '{quotation.status}'")

        # Check if quotation has items
        if not quotation.items.exists():
            errors.append("Quotation has no items")

        # Check if quotation has syncable items (non-Bespoke)
        syncable_items = self._get_syncable_items(quotation)
        if not syncable_items:
            errors.append("Quotation has no syncable items (all items are Bespoke or missing CIN7 IDs)")

        # Validate CIN7 product IDs for syncable items
        for item in syncable_items:
            if not hasattr(item.product, 'cin7_id') or not item.product.cin7_id:
                errors.append(f"Product '{item.product_name}' missing CIN7 ID")

        # Check financial data
        if quotation.total <= 0:
            errors.append("Quotation total must be greater than 0")

        # Check contact information
        if not quotation.created_by or not quotation.created_by.email:
            errors.append("Quotation creator must have an email address")

        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Quotation validation failed: {error_msg}")
            raise ValueError(f"Quotation validation failed: {error_msg}")

    def _get_syncable_items(self, quotation: Quotation) -> List:
        """
        Get quotation items that can be synced to CIN7.

        CRITICAL: Excludes all Bespoke products.

        Args:
            quotation: Quotation instance

        Returns:
            list: QuotationItem instances that can be synced
        """
        # Get ContentType for BespokeProduct
        try:
            bespoke_ct = ContentType.objects.get(app_label='bespoke', model='bespokeproduct')
        except ContentType.DoesNotExist:
            # If BespokeProduct doesn't exist, all items are syncable
            bespoke_ct = None

        syncable_items = []
        excluded_count = 0

        for item in quotation.items.all():
            # Skip Bespoke products
            if bespoke_ct and item.product_content_type == bespoke_ct:
                excluded_count += 1
                logger.info(f"Excluding Bespoke product '{item.product_name}' from CIN7 sync")
                continue

            # Skip items without CIN7 ID
            if not hasattr(item.product, 'cin7_id') or not item.product.cin7_id:
                excluded_count += 1
                logger.warning(f"Excluding product '{item.product_name}' - missing CIN7 ID")
                continue

            syncable_items.append(item)

        logger.info(f"Quotation {quotation.quotation_number}: {len(syncable_items)} syncable items, {excluded_count} excluded")
        return syncable_items

    def _build_sales_order_payload(self, quotation: Quotation) -> Dict:
        """
        Build CIN7 Sales Order API payload from quotation.

        Args:
            quotation: Quotation instance

        Returns:
            dict: CIN7 API payload
        """
        creator = quotation.created_by

        # Parse delivery address
        delivery_info = self._parse_delivery_address(
            quotation.recipient_name,
            quotation.recipient_address
        )

        # Calculate discount
        discount_total = self._calculate_discount(quotation)

        # Build payload
        payload = {
            # Contact information
            'firstName': creator.first_name or '',
            'lastName': creator.last_name or '',
            'company': quotation.institution_name if quotation.institution else (quotation.recipient_name or ''),
            'email': creator.email,
            'phone': getattr(creator, 'phone', '') or '',

            # Delivery address
            **delivery_info,

            # Billing address (same as delivery)
            'billingFirstName': delivery_info['deliveryFirstName'],
            'billingLastName': delivery_info['deliveryLastName'],
            'billingCompany': delivery_info['deliveryCompany'],
            'billingAddress1': delivery_info['deliveryAddress1'],
            'billingAddress2': delivery_info['deliveryAddress2'],
            'billingCity': delivery_info['deliveryCity'],
            'billingState': delivery_info['deliveryState'],
            'billingPostalCode': delivery_info['deliveryPostalCode'],
            'billingCountry': delivery_info['deliveryCountry'],

            # Financial fields
            'productTotal': str(quotation.subtotal),
            'freightTotal': '0.00',
            'surcharge': '0.00',
            'discountTotal': str(discount_total),
            'total': str(quotation.total),
            'taxRate': str(quotation.tax_percentage),
            'taxStatus': 'Excl',  # Tax exclusive (added to subtotal)
            'currencyCode': 'NZD',
            'currencyRate': '1.0',
            'currencySymbol': '$',

            # Order details
            'reference': quotation.quotation_number,
            'memberEmail': creator.email,
            'stage': self._map_quotation_stage(quotation.status),
            'isApproved': quotation.status == 'confirmed',
            'isVoid': False,

            # Dates
            'createdDate': self._format_date(quotation.created_at),
            'modifiedDate': self._format_date(quotation.updated_at),
            'invoiceDate': self._format_date(quotation.approved_at),

            # Additional fields
            'branchId': config('CIN7_DEFAULT_BRANCH_ID', default=1, cast=int),
            'paymentTerms': config('CIN7_DEFAULT_PAYMENT_TERMS', default='Net 30'),
            'customerOrderNo': quotation.reference_number or '',

            # Line items (excluding Bespoke products)
            'lines': self._build_line_items(quotation)
        }

        return payload

    def _build_line_items(self, quotation: Quotation) -> List[Dict]:
        """
        Convert quotation items to CIN7 line items.

        CRITICAL: Excludes all Bespoke products.

        Args:
            quotation: Quotation instance

        Returns:
            list: Array of CIN7 line item dictionaries
        """
        syncable_items = self._get_syncable_items(quotation)

        if not syncable_items:
            logger.warning(f"No syncable items found for quotation {quotation.quotation_number}")
            return []

        line_items = []
        for item in syncable_items:
            line_items.append({
                'productId': item.product.cin7_id,
                'quantity': item.quantity,
                'price': str(item.unit_price),
                'discount': '0.00',  # Item-level discounts not currently implemented
                'taxRate': str(quotation.tax_percentage)
            })

        logger.info(f"Built {len(line_items)} line items for quotation {quotation.quotation_number}")
        return line_items

    def _parse_delivery_address(self, recipient_name: str, recipient_address: str) -> Dict:
        """
        Parse recipient name and address into CIN7 delivery address fields.

        Args:
            recipient_name: Recipient name (may be empty)
            recipient_address: Full address (may be multi-line)

        Returns:
            dict: Delivery address fields for CIN7
        """
        # Parse name
        name_parts = (recipient_name or '').strip().split(' ', 1)
        first_name = name_parts[0] if len(name_parts) > 0 else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Parse address lines
        lines = (recipient_address or '').strip().split('\n')
        address1 = lines[0].strip() if len(lines) > 0 else ''
        address2 = lines[1].strip() if len(lines) > 2 else ''

        # Extract city and postal code from second line (if available)
        # Format: "City PostalCode" or just "City"
        city_line = lines[1].strip() if len(lines) > 1 and len(lines) <= 2 else ''
        city_parts = city_line.split(' ')

        # Simple heuristic: if last part is digits, it's a postal code
        if city_parts and city_parts[-1].isdigit():
            postal_code = city_parts[-1]
            city = ' '.join(city_parts[:-1])
        else:
            postal_code = ''
            city = city_line

        # Extract country from last line (if available)
        country = lines[-1].strip() if len(lines) > 2 else 'New Zealand'

        return {
            'deliveryFirstName': first_name[:250],
            'deliveryLastName': last_name[:250],
            'deliveryCompany': '',
            'deliveryAddress1': address1[:250],
            'deliveryAddress2': address2[:250],
            'deliveryCity': city[:250],
            'deliveryState': '',  # Not extracted from address
            'deliveryPostalCode': postal_code[:250],
            'deliveryCountry': country[:250]
        }

    def _calculate_discount(self, quotation: Quotation) -> Decimal:
        """
        Calculate total discount amount.

        Args:
            quotation: Quotation instance

        Returns:
            Decimal: Discount amount
        """
        if quotation.discount_amount:
            return quotation.discount_amount
        elif quotation.discount_percentage:
            return (quotation.subtotal * quotation.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        return Decimal('0.00')

    def _map_quotation_stage(self, status: str) -> str:
        """
        Map quotation status to CIN7 order stage.

        Args:
            status: Quotation status

        Returns:
            str: CIN7 stage name
        """
        mapping = {
            'draft': 'New',
            'pending': 'Awaiting Payment',
            'approved': 'Processing',
            'confirmed': 'Processing',
            'rejected': 'New',  # Shouldn't sync rejected
            'expired': 'New',   # Shouldn't sync expired
            'cancelled': 'New'  # Handle with isVoid
        }
        return mapping.get(status, 'New')

    def _format_date(self, dt) -> Optional[str]:
        """
        Format datetime to CIN7 API format (ISO 8601 UTC).

        Args:
            dt: datetime object or None

        Returns:
            str: Formatted date string or None
        """
        if dt is None:
            return None

        # Ensure UTC timezone
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _check_rate_limit(self):
        """
        Check if API rate limits allow making a request.

        Uses Django cache to track requests.

        Raises:
            Exception: If rate limit exceeded
        """
        now = int(time.time())

        # Check per-second limit (3 requests)
        second_key = f"cin7_sales_order_second_{now}"
        second_count = cache.get(second_key, 0)
        if second_count >= self.MAX_CALLS_PER_SECOND:
            raise Exception("CIN7 rate limit exceeded: 3 requests per second")

        # Check per-minute limit (60 requests)
        minute_key = f"cin7_sales_order_minute_{now // 60}"
        minute_count = cache.get(minute_key, 0)
        if minute_count >= self.MAX_CALLS_PER_MINUTE:
            raise Exception("CIN7 rate limit exceeded: 60 requests per minute")

        # Check daily limit (5000 requests)
        today = timezone.now().date().isoformat()
        daily_key = f"cin7_sales_order_daily_{today}"
        daily_count = cache.get(daily_key, 0)
        if daily_count >= self.MAX_CALLS_PER_DAY:
            raise Exception("CIN7 rate limit exceeded: 5000 requests per day")

        # Increment counters
        cache.set(second_key, second_count + 1, timeout=1)
        cache.set(minute_key, minute_count + 1, timeout=60)
        cache.set(daily_key, daily_count + 1, timeout=86400)

        logger.debug(f"Rate limit check passed: {second_count}/3 (sec), {minute_count}/60 (min), {daily_count}/5000 (day)")

    def _handle_success_response(self, quotation: Quotation, response) -> Dict:
        """
        Handle successful CIN7 API response.

        Updates quotation and creates CIN7OrderMapping.

        Args:
            quotation: Quotation instance
            response: HTTP response object

        Returns:
            dict: Response data
        """
        data = response.json()
        order_data = data['data'][0]

        cin7_order_id = order_data['id']
        cin7_reference = order_data['reference']
        cin7_stage = order_data.get('stage', 'Processing')

        logger.info(f"Successfully created CIN7 order {cin7_order_id} for quotation {quotation.quotation_number}")

        # Update quotation
        quotation.cin7_so_id = str(cin7_order_id)
        quotation.cin7_so_number = cin7_reference
        quotation.cin7_sync_status = 'synced'
        quotation.cin7_synced_at = timezone.now()
        quotation.cin7_sync_error = ''
        quotation.save(update_fields=['cin7_so_id', 'cin7_so_number', 'cin7_sync_status', 'cin7_synced_at', 'cin7_sync_error', 'updated_at'])

        # Create or update CIN7OrderMapping
        mapping, created = CIN7OrderMapping.objects.update_or_create(
            quotation=quotation,
            defaults={
                'cin7_order_id': cin7_order_id,
                'cin7_reference': cin7_reference,
                'cin7_stage': cin7_stage,
                'sync_status': 'synced',
                'error_message': ''
            }
        )

        if created:
            logger.info(f"Created CIN7OrderMapping for quotation {quotation.quotation_number}")
        else:
            logger.info(f"Updated existing CIN7OrderMapping for quotation {quotation.quotation_number}")

        # Create version snapshot
        quotation.create_version_snapshot(
            description=f'Synced to CIN7 Sales Order {cin7_order_id}',
            user=quotation.created_by
        )

        return {
            'success': True,
            'cin7_order_id': cin7_order_id,
            'cin7_reference': cin7_reference,
            'cin7_stage': cin7_stage,
            'message': f'Successfully synced to CIN7 order {cin7_order_id}'
        }

    def _handle_validation_error(self, quotation: Quotation, response) -> Dict:
        """
        Handle validation error response (400).

        Args:
            quotation: Quotation instance
            response: HTTP response object

        Returns:
            dict: Error details

        Raises:
            ValueError: With validation error details
        """
        try:
            error_data = response.json()
            errors = error_data.get('errors', [])
            error_msg = '; '.join([f"{e.get('field', 'unknown')}: {e.get('message', 'unknown error')}" for e in errors])
        except Exception:
            error_msg = response.text

        logger.error(f"CIN7 validation error for quotation {quotation.quotation_number}: {error_msg}")

        # Update quotation
        quotation.cin7_sync_status = 'failed'
        quotation.cin7_sync_error = f"Validation error: {error_msg}"
        quotation.save(update_fields=['cin7_sync_status', 'cin7_sync_error', 'updated_at'])

        # Update or create mapping
        mapping, _ = CIN7OrderMapping.objects.get_or_create(
            quotation=quotation,
            defaults={'cin7_order_id': 0, 'cin7_reference': '', 'sync_status': 'failed'}
        )
        mapping.mark_sync_failed(f"Validation error: {error_msg}")

        raise ValueError(f"CIN7 validation error: {error_msg}")

    def _handle_auth_error(self, response) -> Dict:
        """
        Handle authentication error (401).

        Args:
            response: HTTP response object

        Raises:
            Exception: Authentication error
        """
        error_msg = "CIN7 API authentication failed - check credentials"
        logger.error(error_msg)
        raise Exception(error_msg)

    def _handle_rate_limit_error(self, quotation: Quotation, response) -> Dict:
        """
        Handle rate limit error (429).

        Args:
            quotation: Quotation instance
            response: HTTP response object

        Raises:
            Exception: Rate limit error with retry information
        """
        retry_after = int(response.headers.get('Retry-After', 60))
        error_msg = f"CIN7 rate limit exceeded - retry after {retry_after} seconds"
        logger.warning(error_msg)

        # Update quotation
        quotation.cin7_sync_status = 'pending'
        quotation.cin7_sync_error = error_msg
        quotation.save(update_fields=['cin7_sync_status', 'cin7_sync_error', 'updated_at'])

        raise Exception(error_msg)

    def _handle_server_error(self, quotation: Quotation, response) -> Dict:
        """
        Handle server error (500, 503).

        Args:
            quotation: Quotation instance
            response: HTTP response object

        Raises:
            Exception: Server error with retry suggestion
        """
        error_msg = f"CIN7 server error ({response.status_code}) - {response.text}"
        logger.error(error_msg)

        # Update quotation
        quotation.cin7_sync_status = 'failed'
        quotation.cin7_sync_error = error_msg
        quotation.save(update_fields=['cin7_sync_status', 'cin7_sync_error', 'updated_at'])

        # Update or create mapping
        mapping, _ = CIN7OrderMapping.objects.get_or_create(
            quotation=quotation,
            defaults={'cin7_order_id': 0, 'cin7_reference': '', 'sync_status': 'failed'}
        )
        mapping.mark_sync_failed(error_msg)

        raise Exception(error_msg)
