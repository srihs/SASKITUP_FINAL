# TUS Product Variations Implementation Plan

## Executive Summary

This document provides a comprehensive implementation plan to replicate SAS product variations linking and display patterns for TUS schools. The analysis is based on the existing SAS implementation in the SASKITUP codebase.

**Status**: TUS models have variation support in place. Implementation needed for views, templates, and frontend JavaScript.

---

## 1. SAS Implementation Pattern Analysis

### 1.1 SAS Model Structure

**File**: `/Users/sas/Repos/SASKITUP/clubs/models_sas.py`

#### SASProduct Model (Lines 389-576)
```python
class SASProduct(models.Model):
    # Core fields
    name = CharField(max_length=255)
    slug = SlugField(max_length=255, blank=True)
    woo_product_id = PositiveIntegerField(unique=True)

    # Relationship to club
    club = ForeignKey(SASClub, on_delete=CASCADE, related_name='products')

    # Product type and pricing
    product_type = CharField(max_length=20, choices=TYPE_CHOICES, default='simple')
    price = DecimalField(max_digits=10, decimal_places=2)
    regular_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Stock management
    stock_status = CharField(max_length=20, choices=STOCK_STATUS_CHOICES)
    manage_stock = BooleanField(default=False)
    stock_quantity = IntegerField(null=True, blank=True)

    # Key variation-related properties
    @property
    def has_variations(self):
        """Check if product has variations"""
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
            return True
        # Also check attributes field for variation data
        if self.attributes:
            for attr in self.attributes:
                if attr.get('variation', False) and len(attr.get('options', [])) > 1:
                    return True
        return False

    @property
    def is_variable_product(self):
        """Check if this is a variable product"""
        return self.product_type == 'variable' or self.has_variations
```

**Key Methods** (Lines 637-865):
- `_parse_variation_attributes()` - Parses variation attributes from WooCommerce data
- `available_sizes` - Returns list of unique sizes
- `available_colors` - Returns list of unique colors
- `parsed_variation_attributes` - Returns dict of all parsed attributes
- `get_available_variations_for_selection(**selection)` - Returns available options based on current selection
- `get_variation_combination_stock(**combination)` - Returns stock for specific combination
- `is_variation_combination_available(**combination)` - Checks if combination is available
- `get_variation_data_for_frontend()` - Returns structured data for JavaScript (Lines 965-1059)

#### SASProductVariation Model (Lines 1062-1209)
```python
class SASProductVariation(models.Model):
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('colour', 'Colour'),
        ('material', 'Material'),
        ('style', 'Style'),
        ('gender', 'Gender'),
        ('age_group', 'Age Group'),
        ('other', 'Other'),
    ]

    # Relationships
    product = ForeignKey(SASProduct, on_delete=CASCADE, related_name='variations')

    # Core fields
    variation_type = CharField(max_length=50, choices=VARIATION_TYPE_CHOICES)
    variation_value = CharField(max_length=255)
    woo_variation_id = PositiveIntegerField(unique=True, null=True, blank=True)

    # Pricing (typically no price modifier for SAS)
    price_modifier = DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Stock
    stock_quantity = PositiveIntegerField(default=0)
    sku_suffix = CharField(max_length=50, blank=True, null=True)

    # Status
    is_active = BooleanField(default=True)

    # Additional data
    attributes = JSONField(blank=True, null=True)
    image_url = URLField(blank=True)

    # Properties
    @property
    def final_price(self):
        """Calculate final price including price modifier"""
        return self.product.effective_price + self.price_modifier

    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.is_active and self.stock_quantity > 0

    @property
    def stock_status(self):
        """Get stock status based on quantity"""
        if not self.is_active:
            return 'discontinued'
        elif self.stock_quantity > 0:
            return 'instock'
        else:
            return 'outofstock'
```

### 1.2 SAS View Implementation

**File**: `/Users/sas/Repos/SASKITUP/clubs/views.py`

#### SASProductDetailView (Lines 1749-1859)
```python
class SASProductDetailView(ClubProductAuditMixin, DetailView):
    model = SASProduct
    template_name = 'clubs/sas_product_detail.html'

    def get_queryset(self):
        return SASProduct.objects.filter(
            stock_status__in=['instock', 'outofstock', 'onbackorder']
        ).select_related('club__sport').prefetch_related('variations')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # Add variations
        context['variations'] = product.variations.all()

        # Stock management for single-variant products
        effective_stock_status = (
            product.calculated_stock_status if product.has_variations
            else product.stock_status
        )

        # Parse available sizes and colors
        variations = product.variations.all()
        context['available_sizes'] = list(set(
            var.variation_value.split(' - ')[0] if ' - ' in var.variation_value
            else var.variation_value for var in variations
            if var.variation_type in ['size', 'Size']
        ))
        context['available_colors'] = list(set(
            var.variation_value.split(' - ')[-1] if ' - ' in var.variation_value
            else var.variation_value for var in variations
            if var.variation_type in ['color', 'Color', 'colour', 'Colour']
        ))

        # Detect size-only products
        variation_types = set(var.variation_type.lower() for var in variations)
        has_size_variations = any(vtype in ['size', 'sizing'] for vtype in variation_types)
        has_color_variations = any(vtype in ['color', 'colour'] for vtype in variation_types)

        is_size_only_product = has_size_variations and not has_color_variations
        context['is_size_only_product'] = is_size_only_product

        # For size-only products, get size-specific stock info
        if is_size_only_product:
            size_stock_info = []
            for size in context['available_sizes']:
                size_variation = variations.filter(
                    variation_type__iexact='size',
                    variation_value__icontains=size
                ).first()

                stock_quantity_size = (
                    size_variation.stock_quantity if size_variation
                    else 25  # Default stock
                )

                size_stock_info.append({
                    'size': size,
                    'stock_quantity': stock_quantity_size,
                    'is_available': stock_quantity_size > 0
                })

            context['size_stock_info'] = size_stock_info

        return context
```

#### sas_product_variations_api (Lines 2677-2773)
```python
def sas_product_variations_api(request, product_id):
    """API endpoint to get product variations with stock information"""
    try:
        product = get_object_or_404(SASProduct, id=product_id)

        if product.has_variations:
            variation_data = product.get_variation_data_for_frontend()
            variations_data = variation_data.get('variations', [])
            grouped_variations = {}

            # Group variations by type
            for variation in variations_data:
                var_type = variation['type']
                if var_type not in grouped_variations:
                    grouped_variations[var_type] = []

                stock_quantity = variation.get('stock', 0) or 0
                is_in_stock = variation.get('is_in_stock', stock_quantity > 0)

                # Calculate stock_status
                if not variation.get('is_active', True):
                    stock_status = 'discontinued'
                elif stock_quantity > 0:
                    stock_status = 'instock'
                else:
                    stock_status = 'outofstock'

                # For SAS, colors/categories always selectable
                is_available = is_in_stock
                if var_type in ['color', 'colour', 'age_group', 'gender']:
                    is_available = True

                enhanced_variation = {
                    'id': variation['id'],
                    'type': var_type,
                    'value': variation['value'],
                    'is_available': is_available,
                    'stock_quantity': stock_quantity,
                    'stock_status': stock_status,
                    'price_modifier': variation.get('price_modifier', 0.0),
                    'final_price': variation.get('final_price', float(product.effective_price)),
                    'sku_suffix': variation.get('sku_suffix', ''),
                    'image': variation.get('image', product.image_url),
                    'attributes': variation.get('attributes', {})
                }

                grouped_variations[var_type].append(enhanced_variation)

            # Sort variations: age_group/gender -> size -> color -> others
            sas_order = ['age_group', 'gender', 'size', 'color', 'colour', 'material', 'style']
            ordered_grouped_variations = {}

            for var_type in sas_order:
                if var_type in grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values(
                        grouped_variations[var_type], var_type
                    )

            # Add remaining variations
            for var_type, variations in grouped_variations.items():
                if var_type not in ordered_grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values(
                        variations, var_type
                    )

            grouped_variations = ordered_grouped_variations
        else:
            variations_data = []
            grouped_variations = {}

        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_name': product.name,
            'base_price': float(product.effective_price),
            'variations': variations_data,
            'grouped_variations': grouped_variations,
            'total_variations': len(variations_data),
            'variation_order': list(grouped_variations.keys())
        })

    except Exception as e:
        logger.error(f"Error fetching SAS product variations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch product variations',
            'message': str(e)
        }, status=500)
```

