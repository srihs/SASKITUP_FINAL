# BallStore Sync - Quick Start Guide

## 5-Minute Setup

### 1. Environment Configuration (2 minutes)

Add to your `.env` file:

```bash
# WooCommerce API Configuration - BallStore
BS_WOOCOMMERCE_API_URL=https://theballstore.co.nz/wp-json/wc/v3/
BS_WOOCOMMERCE_API_CONSUMER_KEY=ck_fa7230bc12287dc32b1514af4aa363768090c996
BS_WOOCOMMERCE_API_SECRET=cs_f0e43e8d5037f57f8abee563c9e9f2f8bcb29760
```

### 2. Database Migration (1 minute)

```bash
# Activate virtual environment
source env/bin/activate

# Apply migrations
python manage.py migrate ballstore
```

### 3. Test Connection (1 minute)

```bash
# Test the command
python manage.py sync_ballstore --help
```

Expected output:
```
Synchronize BallStore products from WooCommerce API

options:
  --full                Force full sync of all products
  --incremental         Incremental sync (only modified products) - default
  --categories-only     Only sync categories without products
  --verbose             Enable verbose output
```

### 4. First Sync (varies)

```bash
# Categories only (fast test)
python manage.py sync_ballstore --categories-only

# Full sync with verbose output
python manage.py sync_ballstore --full --verbose
```

## Common Commands

```bash
# Daily incremental sync (recommended)
python manage.py sync_ballstore

# Full sync (initial setup or after major changes)
python manage.py sync_ballstore --full

# Categories only
python manage.py sync_ballstore --categories-only

# Debug mode
python manage.py sync_ballstore --full --verbose
```

## Verify Results

### Django Shell
```bash
python manage.py shell
```

```python
from ballstore.models import *

# Check counts
print(f"Categories: {BallStoreCategory.objects.count()}")
print(f"Products: {BallStoreProduct.objects.count()}")
print(f"Variations: {BallStoreProductVariation.objects.count()}")
print(f"Images: {BallStoreProductImage.objects.count()}")

# View recent sync logs
for log in BallStoreSyncLog.objects.all()[:5]:
    print(f"{log.sync_type}: {log.products_synced} products, "
          f"{log.errors_count} errors, {log.duration_seconds}s")
```

### Django Admin
```
http://localhost:8000/admin/ballstore/
```

## Troubleshooting

### Problem: "Module named 'django' not found"
**Solution:** Activate virtual environment
```bash
source env/bin/activate
```

### Problem: "BS_WOOCOMMERCE_API_URL not configured"
**Solution:** Check `.env` file and restart Django
```bash
# Verify settings
python manage.py shell
>>> from django.conf import settings
>>> print(settings.BS_WOO_URL)
```

### Problem: Connection errors
**Solution:** Test API directly
```bash
curl -u "ck_fa7230bc12287dc32b1514af4aa363768090c996:cs_f0e43e8d5037f57f8abee563c9e9f2f8bcb29760" \
  "https://theballstore.co.nz/wp-json/wc/v3/products?per_page=1"
```

## Next Steps

1. **Schedule Regular Syncs**: Set up cron job for hourly incremental syncs
2. **Monitor Logs**: Check `BallStoreSyncLog` table regularly
3. **Review Documentation**: See `README_SYNC.md` for comprehensive guide
4. **Build Features**: Use synced data in your application

## Support

- Full documentation: `ballstore/README_SYNC.md`
- Django admin: http://localhost:8000/admin/ballstore/
- Logs: Check Django logs for detailed error messages
