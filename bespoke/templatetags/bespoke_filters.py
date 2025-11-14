from django import template

register = template.Library()


@register.filter(name='get_price')
def get_price(prices, tier_and_size):
    """
    Get price for specific tier and size combination.
    Usage: {% with price=data.prices|get_price:tier.id|add:","|add:size.id %}
    """
    try:
        parts = str(tier_and_size).split(',')
        if len(parts) != 2:
            return None

        tier_id = int(parts[0])
        size_id = int(parts[1])

        for price in prices:
            if price.tier_id == tier_id and price.size_definition_id == size_id:
                return price
        return None
    except (ValueError, AttributeError, TypeError):
        return None


@register.simple_tag
def price_lookup(prices, tier_id, size_id):
    """
    Simple tag for price lookup.
    Usage: {% price_lookup data.prices tier.id size.id as price %}
    """
    for price in prices:
        if price.tier_id == tier_id and price.size_definition_id == size_id:
            return price
    return None


@register.simple_tag
def price_lookup_with_color(prices, tier_id, size_code, color_range):
    """
    Price lookup with color range matching.
    Matches prices based on tier, size_code, and color range in display_label.
    Usage: {% price_lookup_with_color data.prices tier.id 'small' "1-2" as price %}
    """
    for price in prices:
        if price.tier_id == tier_id:
            size_def = price.size_definition
            # Match size code
            if size_def.size_code == size_code:
                # For EMB/Applique
                if color_range in ['emb', 'applique']:
                    # For APPLIQUE, only return prices for medium and large (avg and lrg stitch)
                    if color_range == 'applique':
                        if size_code == 'small':  # Low stitch shows N/A for APPLIQUE
                            return None
                        # For medium and large, return the same price as EMB
                        return price
                    else:
                        # For EMB, return the price for all sizes
                        return price
                else:
                    # For Heat Transfer/Screen Print, match color range in display_label
                    size_label = size_def.display_label
                    if f"({color_range} color" in size_label or f"({color_range})" in size_label:
                        return price
    return None


@register.filter
def split(value, delimiter=','):
    """
    Split a string by delimiter.
    Usage: {% for item in "a,b,c"|split:"," %}
    """
    return value.split(delimiter)
