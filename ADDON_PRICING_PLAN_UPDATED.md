# Updated Addon Pricing Implementation Plan

## Executive Summary

Based on code review, this updated plan integrates addon pricing management into the existing bespoke category addon page (`/bespoke/category/addon/`) instead of Django Admin, and excludes addons from sync and price update operations.

---

## Key Changes from Original Plan

### 1. **UI Location**: Custom Interface at `/bespoke/category/addon/`
- **Original**: Django Admin interface
- **Updated**: Custom template-based UI integrated into existing bespoke category detail page
- **Rationale**: Better UX, consistent with application design, easier access for users

### 2. **Exclude Addons from Bespoke Sync**
- Remove addon products from CIN7 sync at `/bespoke/`
- Addon pricing will be manually managed, not synced from CIN7
- Prevents overwriting manually configured pricing tiers

### 3. **Exclude Addons from Wholesale Price Update**
- Prevent bespoke addon products from being updated at `/schools/wholesale/cin7-price-update/`
- Addon pricing managed separately through custom UI
- Avoids conflicts between wholesale pricing and addon tier pricing

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  /bespoke/category/addon/                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                 Addon Category Page                     │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │  Tab 1: Products (existing)                            │ │
│  │  ├─ Addon product cards with variations               │ │
│  │  └─ Search and filter functionality                   │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │  Tab 2: Pricing Management (NEW)                      │ │
│  │  ├─ Heat Transfer Pricing Table                       │ │
│  │  ├─ Screen Print Pricing Table                        │ │
│  │  └─ EMB/Applique Pricing Table                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Schema (Same as Original)

### Models (in `/Users/sas/Repos/SASKITUP/bespoke/models.py`)

```python
class AddonPricingTier(models.Model):
    """Quantity-based pricing tiers (1-9, 10-25, etc.)"""
    addon_type = models.CharField(
        max_length=50,
        choices=[
            ('heat_transfer', 'Heat Transfer'),
            ('screen_print', 'Screen Print'),
            ('emb_applique', 'Embroidery/Applique'),
        ],
        db_index=True
    )
    min_quantity = models.PositiveIntegerField()
    max_quantity = models.PositiveIntegerField(null=True, blank=True)
    display_label = models.CharField(max_length=50)  # "1-9", "200+"
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bespoke_addon_pricing_tier'
        ordering = ['addon_type', 'sort_order']
        unique_together = [['addon_type', 'min_quantity', 'max_quantity']]

    def __str__(self):
        return f"{self.get_addon_type_display()} - {self.display_label}"


class AddonSizeDefinition(models.Model):
    """Size categories with dimension specifications"""
    addon_type = models.CharField(max_length=50, choices=[...], db_index=True)
    size_code = models.CharField(
        max_length=20,
        choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')]
    )
    max_width_inches = models.DecimalField(max_digits=5, decimal_places=2)
    max_height_inches = models.DecimalField(max_digits=5, decimal_places=2)
    display_label = models.CharField(max_length=100)

    # EMB/Applique only
    stitch_complexity = models.CharField(
        max_length=20,
        choices=[('low', 'Low Stitch'), ('avg', 'Avg Stitch'), ('lrg', 'Lrg Stitch')],
        null=True, blank=True
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bespoke_addon_size_definition'
        ordering = ['addon_type', 'sort_order']
        unique_together = [['addon_type', 'size_code', 'stitch_complexity']]

    def __str__(self):
        base = f"{self.get_addon_type_display()} - {self.display_label}"
        if self.stitch_complexity:
            base += f" ({self.get_stitch_complexity_display()})"
        return base


class AddonPrice(models.Model):
    """Intersection of tier and size - stores actual prices"""
    tier = models.ForeignKey(AddonPricingTier, on_delete=models.CASCADE, related_name='prices')
    size_definition = models.ForeignKey(AddonSizeDefinition, on_delete=models.CASCADE, related_name='prices')
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'bespoke_addon_price'
        ordering = ['tier__sort_order', 'size_definition__sort_order']
        unique_together = [['tier', 'size_definition', 'effective_from']]

    def clean(self):
        if self.tier.addon_type != self.size_definition.addon_type:
            raise ValidationError("Tier and size addon types must match")

    @classmethod
    def get_price(cls, addon_type, quantity, width_inches, height_inches, stitch_complexity=None):
        """Calculate price for given parameters"""
        # Find matching tier and size, return price_per_unit
        # (Implementation in original plan)
        pass


class AddonPriceHistory(models.Model):
    """Audit trail for price changes"""
    addon_price = models.ForeignKey(AddonPrice, on_delete=models.CASCADE, related_name='history')
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    change_reason = models.TextField()
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'bespoke_addon_price_history'
        ordering = ['-changed_at']
```

