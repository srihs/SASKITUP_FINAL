-- ============================================================================
-- BESPOKE PRODUCTS - PRICE UPDATE ANALYSIS & FIX
-- ============================================================================
-- Purpose: Analyze current bespoke pricing and optionally set price = margin_75_price
-- Date: 2025-11-12
-- ============================================================================

-- ============================================================================
-- SECTION 1: CURRENT STATE ANALYSIS
-- ============================================================================

-- 1.1: Overall Statistics
SELECT
    'OVERALL STATISTICS' as section,
    '' as subsection,
    '' as metric,
    '' as value;

SELECT
    'Products' as section,
    'Total' as subsection,
    'Total Active Products' as metric,
    COUNT(*)::text as value
FROM bespoke_product
WHERE is_active = true
UNION ALL
SELECT
    'Products' as section,
    'With Pricing' as subsection,
    'Have Cost Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product
WHERE is_active = true AND cost_price > 0
UNION ALL
SELECT
    'Products' as section,
    'With Pricing' as subsection,
    'Have Margin 75% Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product
WHERE is_active = true AND margin_75_price > 0
UNION ALL
SELECT
    'Products' as section,
    'With Pricing' as subsection,
    'Have Selling Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product
WHERE is_active = true AND price > 0
UNION ALL
SELECT
    'Products' as section,
    'Pricing Issues' as subsection,
    'Price != Margin (needs update)' as metric,
    COUNT(*)::text as value
FROM bespoke_product
WHERE is_active = true
  AND cost_price > 0
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01)

UNION ALL

SELECT
    'Variations' as section,
    'Total' as subsection,
    'Total Active Variations' as metric,
    COUNT(*)::text as value
FROM bespoke_product_variation
WHERE is_active = true
UNION ALL
SELECT
    'Variations' as section,
    'With Pricing' as subsection,
    'Have Cost Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product_variation
WHERE is_active = true AND cost_price > 0
UNION ALL
SELECT
    'Variations' as section,
    'With Pricing' as subsection,
    'Have Margin 75% Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product_variation
WHERE is_active = true AND margin_75_price > 0
UNION ALL
SELECT
    'Variations' as section,
    'With Pricing' as subsection,
    'Have Selling Price' as metric,
    COUNT(*)::text as value
FROM bespoke_product_variation
WHERE is_active = true AND price > 0
UNION ALL
SELECT
    'Variations' as section,
    'Pricing Issues' as subsection,
    'Price != Margin (needs update)' as metric,
    COUNT(*)::text as value
FROM bespoke_product_variation
WHERE is_active = true
  AND cost_price > 0
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01)
ORDER BY section, subsection, metric;


-- 1.2: Price Distribution Analysis
SELECT
    'PRICE DISTRIBUTION' as analysis_type,
    '' as details;

SELECT
    'Products Price Distribution' as category,
    CASE
        WHEN price IS NULL THEN 'No Price Set'
        WHEN price = 0 THEN 'Price = $0'
        WHEN price < 10 THEN '$0-$10'
        WHEN price < 50 THEN '$10-$50'
        WHEN price < 100 THEN '$50-$100'
        WHEN price < 500 THEN '$100-$500'
        ELSE '$500+'
    END as price_range,
    COUNT(*) as product_count,
    ROUND(AVG(cost_price)::numeric, 2) as avg_cost,
    ROUND(AVG(margin_75_price)::numeric, 2) as avg_margin_75,
    ROUND(AVG(price)::numeric, 2) as avg_selling_price
FROM bespoke_product
WHERE is_active = true
GROUP BY
    CASE
        WHEN price IS NULL THEN 'No Price Set'
        WHEN price = 0 THEN 'Price = $0'
        WHEN price < 10 THEN '$0-$10'
        WHEN price < 50 THEN '$10-$50'
        WHEN price < 100 THEN '$50-$100'
        WHEN price < 500 THEN '$100-$500'
        ELSE '$500+'
    END
ORDER BY product_count DESC;


-- 1.3: Sample Products Analysis (First 20)
SELECT
    'SAMPLE PRODUCTS (First 20)' as analysis_type,
    '' as details;

SELECT
    id,
    name,
    sku,
    barcode,
    ROUND(cost_price::numeric, 2) as cost,
    ROUND(margin_75_price::numeric, 2) as margin_75,
    ROUND(price::numeric, 2) as current_price,
    CASE
        WHEN price IS NULL THEN 'NO PRICE'
        WHEN ABS(price - margin_75_price) < 0.01 THEN 'CORRECT'
        WHEN price < margin_75_price THEN 'BELOW MARGIN'
        WHEN price > margin_75_price THEN 'ABOVE MARGIN'
    END as pricing_status,
    CASE
        WHEN margin_75_price > 0 AND price > 0
            THEN ROUND(((price - margin_75_price) / margin_75_price * 100)::numeric, 1)
        ELSE 0
    END as price_diff_pct