### 1.3 SAS Template Implementation

**File**: `/Users/sas/Repos/SASKITUP/template/clubs/sas_product_detail.html`

#### Key Template Structure (Lines 1111-1266)
```django
<div class="sas-product-page">
    <div class="row">
        <!-- Product Image Gallery (Left Column) -->
        <div class="col-lg-6 col-md-12">
            <div class="product-gallery">
                <div class="main-product-image" id="mainImageContainer">
                    <img src="{{ product.image_url }}"
                         alt="{{ product.name }}"
                         id="mainProductImage">
                </div>

                <!-- Thumbnail Gallery -->
                <div class="product-thumbnails" id="thumbnailGallery">
                    <!-- Thumbnails rendered here -->
                </div>

                <!-- Color Variation Thumbnail Sidebar -->
                <div class="thumbnail-sidebar" id="colorThumbnailSidebar">
                    <!-- Color thumbnails inserted by JavaScript -->
                </div>
            </div>

            <!-- Stock Availability Grid (under image) -->
            <div class="stock-grid-container mt-3">
                <!-- Stock grid populated by JavaScript -->
            </div>

            <!-- Stock Status for Single-Variant Products -->
            <div id="stockStatusContainer" class="stock-status-container mt-3">
                <!-- Stock tile for simple products -->
            </div>
        </div>

        <!-- Product Information (Right Column) -->
        <div class="col-lg-6 col-md-12">
            <div class="product-info">
                <!-- Club Information -->
                <div class="product-club-info">
                    <img src="{{ primary_category.club.logo }}" class="club-logo">
                    <div>
                        <div class="club-name">{{ primary_category.club.name }}</div>
                        <small>{{ primary_category.name }}</small>
                    </div>
                    <span class="badge badge-sas ms-auto">SAS</span>
                </div>

                <!-- Product Title -->
                <h1 class="product-title">{{ product.name }}</h1>

                <!-- Product Pricing -->
                <div class="product-pricing">
                    <div class="price-container">
                        <div class="current-price" id="productPrice">
                            ${{ product.effective_price|floatformat:2 }}
                        </div>
                        {% if product.is_on_sale %}
                            <div class="original-price">
                                ${{ product.regular_price|floatformat:2 }}
                            </div>
                            <span class="discount-badge">
                                {{ product.sale_discount_percentage|floatformat:0 }}% OFF
                            </span>
                        {% endif %}
                    </div>
                </div>

                <!-- Dynamic Product Variations -->
                <div class="variation-section" id="productVariations">
                    <!-- Category Options (Adults/Kids) -->
                    <div class="category-options mb-4">
                        <div class="option-label mb-3">
                            <h6>Category:</h6>
                        </div>
                        <div class="category-swatches">
                            <!-- Category swatches loaded by JavaScript -->
                        </div>
                    </div>

                    <!-- Color Options -->
                    <div class="color-options mb-4">
                        <div class="option-label mb-3">
                            <h6>Color:</h6>
                        </div>
                        <div class="color-swatches">
                            <!-- Color swatches loaded by JavaScript -->
                        </div>
                    </div>

                    <!-- Size Options -->
                    <div class="size-options mb-4">
                        <div class="option-label mb-3">
                            <h6>Select Size</h6>
                        </div>
                        <div class="size-buttons">
                            <!-- Size buttons loaded by JavaScript -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
```

#### JavaScript Initialization (Lines 1268-1470)
```javascript
// Initialize product variations
function initializeProductVariations() {
    const productId = {{ product.woo_product_id }};
    const productType = 'sas';

    // Create variation manager
    variationManager = new ProductVariationManager(productId, productType, {
        enableStockCheck: true,
        enablePriceUpdates: true,
        enableLoadingStates: true,
        debounceDelay: 300
    });

    // Pass stock data to JavaScript
    if (variationManager) {
        variationManager.productData = {
            stock_status: '{{ effective_stock_status|default:product.stock_status }}',
            stock_quantity: {{ stock_quantity|default:0 }},
            manage_stock: {{ manage_stock|yesno:"true,false" }}
        };

        // Set global stock variables
        window.stockQuantity = {{ stock_quantity|default:0 }};
        window.stockStatus = '{{ effective_stock_status|default:product.stock_status }}';
        window.manageStock = {{ manage_stock|yesno:"true,false" }};

        // Set size-only product info
        window.isSizeOnlyProduct = {{ is_size_only_product|yesno:"true,false" }};
        {% if is_size_only_product and size_stock_info %}
        window.sizeStockInfo = [
            {% for size_info in size_stock_info %}
            {
                size: '{{ size_info.size }}',
                stock_quantity: {{ size_info.stock_quantity }},
                is_available: {{ size_info.is_available|yesno:"true,false" }}
            }{% if not forloop.last %},{% endif %}
            {% endfor %}
        ];
        {% endif %}
    }

    // Listen for variation changes
    document.addEventListener('variationChanged', function(event) {
        const detail = event.detail;
        updateProductInfo(detail);
    });
}
```

**JavaScript Library**: `/Users/sas/Repos/SASKITUP/static/assets/js/product-variations.js` (referenced in template line 1270)

---

## 2. TUS Current State Analysis

### 2.1 TUS Model Structure

**File**: `/Users/sas/Repos/SASKITUP/clubs/models_tus.py`

#### TUSProduct Model (Lines 449-633)
```python
class TUSProduct(models.Model):
    # Core fields - SIMILAR TO SAS
    name = CharField(max_length=255)
    slug = SlugField(max_length=255, blank=True)
    woo_product_id = PositiveIntegerField(unique=True)

    # Multi-category support (different from SAS club relationship)
    # Products link to categories via TUSProductCategoryAssignment

    # Product type and pricing - SAME AS SAS
    type = CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple')
    price = DecimalField(max_digits=10, decimal_places=2)
    regular_price = DecimalField(max_digits=10, decimal_places=2, null=True)
    sale_price = DecimalField(max_digits=10, decimal_places=2, null=True)
    on_sale = BooleanField(default=False)

    # Stock management - SAME AS SAS
    stock_status = CharField(max_length=20, choices=STOCK_STATUS_CHOICES)
    manage_stock = BooleanField(default=False)
    stock_quantity = IntegerField(null=True)

    # Pricing management fields - SAME AS SAS
    cost_price = DecimalField(...)
    margin_75_price = DecimalField(...)
    discount_percentage = DecimalField(...)
    last_price_update = DateTimeField(...)
    barcode = CharField(...)

    # Properties
    @property
    def has_variations(self):
        """Check if product has variations"""
        return self.variations.exists()

    @property
    def is_variable_product(self):
        """Check if this is a variable product"""
        return self.type == 'variable' or self.has_variations

    # Category relationships
    @property
    def primary_category(self):
        """Get primary category assignment"""
        assignment = self.category_assignments.filter(is_primary=True).first()
        if assignment:
            return assignment.school_category or assignment.general_category
        return None
```

