# SAS Complete Sync Logic Implementation

**Document Version:** 1.0
**Created:** September 17, 2025
**Last Updated:** September 17, 2025
**Purpose:** Comprehensive sync logic for SAS sports clubs, products, variations, and categories

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Data Architecture](#data-architecture)
3. [Sync Command Implementation](#sync-command-implementation)
4. [Product Variation Sync Logic](#product-variation-sync-logic)
5. [Category Management](#category-management)
6. [Error Handling & Recovery](#error-handling--recovery)
7. [Performance Optimization](#performance-optimization)
8. [Monitoring & Logging](#monitoring--logging)
9. [API Integration](#api-integration)
10. [Implementation Examples](#implementation-examples)

---

## System Overview

### Architecture Hierarchy

```
WooCommerce SAS Store
├── Sports (Root Categories)
│   ├── Basketball (ID: 46)
│   ├── Rugby (ID: 60)
│   ├── Athletics (ID: 17)
│   └── ...
├── Clubs (Sub-Categories)
│   ├── Auckland Blues
│   ├── Canterbury Crusaders
│   └── ...
└── Products (Individual Items)
    ├── Team Jerseys
    ├── Training Gear
    └── ...
```

### Core Models

```python
# SAS Models Hierarchy
SASSport (1:N) → SASClub (1:N) → SASProduct (1:N) → SASProductVariation
```

### Sync Process Flow

1. **Sports Sync** - Root categories with filtering
2. **Clubs Sync** - Subcategories with school exclusion
3. **Products Sync** - Individual products with metadata
4. **Variations Sync** - Multi-dimensional product options
5. **Data Validation** - Integrity checks and cleanup

---

## Data Architecture

### SASSport Model

```python
class SASSport(models.Model):
    # Core identification
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    woo_category_id = models.PositiveIntegerField(unique=True)

    # Metadata
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)

    # Tracking & Status
    is_active = models.BooleanField(default=True)
    club_count = models.PositiveIntegerField(default=0)
    product_count = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    def update_counts(self):
        """Update club_count and product_count from related objects"""
        active_clubs = self.clubs.filter(is_active=True)
        self.club_count = active_clubs.count()
        self.product_count = SASProduct.objects.filter(
            club__in=active_clubs,
            stock_status__in=['instock', 'onbackorder']
        ).count()
        self.save(update_fields=['club_count', 'product_count'])
```

### SASClub Model

```python
class SASClub(models.Model):
    # Relationships
    sport = models.ForeignKey(SASSport, on_delete=models.CASCADE, related_name='clubs')

    # Core identification
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    woo_category_id = models.PositiveIntegerField(unique=True)

    # Contact & Location
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    # Classification
    is_active = models.BooleanField(default=True)
    is_school = models.BooleanField(default=False)
    is_generic_category = models.BooleanField(default=False)

    # Metrics
    product_count = models.PositiveIntegerField(default=0)

    # School Detection Logic
    def _detect_school(self):
        school_indicators = [
            'school', 'high', 'primary', 'academy', 'college',
            'university', 'education', 'learners', 'students'
        ]
        name_lower = self.name.lower()
        return any(indicator in name_lower for indicator in school_indicators)

    # Generic Category Detection
    def _detect_generic_category(self):
        generic_patterns = [
            r'^bags?$', r'^balls?$', r'^bottles?$', r'^caps?$',
            r'^equipment$', r'^accessories?$', r'^clothing$',
            r'^basketball$', r'^rugby$', r'^athletics$',
            r'^mens?$', r'^womens?$', r'^kids?$', r'^adults?$',
            r'.*\bpacks?$', r'.*\bsets?$', r'.*\bbundles?$'
        ]
        name_lower = self.name.lower()
        return any(re.match(pattern, name_lower) for pattern in generic_patterns)
```

### SASProduct Model

```python
class SASProduct(models.Model):
    # Relationships
    club = models.ForeignKey(SASClub, on_delete=models.CASCADE, related_name='products')

    # Core identification
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    woo_product_id = models.PositiveIntegerField(unique=True)

    # Product details
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='simple')
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    sku = models.CharField(max_length=100, blank=True)

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Content
    description = models.TextField(blank=True)
    short_description = models.TextField(blank=True)

    # Media
    image_url = models.URLField(blank=True)
    gallery_urls = models.JSONField(default=list, blank=True)

    # WooCommerce metadata
    tags = models.JSONField(default=list, blank=True)
    attributes = models.JSONField(default=list, blank=True)
    categories = models.JSONField(default=list, blank=True)

    # Stock management
    manage_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(null=True, blank=True)

    # Variation parsing for frontend
    def _parse_variation_attributes(self):
        """Parse variation attributes from WooCommerce data"""
        parsed_attributes = {}

        # Check actual SAS variations first
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
                    attr_type = self._normalize_attribute_type(attr_name)
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
```

### SASProductVariation Model

```python
class SASProductVariation(models.Model):
    # Relationships
    product = models.ForeignKey(SASProduct, on_delete=models.CASCADE, related_name='variations')

    # Core variation data
    variation_type = models.CharField(max_length=50, choices=VARIATION_TYPE_CHOICES)
    variation_value = models.CharField(max_length=255)
    woo_variation_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    # Pricing (usually no modifiers for SAS)
    price_modifier = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Stock
    stock_quantity = models.PositiveIntegerField(default=0)
    sku_suffix = models.CharField(max_length=50, blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True)

    # Additional data
    attributes = models.JSONField(blank=True, null=True)
    image_url = models.URLField(blank=True)

    @property
    def final_price(self):
        """Calculate final price including modifier"""
        base_price = self.product.effective_price or 0
        return base_price + self.price_modifier

    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.is_active and self.stock_quantity > 0
```

---

## Sync Command Implementation

### Management Command: sync_sas_clubs.py

```python
class Command(BaseCommand):
    help = 'Synchronize SAS sports clubs data from WooCommerce API'

    # Configuration
    SCHOOL_KEYWORDS = [
        'school', 'high school', 'primary school', 'college', 'university',
        'academy', 'institute', 'education', 'learning', 'student'
    ]
    SCHOOLS_CATEGORY_ID = 98

    def add_arguments(self, parser):
        """Command line arguments"""
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--sport-filter', type=str)
        parser.add_argument('--force-update', action='store_true')
        parser.add_argument('--limit-clubs', type=int)
        parser.add_argument('--skip-schools', action='store_true', default=True)
        parser.add_argument('--sync-variations', action='store_true', default=True)
        parser.add_argument('--verbose', action='store_true')

    def handle(self, *args, **options):
        """Main command handler"""
        try:
            # Initialize WooCommerce service
            self.woo_service = WooCommerceService(store_type='SAS')

            # Test connection
            if not self.woo_service.test_connection():
                raise CommandError('Failed to connect to SAS WooCommerce API')

            # Start synchronization
            self._sync_sas_data(
                dry_run=options['dry_run'],
                sport_filter=options.get('sport_filter'),
                force_update=options['force_update'],
                limit_clubs=options.get('limit_clubs'),
                skip_schools=options['skip_schools'],
                sync_variations=options['sync_variations']
            )

        except Exception as e:
            logger.error(f"SAS sync failed: {str(e)}", exc_info=True)
            raise CommandError(f"SAS sync failed: {str(e)}")

    def _sync_sas_data(self, dry_run=False, sport_filter=None, force_update=False,
                       limit_clubs=None, skip_schools=True, sync_variations=True):
        """Main synchronization logic"""

        # Step 1: Fetch and process sport categories
        sport_categories = self._fetch_sport_categories(sport_filter, skip_schools)

        if not sport_categories:
            self.stdout.write('No sport categories found to process')
            return

        # Step 2: Process each sport
        for sport_data in sport_categories:
            try:
                with transaction.atomic():
                    sport_obj = self._process_sport(
                        sport_data, dry_run, force_update,
                        limit_clubs, skip_schools, sync_variations
                    )
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Error processing sport {sport_data.get('name')}: {str(e)}")
                continue

    def _process_sport(self, sport_data, dry_run, force_update,
                       limit_clubs, skip_schools, sync_variations):
        """Process a single sport category"""
        sport_name = sport_data['name']
        sport_id = sport_data['id']

        # Create or update SASSport
        sport_obj = None
        if not dry_run:
            sport_obj, sport_created = self._process_sas_sport(sport_data, force_update)

        # Fetch and process clubs
        clubs = self._fetch_clubs_for_sport(sport_id, skip_schools)

        if limit_clubs:
            clubs = clubs[:limit_clubs]

        # Process each club
        for club_data in clubs:
            try:
                club_obj = self._process_club(
                    club_data, sport_obj, dry_run, force_update, sync_variations
                )
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Error processing club {club_data.get('name')}: {str(e)}")
                continue

        return sport_obj

    def _process_club(self, club_data, sport_obj, dry_run, force_update, sync_variations):
        """Process a single club with products and variations"""
        club_name = club_data['name']
        club_id = club_data['id']

        # Create or update SASClub
        club_obj = None
        if not dry_run:
            club_obj, club_created = self._process_sas_club(club_data, sport_obj, force_update)

        # Fetch and process products
        products = self._fetch_products_for_club(club_id)

        for product_data in products:
            try:
                product_obj = self._process_product(
                    product_data, club_obj, dry_run, force_update, sync_variations
                )
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Error processing product {product_data.get('name')}: {str(e)}")
                continue

        return club_obj

    def _process_product(self, product_data, club_obj, dry_run, force_update, sync_variations):
        """Process a single product with variations"""
        product_name = product_data['name']
        product_id = product_data['id']

        if not dry_run:
            product_obj, product_created = self._process_sas_product(
                product_data, club_obj, force_update
            )

            # Sync variations if enabled and product supports them
            if sync_variations and product_data.get('type') == 'variable':
                self._sync_product_variations(product_obj, product_id, force_update)

            return product_obj

        return None
```

---

## Product Variation Sync Logic

### Variation Data Fetching

```python
def _sync_product_variations(self, product_obj, woo_product_id, force_update=False):
    """Sync product variations from WooCommerce"""
    try:
        # Fetch variations from WooCommerce
        variations_data = self.woo_service.get_product_variations(woo_product_id)

        if not variations_data:
            logger.info(f"No variations found for product {product_obj.name}")
            return

        logger.info(f"Processing {len(variations_data)} variations for {product_obj.name}")

        # Track processed variation IDs for cleanup
        processed_variation_ids = set()

        for variation_data in variations_data:
            try:
                variation_obj = self._process_single_variation(
                    product_obj, variation_data, force_update
                )
                if variation_obj:
                    processed_variation_ids.add(variation_obj.id)

            except Exception as e:
                logger.error(f"Error processing variation {variation_data.get('id')}: {str(e)}")
                self.stats['variation_errors'] += 1
                continue

        # Clean up variations that no longer exist in WooCommerce
        if not force_update:  # Only cleanup on normal sync, not force updates
            self._cleanup_obsolete_variations(product_obj, processed_variation_ids)

        # Update product stock status based on variations
        product_obj.update_stock_status_from_variations()

    except Exception as e:
        logger.error(f"Failed to sync variations for product {product_obj.name}: {str(e)}")
        raise

def _process_single_variation(self, product_obj, variation_data, force_update=False):
    """Process a single product variation"""
    woo_variation_id = variation_data['id']

    # Extract variation attributes
    attributes = variation_data.get('attributes', [])
    variation_type, variation_value = self._extract_variation_info(attributes)

    if not variation_type or not variation_value:
        logger.warning(f"Could not extract variation info from: {attributes}")
        return None

    # Check for existing variation
    existing_variation = SASProductVariation.objects.filter(
        woo_variation_id=woo_variation_id
    ).first()

    # Prepare variation data
    variation_data_obj = {
        'product': product_obj,
        'variation_type': variation_type,
        'variation_value': variation_value,
        'woo_variation_id': woo_variation_id,
        'stock_quantity': self._extract_stock_quantity(variation_data),
        'price_modifier': self._extract_price_modifier(variation_data, product_obj),
        'attributes': self._extract_variation_attributes(variation_data),
        'image_url': self._extract_variation_image(variation_data),
        'is_active': variation_data.get('status', 'publish') == 'publish'
    }

    # Create or update variation
    if existing_variation:
        if force_update or self._variation_needs_update(existing_variation, variation_data_obj):
            for key, value in variation_data_obj.items():
                if key != 'product':  # Don't change product relationship
                    setattr(existing_variation, key, value)
            existing_variation.save()
            self.stats['variations_updated'] += 1
            return existing_variation
        else:
            return existing_variation
    else:
        # Check for duplicate by product + type + value
        duplicate = SASProductVariation.objects.filter(
            product=product_obj,
            variation_type=variation_type,
            variation_value=variation_value
        ).first()

        if duplicate:
            # Update the WooCommerce ID if it's missing
            if not duplicate.woo_variation_id:
                duplicate.woo_variation_id = woo_variation_id
                duplicate.save()
            logger.warning(f"Duplicate variation found: {variation_type}={variation_value}")
            return duplicate

        # Create new variation
        variation_obj = SASProductVariation.objects.create(**variation_data_obj)
        self.stats['variations_created'] += 1
        return variation_obj

def _extract_variation_info(self, attributes):
    """Extract variation type and value from WooCommerce attributes"""
    if not attributes:
        return None, None

    # Priority order for variation types
    type_priority = ['size', 'color', 'colour', 'material', 'style', 'gender', 'age_group']

    # Find the first attribute that matches our priority
    for attr in attributes:
        if not isinstance(attr, dict):
            continue

        attr_name = attr.get('name', '').lower()
        attr_option = attr.get('option', '')

        if not attr_option:
            continue

        # Normalize attribute name
        variation_type = self._normalize_variation_type(attr_name)

        if variation_type in type_priority:
            return variation_type, str(attr_option)

    # Fallback: use first attribute
    if attributes:
        first_attr = attributes[0]
        if isinstance(first_attr, dict):
            attr_name = first_attr.get('name', 'other')
            attr_option = first_attr.get('option', '')
            if attr_option:
                return self._normalize_variation_type(attr_name), str(attr_option)

    return None, None

def _normalize_variation_type(self, attr_name):
    """Normalize attribute names to standard variation types"""
    attr_name = attr_name.lower().strip()

    # Size variations
    if any(term in attr_name for term in ['size', 'sizes']):
        return 'size'

    # Color variations
    if any(term in attr_name for term in ['color', 'colour', 'colors', 'colours']):
        return 'color'

    # Material variations
    if any(term in attr_name for term in ['material', 'fabric', 'textile']):
        return 'material'

    # Style variations
    if any(term in attr_name for term in ['style', 'design', 'type']):
        return 'style'

    # Gender variations
    if any(term in attr_name for term in ['gender', 'sex']):
        return 'gender'

    # Age group variations
    if any(term in attr_name for term in ['age', 'group', 'category']):
        return 'age_group'

    # Default: return normalized name
    return attr_name.replace(' ', '_')

def _extract_stock_quantity(self, variation_data):
    """Extract stock quantity from variation data"""
    # Try multiple fields for stock quantity
    stock_quantity = variation_data.get('stock_quantity')

    if stock_quantity is not None:
        try:
            return max(0, int(stock_quantity))
        except (ValueError, TypeError):
            pass

    # Fallback based on stock status
    stock_status = variation_data.get('stock_status', 'outofstock')
    if stock_status == 'instock':
        return 1  # Default to 1 if in stock but no quantity specified
    elif stock_status == 'onbackorder':
        return 0  # Allow backorders but show as 0 stock
    else:
        return 0

def _extract_price_modifier(self, variation_data, product_obj):
    """Extract price modifier from variation data"""
    try:
        variation_price = Decimal(str(variation_data.get('price', '0') or '0'))
        base_price = product_obj.effective_price or Decimal('0')

        # Calculate modifier
        if base_price > 0:
            return variation_price - base_price
        else:
            return Decimal('0')

    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')

def _cleanup_obsolete_variations(self, product_obj, current_variation_ids):
    """Remove variations that no longer exist in WooCommerce"""
    obsolete_variations = SASProductVariation.objects.filter(
        product=product_obj
    ).exclude(id__in=current_variation_ids)

    count = obsolete_variations.count()
    if count > 0:
        obsolete_variations.delete()
        logger.info(f"Removed {count} obsolete variations for {product_obj.name}")
        self.stats['variations_deleted'] += count
```

### Multi-Dimensional Variation Support

```python
def get_variation_data_for_frontend(self):
    """Get structured variation data for frontend JavaScript"""
    if not self.has_variations:
        return {}

    variations_data = {
        'product_id': self.id,
        'has_variations': True,
        'variation_types': [],
        'variations': [],
        'grouped_variations': {},
        'parsed_attributes': self.parsed_variation_attributes,
        'total_stock': self.total_stock,
        'color_size_matrix': self.get_all_color_size_combinations()
    }

    # Group variations by type
    if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
        variation_types = set()
        grouped_vars = {}

        for variation in self.variations.filter(is_active=True):
            var_type = variation.variation_type
            variation_types.add(var_type)

            if var_type not in grouped_vars:
                grouped_vars[var_type] = []

            is_in_stock = variation.stock_quantity > 0
            stock_status = 'instock' if is_in_stock else 'outofstock'
            if variation.stock_quantity == 0 and variation.is_active:
                stock_status = 'onbackorder'

            var_data = {
                'id': f"{self.id}_{var_type}_{variation.variation_value}",
                'type': var_type,
                'value': variation.variation_value,
                'stock': variation.stock_quantity,
                'stock_status': stock_status,
                'is_available': is_in_stock or stock_status == 'onbackorder',
                'price_modifier': float(variation.price_modifier),
                'final_price': float(variation.final_price),
                'image': variation.effective_image_url,
                'sku_suffix': variation.sku_suffix,
                'attributes': variation.attributes or {}
            }

            grouped_vars[var_type].append(var_data)
            variations_data['variations'].append(var_data)

        variations_data['variation_types'] = sorted(list(variation_types))
        variations_data['grouped_variations'] = grouped_vars

    return variations_data

def get_available_variations_for_selection(self, **selection):
    """Get available variation options based on current selection"""
    result = {}

    # Filter variations based on current selection
    base_variations = self.variations.filter(is_active=True)

    # Apply selection filters
    for var_type, var_value in selection.items():
        if var_value:
            base_variations = base_variations.filter(
                variation_type=var_type,
                variation_value=var_value
            )

    # Get available options for each unselected variation type
    variation_types = ['size', 'color', 'material', 'style', 'gender', 'age_group']

    for var_type in variation_types:
        if var_type in selection and selection[var_type]:
            continue  # Skip already selected types

        # Get available options for this type
        type_variations = base_variations.filter(variation_type=var_type).distinct()

        options = []
        for variation in type_variations:
            options.append({
                'value': variation.variation_value,
                'stock': variation.stock_quantity,
                'available': variation.stock_quantity > 0,
                'variation_id': variation.id,
                'price_modifier': float(variation.price_modifier),
                'image': variation.effective_image_url
            })

        if options:
            # Sort options naturally
            options.sort(key=lambda x: self._get_sort_order(var_type, x['value']))
            result[var_type] = options

    return result

def _get_sort_order(self, var_type, value):
    """Get sort order for variation values"""
    if var_type == 'size':
        return self._get_size_sort_order(value)
    elif var_type == 'color':
        return self._get_color_sort_order(value)
    else:
        return value.lower()

def _get_size_sort_order(self, size):
    """Sort sizes in logical order"""
    size_order = [
        '4k', '6k', '8k', '10k', '12k', '14k', '16k',  # Kids sizes
        'xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl'  # Adult sizes
    ]
    try:
        return size_order.index(size.lower())
    except ValueError:
        return 999  # Unknown sizes at the end
```

---

## Category Management

### Category Processing Logic

```python
def _process_sas_sport(self, sport_data, force_update):
    """Create or update SASSport model"""
    woo_category_id = sport_data['id']

    # Check if sport already exists
    existing_sport = SASSport.objects.filter(woo_category_id=woo_category_id).first()

    # Prepare sport data
    sport_data_obj = {
        'name': sport_data['name'],
        'woo_category_id': woo_category_id,
        'slug': sport_data.get('slug', slugify(sport_data['name'])),
        'description': sport_data.get('description', ''),
        'product_count': sport_data.get('count', 0),
        'is_active': True,
        'last_sync_at': timezone.now(),
    }

    # Store sport image URL if available
    if sport_data.get('image') and sport_data['image'].get('src'):
        try:
            image_url = self._process_image_url(sport_data['image']['src'])
            if image_url:
                sport_data_obj['image_url'] = image_url
        except Exception as e:
            logger.warning(f"Failed to process sport image: {str(e)}")

    # Create or update
    if existing_sport:
        if force_update or self._sport_needs_update(existing_sport, sport_data_obj):
            for key, value in sport_data_obj.items():
                if key != 'image_url' or value:  # Only update image_url if we have a new one
                    setattr(existing_sport, key, value)
            existing_sport.save()
            return existing_sport, False
        else:
            return existing_sport, False
    else:
        return SASSport.objects.create(**sport_data_obj), True

def _process_sas_club(self, club_data, sport_obj, force_update):
    """Create or update SASClub model with enhanced filtering"""
    woo_category_id = club_data['id']

    # Check if club already exists
    existing_club = SASClub.objects.filter(woo_category_id=woo_category_id).first()

    # Prepare club data
    club_data_obj = {
        'sport': sport_obj,
        'name': club_data['name'],
        'woo_category_id': woo_category_id,
        'slug': club_data.get('slug', slugify(club_data['name'])),
        'description': club_data.get('description', ''),
        'product_count': club_data.get('count', 0),
        'is_active': True,
        'last_sync_at': timezone.now(),
    }

    # Store club image URL if available
    if club_data.get('image') and club_data['image'].get('src'):
        try:
            image_url = self._process_image_url(club_data['image']['src'])
            if image_url:
                club_data_obj['image_url'] = image_url
        except Exception as e:
            logger.warning(f"Failed to process club image: {str(e)}")

    # Auto-detect classification
    temp_club = SASClub(**club_data_obj)
    temp_club._skip_school_detection = False
    temp_club._skip_generic_detection = False

    club_data_obj['is_school'] = temp_club._detect_school()
    club_data_obj['is_generic_category'] = temp_club._detect_generic_category()

    # Create or update
    if existing_club:
        if force_update or self._club_needs_update(existing_club, club_data_obj):
            for key, value in club_data_obj.items():
                if key != 'image_url' or value:
                    setattr(existing_club, key, value)
            existing_club._skip_school_detection = True
            existing_club._skip_generic_detection = True
            existing_club.save()
            return existing_club, False
        else:
            return existing_club, False
    else:
        club_obj = SASClub(**club_data_obj)
        club_obj._skip_school_detection = True
        club_obj._skip_generic_detection = True
        club_obj.save()
        return club_obj, True

def _fetch_clubs_for_sport(self, sport_id, skip_schools):
    """Fetch club subcategories with filtering"""
    try:
        clubs = self.woo_service.get_categories(parent_id=sport_id, per_page=100)

        if not clubs:
            return []

        filtered_clubs = []

        for club in clubs:
            club_name = club['name']

            # Skip school-related clubs if filtering enabled
            if skip_schools and self._is_school_related(club_name):
                if self.options['verbose']:
                    self.stdout.write(f'    ⏭️  Skipping school: {club_name}')
                self.stats['clubs_skipped'] += 1
                continue

            # Skip generic categories
            if self._is_generic_category(club_name):
                if self.options['verbose']:
                    self.stdout.write(f'    ⏭️  Skipping generic category: {club_name}')
                self.stats['clubs_skipped'] += 1
                continue

            # Only include clubs with products
            if club.get('count', 0) > 0:
                filtered_clubs.append(club)

        return filtered_clubs

    except Exception as e:
        logger.error(f"Failed to fetch clubs for sport {sport_id}: {str(e)}")
        return []

def _is_school_related(self, name):
    """Check if a category/club name is school-related"""
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in self.SCHOOL_KEYWORDS)

def _is_generic_category(self, name):
    """Check if a category name represents a generic product category"""
    generic_patterns = [
        r'^bags?$', r'^balls?$', r'^bottles?$', r'^caps?$', r'^clothing$',
        r'^equipment$', r'^accessories?$', r'^beanie$', r'^bucket\s*hats?$',
        r'^face\s*masks?$', r'^clearance$', r'^sport\s*accessories?$',
        r'^tag\s*sets?$', r'^socks?$', r'^shorts?$', r'^shirts?$',
        r'^bibs?$', r'^numbers?$', r'^tags?$', r'^uniforms?$',
        r'^basketball$', r'^cricket$', r'^rugby$', r'^football$',
        r'^athletics$', r'^touch$', r'^netball$', r'^hockey$',
        r'^mens?$', r'^womens?$', r'^kids?$', r'^adults?$',
        r'.*\bpacks?$', r'.*\bsets?$', r'.*\bbundles?$'
    ]

    name_lower = name.lower()
    return any(re.match(pattern, name_lower) for pattern in generic_patterns)
```

---

## Error Handling & Recovery

### Comprehensive Error Management

```python
class SyncErrorHandler:
    """Centralized error handling for sync operations"""

    def __init__(self, command_instance):
        self.command = command_instance
        self.error_log = []

    def handle_api_error(self, operation, entity_id, error):
        """Handle API-related errors"""
        error_info = {
            'operation': operation,
            'entity_id': entity_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': timezone.now(),
            'recoverable': self._is_recoverable_error(error)
        }

        self.error_log.append(error_info)

        # Log based on severity
        if error_info['recoverable']:
            logger.warning(f"Recoverable error in {operation} for {entity_id}: {error}")
        else:
            logger.error(f"Fatal error in {operation} for {entity_id}: {error}")

        return error_info['recoverable']

    def handle_data_error(self, operation, entity_data, error):
        """Handle data processing errors"""
        entity_name = entity_data.get('name', 'Unknown')
        entity_id = entity_data.get('id', 'Unknown')

        error_info = {
            'operation': operation,
            'entity_name': entity_name,
            'entity_id': entity_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': timezone.now(),
            'data_sample': str(entity_data)[:200]  # Sample of problematic data
        }

        self.error_log.append(error_info)
        logger.error(f"Data error in {operation} for {entity_name}: {error}")

        return False  # Data errors are typically not recoverable

    def _is_recoverable_error(self, error):
        """Determine if an error is recoverable"""
        recoverable_errors = [
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError  # Only if status code is 5xx
        ]

        if isinstance(error, requests.exceptions.HTTPError):
            # 5xx errors are typically recoverable, 4xx are not
            return 500 <= error.response.status_code < 600

        return any(isinstance(error, err_type) for err_type in recoverable_errors)

    def generate_error_report(self):
        """Generate a comprehensive error report"""
        if not self.error_log:
            return "No errors occurred during sync."

        report = ["SYNC ERROR REPORT", "=" * 50]

        # Summary
        total_errors = len(self.error_log)
        recoverable = sum(1 for e in self.error_log if e.get('recoverable', False))
        fatal = total_errors - recoverable

        report.extend([
            f"Total Errors: {total_errors}",
            f"Recoverable: {recoverable}",
            f"Fatal: {fatal}",
            ""
        ])

        # Group by error type
        error_groups = {}
        for error in self.error_log:
            err_type = error['error_type']
            if err_type not in error_groups:
                error_groups[err_type] = []
            error_groups[err_type].append(error)

        for err_type, errors in error_groups.items():
            report.extend([
                f"{err_type} ({len(errors)} occurrences):",
                "-" * 40
            ])

            for error in errors[:5]:  # Show first 5 of each type
                report.append(f"  • {error['operation']} - {error['error_message'][:100]}")

            if len(errors) > 5:
                report.append(f"  ... and {len(errors) - 5} more")

            report.append("")

        return "\n".join(report)

# Enhanced sync methods with error handling
def _process_sport_with_recovery(self, sport_data, dry_run, force_update,
                                limit_clubs, skip_schools, sync_variations):
    """Process sport with comprehensive error handling"""
    error_handler = SyncErrorHandler(self)
    sport_name = sport_data.get('name', 'Unknown')

    try:
        # Process sport
        sport_obj = self._process_sport(
            sport_data, dry_run, force_update,
            limit_clubs, skip_schools, sync_variations
        )

        return sport_obj

    except requests.exceptions.RequestException as e:
        if error_handler.handle_api_error('process_sport', sport_name, e):
            # Retry with exponential backoff
            time.sleep(2)
            return self._process_sport_with_recovery(
                sport_data, dry_run, force_update,
                limit_clubs, skip_schools, sync_variations
            )
        else:
            raise

    except Exception as e:
        error_handler.handle_data_error('process_sport', sport_data, e)
        raise

def _sync_with_transaction_rollback(self, sync_function, *args, **kwargs):
    """Execute sync function with transaction rollback on error"""
    try:
        with transaction.atomic():
            return sync_function(*args, **kwargs)
    except Exception as e:
        logger.error(f"Transaction rolled back due to error: {str(e)}")
        # Log the state for manual recovery
        self._log_rollback_state(sync_function.__name__, args, kwargs)
        raise

def _log_rollback_state(self, function_name, args, kwargs):
    """Log state information for manual recovery"""
    rollback_info = {
        'function': function_name,
        'timestamp': timezone.now().isoformat(),
        'args_count': len(args),
        'kwargs_keys': list(kwargs.keys()),
        'stats_snapshot': dict(self.stats)
    }

    logger.error(f"ROLLBACK STATE: {json.dumps(rollback_info, indent=2)}")
```

### Data Validation & Integrity

```python
class DataValidator:
    """Validate sync data integrity"""

    @staticmethod
    def validate_sport_data(sport_data):
        """Validate sport data before processing"""
        required_fields = ['id', 'name']
        errors = []

        for field in required_fields:
            if not sport_data.get(field):
                errors.append(f"Missing required field: {field}")

        # Validate data types
        if sport_data.get('id') and not isinstance(sport_data['id'], int):
            errors.append("Sport ID must be an integer")

        if sport_data.get('count') and not isinstance(sport_data['count'], int):
            errors.append("Sport count must be an integer")

        return errors

    @staticmethod
    def validate_club_data(club_data):
        """Validate club data before processing"""
        required_fields = ['id', 'name', 'parent']
        errors = []

        for field in required_fields:
            if not club_data.get(field):
                errors.append(f"Missing required field: {field}")

        # Validate parent relationship
        if club_data.get('parent') == 0:
            errors.append("Club cannot have parent ID of 0 (should be a sport category)")

        return errors

    @staticmethod
    def validate_product_data(product_data):
        """Validate product data before processing"""
        required_fields = ['id', 'name', 'categories']
        errors = []

        for field in required_fields:
            if not product_data.get(field):
                errors.append(f"Missing required field: {field}")

        # Validate categories
        categories = product_data.get('categories', [])
        if not categories:
            errors.append("Product must belong to at least one category")

        # Validate price data
        price = product_data.get('price')
        if price is not None:
            try:
                float(price)
            except (ValueError, TypeError):
                errors.append(f"Invalid price format: {price}")

        return errors

    @staticmethod
    def validate_variation_data(variation_data):
        """Validate variation data before processing"""
        required_fields = ['id', 'attributes']
        errors = []

        for field in required_fields:
            if not variation_data.get(field):
                errors.append(f"Missing required field: {field}")

        # Validate attributes
        attributes = variation_data.get('attributes', [])
        if not attributes:
            errors.append("Variation must have at least one attribute")

        # Validate stock quantity
        stock_qty = variation_data.get('stock_quantity')
        if stock_qty is not None:
            try:
                int(stock_qty)
            except (ValueError, TypeError):
                errors.append(f"Invalid stock quantity: {stock_qty}")

        return errors

# Integration in sync methods
def _validate_and_process_sport(self, sport_data, *args, **kwargs):
    """Validate sport data before processing"""
    validation_errors = DataValidator.validate_sport_data(sport_data)

    if validation_errors:
        error_msg = f"Sport validation failed: {'; '.join(validation_errors)}"
        logger.error(error_msg)
        self.stats['validation_errors'] += 1
        raise ValueError(error_msg)

    return self._process_sport(sport_data, *args, **kwargs)
```

---

## Performance Optimization

### Bulk Operations & Caching

```python
class SyncOptimizer:
    """Performance optimization for sync operations"""

    def __init__(self):
        self.batch_size = 100
        self.cache = {}
        self.bulk_create_cache = {
            'sports': [],
            'clubs': [],
            'products': [],
            'variations': []
        }

    def bulk_create_sports(self, sports_data):
        """Bulk create sports for better performance"""
        sports_to_create = []

        for sport_data in sports_data:
            # Check cache first
            cache_key = f"sport_{sport_data['id']}"
            if cache_key in self.cache:
                continue

            # Check database
            if SASSport.objects.filter(woo_category_id=sport_data['id']).exists():
                continue

            # Prepare for bulk create
            sport_obj = SASSport(
                name=sport_data['name'],
                woo_category_id=sport_data['id'],
                slug=slugify(sport_data['name']),
                description=sport_data.get('description', ''),
                product_count=sport_data.get('count', 0),
                is_active=True,
                image_url=self._extract_image_url(sport_data)
            )

            sports_to_create.append(sport_obj)

            # Batch when reaching batch_size
            if len(sports_to_create) >= self.batch_size:
                self._execute_bulk_create('sports', sports_to_create)
                sports_to_create = []

        # Create remaining items
        if sports_to_create:
            self._execute_bulk_create('sports', sports_to_create)

    def _execute_bulk_create(self, model_name, objects):
        """Execute bulk create operation"""
        if not objects:
            return

        try:
            if model_name == 'sports':
                SASSport.objects.bulk_create(objects, ignore_conflicts=True)
            elif model_name == 'clubs':
                SASClub.objects.bulk_create(objects, ignore_conflicts=True)
            elif model_name == 'products':
                SASProduct.objects.bulk_create(objects, ignore_conflicts=True)
            elif model_name == 'variations':
                SASProductVariation.objects.bulk_create(objects, ignore_conflicts=True)

            logger.info(f"Bulk created {len(objects)} {model_name}")

        except Exception as e:
            logger.error(f"Bulk create failed for {model_name}: {str(e)}")
            # Fallback to individual creates
            self._fallback_individual_create(model_name, objects)

    def _fallback_individual_create(self, model_name, objects):
        """Fallback to individual object creation"""
        logger.info(f"Falling back to individual creation for {len(objects)} {model_name}")

        for obj in objects:
            try:
                obj.save()
            except Exception as e:
                logger.error(f"Failed to create individual {model_name}: {str(e)}")

# Query optimization
def _optimize_database_queries(self):
    """Optimize database queries for sync operations"""

    # Prefetch related objects to reduce query count
    sports_with_clubs = SASSport.objects.prefetch_related(
        Prefetch('clubs', queryset=SASClub.objects.filter(is_active=True))
    ).filter(is_active=True)

    clubs_with_products = SASClub.objects.prefetch_related(
        Prefetch('products', queryset=SASProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ))
    ).filter(is_active=True)

    products_with_variations = SASProduct.objects.prefetch_related(
        'variations'
    ).filter(product_type='variable')

    return {
        'sports': sports_with_clubs,
        'clubs': clubs_with_products,
        'products': products_with_variations
    }

# Connection pooling
def _setup_connection_pooling(self):
    """Setup database connection pooling for better performance"""
    from django.db import connections

    # Configure connection pooling parameters
    db_settings = {
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
        'OPTIONS': {
            'MAX_CONNS': 20,
            'MIN_CONNS': 5,
        }
    }

    # Apply to default database
    connections.databases['default'].update(db_settings)

# Memory optimization
def _optimize_memory_usage(self):
    """Optimize memory usage during sync"""
    import gc

    # Process in chunks to avoid memory issues
    chunk_size = 50

    # Force garbage collection between chunks
    def process_chunk(items, processor_func):
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            processor_func(chunk)

            # Force garbage collection
            gc.collect()
```

---

## Monitoring & Logging

### Comprehensive Logging System

```python
import structlog
from django.core.cache import cache

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

class SyncMonitor:
    """Monitor sync operations with detailed metrics"""

    def __init__(self, command_instance):
        self.command = command_instance
        self.logger = structlog.get_logger(__name__)
        self.start_time = timezone.now()
        self.metrics = {
            'api_calls': 0,
            'api_call_duration': [],
            'database_operations': 0,
            'memory_usage': [],
            'error_count': 0,
            'warning_count': 0
        }

    def track_api_call(self, endpoint, duration, status_code):
        """Track API call metrics"""
        self.metrics['api_calls'] += 1
        self.metrics['api_call_duration'].append(duration)

        self.logger.info(
            "api_call_completed",
            endpoint=endpoint,
            duration_ms=duration * 1000,
            status_code=status_code,
            total_calls=self.metrics['api_calls']
        )

        # Cache API performance data
        cache_key = f"sas_sync_api_performance_{timezone.now().strftime('%Y%m%d')}"
        cached_data = cache.get(cache_key, [])
        cached_data.append({
            'endpoint': endpoint,
            'duration': duration,
            'status_code': status_code,
            'timestamp': timezone.now().isoformat()
        })
        cache.set(cache_key, cached_data, 86400)  # 24 hours

    def track_database_operation(self, operation_type, model_name, count):
        """Track database operation metrics"""
        self.metrics['database_operations'] += 1

        self.logger.info(
            "database_operation",
            operation=operation_type,
            model=model_name,
            count=count,
            total_operations=self.metrics['database_operations']
        )

    def track_memory_usage(self):
        """Track memory usage during sync"""
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024

        self.metrics['memory_usage'].append(memory_mb)

        self.logger.info(
            "memory_usage",
            memory_mb=memory_mb,
            peak_memory_mb=max(self.metrics['memory_usage'])
        )

    def log_sync_progress(self, stage, current, total, details=None):
        """Log sync progress with structured data"""
        progress_pct = (current / total * 100) if total > 0 else 0

        self.logger.info(
            "sync_progress",
            stage=stage,
            current=current,
            total=total,
            progress_pct=round(progress_pct, 1),
            details=details or {}
        )

    def log_error(self, error_type, message, context=None):
        """Log errors with context"""
        self.metrics['error_count'] += 1

        self.logger.error(
            "sync_error",
            error_type=error_type,
            message=message,
            context=context or {},
            total_errors=self.metrics['error_count']
        )

    def log_warning(self, warning_type, message, context=None):
        """Log warnings with context"""
        self.metrics['warning_count'] += 1

        self.logger.warning(
            "sync_warning",
            warning_type=warning_type,
            message=message,
            context=context or {},
            total_warnings=self.metrics['warning_count']
        )

    def generate_performance_report(self):
        """Generate comprehensive performance report"""
        end_time = timezone.now()
        total_duration = (end_time - self.start_time).total_seconds()

        api_durations = self.metrics['api_call_duration']
        avg_api_duration = sum(api_durations) / len(api_durations) if api_durations else 0

        memory_usage = self.metrics['memory_usage']
        peak_memory = max(memory_usage) if memory_usage else 0
        avg_memory = sum(memory_usage) / len(memory_usage) if memory_usage else 0

        report = {
            'sync_duration_seconds': total_duration,
            'api_metrics': {
                'total_calls': self.metrics['api_calls'],
                'average_duration_ms': avg_api_duration * 1000,
                'calls_per_minute': (self.metrics['api_calls'] / total_duration * 60) if total_duration > 0 else 0
            },
            'database_metrics': {
                'total_operations': self.metrics['database_operations'],
                'operations_per_minute': (self.metrics['database_operations'] / total_duration * 60) if total_duration > 0 else 0
            },
            'memory_metrics': {
                'peak_memory_mb': peak_memory,
                'average_memory_mb': avg_memory
            },
            'error_metrics': {
                'error_count': self.metrics['error_count'],
                'warning_count': self.metrics['warning_count']
            }
        }

        self.logger.info("sync_performance_report", **report)
        return report

# Integration in sync command
def _setup_monitoring(self):
    """Setup monitoring for sync operations"""
    self.monitor = SyncMonitor(self)

    # Track memory usage periodically
    def memory_tracker():
        while getattr(self, 'sync_running', True):
            self.monitor.track_memory_usage()
            time.sleep(30)  # Every 30 seconds

    import threading
    self.memory_thread = threading.Thread(target=memory_tracker, daemon=True)
    self.memory_thread.start()

def _log_sync_statistics(self):
    """Log comprehensive sync statistics"""
    # Generate performance report
    performance_report = self.monitor.generate_performance_report()

    # Log final statistics
    self.logger.info(
        "sync_completed",
        stats=dict(self.stats),
        performance=performance_report,
        duration_seconds=performance_report['sync_duration_seconds']
    )

    # Save to file for historical analysis
    log_file = f"sas_sync_log_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w') as f:
        json.dump({
            'stats': dict(self.stats),
            'performance': performance_report,
            'timestamp': timezone.now().isoformat()
        }, f, indent=2)
```

---

## API Integration

### Enhanced WooCommerce Service

```python
def get_product_variations(self, product_id):
    """Fetch variations for a specific product"""
    endpoint = f"products/{product_id}/variations"
    params = {
        'per_page': 100,
        'status': 'any'  # Include all variations
    }

    all_variations = []
    page = 1

    while True:
        params['page'] = page
        variations = self._make_request(endpoint, params)

        if not variations:
            break

        all_variations.extend(variations)

        # Check if we have more pages
        if len(variations) < params['per_page']:
            break

        page += 1

    logger.info(f"Fetched {len(all_variations)} variations for product {product_id}")
    return all_variations

def get_products_by_category_with_variations(self, category_id):
    """Fetch products with their variations in a single call"""
    products = self.get_products_by_category(category_id)

    # Fetch variations for variable products
    for product in products:
        if product.get('type') == 'variable':
            variations = self.get_product_variations(product['id'])
            product['variations'] = variations

    return products

def test_connection_detailed(self):
    """Test API connection with detailed diagnostics"""
    try:
        # Test basic connectivity
        response = self._make_request('system_status')

        if response:
            logger.info("✅ WooCommerce API connection successful")

            # Test specific endpoints
            endpoints_to_test = [
                ('products', 'Products endpoint'),
                ('products/categories', 'Categories endpoint'),
                ('products/1/variations', 'Variations endpoint')
            ]

            test_results = {}
            for endpoint, description in endpoints_to_test:
                try:
                    test_response = self._make_request(endpoint, {'per_page': 1})
                    test_results[endpoint] = {
                        'status': 'success',
                        'response_size': len(str(test_response)) if test_response else 0
                    }
                    logger.info(f"✅ {description} accessible")
                except Exception as e:
                    test_results[endpoint] = {
                        'status': 'failed',
                        'error': str(e)
                    }
                    logger.warning(f"⚠️ {description} failed: {str(e)}")

            return True, test_results
        else:
            logger.error("❌ WooCommerce API connection failed")
            return False, {}

    except Exception as e:
        logger.error(f"❌ WooCommerce API connection error: {str(e)}")
        return False, {'connection_error': str(e)}

def get_api_usage_stats(self):
    """Get API usage statistics"""
    # This would typically require WooCommerce API rate limiting headers
    # Implementation depends on your specific WooCommerce setup
    pass
```

---

## Implementation Examples

### Complete Sync Command Usage

```bash
# Basic sync (dry run first)
python manage.py sync_sas_clubs --dry-run --verbose

# Full sync with variations
python manage.py sync_sas_clubs --sync-variations --verbose

# Sync specific sport
python manage.py sync_sas_clubs --sport-filter="Basketball" --force-update

# Limited sync for testing
python manage.py sync_sas_clubs --limit-clubs=5 --verbose

# Production sync with monitoring
python manage.py sync_sas_clubs --force-update 2>&1 | tee sas_sync_$(date +%Y%m%d_%H%M%S).log
```

### Monitoring Dashboard Integration

```python
# views.py - Sync monitoring dashboard
class SASSyncDashboardView(TemplateView):
    template_name = 'clubs/sas_sync_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get sync statistics
        context['sync_stats'] = self.get_sync_statistics()
        context['recent_syncs'] = self.get_recent_sync_logs()
        context['data_health'] = self.get_data_health_metrics()

        return context

    def get_sync_statistics(self):
        """Get current sync statistics"""
        return {
            'total_sports': SASSport.objects.count(),
            'active_sports': SASSport.objects.filter(is_active=True).count(),
            'total_clubs': SASClub.objects.count(),
            'active_clubs': SASClub.objects.filter(is_active=True, is_school=False, is_generic_category=False).count(),
            'total_products': SASProduct.objects.count(),
            'available_products': SASProduct.objects.filter(stock_status__in=['instock', 'onbackorder']).count(),
            'total_variations': SASProductVariation.objects.count(),
            'active_variations': SASProductVariation.objects.filter(is_active=True).count(),
        }

    def get_data_health_metrics(self):
        """Get data health and integrity metrics"""
        return {
            'orphaned_clubs': SASClub.objects.filter(sport__isnull=True).count(),
            'orphaned_products': SASProduct.objects.filter(club__isnull=True).count(),
            'products_without_variations': SASProduct.objects.filter(
                product_type='variable',
                variations__isnull=True
            ).count(),
            'clubs_without_products': SASClub.objects.filter(
                is_active=True,
                products__isnull=True
            ).count(),
        }
```

### Frontend Integration

```javascript
// Frontend variation handling for SAS products
class SASProductVariationManager {
    constructor(productData) {
        this.productData = productData;
        this.selectedVariations = {};
        this.availableStock = 0;

        this.init();
    }

    init() {
        if (!this.productData.has_variations) {
            return;
        }

        this.setupVariationControls();
        this.bindEvents();
    }

    setupVariationControls() {
        const variationTypes = this.productData.variation_types || [];

        variationTypes.forEach(type => {
            this.createVariationControl(type);
        });
    }

    createVariationControl(variationType) {
        const variations = this.getVariationsForType(variationType);

        if (!variations.length) return;

        const container = document.querySelector(`[data-variation-type="${variationType}"]`);
        if (!container) return;

        // Create variation options
        variations.forEach(variation => {
            const option = this.createVariationOption(variation);
            container.appendChild(option);
        });
    }

    createVariationOption(variation) {
        const option = document.createElement('div');
        option.className = 'variation-option';
        option.dataset.variationType = variation.type;
        option.dataset.variationValue = variation.value;
        option.dataset.stock = variation.stock;
        option.dataset.available = variation.is_available;

        // Add stock indicator for SAS products
        if (variation.stock !== null) {
            const stockBadge = document.createElement('span');
            stockBadge.className = 'sas-stock-badge';
            stockBadge.textContent = `${variation.stock} available`;
            option.appendChild(stockBadge);
        }

        option.textContent = variation.value;

        // Disable if not available
        if (!variation.is_available) {
            option.classList.add('disabled');
        }

        return option;
    }

    bindEvents() {
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('variation-option')) {
                this.handleVariationSelection(e.target);
            }
        });
    }

    handleVariationSelection(element) {
        if (element.classList.contains('disabled')) {
            return;
        }

        const variationType = element.dataset.variationType;
        const variationValue = element.dataset.variationValue;

        // Update selection
        this.selectedVariations[variationType] = variationValue;

        // Update UI
        this.updateVariationDisplay();
        this.updateStockDisplay();
        this.updateAvailableOptions();
    }

    updateStockDisplay() {
        const stockInfo = this.getStockForCurrentSelection();

        const stockDisplay = document.querySelector('.stock-display');
        if (stockDisplay) {
            if (stockInfo.available) {
                stockDisplay.innerHTML = `
                    <span class="sas-stock-available">
                        ${stockInfo.quantity} available
                    </span>
                `;
            } else {
                stockDisplay.innerHTML = `
                    <span class="sas-stock-unavailable">
                        Out of stock
                    </span>
                `;
            }
        }
    }

    getStockForCurrentSelection() {
        // Use the product's variation combination stock method
        const combination = this.selectedVariations;

        // Find matching variation
        const matchingVariation = this.productData.variations.find(v => {
            return Object.keys(combination).every(type => {
                return v.attributes[type] === combination[type];
            });
        });

        if (matchingVariation) {
            return {
                available: matchingVariation.is_available,
                quantity: matchingVariation.stock
            };
        }

        return { available: false, quantity: 0 };
    }
}

// Initialize for SAS products
document.addEventListener('DOMContentLoaded', function() {
    const productData = window.sasProductData;

    if (productData && productData.has_variations) {
        new SASProductVariationManager(productData);
    }
});
```

---

## Conclusion

This comprehensive sync logic implementation provides:

1. **Complete Data Hierarchy** - Sports → Clubs → Products → Variations
2. **Robust Error Handling** - Recovery mechanisms and validation
3. **Performance Optimization** - Bulk operations and query optimization
4. **Comprehensive Monitoring** - Detailed logging and metrics
5. **Smart Filtering** - School exclusion and generic category detection
6. **Multi-dimensional Variations** - Full support for size, color, material combinations
7. **Frontend Integration** - JavaScript components for variation handling
8. **Production Ready** - Transaction support, rollback capabilities, and monitoring

The implementation follows Django best practices, includes comprehensive error handling, and provides detailed monitoring capabilities for production use.

---

**Document Status:** Complete
**Implementation Ready:** Yes
**Testing Required:** Integration testing with live WooCommerce API
**Production Deployment:** Ready with monitoring setup