FROM bespoke_product
WHERE is_active = true
  AND cost_price > 0
ORDER BY id
LIMIT 20;


-- 1.4: Margin Calculation Verification
SELECT
    'MARGIN CALCULATION VERIFICATION' as analysis_type,
    '' as details;

SELECT
    'Products' as type,
    COUNT(*) as total_with_cost,
    COUNT(CASE WHEN margin_75_price IS NOT NULL THEN 1 END) as has_margin_75,
    COUNT(CASE WHEN cost_price > 0 AND margin_75_price IS NULL THEN 1 END) as missing_margin,
    COUNT(CASE
        WHEN cost_price > 0 AND margin_75_price > 0
            AND ABS(margin_75_price - (cost_price / 0.25)) < 0.01
        THEN 1
    END) as margin_correct,
    COUNT(CASE
        WHEN cost_price > 0 AND margin_75_price > 0
            AND ABS(margin_75_price - (cost_price / 0.25)) >= 0.01
        THEN 1
    END) as margin_incorrect
FROM bespoke_product
WHERE is_active = true AND cost_price > 0

UNION ALL

SELECT
    'Variations' as type,
    COUNT(*) as total_with_cost,
    COUNT(CASE WHEN margin_75_price IS NOT NULL THEN 1 END) as has_margin_75,
    COUNT(CASE WHEN cost_price > 0 AND margin_75_price IS NULL THEN 1 END) as missing_margin,
    COUNT(CASE
        WHEN cost_price > 0 AND margin_75_price > 0
            AND ABS(margin_75_price - (cost_price / 0.25)) < 0.01
        THEN 1
    END) as margin_correct,
    COUNT(CASE
        WHEN cost_price > 0 AND margin_75_price > 0
            AND ABS(margin_75_price - (cost_price / 0.25)) >= 0.01
        THEN 1
    END) as margin_incorrect
FROM bespoke_product_variation
WHERE is_active = true AND cost_price > 0;


-- 1.5: Products by Category Assignment
SELECT
    'PRODUCTS BY CATEGORY' as analysis_type,
    '' as details;

SELECT
    c.name as category_name,
    COUNT(DISTINCT p.id) as product_count,
    COUNT(DISTINCT CASE WHEN p.price > 0 THEN p.id END) as products_with_price,
    COUNT(DISTINCT CASE WHEN p.margin_75_price > 0 THEN p.id END) as products_with_margin,
    ROUND(AVG(p.price)::numeric, 2) as avg_selling_price,
    ROUND(AVG(p.margin_75_price)::numeric, 2) as avg_margin_75_price
FROM bespoke_category c
LEFT JOIN bespoke_product_category_assignment pa ON pa.category_id = c.id
LEFT JOIN bespoke_product p ON p.id = pa.product_id AND p.is_active = true
WHERE c.is_active = true
GROUP BY c.id, c.name
ORDER BY product_count DESC;


-- ============================================================================
-- SECTION 2: IDENTIFY PRODUCTS NEEDING UPDATE
-- ============================================================================

SELECT
    'PRODUCTS NEEDING UPDATE' as analysis_type,
    '' as details;

-- 2.1: Products where price != margin_75_price
SELECT
    'Products (price != margin_75_price)' as category,
    id,
    name,
    sku,
    ROUND(cost_price::numeric, 2) as cost,
    ROUND(margin_75_price::numeric, 2) as should_be,
    ROUND(price::numeric, 2) as current_price,
    ROUND((margin_75_price - COALESCE(price, 0))::numeric, 2) as price_difference
FROM bespoke_product
WHERE is_active = true
  AND cost_price > 0
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01)
ORDER BY margin_75_price DESC
LIMIT 50;

-- 2.2: Variations where price != margin_75_price
SELECT
    'Variations (price != margin_75_price)' as category,
    v.id,
    p.name as product_name,
    v.sku,
    ROUND(v.cost_price::numeric, 2) as cost,
    ROUND(v.margin_75_price::numeric, 2) as should_be,
    ROUND(v.price::numeric, 2) as current_price,
    ROUND((v.margin_75_price - COALESCE(v.price, 0))::numeric, 2) as price_difference
FROM bespoke_product_variation v
JOIN bespoke_product p ON p.id = v.parent_product_id
WHERE v.is_active = true
  AND v.cost_price > 0
  AND v.margin_75_price > 0
  AND (v.price IS NULL OR ABS(v.price - v.margin_75_price) > 0.01)
ORDER BY v.margin_75_price DESC
LIMIT 50;


-- ============================================================================
-- SECTION 3: PRE-UPDATE SUMMARY
-- ============================================================================

SELECT
    'PRE-UPDATE SUMMARY' as analysis_type,
    '' as details;