**MISSING METHODS** (compared to SAS):
- ❌ `_parse_variation_attributes()` - Parse variation data from WooCommerce
- ❌ `available_sizes` - Get unique sizes
- ❌ `available_colors` - Get unique colors
- ❌ `parsed_variation_attributes` - Get all parsed attributes
- ❌ `get_available_variations_for_selection(**selection)` - Filter available options
- ❌ `get_variation_combination_stock(**combination)` - Get stock for combination
- ❌ `is_variation_combination_available(**combination)` - Check availability
- ❌ `get_variation_data_for_frontend()` - Structured data for JavaScript

#### TUSProductVariation Model (Lines 635-699+)
```python
class TUSProductVariation(models.Model):
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('gender', 'Gender'),
        ('style', 'Style'),
        ('length', 'Length'),
        ('fit', 'Fit'),
        ('other', 'Other'),
    ]

    # Relationships - SAME AS SAS
    product = ForeignKey(TUSProduct, on_delete=CASCADE, related_name='variations')

    # Core fields - SAME AS SAS
    variation_type = CharField(max_length=50, choices=VARIATION_TYPE_CHOICES)
    variation_value = CharField(max_length=255)
    woo_variation_id = PositiveIntegerField(unique=True)

    # Pricing - SAME AS SAS
    price = DecimalField(max_digits=10, decimal_places=2)
    regular_price = DecimalField(...)
    sale_price = DecimalField(...)

    # Stock - SAME AS SAS
    stock_quantity = PositiveIntegerField(default=0)
    stock_status = CharField(...)
    sku = CharField(...)

    # Status and metadata - SAME AS SAS
    is_active = BooleanField(default=True)
    attributes = JSONField(...)
    image_url = URLField(...)
    menu_order = PositiveIntegerField(default=0)
```

**MISSING PROPERTIES** (compared to SAS):
- ❌ `final_price` - Calculate price with modifiers
- ❌ `full_sku` - Generate full SKU
- ❌ `is_in_stock` - Check stock status
- ❌ `stock_status` property - Dynamic status based on quantity
- ❌ `effective_image` - Image with fallback logic
- ❌ Various image-related properties

### 2.2 TUS View Implementation

**File**: `/Users/sas/Repos/SASKITUP/schools/views.py`

#### TUSProductDetailView (Lines 596-639)
```python
class TUSProductDetailView(TUSAuditMixin, DetailView):
    model = TUSProduct
    template_name = 'schools/retail/product_detail.html'

    def get_queryset(self):
        return TUSProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).prefetch_related(
            'variations',
            'category_assignments__school_category__school',
            'category_assignments__general_category'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object

        # Get variations
        context['variations'] = product.variations.filter(is_active=True).order_by('menu_order')

        # Get categories
        context['categories'] = product.all_categories

        # Get related products
        related_products = TUSProduct.objects.filter(
            Q(category_assignments__school_category__in=product.school_categories.all()) |
            Q(category_assignments__general_category__in=product.general_categories.all()),
            stock_status__in=['instock', 'onbackorder']
        ).exclude(id=product.id).distinct()[:6]
        context['related_products'] = related_products

        # Check if product belongs to a school
        school_category = product.category_assignments.filter(
            school_category__isnull=False
        ).first()
        if school_category:
            context['school'] = school_category.school_category.school

        return context
```

**MISSING FUNCTIONALITY** (compared to SAS):
- ❌ Stock quantity information for single-variant products
- ❌ Effective stock status calculation
- ❌ Available sizes parsing
- ❌ Available colors parsing
- ❌ Size-only product detection
- ❌ Size-specific stock information

#### tus_product_variations_api (Lines 781-815)
```python
def tus_product_variations_api(request, product_id):
    """API endpoint to get product variations"""
    try:
        product = get_object_or_404(TUSProduct, id=product_id)
        variations = product.variations.filter(is_active=True)

        # Group variations by type
        variation_data = {}
        for variation in variations:
            var_type = variation.variation_type
            if var_type not in variation_data:
                variation_data[var_type] = []

            variation_data[var_type].append({
                'id': variation.id,
                'value': variation.variation_value,
                'price': str(variation.price),
                'stock_status': variation.stock_status,
                'stock_quantity': variation.stock_quantity,
                'sku': variation.sku,
                'image_url': variation.effective_image_url,  # REQUIRES PROPERTY
                'in_stock': variation.is_in_stock  # REQUIRES PROPERTY
            })

        return JsonResponse({
            'success': True,
            'variations': variation_data,
            'base_price': str(product.price)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
```

**MISSING FUNCTIONALITY** (compared to SAS):
- ❌ Enhanced variation data with stock_status calculation
- ❌ Availability flags for different variation types
- ❌ Variation ordering (age_group/gender → size → color → others)
- ❌ Sorted variation values
- ❌ Grouped variations structure
- ❌ Total variations count
- ❌ Variation order list

### 2.3 TUS Template Implementation

**File**: `/Users/sas/Repos/SASKITUP/schools/templates/schools/retail/product_detail.html`

**Current Status** (Lines 1-200):
- Basic product detail layout
- Product image gallery placeholder
- Product information section
- Pricing display
- Stock status display
- Basic variation section structure

**MISSING FUNCTIONALITY** (compared to SAS):
- ❌ Dynamic variation swatches (category, color, size)
- ❌ JavaScript variation manager initialization
- ❌ Stock grid display under image
- ❌ Color thumbnail sidebar
- ❌ Size inventory tiles
- ❌ Variation change event handling
- ❌ Stock status updates based on selection
- ❌ Price updates based on variation selection
- ❌ Image updates based on color selection

---

## 3. Implementation Plan

### Phase 1: TUSProduct Model Enhancement

**File**: `/Users/sas/Repos/SASKITUP/clubs/models_tus.py`

**Task 1.1**: Add variation parsing methods to TUSProduct model (after line 633)

