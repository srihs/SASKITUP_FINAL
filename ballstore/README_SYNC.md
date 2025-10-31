# BallStore Sync Management Command

## Overview

The `sync_ballstore` management command synchronizes product data from the BallStore WooCommerce API to the Django database. It handles categories, products, variations, and images with comprehensive error handling and progress tracking.

## Features

- **Full Sync**: Complete synchronization of all products from WooCommerce
- **Incremental Sync**: Only sync products modified since the last successful sync
- **Categories Only**: Sync just the category structure without products
- **Category Hierarchy**: Properly handles parent-child category relationships
- **Multi-Category Products**: Products can belong to multiple categories
- **Product Types**: Supports both simple and variable products
- **Variations**: Complete variation data including attributes, pricing, and images
- **Image Handling**: Synchronizes all product images with proper ordering
- **Skip Categories**: Automatically skips Bulk Deal (66) and Uncategorized (104) categories
- **Pagination**: Efficiently handles large datasets with 100 items per page
- **Progress Tracking**: Real-time progress output with color-coded status
- **Error Handling**: Comprehensive error handling with detailed logging
- **Sync Logs**: Maintains detailed sync history in the database

## Prerequisites

### 1. Environment Configuration

Add the following variables to your `.env` file:

```bash
# WooCommerce API Configuration - BallStore
BS_WOOCOMMERCE_API_URL=https://theballstore.co.nz/wp-json/wc/v3/
BS_WOOCOMMERCE_API_CONSUMER_KEY=ck_your_consumer_key_here
BS_WOOCOMMERCE_API_SECRET=cs_your_consumer_secret_here
```

### 2. Django Settings

The command automatically reads settings from `settings.py`:

```python
# WooCommerce API Configuration for BallStore
BS_WOO_URL = config('BS_WOOCOMMERCE_API_URL')
BS_WOO_KEY = config('BS_WOOCOMMERCE_API_CONSUMER_KEY')
BS_WOO_SECRET = config('BS_WOOCOMMERCE_API_SECRET')
```

### 3. Database Migrations

Ensure all BallStore migrations are applied:

```bash
python manage.py migrate ballstore
```

## Usage

### Basic Commands

```bash
# Incremental sync (default - only modified products)
python manage.py sync_ballstore

# Full sync (all products)
python manage.py sync_ballstore --full

# Categories only
python manage.py sync_ballstore --categories-only

# Verbose output
python manage.py sync_ballstore --verbose
python manage.py sync_ballstore --full --verbose
```

### Command Options

| Option | Description |
|--------|-------------|
| `--full` | Force full synchronization of all products |
| `--incremental` | Incremental sync (only modified products) - **default** |
| `--categories-only` | Only synchronize categories without products |
| `--verbose` | Enable detailed output for debugging |
| `-h, --help` | Show help message with all available options |

## Synchronization Process

### 1. Full Sync (`--full`)

Complete synchronization of all data:

```
1. Test API connection
2. Fetch all categories (with pagination)
   - Skip category IDs: 66, 104
   - Handle parent-child relationships
   - Update product counts
3. Fetch all products (with pagination)
   - Process simple products
   - Process variable products
   - Assign categories
   - Sync product images
   - Sync variations (for variable products)
4. Generate sync log
5. Display statistics
```

**When to use:**
- Initial setup
- After major WooCommerce changes
- To rebuild the entire database
- When data integrity issues occur

### 2. Incremental Sync (default)

Only syncs products modified since the last successful sync:

```
1. Get last successful sync timestamp
2. Fetch modified categories
3. Fetch products modified after timestamp
   - Uses WooCommerce 'modified_after' parameter
4. Update only changed records
5. Generate sync log
```

**When to use:**
- Daily/hourly scheduled syncs
- Regular maintenance
- After product updates in WooCommerce
- Production environments (faster, less resource-intensive)

### 3. Categories Only (`--categories-only`)

Syncs only the category structure:

```
1. Fetch all categories
2. Update category hierarchy
3. Skip product synchronization
```

**When to use:**
- After category structure changes
- Quick category updates
- Testing category relationships

## Data Models

### BallStoreCategory

```python
- wc_id: WooCommerce category ID
- name: Category name
- slug: URL-friendly slug
- parent: Parent category (self-referential)
- description: Category description
- display_type: Display type
- product_count: Number of products
- last_synced: Last sync timestamp
- is_active: Active status
```

### BallStoreProduct

```python
- wc_id: WooCommerce product ID
- name: Product name
- slug: URL-friendly slug
- permalink: Product URL
- product_type: 'simple' or 'variable'
- sku: Stock keeping unit
- description: Full HTML description
- short_description: Short HTML description
- price: Current price
- regular_price: Regular price
- sale_price: Sale price (if on sale)
- on_sale: Sale status boolean
- stock_status: 'instock', 'outofstock', 'onbackorder'
- stock_quantity: Stock count
- manage_stock: Stock management boolean
- categories: Many-to-many relationship
- featured_image_url: Main product image URL
- date_created: WooCommerce creation date
- date_modified: WooCommerce modification date
- last_synced: Last sync timestamp
- is_active: Active status
```

