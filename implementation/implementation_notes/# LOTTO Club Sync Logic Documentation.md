# LOTTO Club Sync Logic Documentation

## Overview

The LOTTO Club synchronization system is responsible for importing and maintaining sports club data from the LOTTO WooCommerce store. This document provides a comprehensive overview of the sync logic, data flow, and implementation details.

## Command Structure

**File**: `clubs/management/commands/sync_lotto_clubs.py`  
**Purpose**: Django management command for syncing LOTTO clubs data from WooCommerce API  
**Usage**: `python manage.py sync_lotto_clubs [OPTIONS]`

### Command Arguments

```bash
--store-type {LOTTO,SAS}     # Store type to sync (default: LOTTO)
--parent-category-id INT     # Parent category ID for Club Shops (default: 23)
--dry-run                    # Run without making changes to database
--force-update               # Force update all records regardless of changes
--check-only                 # Show what would be updated without making changes
--verbose                    # Show detailed change information
--limit INT                  # Limit number of clubs to process
```

## Architecture Overview

```
WooCommerce LOTTO Store
└── Club Shops (Category ID: 23)
    ├── Club A (Category)
    │   ├── Subcategory 1
    │   │   ├── Product A
    │   │   │   ├── Variation 1
    │   │   │   └── Variation 2
    │   │   └── Product B
    │   └── Subcategory 2
    └── Club B (Category)
        └── Products (directly under club)
```

## Data Model Mapping

### WooCommerce → Django Model Mapping

| WooCommerce Entity | Django Model | Purpose |
|-------------------|--------------|---------|
| Category (Club Level) | `Club` | Main club entity |
| Category (Subcategory) | `ClubCategory` | Product categories within clubs |
| Product | `Product` | Individual products |
| Product Variation | `ProductVariation` | Size/color/style variations |

## Sync Process Flow

### 1. Initialization Phase

```python
def handle(self, *args, **options):
    # Initialize WooCommerce service
    woo_service = WooCommerceService(store_type='LOTTO')
    
    # Test API connection
    if not woo_service.test_connection():
        raise CommandError('Failed to connect to LOTTO WooCommerce API')
    
    # Fetch categories with products
    categories = woo_service.get_categories_with_products(parent_id=23)
```

**Key Features**:
- Connection validation before processing
- Fetches only categories that contain products
- Configurable parent category ID
- Error handling for API failures

### 2. Club Processing

```python
def _process_club(self, category_data, store_type, woo_service, dry_run, force_update):
    """Process a club from category data with intelligent change detection"""
```

**Processing Logic**:
1. **Existence Check**: Look for existing club by `woo_category_id`
2. **Data Preparation**: Extract club information from WooCommerce category
3. **Change Detection**: Compare new data with existing records
4. **Image Handling**: Download and manage club logos
5. **Database Update**: Create new or update existing club records

**Club Data Fields**:
```python
new_club_data = {
    'name': category_data['name'],
    'club_type': 'LOTTO',
    'woo_category_id': woo_category_id,
    'is_active': True,
    'logo': content_file  # Downloaded image
}
```

### 3. Category Processing

```python
def _process_club_category(self, club, category_data, woo_service, dry_run, force_update):
    """Process a club category with intelligent change detection"""
```

**Two-Level Category Structure**:
1. **With Subcategories**: Process subcategories under main club category
2. **Direct Products**: Process products directly under club category

**Category Data Fields**:
```python
new_category_data = {
    'club': club,
    'name': category_data['name'],
    'woo_category_id': woo_category_id,
    'description': category_data.get('description', ''),
    'product_count': category_data.get('count', 0),
    'image': content_file  # Downloaded image
}
```

### 4. Product Processing

```python
def _process_product(self, category, product_data, woo_service, dry_run, force_update):
    """Process a product with intelligent change detection - Enhanced to capture ALL WooCommerce fields"""
```

**Comprehensive Product Data Capture**:
The system captures ALL WooCommerce product fields, organized into categories:

#### Core Identification
- `name`, `woo_product_id`, `category`

#### WooCommerce Metadata
- `permalink`, `date_created`, `date_modified`, `type`, `status`, `featured`, `catalog_visibility`