```python
def _parse_variation_attributes(self):
    """
    Parse variation attributes from the attributes field.
    Returns dict with attribute type as key and list of values as value.
    """
    # Standard attribute priority order
    attribute_priority = ['size', 'color', 'material', 'style', 'gender', 'length', 'fit']

    # Dictionary to store parsed attributes
    parsed_attributes = {}

    # Check actual TUS variations first
    if hasattr(self, 'variations'):
        variations = self.variations.filter(is_active=True, stock_quantity__gt=0)
        for variation in variations:
            if variation.variation_type not in parsed_attributes:
                parsed_attributes[variation.variation_type] = set()
            parsed_attributes[variation.variation_type].add(variation.variation_value)

    # Parse from attributes field
    if self.attributes:
        for attr in self.attributes:
            if isinstance(attr, dict) and attr.get('variation', False):
                attr_name = attr.get('name', '').lower()
                # Map common attribute names to standard types
                attr_type = attr_name
                if 'colour' in attr_name:
                    attr_type = 'color'
                elif 'size' in attr_name:
                    attr_type = 'size'

                options = attr.get('options', [])
                if options and len(options) > 1:
                    if attr_type not in parsed_attributes:
                        parsed_attributes[attr_type] = set()
                    for option in options:
                        parsed_attributes[attr_type].add(str(option))

    # Convert sets to sorted lists
    result = {}
    for attr_type, values in parsed_attributes.items():
        if values:
            result[attr_type] = sorted(list(values))

    return result

@property
def available_sizes(self):
    """Get available sizes for this product"""
    parsed = self._parse_variation_attributes()
    return parsed.get('size', [])

@property
def available_colors(self):
    """Get available colors for this product"""
    parsed = self._parse_variation_attributes()
    return parsed.get('color', [])

@property
def available_genders(self):
    """Get available genders for this product"""
    parsed = self._parse_variation_attributes()
    return parsed.get('gender', [])

@property
def parsed_variation_attributes(self):
    """Get all parsed variation attributes as a dictionary"""
    return self._parse_variation_attributes()

def get_available_variations_for_selection(self, **selection):
    """
    Get available variation options based on current selection.
    Returns dict with available options for each variation type.
    """
    result = {}

    # If product has actual TUS variations, use them
    if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
        base_variations = self.variations.filter(is_active=True, stock_quantity__gt=0)

        # Apply current selection filters
        for attr_type, attr_value in selection.items():
            if attr_value:
                base_variations = base_variations.filter(
                    variation_type=attr_type,
                    variation_value=attr_value
                )

        # Get available options for each variation type
        variation_types = ['size', 'color', 'gender', 'style', 'length', 'fit']

        for var_type in variation_types:
            if var_type in selection and selection[var_type]:
                continue

            options = []
            type_variations = base_variations.filter(variation_type=var_type).distinct()

            for variation in type_variations:
                options.append({
                    'value': variation.variation_value,
                    'stock': variation.stock_quantity,
                    'available': variation.stock_quantity > 0,
                    'variation_id': variation.id,
                    'price_modifier': 0.0,  # TUS typically doesn't have price modifiers
                    'image': variation.image_url if hasattr(variation, 'image_url') else None
                })

            if options:
                options.sort(key=lambda x: x['value'])
                result[var_type] = options

    else:
        # Use attribute-based variations
        parsed_attrs = self.parsed_variation_attributes
        for attr_type, values in parsed_attrs.items():
            if attr_type in selection and selection[attr_type]:
                continue

            options = []
            for value in values:
                stock_value = None
                if self.manage_stock and self.stock_quantity is not None:
                    stock_value = self.stock_quantity

                options.append({
                    'value': value,
                    'stock': stock_value,
                    'available': self.stock_status in ['instock', 'onbackorder'],
                    'variation_id': f"{self.id}_{attr_type}_{value}",
                    'price_modifier': 0.0,
                    'image': self.image_url
                })

            if options:
                result[attr_type] = options

    return result

def get_variation_combination_stock(self, **combination):
    """
    Get stock quantity for a specific variation combination.
    """
    # If product has actual variations, use them
    if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
        from django.db.models import Sum

        variations = self.variations.filter(is_active=True)
        for attr_type, attr_value in combination.items():
            if attr_value:
                variations = variations.filter(
                    variation_type=attr_type,
                    variation_value=attr_value
                )

        total_stock = variations.aggregate(
            total=Sum('stock_quantity')
        )['total'] or 0

        return total_stock
    else:
        # For attribute-based variations, return product stock
        parsed_attrs = self.parsed_variation_attributes
        for attr_type, attr_value in combination.items():
            if attr_value:
                if attr_type not in parsed_attrs or attr_value not in parsed_attrs[attr_type]:
                    return 0  # Invalid combination

        if self.manage_stock and self.stock_quantity is not None:
            return self.stock_quantity
        elif self.stock_status == 'instock':
            return 1  # Available
        elif self.stock_status == 'onbackorder':
            return 1  # Available for backorder
        else:
            return 0  # Out of stock

def is_variation_combination_available(self, **combination):
    """
    Check if a specific variation combination is available.
    """
    stock = self.get_variation_combination_stock(**combination)
    if stock is None:
        return self.stock_status in ['instock', 'onbackorder']
    return stock > 0

def get_variation_data_for_frontend(self):
    """
    Get structured variation data for frontend JavaScript.

    Returns:
        dict: Structured data for frontend variation handling
    """
    if not self.has_variations:
        return {}

    variations_data = {
        'product_id': self.id,
        'has_variations': True,
        'variation_types': [],
        'variations': [],
        'parsed_attributes': self.parsed_variation_attributes,
        'total_stock': self.stock_quantity
    }

    # If product has actual TUS variations
    if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
        variations_data['variation_types'] = list(
            self.variations.filter(is_active=True).values_list('variation_type', flat=True).distinct()
        )

        for variation in self.variations.filter(is_active=True):
            is_in_stock = getattr(variation, 'is_in_stock', variation.stock_quantity > 0)

            # Calculate stock_status
            if not variation.is_active:
                stock_status = 'discontinued'
            elif variation.stock_quantity > 0:
                stock_status = 'instock'
            else:
                stock_status = 'outofstock'

            var_data = {
                'id': variation.id,
                'type': variation.variation_type,
                'value': variation.variation_value,
                'stock': variation.stock_quantity,
                'stock_status': stock_status,
                'price_modifier': 0.0,
                'final_price': float(self.price),
                'sku_suffix': getattr(variation, 'sku', ''),
                'is_in_stock': is_in_stock,
                'image': getattr(variation, 'image_url', self.image_url),
                'attributes': getattr(variation, 'attributes', {}) or {}
            }
            variations_data['variations'].append(var_data)
    else:
        # Use attribute-based variations
        parsed_attrs = self.parsed_variation_attributes
        variations_data['variation_types'] = list(parsed_attrs.keys())

        for attr_type, values in parsed_attrs.items():
            for value in values:
                stock_value = 0
                if self.manage_stock and self.stock_quantity is not None:
                    stock_value = self.stock_quantity

                is_in_stock = (stock_value > 0) or (self.stock_status == 'onbackorder')

                # Calculate stock_status
                if not self.stock_status == 'instock':
                    stock_status = 'discontinued'
                elif stock_value and stock_value > 0:
                    stock_status = 'instock'
                    is_in_stock = True
                elif self.stock_status == 'onbackorder':
                    stock_status = 'onbackorder'
                    is_in_stock = True
                else:
                    stock_status = 'outofstock'
                    is_in_stock = False

                var_data = {
                    'id': f"{self.id}_{attr_type}_{value}",
                    'type': attr_type,
                    'value': value,
                    'stock': stock_value,
                    'stock_status': stock_status,
                    'price_modifier': 0.0,
                    'final_price': float(self.price),
                    'sku_suffix': f"{attr_type}-{value}",
                    'is_in_stock': is_in_stock,
                    'image': self.image_url,
                    'attributes': {attr_type: value}
                }
                variations_data['variations'].append(var_data)

    return variations_data
```

**Task 1.2**: Add properties to TUSProductVariation model (after line 699)

```python
@property
def final_price(self):
    """Calculate the final price"""
    return self.price

@property
def full_sku(self):
    """Generate full SKU"""
    base_sku = self.product.sku or f"TUS-{self.product.id}"
    if self.sku:
        return self.sku
    return f"{base_sku}-{self.variation_type[:3].upper()}-{self.variation_value[:5].upper()}"

@property
def is_in_stock(self):
    """Check if variation is in stock"""
    return self.is_active and self.stock_quantity > 0

@property
def effective_image_url(self):
    """Get effective image URL with fallback"""
    if self.image_url:
        return self.image_url
    if self.product and self.product.image_url:
        return self.product.image_url
    return None

@property
def is_on_sale(self):
    """Check if variation is on sale"""
    return (
        self.sale_price is not None and
        self.sale_price > 0 and
        self.regular_price is not None and
        self.sale_price < self.regular_price
    )

@property
def discount_percentage(self):
    """Calculate discount percentage"""
    if self.is_on_sale and self.regular_price:
        return round(((self.regular_price - self.sale_price) / self.regular_price) * 100, 2)
    return 0
```

