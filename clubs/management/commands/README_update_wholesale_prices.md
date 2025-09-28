# Wholesale Price Update Management Command

## Overview

The `update_wholesale_prices` Django management command processes a CSV file containing product pricing information and updates the corresponding WholesaleProduct records with calculated pricing fields including `margin_75_price` and `discount_percentage`.

## Features

### Product Matching Logic
The command uses a cascading matching strategy to find products in the database:

1. **Primary Match**: CSV `Code` field → `WholesaleProduct.cin7_sku`
2. **Secondary Match**: CSV `Barcode` field → `WholesaleProduct.cin7_barcode` (if code is empty)
3. **Tertiary Match**: CSV `Style Code` field → `WholesaleProduct.cin7_id` (if barcode is empty)

### School Matching Logic
Schools are matched using intelligent name normalization:

1. **Primary**: CSV `School or Club Name` field → `WholesaleSchool.name`
2. **Fallback**: CSV `Sub Category` field → `WholesaleSchool.name` (if School or Club Name is empty)
3. **Normalization**: Case-insensitive matching with whitespace normalization
4. **School name cleanup**: Removes common suffixes like "school", "high school", "college"

### CSV Processing
- **Encoding Detection**: Automatically detects CSV encoding (UTF-8, Latin1, CP1252, etc.)
- **Large Field Handling**: Handles CSV files with very large text fields
- **Column Validation**: Validates that all required columns are present
- **Data Cleaning**: Strips whitespace and handles empty values

### Price Calculations
- **Cost Price**: Parses `Cost NZD Excl` field from CSV
- **75% Margin Price**: Calculates using formula: `Cost ÷ 0.25`
- **Discount Percentage**: Calculates discount from 75% margin price if current wholesale price exists

### Error Handling
- **Unmatched Products**: Tracks products that couldn't be found in database
- **Unmatched Schools**: Tracks schools that couldn't be found in database
- **Duplicate Matches**: Handles cases where multiple products/schools match
- **Invalid Data**: Handles invalid price data with detailed error reporting
- **Transaction Safety**: Uses database transactions to ensure data consistency

## Usage

### Basic Usage
```bash
python manage.py update_wholesale_prices
```

### Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--csv-file` | Path to CSV file | `/Users/sas/Downloads/All products.csv` |
| `--dry-run` | Preview changes without updating database | False |
| `--school-filter` | Filter processing to specific school (partial name match) | None |
| `--limit` | Limit number of rows to process (for testing) | None |
| `--verbose` | Enable verbose output | False |
| `--report-file` | Save detailed report to file | None |

### Examples

#### Dry Run (Preview Changes)
```bash
python manage.py update_wholesale_prices --dry-run --verbose
```

#### Process Specific School
```bash
python manage.py update_wholesale_prices --school-filter "onehunga" --dry-run
```

#### Limited Processing for Testing
```bash
python manage.py update_wholesale_prices --dry-run --limit 100 --verbose
```

#### Generate Detailed Report
```bash
python manage.py update_wholesale_prices --dry-run --report-file /path/to/report.txt
```

#### Production Run (Actual Update)
```bash
python manage.py update_wholesale_prices --verbose
```

## Output Reports

### Console Output
The command provides comprehensive reporting including:

- **Processing Summary**: Total rows, processed, skipped, updated, errors
- **Product Matching Statistics**: Breakdown by matching method
- **School Matching Statistics**: Breakdown by matching type
- **Error Reports**: First 10 errors with details
- **Unmatched Products**: First 10 unmatched products with reasons
- **Unmatched Schools**: First 10 unmatched schools with reasons

### Detailed Report File
When using `--report-file`, a comprehensive report is generated containing:

- All processing statistics
- Complete list of all errors
- Complete list of all unmatched products with details
- Complete list of all unmatched schools with details
- Timestamp and configuration information

## CSV File Format

### Required Columns
- `Code`: Product code for primary matching
- `Barcode`: Product barcode for secondary matching
- `Style Code`: Style code for tertiary matching
- `School or Club Name`: Primary school name field
- `Sub Category`: Fallback school name field
- `Product Name`: Product name for identification
- `Cost NZD Excl`: Cost price in NZD excluding GST

### Sample CSV Structure
```csv
Category,Sub Category,School or Club Name,Product Name,Code,Barcode,Style Code,Cost NZD Excl
Wholesale Schools,Onehunga High school,,Onehunga High School - Leavers Hoodie,HOOD 12 CL OHS LVS 25 -M,,92211,28.13
Clubs & Sportswear,Cricket,North Shore Cricket Club,North Shore Cricket Club Jacket,JKT 600CL NAVY NSCC -XS,,65919,24.98
```