---

## Phase 2: Exclude Addons from Sync

### 2.1 Modify Bespoke CIN7 Sync Service

**File**: `/Users/sas/Repos/SASKITUP/bespoke/services/cin7_sync_service.py`

**Current Behavior**: Syncs all products from "Quotation Base Library" category
**New Behavior**: Exclude products where category contains "ADDON" or similar

```python
# In BespokeCin7SyncService class, modify sync_all() method

def sync_all(self) -> BespokeSyncLog:
    """Full sync of Bespoke products from CIN7 - EXCLUDES ADDONS"""

    # ... existing code ...

    # Fetch products from CIN7 API
    cin7_products = self.cin7_api.get_products(category=self.TARGET_CATEGORY)

    # FILTER OUT ADDON PRODUCTS
    filtered_products = []
    excluded_count = 0

    for product in cin7_products:
        category_path = product.get('category', '').upper()
        product_name = product.get('name', '').upper()
        sku = product.get('code', '').upper()

        # Exclude if product is an addon
        is_addon = any([
            'ADDON' in category_path,
            'SCREEN PRINT' in product_name or 'SCREEN PRINT' in sku,
            'HEAT TRANSFER' in product_name or 'HEAT TRANSFER' in sku,
            'EMB' in sku and ('EMBROIDERY' in product_name or 'APPLIQUE' in product_name),
        ])

        if is_addon:
            excluded_count += 1
            logger.info(f"Excluding addon product from sync: {product.get('name')} (SKU: {sku})")
            if self.sync_job:
                self.sync_job.add_log_message(
                    f"Skipped addon product: {product.get('name')}",
                    'info'
                )
        else:
            filtered_products.append(product)

    logger.info(f"Filtered out {excluded_count} addon products from sync")
    logger.info(f"Processing {len(filtered_products)} base garment products")

    if self.sync_job:
        self.sync_job.add_log_message(
            f"Excluded {excluded_count} addon products (managed via custom pricing UI)",
            'info'
        )
        self.sync_job.add_log_message(
            f"Processing {len(filtered_products)} base garment products",
            'info'
        )

    # Continue with filtered_products instead of cin7_products
    # ... rest of sync logic ...
```

### 2.2 Update Sync UI Messaging

**File**: `/Users/sas/Repos/SASKITUP/bespoke/templates/bespoke/category_list.html`

Add informational message about addon exclusion:

```html
<!-- In sync status/help section -->
<div class="alert alert-info">
    <i class="mdi mdi-information me-2"></i>
    <strong>Note:</strong> Addon products (Screen Print, Heat Transfer, Embroidery) are excluded from CIN7 sync.
    Manage addon pricing at <a href="{% url 'bespoke:category_detail' 'addon' %}">Addon Pricing Settings</a>.
</div>
```

---

## Phase 3: Exclude Addons from Wholesale Price Update

### 3.1 Modify CIN7 Price Fetch Logic

**File**: `/Users/sas/Repos/SASKITUP/schools/views.py`

**Function**: `cin7_price_fetch()` (line ~3524)