### Phase 2: TUSProductDetailView Enhancement

**File**: `/Users/sas/Repos/SASKITUP/schools/views.py`

**Task 2.1**: Update TUSProductDetailView.get_context_data() (lines 613-639)

```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    product = self.object

    # Add product variations with stock information
    context['variations'] = product.variations.filter(is_active=True).order_by('menu_order')

    # Add stock quantity information for single-variant products
    stock_quantity = 0
    manage_stock = False

    # For TUS products, provide stock management similar to SAS
    effective_stock_status = (
        product.stock_status  # TUS doesn't have calculated_stock_status yet
    )

    if not product.has_variations and effective_stock_status == 'instock':
        # For single-variant products without specific stock data
        stock_quantity = 25  # Default stock for simple products
        manage_stock = True
    elif hasattr(product, 'stock_quantity') and product.stock_quantity is not None:
        stock_quantity = product.stock_quantity
        manage_stock = True

    context['stock_quantity'] = stock_quantity
    context['manage_stock'] = manage_stock
    context['effective_stock_status'] = effective_stock_status

    # Add available sizes and colors from variations
    variations = product.variations.filter(is_active=True)
    context['available_sizes'] = list(set(
        var.variation_value.split(' - ')[0] if ' - ' in var.variation_value
        else var.variation_value for var in variations
        if var.variation_type in ['size', 'Size']
    ))
    context['available_colors'] = list(set(
        var.variation_value.split(' - ')[-1] if ' - ' in var.variation_value
        else var.variation_value for var in variations
        if var.variation_type in ['color', 'Color', 'colour', 'Colour']
    ))
    context['available_genders'] = list(set(
        var.variation_value for var in variations
        if var.variation_type in ['gender', 'Gender']
    ))

    # Determine variation patterns
    variation_types = set(var.variation_type.lower() for var in variations)
    has_size_variations = any(vtype in ['size', 'sizing'] for vtype in variation_types)
    has_color_variations = any(vtype in ['color', 'colour'] for vtype in variation_types)
    has_gender_variations = any(vtype in ['gender'] for vtype in variation_types)
    has_other_variations = any(
        vtype not in ['size', 'sizing', 'color', 'colour', 'gender']
        for vtype in variation_types
    )

    is_size_only_product = has_size_variations and not has_color_variations and not has_other_variations
    context['is_size_only_product'] = is_size_only_product

    # For size-only products, get size-specific stock information
    if is_size_only_product:
        size_stock_info = []

        for size in context['available_sizes']:
            size_variation = variations.filter(
                variation_type__iexact='size',
                variation_value__icontains=size
            ).first()

            if size_variation and hasattr(size_variation, 'stock_quantity'):
                stock_quantity_size = size_variation.stock_quantity or 0
            else:
                stock_quantity_size = 25  # Default stock

            size_stock_info.append({
                'size': size,
                'stock_quantity': stock_quantity_size,
                'is_available': stock_quantity_size > 0
            })

        context['size_stock_info'] = size_stock_info

    # Get categories
    context['categories'] = product.all_categories

    # Get related products from same categories
    related_products = TUSProduct.objects.filter(
        Q(category_assignments__school_category__in=product.school_categories.all()) |
        Q(category_assignments__general_category__in=product.general_categories.all()),
        stock_status__in=['instock', 'onbackorder']
    ).exclude(id=product.id).distinct()[:6]
    context['related_products'] = related_products

    # Check if product belongs to a specific school
    school_category = product.category_assignments.filter(
        school_category__isnull=False
    ).first()
    if school_category:
        context['school'] = school_category.school_category.school

    # Get primary category for display
    context['primary_category'] = product.primary_category

    return context
```

**Task 2.2**: Update tus_product_variations_api() (lines 781-815)

```python
def tus_product_variations_api(request, product_id):
    """
    API endpoint to get product variations with stock information for TUS products
    Enhanced with proper ordering and filtering support (based on SAS implementation)
    """
    try:
        product = get_object_or_404(TUSProduct, id=product_id)

        # Use the new variation methods for TUS products
        if product.has_variations:
            variation_data = product.get_variation_data_for_frontend()
            variations_data = variation_data.get('variations', [])
            grouped_variations = {}

            # Group variations by type for easier frontend handling
            for variation in variations_data:
                var_type = variation['type']
                if var_type not in grouped_variations:
                    grouped_variations[var_type] = []

                # Enhanced variation data with proper structure for frontend
                stock_quantity = variation.get('stock', 0) or 0
                is_in_stock = variation.get('is_in_stock', stock_quantity > 0)

                # Calculate stock_status
                if not variation.get('is_active', True):
                    stock_status = 'discontinued'
                elif stock_quantity > 0:
                    stock_status = 'instock'
                else:
                    stock_status = 'outofstock'

                # For TUS products, genders and colors should always be selectable
                is_available = is_in_stock
                if var_type in ['color', 'colour', 'gender', 'style']:
                    is_available = True  # Always allow selection for TUS

                enhanced_variation = {
                    'id': variation['id'],
                    'type': var_type,
                    'value': variation['value'],
                    'is_available': is_available,
                    'stock_quantity': stock_quantity,
                    'stock_status': stock_status,
                    'price_modifier': variation.get('price_modifier', 0.0),
                    'final_price': variation.get('final_price', float(product.price)),
                    'sku_suffix': variation.get('sku_suffix', ''),
                    'image': variation.get('image', product.image_url),
                    'attributes': variation.get('attributes', {})
                }

                grouped_variations[var_type].append(enhanced_variation)

            # Sort variations in TUS-specific order: gender -> size -> color -> others
            tus_order = ['gender', 'size', 'color', 'colour', 'style', 'length', 'fit']
            ordered_grouped_variations = {}

            # Add variations in the preferred order
            for var_type in tus_order:
                if var_type in grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values_tus(
                        grouped_variations[var_type], var_type
                    )

            # Add any remaining variations not in the preferred order
            for var_type, variations in grouped_variations.items():
                if var_type not in ordered_grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values_tus(
                        variations, var_type
                    )

            grouped_variations = ordered_grouped_variations
        else:
            # No variations
            variations_data = []
            grouped_variations = {}

        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_name': product.name,
            'base_price': float(product.price),
            'variations': variations_data,
            'grouped_variations': grouped_variations,
            'total_variations': len(variations_data),
            'variation_order': list(grouped_variations.keys())
        })

    except Exception as e:
        logger.error(f"Error fetching TUS product variations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch product variations',
            'message': str(e)
        }, status=500)


def _sort_variation_values_tus(variations, var_type):
    """
    Helper function to sort variation values in logical order for TUS products
    """
    def sort_key(variation):
        value = variation['value'].lower()

        if var_type == 'size':
            # Standard sizes order
            size_order = ['4', '6', '8', '10', '12', '14', '16', '18',
                         'xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl']

            # Try numeric first
            try:
                numeric_value = int(value)
                return (0, numeric_value)
            except ValueError:
                pass

            # Try standard size names
            if value in size_order:
                return (1, size_order.index(value))
            else:
                return (2, value)  # Unknown sizes last

        elif var_type == 'gender':
            # Gender order: Boys/Girls -> Mens/Womens -> Unisex
            gender_order = ['boys', 'girls', 'mens', 'womens', 'men', 'women', 'unisex']
            if value in gender_order:
                return (0, gender_order.index(value))
            else:
                return (1, value)

        elif var_type in ['color', 'colour']:
            # Color order: common colors first
            common_colors = ['black', 'white', 'navy', 'red', 'blue', 'green',
                           'yellow', 'grey', 'gray', 'maroon']
            if value in common_colors:
                return (0, common_colors.index(value))
            else:
                return (1, value)

        else:
            # Default alphabetical sorting
            return (0, value)

    return sorted(variations, key=sort_key)
```

