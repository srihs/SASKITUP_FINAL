# Price Update Logging System

## Overview

This directory contains a dedicated logging system for tracking price update operations across all product categories (Wholesale Schools, TUS Schools, SAS Clubs, LOTTO Clubs).

## Components

### 1. PriceUpdateLogger (`price_update_logger.py`)

Thread-safe singleton logger class that provides specialized logging for price update operations.

**Features:**
- Separate log file (`priceupdate.log`) with automatic rotation
- Structured message formatting with operation types
- Thread-safe logging for concurrent operations
- Detailed tracking of matches, updates, errors, and performance

**Log File Location:**
- Primary: `/logs/priceupdate.log`
- Fallback: `<project_root>/priceupdate.log`

**Log File Rotation:**
- Maximum size: 10MB
- Backup count: 5 files
- Format: `[%(asctime)s] [%(levelname)s] [%(operation)s] %(message)s`

### 2. Logging Configuration (`logging_config.py`)

Django settings integration for the price update logging system.

**Usage in settings.py:**
```python
from schools.utils.logging_config import PRICE_UPDATE_LOGGING_CONFIG

# Merge with existing LOGGING configuration
LOGGING['handlers'].update(PRICE_UPDATE_LOGGING_CONFIG['handlers'])
LOGGING['formatters'].update(PRICE_UPDATE_LOGGING_CONFIG['formatters'])
LOGGING['loggers'].update(PRICE_UPDATE_LOGGING_CONFIG['loggers'])
```

## Usage

### Basic Usage

```python
from schools.utils.price_update_logger import price_logger

# Start operation
price_logger.log_start(total_items=86671, category='lotto-clubs')

# Log successful match
price_logger.log_match(
    row_number=1,
    product_code='R9039 -4--7',
    target_type='LottoProductVariation',
    target_id=1234,
    match_method='sku_suffix_exact'
)

# Log failed match
price_logger.log_no_match(
    row_number=2,
    product_code='ABC123',
    barcode='',
    tried_fields=['sku', 'sku_suffix', 'barcode']
)

# Log price update
from decimal import Decimal

price_logger.log_update(
    target_type='Variation',
    target_id=1234,
    old_cost=Decimal('0.00'),
    new_cost=Decimal('5.50'),
    old_margin=Decimal('20.00'),
    new_margin=Decimal('22.00'),
    old_retail=Decimal('30.00'),
    new_retail=Decimal('35.00')
)

# Log error
price_logger.log_error(
    row_number=3,
    product_code='XYZ789',
    error_message='Invalid cost value: N/A'
)

# Log performance timing
price_logger.log_performance(
    phase='matching',
    duration_seconds=15.3,
    items_count=86671
)

# Log summary
price_logger.log_summary({
    'total_items': 86671,
    'matched': 85000,
    'no_match': 1500,
    'errors': 171,
    'duration_seconds': 27.3,
    'category': 'lotto-clubs'
})
```

## Available Logging Methods

### `log_start(total_items, category)`
Log the start of a price update operation.

**Example:**
```
[2025-10-10 12:34:56] [INFO] [START] Price update started: 86671 items | Category: lotto-clubs
```

### `log_match(row_number, product_code, target_type, target_id, match_method)`
Log a successful product/variation match.

**Example:**
```
[2025-10-10 12:34:58] [INFO] [MATCH] Row 1: Matched "R9039 -4--7" to LottoProductVariation #1234 via sku_suffix_exact
```

### `log_no_match(row_number, product_code, barcode, tried_fields)`
Log a failed product match.

**Example:**
```
[2025-10-10 12:34:58] [WARNING] [NO_MATCH] Row 2: No match for "ABC123" (tried: sku, sku_suffix, barcode)
```

### `log_update(target_type, target_id, old_cost, new_cost, old_margin, new_margin, old_retail, new_retail)`
Log a price update with before/after values.

**Example:**
```
[2025-10-10 12:34:58] [INFO] [UPDATE] Variation #1234: cost $0.00 → $5.50, margin $20.00 → $22.00, retail $30.00 → $35.00
```

### `log_error(row_number, product_code, error_message)`
Log an error during processing.

**Example:**
```
[2025-10-10 12:34:58] [ERROR] [ERROR] Row 3: Error processing "XYZ789" - Invalid cost value: N/A
```

### `log_validation_error(row_number, field_name, field_value, error_reason)`
Log a data validation error.

**Example:**
```
[2025-10-10 12:34:59] [WARNING] [VALIDATION] Row 4: Invalid cost value "invalid" - Not a valid decimal number
```

### `log_performance(phase, duration_seconds, items_count=None)`
Log performance timing for a specific phase.

**Example:**
```
[2025-10-10 12:35:15] [INFO] [PERFORMANCE] Phase: matching | Duration: 15.30s | Items: 86671 | Rate: 5663 items/s
```

### `log_summary(stats)`
Log operation summary with statistics.

**Example:**
```
[2025-10-10 12:35:25] [INFO] [SUMMARY] Completed: 85000 matched (98.1%), 1500 no match (1.7%), 171 errors (0.2%) | Duration: 27.3s | Throughput: 3175 items/s | Category: lotto-clubs
```

### Additional Methods

- `log_category_switch(from_category, to_category)` - Log category switches
- `log_backup_created(target_type, target_id, backup_data)` - Log backup creation
- `log_bulk_update_start(chunk_number, chunk_size, total_items)` - Log bulk update chunks

## Integration Points