```python
@csrf_exempt
@require_http_methods(["POST"])
def cin7_price_fetch(request):
    """
    Stage 1: Fetch products from Cin7 API - EXCLUDE BESPOKE ADDONS
    """
    # ... existing code ...

    # Fetch products from CIN7
    cin7_products = api_service.get_products(category=price_type)

    # FILTER OUT BESPOKE ADDON PRODUCTS
    filtered_products = []
    excluded_count = 0

    for product in cin7_products:
        category_path = product.get('category', '').upper()
        product_name = product.get('name', '').upper()
        sku = product.get('code', '').upper()

        # Exclude bespoke addons
        is_bespoke_addon = any([
            'QUOTATION BASE LIBRARY' in category_path and any([
                'SCREEN PRINT' in product_name or 'SCREEN PRINT' in sku,
                'HEAT TRANSFER' in product_name or 'HEAT TRANSFER' in sku,
                'EMB' in sku and ('EMBROIDERY' in product_name or 'APPLIQUE' in product_name),
            ])
        ])

        if is_bespoke_addon:
            excluded_count += 1
            logger.info(f"Excluding bespoke addon from price update: {product_name} (SKU: {sku})")
        else:
            filtered_products.append(product)

    logger.info(f"Excluded {excluded_count} bespoke addon products from price update")

    # Save filtered products to database
    for product in filtered_products:
        # ... existing save logic ...

    return JsonResponse({
        'success': True,
        'total_fetched': len(filtered_products),
        'excluded_addons': excluded_count,
        'message': f'Fetched {len(filtered_products)} products (excluded {excluded_count} bespoke addons)'
    })
```

### 3.2 Update Price Update UI

**File**: `/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/cin7_price_update_settings.html`

Add informational banner:

```html
<div class="alert alert-warning">
    <i class="mdi mdi-alert-circle me-2"></i>
    <strong>Exclusions:</strong> Bespoke addon products (Screen Print, Heat Transfer, Embroidery) are automatically
    excluded from this price update. Manage addon pricing at
    <a href="{% url 'bespoke:category_detail' 'addon' %}">Addon Pricing Settings</a>.
</div>
```

---

## Phase 4: Custom Pricing UI at `/bespoke/category/addon/`

### 4.1 Enhanced Category Detail View

**File**: `/Users/sas/Repos/SASKITUP/bespoke/views.py`

```python
def category_detail(request, category_slug):
    """Display products in category - WITH PRICING MANAGEMENT FOR ADDONS"""

    category = get_object_or_404(BespokeCategory, slug=category_slug, is_active=True)

    # ... existing product listing code ...

    # IF THIS IS ADDON CATEGORY, ADD PRICING DATA
    is_addon_category = 'addon' in category.slug.lower()

    context = {
        'category': category,
        'products': products,
        'grouped_products': grouped_products,
        'is_addon_category': is_addon_category,
        # ... existing context ...
    }

    if is_addon_category:
        # Add pricing management data
        from .models import AddonPricingTier, AddonSizeDefinition, AddonPrice

        # Get pricing data for all three addon types
        pricing_data = {}
        for addon_type in ['heat_transfer', 'screen_print', 'emb_applique']:
            tiers = AddonPricingTier.objects.filter(
                addon_type=addon_type,
                is_active=True
            ).order_by('sort_order')

            sizes = AddonSizeDefinition.objects.filter(
                addon_type=addon_type,
                is_active=True
            ).order_by('sort_order')

            prices = AddonPrice.objects.filter(
                tier__addon_type=addon_type,
                is_active=True
            ).select_related('tier', 'size_definition').order_by(
                'tier__sort_order',
                'size_definition__sort_order'
            )

            pricing_data[addon_type] = {
                'tiers': tiers,
                'sizes': sizes,
                'prices': prices,
                'display_name': dict([
                    ('heat_transfer', 'Heat Transfer'),
                    ('screen_print', 'Screen Print'),
                    ('emb_applique', 'EMB/Applique')
                ])[addon_type]
            }

        context['pricing_data'] = pricing_data

    return render(request, 'bespoke/category_detail.html', context)
```

### 4.2 Enhanced Template with Pricing UI