### BallStoreProductVariation

```python
- wc_id: WooCommerce variation ID
- parent_product: Foreign key to BallStoreProduct
- sku: Variation SKU
- description: Variation description
- price: Variation price
- regular_price: Regular price
- sale_price: Sale price
- on_sale: Sale status
- stock_status: Stock status
- stock_quantity: Stock count
- manage_stock: Stock management
- attributes: JSON field with variation attributes
- image_url: Variation image URL
- date_created: Creation date
- date_modified: Modification date
- last_synced: Last sync timestamp
- is_active: Active status
```

### BallStoreProductImage

```python
- wc_id: WooCommerce image ID
- product: Foreign key to BallStoreProduct
- src: Image URL
- name: Image name
- alt: Alt text
- position: Display order
```

### BallStoreSyncLog

```python
- sync_type: 'full', 'incremental', 'categories'
- status: 'running', 'completed', 'failed'
- categories_synced: Count
- products_synced: Count
- variations_synced: Count
- images_synced: Count
- errors_count: Error count
- started_at: Start timestamp
- completed_at: Completion timestamp
- duration_seconds: Total duration
- error_message: Error details
- details: JSON field for additional data
```

## Example Output

### Successful Full Sync

```
Testing BallStore WooCommerce connection...
✓ Connected to BallStore WooCommerce API
============================================================
BallStore Sync - FULL MODE
============================================================

📂 Syncing categories...
  Processed 45 categories

📦 Syncing products...
  Processed 234 products

============================================================
🎉 BALLSTORE SYNC SUMMARY
============================================================

📊 Statistics:
  • Categories synced: 45
  • Products synced: 234
  • Variations synced: 567
  • Images synced: 892
  • Errors: 0

📈 Summary:
  • Total items synced: 1738
  • Duration: 127.34 seconds
  • Success rate: 100.0%
============================================================

✨ Sync completed successfully with no errors!
```

### Incremental Sync with Verbose Output

```
Testing BallStore WooCommerce connection...
✓ Connected to BallStore WooCommerce API
============================================================
BallStore Sync - INCREMENTAL MODE
============================================================

📂 Syncing categories...
  ✓ Synced: Footballs
  ✓ Synced: Training Equipment
  ✓ Synced: Team Wear
  Processed 12 categories

📦 Syncing products...
  ✓ Synced: Nike Strike Football - Size 5
    ✓ Variation: 123456
    ✓ Variation: 123457
  ✓ Synced: Adidas Training Cones Set
  ✓ Synced: Puma Team Jersey - Home Kit
    ✓ Variation: 234567
    ✓ Variation: 234568
    ✓ Variation: 234569
  Processed 23 products

============================================================
🎉 BALLSTORE SYNC SUMMARY
============================================================

📊 Statistics:
  • Categories synced: 12
  • Products synced: 23
  • Variations synced: 45
  • Images synced: 89
  • Errors: 0

📈 Summary:
  • Total items synced: 169
  • Duration: 34.56 seconds
  • Success rate: 100.0%
============================================================

✨ Sync completed successfully with no errors!
```

## Error Handling

The command includes comprehensive error handling:

### Connection Errors
- **Issue**: Cannot connect to WooCommerce API
- **Handling**:
  - Validates credentials before sync
  - Tests connection with a sample request
  - Displays clear error messages
  - Exits gracefully with error code

### API Errors
- **Issue**: WooCommerce API returns errors
- **Handling**:
  - Logs error details
  - Continues with remaining items
  - Increments error counter
  - Includes in final report

### Data Errors
- **Issue**: Invalid data from WooCommerce
- **Handling**:
  - Validates all data before saving
  - Handles missing fields gracefully
  - Logs parsing errors
  - Uses safe defaults where appropriate

### Timeout Errors
- **Issue**: API requests timeout
- **Handling**:
  - 30-second timeout per request
  - Logs timeout events
  - Continues with next item
  - Included in error count

## Performance Considerations

### Pagination
- Processes 100 items per page (WooCommerce limit)
- Uses efficient cursor-based pagination
- Minimizes memory usage

### Rate Limiting
- 0.5 second delay between category pages
- 0.5 second delay between product pages
- 0.3 second delay between variation pages
- Prevents API throttling

### Database Optimization
- Uses `update_or_create()` for upserts
- Bulk operations where possible
- Transaction-based processing
- Efficient relationship management

### Typical Performance

| Operation | Items | Duration |
|-----------|-------|----------|
| Full Sync | 250 products | ~2-3 minutes |
| Incremental | 50 products | ~30-45 seconds |
| Categories Only | 50 categories | ~10-15 seconds |

## Monitoring and Logging

### Sync Logs

View sync history in Django admin or via database:

```python
from ballstore.models import BallStoreSyncLog

# Get recent syncs
recent_syncs = BallStoreSyncLog.objects.all()[:10]

# Get last successful sync
last_sync = BallStoreSyncLog.objects.filter(
    status='completed'
).order_by('-completed_at').first()

# Get sync statistics
for sync in recent_syncs:
    print(f"{sync.sync_type}: {sync.products_synced} products, "
          f"{sync.errors_count} errors, {sync.duration_seconds}s")
```

### Application Logs

Check Django logs for detailed information:

```bash
# Monitor real-time
tail -f django.log | grep ballstore

# Search for errors
grep "ERROR.*ballstore" django.log

# View sync operations
grep "BallStore sync" django.log
```

## Scheduled Synchronization

### Using Cron (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Add daily sync at 2 AM
0 2 * * * cd /path/to/SASKITUP && source env/bin/activate && python manage.py sync_ballstore >> /var/log/ballstore_sync.log 2>&1

# Add hourly incremental sync
0 * * * * cd /path/to/SASKITUP && source env/bin/activate && python manage.py sync_ballstore --incremental >> /var/log/ballstore_sync.log 2>&1
```

### Using Django-Cron (Python)

```python
# In ballstore/cron.py
from django_cron import CronJobBase, Schedule
from django.core.management import call_command

class BallStoreSyncCronJob(CronJobBase):
    RUN_EVERY_MINS = 60  # Every hour

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'ballstore.sync_ballstore'

    def do(self):
        call_command('sync_ballstore', '--incremental')
```

### Using Celery (Recommended for Production)

```python
# In ballstore/tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def sync_ballstore_products(full_sync=False):
    """Celery task for BallStore synchronization"""
    args = ['--full'] if full_sync else ['--incremental']
    call_command('sync_ballstore', *args)
```

## Troubleshooting

### Problem: Command not found

**Solution:**
```bash
# Ensure you're in the project directory
cd /path/to/SASKITUP

# Activate virtual environment
source env/bin/activate

# Verify Django can find the command
python manage.py help sync_ballstore
```

### Problem: Connection refused

**Solution:**
1. Check `.env` file has correct credentials
2. Verify API URL is accessible
3. Test with curl:
```bash
curl -u "consumer_key:consumer_secret" \
  "https://theballstore.co.nz/wp-json/wc/v3/products?per_page=1"
```

### Problem: Credential errors

**Solution:**
1. Verify environment variables:
```bash
python manage.py shell
>>> from django.conf import settings
>>> print(settings.BS_WOO_URL)
>>> print(settings.BS_WOO_KEY)
```
2. Check WooCommerce API keys are active
3. Ensure API permissions are set correctly

### Problem: Slow sync performance

**Solution:**
1. Use incremental sync instead of full sync
2. Check network connection
3. Monitor API response times
4. Consider running during off-peak hours

### Problem: Products not updating

**Solution:**
1. Check `date_modified` field in WooCommerce
2. Use `--full` flag to force update
3. Verify sync log timestamps
4. Check for API errors in logs

## Best Practices

### Development
- Use `--verbose` flag for debugging
- Test with `--categories-only` first
- Use incremental sync for regular updates
- Monitor sync logs regularly

### Production
- Schedule incremental syncs hourly
- Run full sync weekly/monthly
- Set up error monitoring
- Keep sync logs for auditing
- Use Celery for background processing
- Monitor API rate limits

### Data Integrity
- Run full sync after major WooCommerce changes
- Verify category relationships periodically
- Check variation data consistency
- Monitor image URL validity
- Review error logs regularly

## API Reference

### WooCommerce Endpoints Used

```
GET /products/categories          - List categories
GET /products                     - List products
GET /products/{id}/variations     - List product variations
```

### Query Parameters

```python
# Pagination
per_page=100                      # Items per page (max 100)
page=1                           # Page number

# Filtering
status=publish                    # Only published products
modified_after=2024-01-01T00:00:00 # Incremental sync

# Sorting
orderby=id                       # Sort field
order=asc                        # Sort direction
```

## Security Considerations

1. **Credentials**: Never commit `.env` file to version control
2. **API Keys**: Use WooCommerce REST API keys with minimum required permissions
3. **HTTPS**: Always use HTTPS for API connections
4. **Validation**: All input data is validated before database operations
5. **Sanitization**: HTML content is stored as-is (sanitization happens at display time)

## Support and Maintenance

### Logs Location
- Application logs: `django.log`
- Sync history: Database table `ballstore_sync_log`

### Admin Interface
Access sync logs via Django admin:
```
http://localhost:8000/admin/ballstore/ballstoresynclog/
```

### Contact
For issues or questions, check:
1. This README
2. Django logs
3. WooCommerce API documentation
4. Project maintainers

## Version History

- **v1.0.0** (2024-10-31): Initial release
  - Full sync support
  - Incremental sync support
  - Category synchronization
  - Product and variation handling
  - Image synchronization
  - Comprehensive error handling
  - Sync logging
