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

        # Calculate totals
        totals = calculate_quotation_totals(quotation_data)

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
                    # Normalize product_type - it might be stored as "LOTTO", "SAS", "TUS"
                    # but get_product_by_type_and_id expects "LottoProduct", "SASProduct", etc.
                    normalized_type = product_type
                    if product_type.upper() == 'LOTTO':
                        normalized_type = 'LottoProduct'
                    elif product_type.upper() == 'SAS':
                        normalized_type = 'SASProduct'
                    elif product_type.upper() == 'TUS':
                        normalized_type = 'TUSProduct'
                    elif product_type.lower() == 'wholesale':
                        normalized_type = 'WholesaleProduct'

                    product = get_product_by_type_and_id(normalized_type, product_id)
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
                except Exception as e:
                    # If product fetch fails, just continue without image
                    import traceback
                    print(f"Error fetching product image for {product_type} {product_id}: {e}")
                    print(traceback.format_exc())
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
