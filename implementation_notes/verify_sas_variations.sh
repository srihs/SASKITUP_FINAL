#!/bin/bash
# Quick verification script for SAS variations

echo "======================================"
echo "SAS VARIATION VERIFICATION"
echo "======================================"
echo ""

# Activate virtual environment
source env/bin/activate

# Check database state
echo "Database Status:"
echo "----------------"
python manage.py shell <<'EOF'
from clubs.models_sas import SASProduct, SASProductVariation

total_products = SASProduct.objects.count()
variable_products = SASProduct.objects.filter(product_type='variable').count()
total_variations = SASProductVariation.objects.count()

print(f"Total SAS Products: {total_products}")
print(f"Variable Products: {variable_products}")
print(f"Total Variations: {total_variations}")
print("")

if variable_products > 0:
    print("✓ Variable products found!")
    print("\nSample variable products:")
    for p in SASProduct.objects.filter(product_type='variable')[:3]:
        var_count = p.variations.count()
        print(f"  - {p.name}: {var_count} variations")
else:
    print("✗ No variable products found")
    print("  → Need to run sync command")

print("")

if total_variations > 0:
    print("✓ Variations found!")
    print("\nSample variations:")
    for v in SASProductVariation.objects.all()[:5]:
        print(f"  - {v.product.name}")
        print(f"    Type: {v.variation_type}, Value: {v.variation_value}")
        print(f"    Stock: {v.stock_quantity}, Price Modifier: {v.price_modifier}")
else:
    print("✗ No variations found")
    print("  → Need to run sync command")
EOF

echo ""
echo "======================================"
echo "To sync variations, run:"
echo "  python manage.py sync_sas_clubs --verbose"
echo "======================================"
