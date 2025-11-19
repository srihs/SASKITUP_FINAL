"""
Context processors for quotations app.

Makes quotation cart data available globally in all templates.
"""

from collections import defaultdict
from decimal import Decimal
from .views import get_quotation_session, calculate_quotation_totals, get_product_by_type_and_id


def quotation_cart(request):
    """
    Context processor to make quotation cart data available in all templates.

    Returns:
        dict: Context data with cart_item_count, cart_total, and grouped_cart_items
    """
    # Only process for authenticated users
    if not request.user.is_authenticated:
        return {
            'cart_item_count': 0,
            'cart_total': '0.00',
            'grouped_cart_items': [],
        }

    try:
        # Get quotation session data
        quotation_data = get_quotation_session(request)

        # Calculate totals (pass customer for shipping calculation)
        totals = calculate_quotation_totals(quotation_data, customer=request.user)

        # Group items by product name for mini cart display
        product_groups = defaultdict(lambda: {
            'product_name': '',
            'product_type': '',
            'product_id': None,
            'variations': [],
            'group_total': Decimal('0.00'),
            'image_url': '',
        })

        for item in quotation_data.get('items', []):
            product_name = item.get('product_name', 'Unknown Product')
            product_type = item.get('product_type', '')
            product_id = item.get('product_id', '')
            product_key = f"{product_type}_{product_id}"

            # Calculate line total
            line_total = Decimal(str(item.get('unit_price', 0))) * Decimal(str(item.get('quantity', 0)))

            # Add to group
            if not product_groups[product_key]['product_name']:
                product_groups[product_key]['product_name'] = product_name
                product_groups[product_key]['product_type'] = product_type
                product_groups[product_key]['product_id'] = product_id

                # Fetch product image
                try:
                    # Product type is stored as lowercase model name (lottoproduct, sasproduct, tusproduct, wholesaleproduct)
                    # get_product_by_type_and_id expects the same format
                    product = get_product_by_type_and_id(product_type, product_id)

                    if product:
                        # Try different image field names
                        image_url = None
                        if hasattr(product, 'image') and product.image:
                            image_url = product.image
                        elif hasattr(product, 'featured_image') and product.featured_image:
                            image_url = product.featured_image
                        elif hasattr(product, 'product_image') and product.product_image:
                            image_url = product.product_image

                        product_groups[product_key]['image_url'] = image_url or ''
                except Exception:
                    # If product fetch fails, just continue without image
                    pass

            product_groups[product_key]['variations'].append({
                'variation_details': item.get('variation_details', {}),
                'quantity': item.get('quantity', 0),
                'unit_price': item.get('unit_price', 0),
                'line_total': line_total,
            })
            product_groups[product_key]['group_total'] += line_total

        # Convert to list for template
        grouped_items = [
            {
                'product_name': data['product_name'],
                'variation_count': len(data['variations']),
                'group_total': data['group_total'],
                'image_url': data['image_url'],
            }
            for data in product_groups.values()
        ]

        return {
            'cart_item_count': len(product_groups),  # Count unique product groups
            'cart_total': str(totals['total']),
            'grouped_cart_items': grouped_items,
        }
    except Exception:
        # Return empty cart on any error
        return {
            'cart_item_count': 0,
            'cart_total': '0.00',
            'grouped_cart_items': [],
        }