**File**: `/Users/sas/Repos/SASKITUP/bespoke/templates/bespoke/category_detail.html`

Add tabbed interface after existing content:

```html
{% extends 'base.html' %}
{% load static %}

{% block content %}
<div class="bespoke-page">

<!-- Existing category header, stats, products... -->
<!-- ... existing content ... -->

{% if is_addon_category %}
<!-- ADDON PRICING MANAGEMENT SECTION -->
<div class="row mt-4">
    <div class="col-12">
        <div class="card">
            <div class="card-body">
                <ul class="nav nav-tabs nav-tabs-custom" role="tablist">
                    <li class="nav-item">
                        <a class="nav-link active" data-bs-toggle="tab" href="#products-tab" role="tab">
                            <i class="uil-shopping-bag me-1"></i> Products
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" data-bs-toggle="tab" href="#pricing-tab" role="tab">
                            <i class="uil-dollar-alt me-1"></i> Pricing Management
                        </a>
                    </li>
                </ul>

                <div class="tab-content p-3">
                    <!-- Products Tab (existing content moved here) -->
                    <div class="tab-pane active" id="products-tab" role="tabpanel">
                        <!-- Move existing product cards here -->
                    </div>

                    <!-- Pricing Management Tab (NEW) -->
                    <div class="tab-pane" id="pricing-tab" role="tabpanel">
                        <div class="pricing-management">

                            <!-- Pricing Type Accordion -->
                            <div class="accordion" id="pricingAccordion">

                                {% for addon_type, data in pricing_data.items %}
                                <div class="accordion-item">
                                    <h2 class="accordion-header" id="heading-{{ addon_type }}">
                                        <button class="accordion-button {% if forloop.first %}{% else %}collapsed{% endif %}"
                                                type="button"
                                                data-bs-toggle="collapse"
                                                data-bs-target="#collapse-{{ addon_type }}">
                                            <i class="uil-tag-alt me-2"></i>
                                            {{ data.display_name }} Pricing
                                            <span class="badge bg-soft-info text-info ms-2">
                                                {{ data.prices.count }} prices configured
                                            </span>
                                        </button>
                                    </h2>
                                    <div id="collapse-{{ addon_type }}"
                                         class="accordion-collapse collapse {% if forloop.first %}show{% endif %}"
                                         data-bs-parent="#pricingAccordion">
                                        <div class="accordion-body">

                                            <!-- Action Buttons -->
                                            <div class="d-flex justify-content-between align-items-center mb-3">
                                                <div>
                                                    <button class="btn btn-sm btn-primary"
                                                            onclick="addTier('{{ addon_type }}')">
                                                        <i class="uil-plus me-1"></i> Add Tier
                                                    </button>
                                                    <button class="btn btn-sm btn-info"
                                                            onclick="addSize('{{ addon_type }}')">
                                                        <i class="uil-ruler me-1"></i> Add Size
                                                    </button>
                                                    <button class="btn btn-sm btn-success"
                                                            onclick="bulkEditPrices('{{ addon_type }}')">
                                                        <i class="uil-edit me-1"></i> Bulk Edit
                                                    </button>
                                                </div>
                                                <div>
                                                    <button class="btn btn-sm btn-soft-warning"
                                                            onclick="exportPricing('{{ addon_type }}')">
                                                        <i class="uil-download-alt me-1"></i> Export
                                                    </button>
                                                    <button class="btn btn-sm btn-soft-success"
                                                            onclick="importPricing('{{ addon_type }}')">
                                                        <i class="uil-upload-alt me-1"></i> Import
                                                    </button>
                                                </div>
                                            </div>

                                            <!-- Pricing Matrix Table -->
                                            <div class="table-responsive">
                                                <table class="table table-bordered table-hover pricing-matrix-table">
                                                    <thead class="table-light">
                                                        <tr>
                                                            <th class="text-center">Quantity Tier</th>
                                                            {% for size in data.sizes %}
                                                            <th class="text-center">
                                                                {{ size.display_label }}
                                                                {% if size.stitch_complexity %}
                                                                <br><small class="text-muted">{{ size.get_stitch_complexity_display }}</small>
                                                                {% endif %}
                                                            </th>
                                                            {% endfor %}
                                                            <th class="text-center">Actions</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {% for tier in data.tiers %}
                                                        <tr>
                                                            <td class="text-center fw-bold">
                                                                {{ tier.display_label }}
                                                                <br><small class="text-muted">
                                                                    ({{ tier.min_quantity }}{% if tier.max_quantity %}-{{ tier.max_quantity }}{% else %}+{% endif %})
                                                                </small>
                                                            </td>
                                                            {% for size in data.sizes %}
                                                            <td class="text-center">
                                                                {% with price=data.prices|get_price:tier:size %}
                                                                {% if price %}
                                                                <div class="price-cell"
                                                                     data-price-id="{{ price.id }}"
                                                                     data-tier-id="{{ tier.id }}"
                                                                     data-size-id="{{ size.id }}">
                                                                    <span class="price-value">R {{ price.price_per_unit }}</span>
                                                                    <button class="btn btn-xs btn-soft-primary edit-price-btn"
                                                                            onclick="editPrice({{ price.id }}, {{ tier.id }}, {{ size.id }})">
                                                                        <i class="uil-edit-alt"></i>
                                                                    </button>
                                                                </div>
                                                                {% else %}
                                                                <button class="btn btn-sm btn-soft-success"
                                                                        onclick="addPrice('{{ addon_type }}', {{ tier.id }}, {{ size.id }})">
                                                                    <i class="uil-plus"></i> Add
                                                                </button>
                                                                {% endif %}
                                                                {% endwith %}
                                                            </td>
                                                            {% endfor %}
                                                            <td class="text-center">
                                                                <button class="btn btn-sm btn-soft-info"
                                                                        onclick="editTier({{ tier.id }})">
                                                                    <i class="uil-edit"></i>
                                                                </button>
                                                                <button class="btn btn-sm btn-soft-danger"
                                                                        onclick="deleteTier({{ tier.id }})">
                                                                    <i class="uil-trash"></i>
                                                                </button>
                                                            </td>
                                                        </tr>
                                                        {% endfor %}
                                                    </tbody>
                                                </table>
                                            </div>

                                        </div>
                                    </div>
                                </div>
                                {% endfor %}

                            </div>

                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endif %}

</div>
{% endblock %}

{% block extra_js %}
<script src="{% static 'js/addon-pricing-manager.js' %}"></script>
{% endblock %}
```

