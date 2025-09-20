from django import template

register = template.Library()

@register.filter
def product_count_for_school(category, school):
    """Get the product count for a specific school within a category"""
    return category.product_count_for_school(school)