#### Pricing and Sales
- `price`, `regular_price`, `sale_price`, `price_html`, `on_sale`, `purchasable`, `total_sales`
- `date_on_sale_from`, `date_on_sale_to`

#### Product Content
- `description`, `short_description`, `sku`

#### Product Characteristics
- `virtual`, `downloadable`, `downloads`, `download_limit`, `download_expiry`

#### External Product Fields
- `external_url`, `button_text`

#### Inventory and Stock
- `stock_status`, `manage_stock`, `stock_quantity`, `backorders`, `sold_individually`

#### Tax Settings
- `tax_status`, `tax_class`

#### Shipping
- `weight`, `dimensions`, `shipping_required`, `shipping_taxable`, `shipping_class`, `shipping_class_id`

#### Reviews and Ratings
- `reviews_allowed`, `average_rating`, `rating_count`

#### Related Products
- `related_ids`, `upsell_ids`, `cross_sell_ids`

#### Variable/Grouped Products
- `parent_id`, `grouped_products`, `woo_variations`, `default_attributes`

#### Additional Fields
- `purchase_note`, `menu_order`, `meta_data`

#### Enhanced Fields
- `woo_categories`, `images`, `tags`, `attributes`

### 5. Variation Processing

```python
def _process_product_variations(self, product, product_data, woo_service, force_update):
    """Process variations for a variable product"""
```

**Intelligent Variation Handling**:
1. **Deduplication**: Prevents duplicate variations using `(variation_type, variation_value)` keys
2. **Multiple Attributes**: Handles products with multiple variation attributes
3. **Image Strategy**: Uses intelligent image selection for variations
4. **Error Recovery**: Continues processing even if individual variations fail

**Variation Data Structure**:
```python
new_variation_data = {
    'product': product,
    'variation_type': extracted_data['variation_type'],
    'variation_value': extracted_data['variation_value'],
    'price_modifier': extracted_data['price_modifier'],
    'stock_quantity': extracted_data['stock_quantity'],
    'sku_suffix': extracted_data['sku_suffix'],
    'woo_variation_id': woo_variation_id,
    'is_active': extracted_data['is_active'],
    'attributes': extracted_data['attributes'],
    'weight': extracted_data['weight'],
    'dimensions': extracted_data['dimensions'],
    'image': content_file  # Downloaded image
}
```

## Intelligent Change Detection System

### Philosophy
The sync system implements intelligent change detection to avoid unnecessary database operations and improve performance. Only records with actual changes are updated.

### Change Detection Methods

#### 1. Club Changes
```python
def _detect_club_changes(self, existing_club, new_data, new_image_url):
    """Detect changes in club data"""
```
- Name changes
- Club type changes
- Active status changes
- Logo/image changes

#### 2. Category Changes
```python
def _detect_category_changes(self, existing_category, new_data, new_image_url):
    """Detect changes in category data"""
```
- Name changes
- Description changes
- Product count changes
- Image changes

#### 3. Product Changes
```python
def _detect_product_changes(self, existing_product, new_data, new_image_url):
    """Detect changes in product data - Enhanced for all WooCommerce fields"""
```

**Field Categories Checked**:
- **Basic Fields**: `name`, `sku`, `description`, `short_description`, `weight`, etc.
- **Boolean Fields**: `featured`, `on_sale`, `purchasable`, `virtual`, etc.
- **Integer Fields**: `total_sales`, `download_limit`, `stock_quantity`, etc.
- **Choice Fields**: `stock_status`, `backorders`
- **Decimal Fields**: `price`, `regular_price`, `sale_price`, `average_rating`
- **Date Fields**: `date_created`, `date_modified`, `date_on_sale_from`, `date_on_sale_to`
- **JSON Fields**: `dimensions`, `tags`, `attributes`, `downloads`, etc.
- **Image Changes**: Intelligent image comparison

#### 4. Variation Changes
```python
def _detect_variation_changes(self, existing_variation, new_data, new_image_url):
    """Detect changes in variation data"""
```
- Type and value changes
- Price modifier changes
- Stock quantity changes
- Attribute changes
- Intelligent variation image changes

### Image Change Detection