-- Count of products that will be updated
SELECT
    'Products to Update' as item,
    COUNT(*) as count,
    ROUND(SUM(margin_75_price)::numeric, 2) as total_value,
    ROUND(AVG(margin_75_price)::numeric, 2) as avg_value
FROM bespoke_product
WHERE is_active = true
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01)

UNION ALL

SELECT
    'Variations to Update' as item,
    COUNT(*) as count,
    ROUND(SUM(margin_75_price)::numeric, 2) as total_value,
    ROUND(AVG(margin_75_price)::numeric, 2) as avg_value
FROM bespoke_product_variation
WHERE is_active = true
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01);


-- ============================================================================
-- SECTION 4: THE FIX (UNCOMMENT TO EXECUTE)
-- ============================================================================
-- WARNING: This will update prices for ALL active bespoke products
-- Only uncomment and run after reviewing the analysis above!
-- ============================================================================

/*
-- Begin transaction for safety
BEGIN;

-- 4.1: Update BespokeProduct prices
UPDATE bespoke_product
SET
    price = margin_75_price,
    updated_at = NOW()
WHERE is_active = true
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01);

-- Check products update count
SELECT 'Products Updated' as status, COUNT(*) as count
FROM bespoke_product
WHERE is_active = true
  AND margin_75_price > 0
  AND ABS(price - margin_75_price) < 0.01;


-- 4.2: Update BespokeProductVariation prices
UPDATE bespoke_product_variation
SET
    price = margin_75_price,
    updated_at = NOW()
WHERE is_active = true
  AND margin_75_price > 0
  AND (price IS NULL OR ABS(price - margin_75_price) > 0.01);

-- Check variations update count
SELECT 'Variations Updated' as status, COUNT(*) as count
FROM bespoke_product_variation
WHERE is_active = true
  AND margin_75_price > 0
  AND ABS(price - margin_75_price) < 0.01;


-- 4.3: Verification - All prices should match margin now
SELECT
    'Verification: Products' as type,
    COUNT(*) as total_active,
    COUNT(CASE WHEN price > 0 THEN 1 END) as with_price,
    COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as price_equals_margin,
    COUNT(CASE WHEN ABS(price - margin_75_price) >= 0.01 THEN 1 END) as price_differs
FROM bespoke_product
WHERE is_active = true AND margin_75_price > 0

UNION ALL

SELECT
    'Verification: Variations' as type,
    COUNT(*) as total_active,
    COUNT(CASE WHEN price > 0 THEN 1 END) as with_price,
    COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as price_equals_margin,
    COUNT(CASE WHEN ABS(price - margin_75_price) >= 0.01 THEN 1 END) as price_differs
FROM bespoke_product_variation
WHERE is_active = true AND margin_75_price > 0;

-- If everything looks good, commit the transaction
-- Otherwise, rollback with: ROLLBACK;
-- COMMIT;
*/


-- ============================================================================
-- SECTION 5: POST-UPDATE VERIFICATION (RUN AFTER EXECUTING THE FIX)
-- ============================================================================
-- Uncomment this section after running the fix to verify results
-- ============================================================================

/*
SELECT
    'POST-UPDATE VERIFICATION' as analysis_type,
    '' as details;

-- 5.1: Overall Success Rate
SELECT
    'Products' as type,
    COUNT(*) as total_with_margin,
    COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as correctly_priced,
    COUNT(CASE WHEN ABS(price - margin_75_price) >= 0.01 THEN 1 END) as incorrectly_priced,
    ROUND(
        COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END)::numeric
        / COUNT(*)::numeric * 100,
        2
    ) as success_rate_pct
FROM bespoke_product
WHERE is_active = true AND margin_75_price > 0

UNION ALL

SELECT
    'Variations' as type,
    COUNT(*) as total_with_margin,
    COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as correctly_priced,
    COUNT(CASE WHEN ABS(price - margin_75_price) >= 0.01 THEN 1 END) as incorrectly_priced,
    ROUND(
        COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END)::numeric
        / COUNT(*)::numeric * 100,
        2
    ) as success_rate_pct
FROM bespoke_product_variation
WHERE is_active = true AND margin_75_price > 0;


-- 5.2: Sample verification (first 10 products)
SELECT
    'Sample Post-Update Products' as verification_type,
    id,
    name,
    ROUND(cost_price::numeric, 2) as cost,
    ROUND(margin_75_price::numeric, 2) as margin_75,
    ROUND(price::numeric, 2) as selling_price,
    CASE
        WHEN ABS(price - margin_75_price) < 0.01 THEN '✓ CORRECT'
        ELSE '✗ INCORRECT'
    END as status
FROM bespoke_product
WHERE is_active = true AND margin_75_price > 0
ORDER BY id
LIMIT 10;
*/


-- ============================================================================
-- END OF SCRIPT
-- ============================================================================

SELECT
    'ANALYSIS COMPLETE' as status,
    'Review results above before running Section 4 (THE FIX)' as next_step;