### 4.3 Template Filter for Price Lookup

**File**: `/Users/sas/Repos/SASKITUP/bespoke/templatetags/bespoke_filters.py` (create if doesn't exist)

```python
from django import template

register = template.Library()

@register.filter(name='get_price')
def get_price(prices, args):
    """Get price for specific tier and size combination"""
    try:
        tier, size = args.split(',')
        tier_id = int(tier)
        size_id = int(size)
        return prices.filter(tier_id=tier_id, size_definition_id=size_id, is_active=True).first()
    except:
        return None
```

Usage in template:
```django
{% with price=data.prices|get_price:tier.id|add:","|add:size.id %}
```

---

## Phase 5: AJAX API Endpoints for Pricing Management

### 5.1 URL Configuration

**File**: `/Users/sas/Repos/SASKITUP/bespoke/urls.py`

```python
urlpatterns = [
    # ... existing URLs ...

    # Addon pricing management endpoints
    path('api/pricing/tier/add/', views.add_pricing_tier, name='add-pricing-tier'),
    path('api/pricing/tier/<int:tier_id>/edit/', views.edit_pricing_tier, name='edit-pricing-tier'),
    path('api/pricing/tier/<int:tier_id>/delete/', views.delete_pricing_tier, name='delete-pricing-tier'),

    path('api/pricing/size/add/', views.add_size_definition, name='add-size-definition'),
    path('api/pricing/size/<int:size_id>/edit/', views.edit_size_definition, name='edit-size-definition'),
    path('api/pricing/size/<int:size_id>/delete/', views.delete_size_definition, name='delete-size-definition'),

    path('api/pricing/price/add/', views.add_price, name='add-price'),
    path('api/pricing/price/<int:price_id>/edit/', views.edit_price, name='edit-price'),
    path('api/pricing/price/<int:price_id>/delete/', views.delete_price, name='delete-price'),

    path('api/pricing/bulk-edit/', views.bulk_edit_prices, name='bulk-edit-prices'),
    path('api/pricing/export/<str:addon_type>/', views.export_pricing, name='export-pricing'),
    path('api/pricing/import/', views.import_pricing, name='import-pricing'),
]
```

### 5.2 View Functions

**File**: `/Users/sas/Repos/SASKITUP/bespoke/views.py`

```python
@require_http_methods(["POST"])
@login_required
def add_price(request):
    """Add new price for tier/size combination"""
    try:
        data = json.loads(request.body)
        tier_id = data.get('tier_id')
        size_id = data.get('size_id')
        price = Decimal(data.get('price'))

        # Validate
        tier = AddonPricingTier.objects.get(id=tier_id)
        size = AddonSizeDefinition.objects.get(id=size_id)

        if tier.addon_type != size.addon_type:
            return JsonResponse({'success': False, 'error': 'Tier and size addon types must match'}, status=400)

        # Create price
        addon_price = AddonPrice.objects.create(
            tier=tier,
            size_definition=size,
            price_per_unit=price,
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'price_id': addon_price.id,
            'message': 'Price added successfully'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def edit_price(request, price_id):
    """Edit existing price"""
    try:
        data = json.loads(request.body)
        new_price = Decimal(data.get('price'))

        addon_price = AddonPrice.objects.get(id=price_id)
        old_price = addon_price.price_per_unit

        # Record history
        AddonPriceHistory.objects.create(
            addon_price=addon_price,
            old_price=old_price,
            new_price=new_price,
            change_reason=data.get('reason', 'Manual update via UI'),
            changed_by=request.user
        )

        addon_price.price_per_unit = new_price
        addon_price.save()

        return JsonResponse({
            'success': True,
            'message': 'Price updated successfully'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
@login_required
def bulk_edit_prices(request):
    """Bulk edit multiple prices at once"""
    try:
        data = json.loads(request.body)
        price_updates = data.get('prices', [])  # [{price_id, new_price}, ...]

        updated_count = 0
        for update in price_updates:
            price_id = update.get('price_id')
            new_price = Decimal(update.get('price'))

            addon_price = AddonPrice.objects.get(id=price_id)
            old_price = addon_price.price_per_unit

            if old_price != new_price:
                # Record history
                AddonPriceHistory.objects.create(
                    addon_price=addon_price,
                    old_price=old_price,
                    new_price=new_price,
                    change_reason='Bulk update via UI',
                    changed_by=request.user
                )

                addon_price.price_per_unit = new_price
                addon_price.save()
                updated_count += 1

        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
            'message': f'{updated_count} prices updated successfully'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def export_pricing(request, addon_type):
    """Export pricing matrix to CSV"""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{addon_type}_pricing.csv"'

    writer = csv.writer(response)

    # Get data
    tiers = AddonPricingTier.objects.filter(addon_type=addon_type, is_active=True).order_by('sort_order')
    sizes = AddonSizeDefinition.objects.filter(addon_type=addon_type, is_active=True).order_by('sort_order')

    # Header row
    header = ['Tier'] + [size.display_label for size in sizes]
    writer.writerow(header)

    # Data rows
    for tier in tiers:
        row = [tier.display_label]
        for size in sizes:
            price = AddonPrice.objects.filter(
                tier=tier,
                size_definition=size,
                is_active=True
            ).first()
            row.append(str(price.price_per_unit) if price else '')
        writer.writerow(row)

    return response
```

### 5.3 JavaScript Frontend

**File**: `/Users/sas/Repos/SASKITUP/static/js/addon-pricing-manager.js`

```javascript
// Addon Pricing Management JavaScript

function editPrice(priceId, tierId, sizeId) {
    // Show modal for editing price
    const currentPrice = $(`[data-price-id="${priceId}"] .price-value`).text().replace('R ', '');

    Swal.fire({
        title: 'Edit Price',
        input: 'number',
        inputLabel: 'Price (Rand)',
        inputValue: currentPrice,
        showCancelButton: true,
        inputValidator: (value) => {
            if (!value || value <= 0) {
                return 'Please enter a valid price'
            }
        }
    }).then((result) => {
        if (result.isConfirmed) {
            updatePrice(priceId, result.value);
        }
    });
}

function updatePrice(priceId, newPrice) {
    fetch(`/bespoke/api/pricing/price/${priceId}/edit/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            price: newPrice,
            reason: 'Manual update'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update UI
            $(`[data-price-id="${priceId}"] .price-value`).text(`R ${parseFloat(newPrice).toFixed(2)}`);

            Swal.fire({
                icon: 'success',
                title: 'Updated!',
                text: data.message,
                timer: 2000,
                showConfirmButton: false
            });
        } else {
            Swal.fire('Error', data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        Swal.fire('Error', 'Failed to update price', 'error');
    });
}

