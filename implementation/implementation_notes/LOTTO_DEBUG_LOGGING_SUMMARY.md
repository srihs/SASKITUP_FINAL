# LOTTO Price Upload Debug Logging Summary

Comprehensive debug logging added to monitor LOTTO price uploads in the wholesale price update system.

## Debug Log Prefixes

- `[LOTTO-CATEGORY]` - Category selection and filtering
- `[LOTTO-MATCH]` - Product/variation matching operations
- `[LOTTO-PRICE]` - Price calculations
- `[LOTTO-UPDATE]` - Database update operations
- `[LOTTO-SUMMARY]` - Summary statistics and final results

## Backend Debug Logs (schools/views.py)

### Preview Function (wholesale_price_preview)

**Line 2311-2312**: Category selection
```python
logger.info(f"[LOTTO-CATEGORY] Category filter selected: {category}")
logger.info(f"[LOTTO-CATEGORY] Is LOTTO category: {category == 'lotto-clubs'}")
```

**Line 2404**: LOTTO variation loading
```python
logger.info(f"[LOTTO-MATCH] Loading {variations.count()} LOTTO variations")
```

**Line 2409**: LOTTO variation indexing
```python
logger.info(f"[LOTTO-MATCH] Indexed {len([k for k in products_by_variation.keys()])} LOTTO variations by sku_suffix")
```

**Line 2505-2506**: Product/variation matching (first 5 rows)
```python
if category == 'lotto-clubs' and row_count <= 5:
    logger.info(f"[LOTTO-MATCH] Row {row_num}: SKU='{product_code_clean}' -> Product={product.name if product else 'None'}, Variation={'Yes' if variation else 'No'}, Method={match_method}")
```

**Line 2514-2515**: Price field selection (first 5 rows)
```python
if category == 'lotto-clubs' and row_count <= 5:
    logger.info(f"[LOTTO-PRICE] Row {row_num}: price_field={price_field}, target_type={'variation' if variation else 'product'}")
```

**Line 2561-2562**: Price calculations (first 5 rows)
```python
if category == 'lotto-clubs' and row_count <= 5:
    logger.info(f"[LOTTO-PRICE] Row {row_num}: cost={cost_value}, margin_75={margin_75_price:.2f}, rrp={rrp:.2f}, discount={discount_percentage:.2f}%")
```

**Line 2663-2668**: Preview summary
```python
logger.info(f"[LOTTO-SUMMARY] CSV processing complete: {row_count} rows processed, "
           f"{valid_rows} valid products found, "
           f"{filtered_count} filtered out (stock=0 & cost=0, or not found)")
if category == 'lotto-clubs':
    logger.info(f"[LOTTO-SUMMARY] LOTTO preview data count: {len(preview_data)}")
    logger.info(f"[LOTTO-SUMMARY] LOTTO valid items: {valid_rows}")
```

### Apply Function (wholesale_price_apply)

**Line 2745-2750**: Category and item counts
```python
logger.info(f"[LOTTO-CATEGORY] Apply category: {category}")
logger.info(f"[LOTTO-SUMMARY] Valid items to process: {len(valid_items)} out of {len(all_items)} total items")
logger.info(f"[LOTTO-SUMMARY] Skipped items: {len(all_items) - len(valid_items)}")

if category == 'lotto-clubs':
    logger.info(f"[LOTTO-SUMMARY] Processing LOTTO price updates")
```

**Line 2886-2891**: Product/variation matching (first 10 items)
```python
if variation:
    logger.info(f"  ✅ Variation found by {search_method}: {product.name} - Variation ID {variation.id}")
    if category == 'lotto-clubs' and index <= 10:
        logger.info(f"[LOTTO-MATCH] Item {index}: Found LOTTO variation - SKU={product_code_clean}, Variation ID={variation.id}")
else:
    logger.info(f"  ✅ Product found by {search_method}: {product.name} (ID: {product.id})")
    if category == 'lotto-clubs' and index <= 10:
        logger.info(f"[LOTTO-MATCH] Item {index}: Found LOTTO product (no variation) - SKU={product_code_clean}")
```

**Line 2949-2950**: Cost price updates (first 10 items)
```python
if category == 'lotto-clubs' and index <= 10:
    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting cost_price={new_cost}")
```

**Line 2957-2958**: Margin price updates (first 10 items)
```python
if category == 'lotto-clubs' and index <= 10:
    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting margin_75_price={new_margin}")
```

**Line 2966-2967**: Discount percentage updates (first 10 items)
```python
if category == 'lotto-clubs' and index <= 10:
    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting discount_percentage={new_discount}%")
```

**Line 2979-2986**: Retail price updates (first 10 items)
```python
if variation:
    updates_to_apply['price'] = new_retail
    target.price = new_retail
    logger.info(f"  - Updating variation price: {new_retail}")
    if category == 'lotto-clubs' and index <= 10:
        logger.info(f"[LOTTO-UPDATE] Item {index}: Setting variation.price={new_retail}")
elif price_field:
    updates_to_apply[price_field] = new_retail
    setattr(target, price_field, new_retail)
    logger.info(f"  - Updating {price_field}: {new_retail}")
    if category == 'lotto-clubs' and index <= 10:
        logger.info(f"[LOTTO-UPDATE] Item {index}: Setting {price_field}={new_retail}")
```

**Line 3011-3021**: Database save operations (first 10 items)
```python
try:
    target.save(update_fields=update_fields)
    logger.debug(f"  - Database save successful")
    if category == 'lotto-clubs' and index <= 10:
        logger.info(f"[LOTTO-UPDATE] Item {index}: Database save SUCCESSFUL - fields={update_fields}")
except Exception as save_error:
    logger.error(f"  - Database save failed: {save_error}")
    if category == 'lotto-clubs':
        logger.error(f"[LOTTO-UPDATE] Item {index}: Database save FAILED - {save_error}")
    raise save_error

results['successful_updates'] += 1
if category == 'lotto-clubs' and index <= 10:
    logger.info(f"[LOTTO-UPDATE] Item {index}: Update count incremented - total={results['successful_updates']}")
```