**Intelligent Image Strategy**:
```python
def _has_image_changed(self, current_image_name, new_image_url):
    """Check if image has changed by comparing URL components"""
```

**Logic**:
1. Extract filename from WooCommerce URL
2. Compare with current stored image filename
3. Use heuristic matching to avoid unnecessary downloads
4. Handle edge cases (no current image, no new image, parsing errors)

**Variation-Specific Image Logic**:
```python
def _has_variation_image_changed(self, existing_variation, current_image_name, new_image_url):
    """Check if variation image has changed with intelligent logic"""
```

**Strategy by Variation Type**:
- **Color/Style/Material**: More sensitive to changes (visual variations)
- **Size/Gender**: Less sensitive to changes (typically same image)

## Price Processing

### Price Parsing Logic
```python
def _parse_product_prices(self, product_data):
    """Parse and validate product prices from WooCommerce data"""
```

**Price Hierarchy**:
1. **Price**: Main selling price from WooCommerce
2. **Regular Price**: Original price before discount
3. **Sale Price**: Discounted price (if on sale)

**Error Handling**:
- Decimal validation with fallback to `0`
- Invalid price handling
- Price relationship validation

## Date Processing

### Date Parsing
```python
def _parse_woo_date(self, date_string):
    """Parse WooCommerce date string to Django datetime"""
```

**Multi-Level Parsing**:
1. **dateutil.parser**: Primary parsing method
2. **Django parse_datetime**: Fallback method
3. **None**: If parsing fails

### Date Comparison
```python
def _dates_significantly_different(self, date1, date2):
    """Check if two dates are significantly different"""
```

**Tolerance**: Allows 60-second difference to account for API variations

## Image Management

### Download Strategy
```python
# Club images
image_result = woo_service.download_image(
    image_url,
    'clubs',
    f"{slugify(category_data['name'])}-logo.jpg"
)

# Category images
image_result = woo_service.download_image(
    image_url,
    'categories', 
    f"{slugify(f'{club.name}-{category_data['name']}')}category.jpg"
)

# Product images
image_result = woo_service.download_image(
    image_url,
    'products',
    f"{slugify(f'{category.club.name}-{product_data['name']}')}product.jpg"
)
```

### Variation Image Strategy
```python
image_result = woo_service.download_variation_image(
    variation_data,
    product_data,
    product.name,
    extracted_data['variation_value']
)
```

**Intelligent Image Selection**:
1. Use variation-specific image if available
2. Fallback to product image for size variations
3. Custom naming strategy per variation type

## Transaction Management

### Atomic Operations
```python
try:
    with transaction.atomic():
        # Process club
        club, club_result = self._process_club(...)
        
        # Process categories and products
        for subcategory_data in subcategories:
            category, category_result = self._process_club_category(...)
            
            for product_data in products:
                product, product_result = self._process_product(...)
                
                # Process variations
                var_created, var_updated, var_skipped = self._process_product_variations(...)

except Exception as e:
    logger.error(f"Error processing club {category_data['name']}: {str(e)}")
    continue
```

**Error Recovery**:
- Individual club failures don't stop the entire sync
- Transaction rollback for failed clubs
- Comprehensive error logging
- Detailed error reporting in output

## Performance Optimizations

### 1. Change Detection
- Skip unnecessary database writes
- Intelligent image comparison
- Field-specific change detection

### 2. Batch Processing
- Process all subcategories and products for a club in one transaction
- Efficient query patterns
- Minimal database connections

### 3. Error Handling
- Continue processing other clubs if one fails
- Detailed progress reporting
- Skip unchanged records

### 4. Deduplication
- Prevent duplicate variations
- Track processed items
- Unique key validation

## Statistics and Reporting

### Comprehensive Metrics
```python
# Tracking Variables
clubs_created = 0
clubs_updated = 0  
clubs_skipped = 0
categories_created = 0
categories_updated = 0
categories_skipped = 0
products_created = 0
products_updated = 0
products_skipped = 0
variations_created = 0
variations_updated = 0
variations_skipped = 0
```