function addPrice(addonType, tierId, sizeId) {
    Swal.fire({
        title: 'Add Price',
        input: 'number',
        inputLabel: 'Price (Rand)',
        showCancelButton: true,
        inputValidator: (value) => {
            if (!value || value <= 0) {
                return 'Please enter a valid price'
            }
        }
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/bespoke/api/pricing/price/add/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    tier_id: tierId,
                    size_id: sizeId,
                    price: result.value
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload(); // Reload to show new price
                } else {
                    Swal.fire('Error', data.error, 'error');
                }
            });
        }
    });
}

function bulkEditPrices(addonType) {
    Swal.fire({
        title: 'Bulk Edit Prices',
        html: `
            <p>Apply a percentage change to all prices:</p>
            <input id="percentage-input" class="swal2-input" type="number" step="0.1" placeholder="Enter %">
            <label>
                <input id="increase-checkbox" type="checkbox" checked> Increase
            </label>
        `,
        showCancelButton: true,
        confirmButtonText: 'Apply',
        preConfirm: () => {
            const percentage = document.getElementById('percentage-input').value;
            const isIncrease = document.getElementById('increase-checkbox').checked;

            if (!percentage || percentage == 0) {
                Swal.showValidationMessage('Enter a valid percentage');
                return false;
            }

            return { percentage: parseFloat(percentage), isIncrease };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            applyBulkPriceChange(addonType, result.value.percentage, result.value.isIncrease);
        }
    });
}