### Phase 3: Template Enhancement

**File**: `/Users/sas/Repos/SASKITUP/schools/templates/schools/retail/product_detail.html`

**Task 3.1**: Replace entire template with TUS-adapted version based on SAS template

Key adaptations needed:
1. Replace `badge-sas` with `badge-tus`
2. Replace SAS blue (#205295) with TUS blue (#387ADF)
3. Update club/category context references:
   - `primary_category.club` → `school` (if applicable)
   - Add school logo display
4. Update breadcrumb navigation for TUS structure
5. Add TUS-specific CSS variables and styling
6. Initialize product variations with `productType = 'tus'`

**New template structure** (similar to SAS but with TUS branding):
```django
{% extends "base.html" %}
{% load static %}

{% block title %}{{ product.name }} - TUS Schools{% endblock %}

{% block extra_css %}
<style>
/* TUS Product Detail Page Styles - Based on SAS Layout */
.tus-product-page {
    background-color: #fafbfc;
    min-height: 100vh;
}

/* TUS Brand Colors */
.badge-tus {
    background-color: #387ADF !important;
    color: white !important;
}

.bg-soft-tus {
    background-color: rgba(56, 122, 223, 0.1);
}

.text-tus {
    color: #387ADF !important;
}

.btn-soft-tus {
    color: #387ADF;
    background-color: rgba(56, 122, 223, 0.1);
    border-color: transparent;
}

.btn-soft-tus:hover {
    color: #fff;
    background-color: #387ADF;
    border-color: #387ADF;
}

.btn-tus {
    background-color: #387ADF;
    border-color: #387ADF;
    color: white;
}

.btn-tus:hover {
    background-color: #2A5FB8;
    border-color: #2A5FB8;
    color: white;
}

/* [Copy remaining CSS from SAS template with TUS color adaptations] */
</style>
{% endblock %}

{% block content %}
<div class="tus-product-page">
    <div class="row">
        <!-- Product Image Gallery (Left Column) -->
        <div class="col-lg-6 col-md-12">
            <div class="product-gallery">
                <div class="main-product-image" id="mainImageContainer">
                    {% if product.image_url %}
                        <img src="{{ product.image_url }}"
                             alt="{{ product.name }}"
                             id="mainProductImage"
                             class="img-fluid">
                    {% else %}
                        <div class="d-flex align-items-center justify-content-center h-100">
                            <div class="text-center text-muted">
                                <i class="uil-image-broken font-size-48 mb-3"></i>
                                <p>No image available</p>
                            </div>
                        </div>
                    {% endif %}
                </div>

                <!-- Stock Availability Grid (under image) -->
                <div class="stock-grid-container mt-3">
                    <!-- Stock grid populated by JavaScript -->
                </div>

                <!-- Stock Status for Single-Variant Products -->
                <div id="stockStatusContainer" class="stock-status-container mt-3" style="display: none;">
                    <!-- Stock tile populated by JavaScript -->
                </div>
            </div>
        </div>

        <!-- Product Information (Right Column) -->
        <div class="col-lg-6 col-md-12">
            <div class="product-info">
                <!-- School Information (if applicable) -->
                {% if school %}
                <div class="product-school-info">
                    {% if school.logo_url %}
                        <img src="{{ school.logo_url }}" alt="{{ school.name }}" class="school-logo">
                    {% else %}
                        <div class="school-logo d-flex align-items-center justify-content-center bg-tus text-white">
                            <i class="uil-graduation-cap font-size-16"></i>
                        </div>
                    {% endif %}
                    <div>
                        <div class="school-name">{{ school.name }}</div>
                        <small class="text-muted">{{ school.location.name }}</small>
                    </div>
                    <span class="badge badge-tus ms-auto">TUS</span>
                </div>
                {% else %}
                <!-- General Category Display -->
                <div class="product-school-info">
                    <div class="school-logo d-flex align-items-center justify-content-center bg-tus text-white">
                        <i class="uil-tag-alt font-size-16"></i>
                    </div>
                    <div>
                        <div class="school-name">{{ primary_category.name }}</div>
                        <small class="text-muted">General Category</small>
                    </div>
                    <span class="badge badge-tus ms-auto">TUS</span>
                </div>
                {% endif %}

                <!-- Product Title -->
                <h1 class="product-title">{{ product.name }}</h1>

                <!-- Product Pricing -->
                <div class="product-pricing">
                    <div class="price-container">
                        <div class="current-price" id="productPrice">
                            ${{ product.price|floatformat:2 }}
                        </div>
                        {% if product.is_on_sale %}
                            <div class="original-price">
                                ${{ product.regular_price|floatformat:2 }}
                            </div>
                            <span class="discount-badge">
                                {{ product.sale_discount_percentage|floatformat:0 }}% OFF
                            </span>
                        {% endif %}
                    </div>
                </div>

                <!-- Dynamic Product Variations -->
                <div class="variation-section" id="productVariations">
                    <!-- Gender Options -->
                    <div class="gender-options mb-4">
                        <div class="option-label mb-3">
                            <h6 class="mb-2">Gender:</h6>
                        </div>
                        <div class="gender-swatches">
                            <!-- Gender swatches loaded by JavaScript -->
                        </div>
                    </div>

                    <!-- Color Options -->
                    <div class="color-options mb-4">
                        <div class="option-label mb-3">
                            <h6 class="mb-2">Color:</h6>
                        </div>
                        <div class="color-swatches">
                            <!-- Color swatches loaded by JavaScript -->
                        </div>
                    </div>

                    <!-- Size Options -->
                    <div class="size-options mb-4">
                        <div class="option-label mb-3">
                            <h6 class="mb-2">Select Size</h6>
                        </div>
                        <div class="size-buttons">
                            <!-- Size buttons loaded by JavaScript -->
                        </div>
                    </div>
                </div>

                <!-- Product Meta Information -->
                <div class="product-meta">
                    {% if product.sku %}
                    <p class="mb-2">
                        <strong>SKU:</strong>
                        <span class="text-muted">{{ product.sku }}</span>
                    </p>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<!-- Include the Product Variations Library -->
<script src="{% static 'assets/js/product-variations.js' %}?v=20250916-3"></script>

<script>
// Global variables for product variation management
let variationManager;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize product detail functionality
    initializeImageGallery();

    // Initialize dynamic product variations
    initializeProductVariations();
});

// Initialize Product Variations
function initializeProductVariations() {
    const productId = {{ product.id }};  // Note: TUS uses id, not woo_product_id
    const productType = 'tus';

    // Ensure price display shows correct initial value
    const priceElement = document.querySelector('#productPrice, .current-price');
    if (priceElement && priceElement.textContent.trim() === '$') {
        priceElement.textContent = '${{ product.price|floatformat:2 }}';
    }

    // Create variation manager
    variationManager = new ProductVariationManager(productId, productType, {
        enableStockCheck: true,
        enablePriceUpdates: true,
        enableLoadingStates: true,
        debounceDelay: 300
    });

    // Pass stock data from backend to JavaScript
    if (variationManager) {
        variationManager.productData = {
            stock_status: '{{ effective_stock_status|default:product.stock_status }}',
            stock_quantity: {{ stock_quantity|default:0 }},
            manage_stock: {{ manage_stock|yesno:"true,false" }}
        };

        // Set global stock variables
        window.stockQuantity = {{ stock_quantity|default:0 }};
        window.stockStatus = '{{ effective_stock_status|default:product.stock_status }}';
        window.manageStock = {{ manage_stock|yesno:"true,false" }};

        // Set size-only product information
        window.isSizeOnlyProduct = {{ is_size_only_product|yesno:"true,false" }};
        {% if is_size_only_product and size_stock_info %}
        window.sizeStockInfo = [
            {% for size_info in size_stock_info %}
            {
                size: '{{ size_info.size }}',
                stock_quantity: {{ size_info.stock_quantity }},
                is_available: {{ size_info.is_available|yesno:"true,false" }}
            }{% if not forloop.last %},{% endif %}
            {% endfor %}
        ];
        {% endif %}
    }

    // Hide stock status container for products with variations
    setTimeout(function() {
        const stockStatusContainer = document.querySelector('#stockStatusContainer');
        if (stockStatusContainer && variationManager && variationManager.hasVariations) {
            stockStatusContainer.style.display = 'none';
        } else if (stockStatusContainer && variationManager && !variationManager.hasVariations) {
            stockStatusContainer.style.display = 'block';

            // Create and display stock tile for single-variant products
            if (window.stockQuantity > 0 && window.manageStock) {
                const stockTile = document.createElement('div');
                stockTile.className = 'tus-stock-tile available';
                stockTile.innerHTML = `
                    <div class="stock-icon">
                        <i class="mdi mdi-check-circle"></i>
                    </div>
                    <div class="stock-text">
                        <span class="stock-quantity">${window.stockQuantity} Available</span>
                        <span class="stock-label">In Stock</span>
                    </div>
                `;
                stockStatusContainer.innerHTML = '';
                stockStatusContainer.appendChild(stockTile);
            }
        }
    }, 1000);

    // Listen for variation changes
    document.addEventListener('variationChanged', function(event) {
        const detail = event.detail;
        updateProductInfo(detail);
    });
}

// Update product information based on variation selection
function updateProductInfo(variationDetail) {
    // Update product image based on color selection
    if (variationDetail.type === 'color') {
        updateProductImageForColor(variationDetail.value);
    }
}

// Update main product image when color is selected
function updateProductImageForColor(colorValue) {
    console.log('Color selected:', colorValue);
}

// Image Gallery Functions
function initializeImageGallery() {
    const thumbnails = document.querySelectorAll('.thumbnail-item');
    const mainImage = document.getElementById('mainProductImage');

    thumbnails.forEach(thumbnail => {
        thumbnail.addEventListener('click', function() {
            thumbnails.forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            if (mainImage) {
                const newImageSrc = this.getAttribute('data-image');
                mainImage.src = newImageSrc;

                mainImage.style.opacity = '0.5';
                setTimeout(() => {
                    mainImage.style.opacity = '1';
                }, 150);
            }
        });
    });
}

// Error handling
window.addEventListener('error', function(e) {
    console.error('Product detail page error:', e.error);
});
</script>
{% endblock %}
```

### Phase 4: JavaScript Product Variations Library

**File**: `/Users/sas/Repos/SASKITUP/static/assets/js/product-variations.js`

The existing JavaScript library should already support TUS products if it's properly designed. Verify that:

1. **ProductVariationManager** class accepts `productType` parameter ('sas' or 'tus')
2. API endpoint is constructed correctly for TUS: `/schools/api/products/${productId}/variations/`
3. TUS-specific color scheme is applied (use #387ADF instead of #205295)
4. Variation ordering respects TUS order: gender → size → color → others

If modifications are needed, add TUS-specific logic:

```javascript
class ProductVariationManager {
    constructor(productId, productType = 'lotto', options = {}) {
        this.productId = productId;
        this.productType = productType;

        // Set API endpoint based on product type
        if (productType === 'sas') {
            this.apiEndpoint = `/clubs/api/sas-products/${productId}/variations/`;
        } else if (productType === 'tus') {
            this.apiEndpoint = `/schools/api/products/${productId}/variations/`;
        } else {
            this.apiEndpoint = `/clubs/api/products/${productId}/variations/`;
        }

        // TUS-specific brand colors
        this.brandColors = {
            'lotto': '#d32f2f',
            'sas': '#205295',
            'tus': '#387ADF'
        };

        this.primaryColor = this.brandColors[productType] || this.brandColors['lotto'];

        // [Rest of initialization...]
    }

    // [Rest of class implementation...]
}
```

### Phase 5: URL Configuration

**File**: `/Users/sas/Repos/SASKITUP/schools/urls.py`

Verify that the variation API endpoint is properly configured:

```python
from django.urls import path
from . import views

urlpatterns = [
    # ... existing patterns ...

    # Product variation API endpoints
    path('api/products/<int:product_id>/variations/',
         views.tus_product_variations_api,
         name='tus-product-variations-api'),

    path('api/products/<int:product_id>/check-variation/',
         views.tus_check_variation_availability,
         name='tus-check-variation-availability'),

    path('api/products/<int:product_id>/variation-details/',
         views.tus_get_variation_details,
         name='tus-get-variation-details'),
]
```

---

## 4. Testing Plan

### 4.1 Model Testing

**Test File**: Create `/Users/sas/Repos/SASKITUP/clubs/tests/test_tus_variations.py`

```python
from django.test import TestCase
from clubs.models_tus import TUSProduct, TUSProductVariation, TUSSchool, TUSLocation

class TUSProductVariationTests(TestCase):
    def setUp(self):
        # Create test data
        location = TUSLocation.objects.create(
            name="Test Location",
            woo_category_id=1000
        )
        school = TUSSchool.objects.create(
            name="Test School",
            location=location,
            woo_category_id=1001
        )
        self.product = TUSProduct.objects.create(
            name="Test Product",
            woo_product_id=2000,
            type='variable',
            price=50.00
        )

    def test_has_variations(self):
        """Test has_variations property"""
        self.assertFalse(self.product.has_variations)

        # Add variation
        TUSProductVariation.objects.create(
            product=self.product,
            variation_type='size',
            variation_value='M',
            woo_variation_id=3000,
            price=50.00,
            stock_quantity=10
        )

        self.assertTrue(self.product.has_variations)

    def test_available_sizes(self):
        """Test available_sizes property"""
        # Add size variations
        sizes = ['S', 'M', 'L', 'XL']
        for size in sizes:
            TUSProductVariation.objects.create(
                product=self.product,
                variation_type='size',
                variation_value=size,
                woo_variation_id=3000 + sizes.index(size),
                price=50.00,
                stock_quantity=10
            )

        available_sizes = self.product.available_sizes
        self.assertEqual(set(available_sizes), set(sizes))

    def test_get_variation_combination_stock(self):
        """Test get_variation_combination_stock method"""
        # Create variation
        variation = TUSProductVariation.objects.create(
            product=self.product,
            variation_type='size',
            variation_value='M',
            woo_variation_id=3000,
            price=50.00,
            stock_quantity=15
        )

        stock = self.product.get_variation_combination_stock(size='M')
        self.assertEqual(stock, 15)

    def test_variation_data_for_frontend(self):
        """Test get_variation_data_for_frontend method"""
        # Add variations
        TUSProductVariation.objects.create(
            product=self.product,
            variation_type='size',
            variation_value='M',
            woo_variation_id=3000,
            price=50.00,
            stock_quantity=10
        )

        data = self.product.get_variation_data_for_frontend()

        self.assertTrue(data['has_variations'])
        self.assertEqual(data['product_id'], self.product.id)
        self.assertEqual(len(data['variations']), 1)
        self.assertEqual(data['variations'][0]['type'], 'size')
        self.assertEqual(data['variations'][0]['value'], 'M')
```

### 4.2 View Testing

```python
class TUSProductDetailViewTests(TestCase):
    def setUp(self):
        # Create test data
        location = TUSLocation.objects.create(
            name="Test Location",
            woo_category_id=1000
        )
        school = TUSSchool.objects.create(
            name="Test School",
            location=location,
            woo_category_id=1001
        )
        self.product = TUSProduct.objects.create(
            name="Test Product",
            slug="test-product",
            woo_product_id=2000,
            type='variable',
            price=50.00,
            stock_status='instock'
        )

        # Add variations
        for size in ['S', 'M', 'L']:
            TUSProductVariation.objects.create(
                product=self.product,
                variation_type='size',
                variation_value=size,
                woo_variation_id=3000 + ['S', 'M', 'L'].index(size),
                price=50.00,
                stock_quantity=10
            )

    def test_product_detail_view(self):
        """Test product detail view loads correctly"""
        response = self.client.get(f'/schools/retail/product/{self.product.slug}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertIn('variations', response.context)
        self.assertIn('available_sizes', response.context)

    def test_variation_api(self):
        """Test variation API endpoint"""
        response = self.client.get(
            f'/schools/api/products/{self.product.id}/variations/'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['product_id'], self.product.id)
        self.assertIn('grouped_variations', data)
        self.assertIn('size', data['grouped_variations'])
        self.assertEqual(len(data['grouped_variations']['size']), 3)
```

### 4.3 Frontend Testing

**Manual Testing Checklist**:

1. **Product Detail Page Load**:
   - ✅ Product image displays correctly
   - ✅ Product title and pricing display
   - ✅ School/category information displays
   - ✅ Variation sections render (gender, color, size)

2. **Variation Selection**:
   - ✅ Gender/category swatches clickable and update
   - ✅ Color swatches clickable and update
   - ✅ Size buttons clickable and update
   - ✅ Stock status updates based on selection
   - ✅ Price updates if variation has different price
   - ✅ Image updates if variation has unique image

3. **Stock Display**:
   - ✅ Stock grid displays under product image for variable products
   - ✅ Stock tiles show correct quantities
   - ✅ Out-of-stock items are properly indicated
   - ✅ Single-variant products show simple stock status

4. **Responsive Design**:
   - ✅ Layout adapts correctly on mobile (< 768px)
   - ✅ Variation swatches stack properly
   - ✅ Images scale appropriately
   - ✅ Text remains readable

5. **Browser Compatibility**:
   - ✅ Chrome/Edge
   - ✅ Firefox
   - ✅ Safari
   - ✅ Mobile browsers (iOS Safari, Chrome Mobile)

---

## 5. Migration Plan

### Step 1: Database Migrations

No new migrations required. The TUSProduct and TUSProductVariation models already have all necessary fields.

### Step 2: Code Deployment

**Deployment Order**:
1. **Models** (Phase 1): Add methods to TUSProduct and TUSProductVariation
2. **Views** (Phase 2): Update TUSProductDetailView and variation API
3. **Templates** (Phase 3): Replace product detail template
4. **Static Files** (Phase 4): Update/verify JavaScript library
5. **URLs** (Phase 5): Verify URL configuration

**Deployment Command Sequence**:
```bash
# 1. Pull latest code
git pull origin dev

# 2. Collect static files
python manage.py collectstatic --noinput

# 3. Restart application server
sudo systemctl restart gunicorn
# or
sudo service nginx restart
```

### Step 3: Data Verification

After deployment, verify existing TUS products:

```python
# Django shell
from clubs.models_tus import TUSProduct, TUSProductVariation

# Check products with variations
variable_products = TUSProduct.objects.filter(type='variable')
print(f"Variable products: {variable_products.count()}")

# Verify variation data
for product in variable_products[:5]:
    print(f"\nProduct: {product.name}")
    print(f"  Variations: {product.variations.count()}")
    print(f"  Has variations: {product.has_variations}")
    print(f"  Available sizes: {product.available_sizes}")
    print(f"  Available colors: {product.available_colors}")

    # Test frontend data
    frontend_data = product.get_variation_data_for_frontend()
    print(f"  Frontend variations: {len(frontend_data.get('variations', []))}")
```

### Step 4: Smoke Testing

**Post-Deployment Checks**:
1. Visit a TUS product with variations
2. Verify variation swatches render
3. Select variations and verify stock updates
4. Check browser console for JavaScript errors
5. Test on mobile device

---

## 6. Summary

### Current TUS State
- ✅ Models in place (TUSProduct, TUSProductVariation)
- ✅ Basic view structure exists
- ✅ Basic template exists
- ❌ Missing model methods for variation handling
- ❌ Views missing stock and variation logic
- ❌ Template missing dynamic variation display
- ❌ JavaScript integration not configured

### Implementation Required
1. **Phase 1** (Models): ~200 lines of Python code
2. **Phase 2** (Views): ~150 lines of Python code
3. **Phase 3** (Templates): ~400 lines of Django template + CSS
4. **Phase 4** (JavaScript): Verify/update existing library (~50 lines)
5. **Phase 5** (URLs): Verify configuration (~10 lines)

**Total Estimated Effort**: 4-6 hours for experienced developer

### Key Differences SAS vs TUS
- **Category Structure**: SAS uses Club → Product, TUS uses School/General Category → Product
- **Variation Order**: SAS (age_group → size → color), TUS (gender → size → color)
- **Brand Colors**: SAS (#205295 blue), TUS (#387ADF lighter blue)
- **Product ID**: SAS uses `woo_product_id`, TUS uses `id` for API calls

### Success Criteria
- ✅ TUS products display variations in swatches/buttons
- ✅ Stock status updates based on variation selection
- ✅ Images update based on color selection (if available)
- ✅ Price updates based on variation (if applicable)
- ✅ Responsive design works on all devices
- ✅ No JavaScript console errors
- ✅ API endpoints return correct data structure
- ✅ All tests pass

---

## Appendix A: Code Locations Reference

### SAS Implementation Files
```
Models:          /Users/sas/Repos/SASKITUP/clubs/models_sas.py (Lines 389-1209)
Views:           /Users/sas/Repos/SASKITUP/clubs/views.py (Lines 1749-2816)
Template:        /Users/sas/Repos/SASKITUP/template/clubs/sas_product_detail.html
JavaScript:      /Users/sas/Repos/SASKITUP/static/assets/js/product-variations.js
URLs:            /Users/sas/Repos/SASKITUP/clubs/urls.py
```

### TUS Implementation Files (To Update)
```
Models:          /Users/sas/Repos/SASKITUP/clubs/models_tus.py (Lines 449-699+)
Views:           /Users/sas/Repos/SASKITUP/schools/views.py (Lines 596-930)
Template:        /Users/sas/Repos/SASKITUP/schools/templates/schools/retail/product_detail.html
JavaScript:      /Users/sas/Repos/SASKITUP/static/assets/js/product-variations.js (shared)
URLs:            /Users/sas/Repos/SASKITUP/schools/urls.py
```

### Test Files (To Create)
```
Model Tests:     /Users/sas/Repos/SASKITUP/clubs/tests/test_tus_variations.py
View Tests:      /Users/sas/Repos/SASKITUP/schools/tests/test_tus_views.py
```

---

**End of Implementation Plan**

*Generated: 2025-01-06*
*Based on: SAS product variations implementation analysis*
*Target: TUS schools product variations implementation*