**Line 3066-3080**: Final summary statistics
```python
logger.info("=== WHOLESALE PRICE APPLY SUMMARY ===")
logger.info(f"[LOTTO-SUMMARY] Total items processed: {processed_count}")
logger.info(f"[LOTTO-SUMMARY] Successfully updated: {results['successful_updates']}")
logger.info(f"[LOTTO-SUMMARY] Failed updates: {results['failed_updates']}")
logger.info(f"[LOTTO-SUMMARY] Products found by SKU: {found_by_sku_count}")
logger.info(f"[LOTTO-SUMMARY] Products found by barcode: {found_by_barcode_count}")
logger.info(f"[LOTTO-SUMMARY] Products not found: {not_found_count}")
logger.info(f"[LOTTO-SUMMARY] Update failures: {update_failed_count}")

if category == 'lotto-clubs':
    logger.info(f"[LOTTO-SUMMARY] ========== LOTTO FINAL STATS ==========")
    logger.info(f"[LOTTO-SUMMARY] Total LOTTO items: {len(all_items)}")
    logger.info(f"[LOTTO-SUMMARY] Valid LOTTO items: {len(valid_items)}")
    logger.info(f"[LOTTO-SUMMARY] LOTTO updates applied: {results['successful_updates']}")
    logger.info(f"[LOTTO-SUMMARY] LOTTO update failures: {results['failed_updates']}")
    logger.info(f"[LOTTO-SUMMARY] Success rate: {(results['successful_updates']/len(valid_items)*100):.1f}%" if len(valid_items) > 0 else "[LOTTO-SUMMARY] Success rate: N/A")
```

## Frontend Debug Logs (price_update_settings.html)

### File Upload (processFilesForPreview)

**Line 1408-1410**: Category filter selection
```javascript
if (categoryFilter.value === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] LOTTO category selected for preview');
}
```

**Line 1465-1468**: Preview response received
```javascript
if (data.category_filter === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] LOTTO preview response received');
    console.log('[LOTTO-SUMMARY] LOTTO items in response:', data.preview_data?.length || 0);
}
```

**Line 1480-1482**: File processing summary
```javascript
if (data.category_filter === 'lotto-clubs') {
    console.log(`[LOTTO-SUMMARY] LOTTO file processed: ${recordsInFile} matched, ${unmatchedRows} unmatched, ${totalRows} total`);
}
```

**Line 1490-1492**: Category storage
```javascript
if (data.category_filter === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] LOTTO category stored for apply');
}
```

**Line 1539-1541**: All files processed
```javascript
if (currentCategoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-SUMMARY] All LOTTO files processed - total items:', allPreviewData.length);
}
```

**Line 1561-1563**: Category stored globally
```javascript
if (currentCategoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] LOTTO category stored globally for apply');
}
```

### Apply Changes (applyPriceChanges)

**Line 2309-2313**: Apply operation start
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] Applying LOTTO price updates');
    console.log('[LOTTO-SUMMARY] Total items in preview data:', window.currentPreviewData?.length || 0);
    console.log('[LOTTO-SUMMARY] Valid items to apply:', validItems.length);
}
```

**Line 2322-2324**: Request data prepared
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-CATEGORY] Request data prepared for LOTTO apply');
}
```

**Line 2341-2349**: Apply response received
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-SUMMARY] LOTTO apply response:', {
        success: data.success,
        successful_updates: data.results?.successful_updates,
        failed_updates: data.results?.failed_updates,
        total_received: data.summary?.total_received,
        valid_items: data.summary?.valid_items
    });
}
```

**Line 2356-2358**: Updates completed
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-UPDATE] LOTTO updates completed:', data.results.successful_updates);
}
```

**Line 2367-2374**: Final results
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-SUMMARY] LOTTO final results:', {
        total_items: totalItems,
        valid_items: totalRecords,
        updates_applied: data.results.successful_updates,
        failed: data.results.failed_updates
    });
}
```

**Line 2400-2402**: Error logging
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-UPDATE] LOTTO update errors:', data.results.errors.length);
}
```

**Line 2410-2412**: First 5 updates logged
```javascript
if (categoryFilter === 'lotto-clubs') {
    console.log('[LOTTO-UPDATE] First 5 LOTTO updates:', data.results.updated_products.slice(0, 5));
}
```

## Usage

When uploading LOTTO price files:

1. Open browser console (F12)
2. Select "LOTTO Clubs" category
3. Upload CSV file
4. Monitor console for debug messages with prefixes:
   - `[LOTTO-CATEGORY]` - Track category selection
   - `[LOTTO-MATCH]` - See product/variation matching
   - `[LOTTO-PRICE]` - View price calculations
   - `[LOTTO-UPDATE]` - Monitor database updates
   - `[LOTTO-SUMMARY]` - Review statistics

Server logs will show:
- First 5 rows during preview (detailed matching and pricing)
- First 10 items during apply (detailed updates)
- Final summary with comprehensive statistics

## Key Insights from Debug Logs

1. **Variation Matching**: Check if SKUs are matched to LottoProductVariation via sku_suffix field
2. **Price Field Usage**: Verify variations use 'price' field (not 'retail_price')
3. **Update Success**: Track database save operations and success counts
4. **Filtering**: Monitor how many items are filtered out (stock=0 & cost=0)
5. **Success Rate**: Final statistics show percentage of successful updates