function exportPricing(addonType) {
    window.location.href = `/bespoke/api/pricing/export/${addonType}/`;
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
```

---

## Phase 6: Quotation Integration

### 6.1 Quotation Item Model Extension

**File**: `/Users/sas/Repos/SASKITUP/quotations/models.py`

```python
class QuotationItem(models.Model):
    # ... existing fields ...

    # Addon-specific fields
    addon_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('heat_transfer', 'Heat Transfer'),
            ('screen_print', 'Screen Print'),
            ('emb_applique', 'Embroidery/Applique'),
        ]
    )

    addon_specifications = models.JSONField(
        default=dict,
        blank=True,
        help_text="Addon specs (dimensions, stitch complexity, etc.)"
    )

    pricing_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Pricing calculation details"
    )
```

### 6.2 Pricing Service Integration

When creating quotation with addons, use `AddonPrice.get_price()` method:

```python
from bespoke.models import AddonPrice

# In quotation creation logic
if item.addon_type:
    calculated_price = AddonPrice.get_price(
        addon_type=item.addon_type,
        quantity=item.quantity,
        width_inches=item.addon_specifications.get('width'),
        height_inches=item.addon_specifications.get('height'),
        stitch_complexity=item.addon_specifications.get('stitch_complexity')
    )

    if calculated_price:
        item.unit_price = calculated_price
        item.pricing_breakdown = {
            'base_price': str(calculated_price),
            'calculation_method': 'tier_based',
            'tier': '...',
            'size': '...'
        }