## Database Updates

The command updates the following fields in `WholesaleProduct` model:

| Field | Description | Calculation |
|-------|-------------|-------------|
| `cost_price` | Cost price from CSV | Direct from `Cost NZD Excl` |
| `margin_75_price` | 75% margin price | `cost_price ÷ 0.25` |
| `discount_percentage` | Discount from 75% margin | `((margin_75_price - wholesale_price) ÷ margin_75_price) × 100` |
| `last_price_update` | Update timestamp | Current timestamp |

## Performance Considerations

### CSV Processing
- Automatically handles large CSV files (85,000+ rows tested)
- Processes fields up to 10,000 characters
- Uses memory-efficient row-by-row processing

### Database Operations
- Uses Django ORM with optimized queries
- School name cache for efficient matching
- Transaction-based updates for consistency
- Bulk processing capabilities

### Memory Usage
- Minimal memory footprint through streaming CSV processing
- Intelligent field truncation for very large text fields
- School cache optimization for repeated lookups

## Error Scenarios and Handling

### Common Issues

#### School Not Found
```
Row 7: School not found - North Shore Cricket Club
```
**Cause**: School doesn't exist in WholesaleSchool table
**Action**: School needs to be created first or check for name variations

#### Product Not Found
```
Row 15: Product not found - Product Name (Reason: no_match)
```
**Cause**: No product found matching Code, Barcode, or Style Code
**Action**: Check if product exists with different identifiers

#### Multiple Matches
```
Row 23: Product not found - Product Name (Reason: multiple_matches_by_code (3 found))
```
**Cause**: Multiple products have the same code/barcode
**Action**: Data cleanup required to ensure unique identifiers

#### Invalid Price Data
```
Row 45: Invalid cost price - abc123
```
**Cause**: Cost price field contains non-numeric data
**Action**: Clean price data in CSV

#### Product-School Mismatch
```
Row 67: Product ABC belongs to School X, not School Y
```
**Cause**: Matched product belongs to different school than CSV indicates
**Action**: Verify correct product-school relationships

## Best Practices

### Before Running
1. **Backup Database**: Always backup before production runs
2. **Test with Dry Run**: Use `--dry-run` to preview changes
3. **Start Small**: Use `--limit` for initial testing
4. **Check Schools**: Ensure target schools exist in database

### During Processing
1. **Monitor Progress**: Use `--verbose` for detailed output
2. **Save Reports**: Use `--report-file` for documentation
3. **Filter Testing**: Use `--school-filter` for focused testing

### After Running
1. **Review Reports**: Check unmatched items and errors
2. **Validate Updates**: Verify pricing calculations are correct
3. **Document Changes**: Keep records of processing runs

## Troubleshooting

### Large CSV Files
If processing very large CSV files:
```bash
# Process in chunks
python manage.py update_wholesale_prices --limit 10000 --report-file chunk1.txt
```

### Memory Issues
If experiencing memory issues:
```bash
# Use school filter to process smaller subsets
python manage.py update_wholesale_prices --school-filter "college" --report-file colleges.txt
```

### Encoding Issues
If CSV has encoding problems:
- The command automatically detects and handles common encodings
- Try saving CSV as UTF-8 if issues persist

### Performance Optimization
For large datasets:
```bash
# Process specific schools
python manage.py update_wholesale_prices --school-filter "target_school"

# Use limits for testing
python manage.py update_wholesale_prices --limit 1000 --dry-run
```

## Monitoring and Logging

### Database Logging
- All updates are logged with timestamps
- Transaction rollback on errors
- Audit trail in `last_price_update` field

### Error Tracking
- Comprehensive error collection
- Detailed error context and row numbers
- Categorized error types for analysis

### Progress Monitoring
- Real-time progress updates with `--verbose`
- Statistical breakdowns by matching method
- Performance metrics in reports

## Integration with Existing Systems

### CIN7 Integration
- Respects existing CIN7 field mappings
- Maintains CIN7 identifier relationships
- Compatible with existing sync processes

### WooCommerce Integration
- Updates don't interfere with WooCommerce sync
- Maintains product relationship integrity
- Supports existing wholesale pricing structures

### Reporting Integration
- Report format compatible with business analysis tools
- CSV-friendly detailed reports
- Structured data for further processing

## Security Considerations

### Data Validation
- All input data is validated and sanitized
- Decimal precision controlled for financial data
- SQL injection protection through Django ORM

### Access Control
- Management command requires Django admin access
- Database transaction safety
- Audit trail for all changes

### File Handling
- Secure file path validation
- Encoding detection prevents malicious content
- Memory limits prevent resource exhaustion