### Sync Summary
```
=== SYNC SUMMARY ===
Clubs created: 5
Clubs updated: 12
Clubs skipped (no changes): 45
Categories created: 15
Categories updated: 8
Categories skipped (no changes): 102
Products created: 125
Products updated: 234
Products skipped (no changes): 1,456
Variations created: 456
Variations updated: 123
Variations skipped (no changes): 2,345

Sync efficiency: 78.5% of items skipped (no changes needed)
```

### Efficiency Calculation
```python
efficiency = (total_skipped / (total_operations + total_skipped)) * 100
```

## Error Handling and Logging

### Multi-Level Logging
1. **Django Logger**: Structured logging to files
2. **Console Output**: Real-time progress updates
3. **Error Tracking**: Detailed error messages with context

### Error Categories
- **API Connection Failures**
- **Data Parsing Errors**
- **Database Constraint Violations**
- **Image Download Failures**
- **Validation Errors**

### Recovery Strategies
- **Continue on Error**: Individual failures don't stop sync
- **Transaction Rollback**: Failed clubs are rolled back
- **Detailed Reporting**: All errors are logged and reported
- **Partial Success**: Report what was successfully processed

## Mode Operations

### Dry Run Mode (`--dry-run`)
- Shows what would be processed
- No database changes
- Safe testing of sync logic

### Check Only Mode (`--check-only`)
- Shows detected changes
- No database updates
- Change impact assessment

### Force Update Mode (`--force-update`)
- Updates all records regardless of changes
- Bypasses change detection
- Complete data refresh

### Verbose Mode (`--verbose`)
- Detailed change information
- Field-by-field change reporting
- Enhanced progress output

## Integration Points

### WooCommerce Service Integration
- **API Authentication**: Consumer key/secret based
- **Rate Limiting**: Handles API rate limits
- **Error Recovery**: Retry logic for failed requests
- **Data Extraction**: Comprehensive field extraction

### Django Model Integration
- **ORM Operations**: Efficient database queries
- **File Handling**: Image upload and management
- **Validation**: Django model validation
- **Relationships**: Foreign key and many-to-many handling

## Configuration

### Environment Variables
```python
LOTTO_WOOCOMMERCE_API_URL=https://lotto-store.co.za/wp-json/wc/v3/
LOTTO_WOOCOMMERCE_API_CONSUMER_KEY=ck_...
LOTTO_WOOCOMMERCE_API_SECRET=cs_...
```

### Default Settings
- **Parent Category ID**: 23 (Club Shops)
- **Store Type**: LOTTO
- **Batch Processing**: Atomic transactions per club
- **Image Management**: Auto-download and storage

## Future Considerations

### Scalability
- **Pagination Support**: Handle large datasets
- **Parallel Processing**: Multi-threaded sync capabilities
- **Incremental Sync**: Only sync changed items
- **Caching Strategy**: Redis-based caching for API responses

### Monitoring
- **Performance Metrics**: Sync duration and throughput
- **Alert System**: Failure notifications
- **Health Checks**: Regular sync validation
- **Audit Trail**: Complete change history

### Enhancement Opportunities
- **Real-time Sync**: Webhook-based updates
- **Conflict Resolution**: Handle concurrent changes
- **Data Validation**: Enhanced business rule validation
- **Backup Integration**: Pre-sync data snapshots

## Usage Examples

### Basic Sync
```bash
python manage.py sync_lotto_clubs
```

### Dry Run Test
```bash
python manage.py sync_lotto_clubs --dry-run --verbose
```

### Limited Sync for Testing
```bash
python manage.py sync_lotto_clubs --limit 5 --verbose
```

### Force Complete Refresh
```bash
python manage.py sync_lotto_clubs --force-update
```

### Check Changes Only
```bash
python manage.py sync_lotto_clubs --check-only --verbose
```

## Technical Requirements

### Dependencies
- Django 5.2.5+
- WooCommerce REST API v3
- Python requests library
- Pillow for image processing
- dateutil for date parsing

### Database Requirements
- MySQL or SQLite support
- Transaction support
- JSON field support
- Foreign key constraints

### System Requirements
- Network access to WooCommerce API
- File system write permissions for images
- Sufficient storage for product images
- Memory for processing large product catalogs

This comprehensive documentation covers all aspects of the LOTTO sync logic, providing both high-level architectural understanding and detailed implementation guidance.