### BulkPriceUpdater Service

The logger is integrated into `/Users/sas/Repos/SASKITUP/schools/services/bulk_price_updater.py` and automatically logs:
- Operation start with item count
- Product/variation matches with methods
- Failed matches with attempted fields
- Price updates with before/after values
- Errors with context
- Performance timings for each phase
- Summary statistics

### wholesale_price_apply View

The logger is integrated into `/Users/sas/Repos/SASKITUP/schools/views.py` (wholesale_price_apply function) and logs:
- Sequential update operations
- Match/no-match events
- Price changes
- Errors
- Performance and summary

## Log Message Examples

### Successful Operation
```
[2025-10-10 12:34:56] [INFO] [START] Price update started: 86671 items | Category: lotto-clubs
[2025-10-10 12:34:58] [INFO] [MATCH] Row 1: Matched "R9039 -4--7" to Variation #1234 via sku_suffix_exact
[2025-10-10 12:34:58] [INFO] [UPDATE] Variation #1234: cost $0.00 → $5.50, margin $22.00
[2025-10-10 12:34:58] [INFO] [MATCH] Row 2: Matched "R9040 -5--8" to Variation #5678 via sku_suffix_normalized
[2025-10-10 12:34:58] [INFO] [UPDATE] Variation #5678: retail $25.00 → $28.00
...
[2025-10-10 12:35:15] [INFO] [PERFORMANCE] Phase: preload | Duration: 2.50s
[2025-10-10 12:35:15] [INFO] [PERFORMANCE] Phase: matching | Duration: 15.30s | Items: 86671 | Rate: 5663 items/s
[2025-10-10 12:35:15] [INFO] [PERFORMANCE] Phase: update | Duration: 10.20s | Items: 85000 | Rate: 8333 items/s
[2025-10-10 12:35:25] [INFO] [SUMMARY] Completed: 85000 matched (98.1%), 1500 no match (1.7%), 171 errors (0.2%) | Duration: 27.3s | Throughput: 3175 items/s | Category: lotto-clubs
```

### With Errors
```
[2025-10-10 12:34:56] [INFO] [START] Price update started: 100 items | Category: sas-clubs
[2025-10-10 12:34:58] [WARNING] [NO_MATCH] Row 2: No match for "ABC123" (tried: sku, sku_suffix, barcode)
[2025-10-10 12:34:58] [ERROR] [ERROR] Row 3: Error processing "XYZ789" - Invalid cost value: N/A
[2025-10-10 12:34:59] [WARNING] [VALIDATION] Row 4: Invalid cost value "invalid" - Not a valid decimal number
...
[2025-10-10 12:35:00] [INFO] [SUMMARY] Completed: 95 matched (95.0%), 3 no match (3.0%), 2 errors (2.0%) | Duration: 4.5s | Throughput: 22 items/s | Category: sas-clubs
```

## Thread Safety

The PriceUpdateLogger uses a singleton pattern with thread-safe initialization using `threading.Lock()`. This ensures:
- Single logger instance across the application
- Thread-safe logging operations
- No duplicate log entries
- Consistent log file handling

## Performance Impact

The logging system is designed for minimal performance overhead:
- Asynchronous log writing to file
- Efficient string formatting
- Minimal memory footprint
- No blocking operations

**Estimated overhead:**
- <1ms per log entry
- <0.1% total operation time for 80,000+ item updates

## Troubleshooting

### Log File Not Created

1. Check directory permissions:
   ```bash
   ls -la /Users/sas/Repos/SASKITUP/logs/
   ```

2. Verify Django BASE_DIR setting:
   ```python
   from django.conf import settings
   print(settings.BASE_DIR)
   ```

3. Check for write permissions:
   ```bash
   touch /Users/sas/Repos/SASKITUP/logs/priceupdate.log
   ```

### No Log Entries

1. Verify logger import:
   ```python
   from schools.utils.price_update_logger import price_logger
   print(price_logger.logger.handlers)
   ```

2. Check log level:
   ```python
   print(price_logger.logger.level)  # Should be 10 (INFO)
   ```

3. Verify file handler:
   ```python
   for handler in price_logger.logger.handlers:
       print(f"{handler.__class__.__name__}: {handler.baseFilename}")
   ```

### Log Rotation Not Working

1. Check file size limit (10MB):
   ```bash
   ls -lh /Users/sas/Repos/SASKITUP/logs/priceupdate.log*
   ```

2. Verify backup count (5 files):
   ```bash
   ls -1 /Users/sas/Repos/SASKITUP/logs/priceupdate.log* | wc -l
   ```

## Best Practices

1. **Always log operation start and summary:**
   ```python
   price_logger.log_start(len(items), category)
   # ... processing ...
   price_logger.log_summary(stats)
   ```

2. **Log match results for debugging:**
   ```python
   if product:
       price_logger.log_match(...)
   else:
       price_logger.log_no_match(...)
   ```

3. **Log all price changes:**
   ```python
   if updates:
       price_logger.log_update(...)
   ```

4. **Log errors with context:**
   ```python
   except Exception as e:
       price_logger.log_error(row_number, product_code, str(e))
   ```

5. **Log performance for optimization:**
   ```python
   start = time.time()
   # ... operation ...
   price_logger.log_performance('operation_name', time.time() - start)
   ```

## Example Integration

See `/Users/sas/Repos/SASKITUP/schools/services/bulk_price_updater.py` for a complete integration example.

## Author

Created by Claude Code on 2025-10-10