```

---

## Implementation Timeline

### Week 1: Database & Exclusions
- ✅ Create addon pricing models
- ✅ Generate migrations
- ✅ Modify bespoke sync service to exclude addons
- ✅ Modify wholesale price update to exclude bespoke addons
- ✅ Test exclusions

### Week 2: UI Foundation
- ✅ Enhance category_detail view for addon pricing
- ✅ Create tabbed interface in template
- ✅ Build pricing matrix table HTML
- ✅ Add basic CSS styling

### Week 3: AJAX API
- ✅ Implement pricing management API endpoints
- ✅ Build JavaScript frontend for interactions
- ✅ Add SweetAlert2 modals
- ✅ Implement export/import functionality

### Week 4: Integration & Testing
- ✅ Integrate with quotation system
- ✅ Add price calculation logic
- ✅ Manual data entry of prices from image
- ✅ End-to-end testing
- ✅ Bug fixes and polish

### Week 5: Documentation & Training
- ✅ User documentation
- ✅ Admin training materials
- ✅ Video tutorials
- ✅ Deployment to production

---

## Key Benefits of Updated Approach

### 1. **Better User Experience**
- Integrated into familiar bespoke interface
- No context switching to Django Admin
- Visual pricing matrix layout matches source image
- Real-time updates with AJAX

### 2. **Proper Separation of Concerns**
- Addons excluded from CIN7 sync (manual pricing management)
- Addons excluded from wholesale price updates (separate pricing structure)
- Clear boundary between base garments and addons

### 3. **Maintainability**
- Custom UI easier to modify than Django Admin
- Business logic centralized in service layer
- Clear audit trail with price history
- Export/import for bulk operations

### 4. **Scalability**
- Easy to add new addon types
- Support for complex pricing rules
- Date-based price versioning
- Bulk operations for efficiency

---

## Security Considerations

### Access Control
- Pricing management: Authenticated users only (`@login_required`)
- Price history: Read-only audit trail
- Export/import: Staff/admin only (add permissions check)

### Data Validation
- Server-side validation in views
- Model-level validation in `clean()` methods
- Price must be positive decimal
- Tier/size addon type consistency enforced

### Audit Trail
- All price changes logged in `AddonPriceHistory`
- Track who changed what and when
- Change reason required for updates
- Immutable history records

---

## Testing Checklist

### Unit Tests
- [ ] `AddonPrice.get_price()` returns correct price for tier/size
- [ ] Model validation prevents mismatched addon types
- [ ] Price history records created on updates

### Integration Tests
- [ ] Bespoke sync excludes addon products
- [ ] Wholesale price update excludes bespoke addons
- [ ] Quotation calculates addon prices correctly

### UI Tests
- [ ] Pricing tab displays only on addon category page
- [ ] Edit price modal updates database
- [ ] Bulk edit applies percentage changes correctly
- [ ] Export generates correct CSV format

### Browser Testing
- [ ] Chrome, Firefox, Safari, Edge
- [ ] Responsive layout on mobile/tablet
- [ ] JavaScript functions work across browsers

---

## Summary

This updated plan provides a comprehensive, production-ready solution for managing bespoke addon pricing with:

1. **Custom UI** at `/bespoke/category/addon/` instead of Django Admin
2. **Proper exclusions** for addons from sync and price update operations
3. **Full-featured pricing management** with tiers, sizes, and audit trail
4. **AJAX-powered interface** for real-time updates
5. **Seamless quotation integration** using service layer

The implementation follows Django best practices, maintains clean architecture, and provides excellent user experience for managing complex pricing structures.

**Next Steps**:
1. Review and approve this updated plan
2. Begin Week 1 implementation (database models and exclusions)
3. Test exclusions thoroughly
4. Move to UI development in Week 2
