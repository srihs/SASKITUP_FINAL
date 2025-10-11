# Quotation New Page - Performance Optimization Plan

## Executive Summary

**Current Performance Issues:**
- **Clubs Tab**: 2,873ms load time, 1,104 queries, 1,477ms DB time
- **Schools Tab**: 1,045ms load time, 77 queries, 521ms DB time
- **Critical Issue**: Severe N+1 query problem with product variations (1,093 variation queries on Clubs tab)

**Performance Goals:**
- **Target Load Time**: < 500ms for both tabs
- **Target Query Count**: < 20 queries per page
- **Target DB Time**: < 100ms

**Expected Improvements:**
- **90% reduction** in query count
- **75% reduction** in load time
- **85% reduction** in database time

---

## Performance Test Results

### Test Metrics Summary

| Test Case | Load Time (ms) | Queries | DB Time (ms) | Performance Score |
|-----------|----------------|---------|--------------|-------------------|
| Schools Tab | 1,045 | 77 | 521 | 1,199 |
| **Clubs Tab** | **2,873** | **1,104** | **1,477** | **5,081** |
| Schools Search | 254 | 46 | 182 | 346 |
| Schools Page 2 | 1,170 | 72 | 539 | 1,314 |

### Critical Findings

#### 1. **Severe N+1 Query Problem** (CRITICAL)
- **Clubs Tab**: 1,093 product variation queries
- **Schools Tab**: 56 product variation queries
- **Root Cause**: Accessing `product.variations.all()` in Python loop after converting QuerySet to list
- **Line Reference**: Lines 1455, 1467, 1612, 1621 in `quotations/views.py`

```python
# Current problematic code:
variations = list(product.variations.all())  # N+1 query!
```

#### 2. **Inefficient Pagination Strategy** (HIGH)
- Converting QuerySets to lists before pagination (lines 1447-1448, 1604-1605)
- Forces loading ALL products into memory even when showing only 24 per page
- Prevents database-level pagination optimization

```python
# Current problematic code:
tus_products_list = list(tus_products_qs)  # Loads ALL products
wholesale_products_list = list(wholesale_products_qs)  # Loads ALL products
```

#### 3. **Table Access Hotspots**
```
LOTTO_PRODUCT_VARIATIONS: 504 accesses
SAS_PRODUCT_VARIATIONS: 594 accesses
LOTTO_PRODUCTS: 503 accesses
SAS_PRODUCTS: 261 accesses
```

#### 4. **Slowest Queries**
1. 335ms - TUS Product Variations fetch (line 1378)
2. 339ms - Lotto Product Variations fetch (line 1592)
3. 122ms - SAS Product Variations fetch (line 1556)

---

## Identified Bottlenecks

### Code Analysis by Section

#### **Lines 1447-1472: Schools Tab - TUS/Wholesale Products**

**Issues:**
1. ❌ Converts QuerySets to lists (lines 1447-1448)
2. ❌ N+1 queries for variations (lines 1455, 1467)
3. ❌ Calls `_get_variation_display_data()` which iterates variations
4. ❌ Calls `_group_wholesale_products_by_base_sku()` with list

**Impact:**
- 77 queries for Schools Tab
- 521ms database time
- Loads all products regardless of pagination

#### **Lines 1604-1626: Clubs Tab - SAS/Lotto Products**

**Issues:**
1. ❌ Converts QuerySets to lists (lines 1604-1605)
2. ❌ N+1 queries for variations (lines 1612, 1621)
3. ❌ Filters variations after fetch (`.filter(is_active=True)`)
4. ❌ Multiple variation table accesses per product

**Impact:**
- **1,104 queries** for Clubs Tab (14x worse than Schools)
- **1,477ms database time** (3x worse than Schools)
- Severe performance degradation

#### **Lines 1770-1836: `_get_variation_display_data()` Method**

**Issues:**
1. ❌ Iterates through variations in Python
2. ❌ Performs attribute access and parsing per variation
3. ❌ Builds display data structures in Python vs. database

**Impact:**
- Called once per product with variations
- Additional processing time per product
- Memory overhead for display data structures

#### **Lines 1672-1718: `_group_wholesale_products_by_base_sku()` Method**

**Issues:**
1. ❌ Python-based grouping logic
2. ❌ Regex operations in Python loop
3. ❌ Builds complex data structures in memory

**Impact:**
- CPU-intensive operation
- Could be optimized with database aggregation

---

## Optimization Plan (Prioritized)

### **PRIORITY 1: CRITICAL - Fix N+1 Variation Queries**

**Impact**: 90% reduction in queries, 70% reduction in load time

#### Solution 1A: Lazy Load Variation Data (Quick Win)
**Implementation Time**: 30 minutes
**Expected Improvement**: 85% query reduction

Only fetch variations for products that will be displayed on current page.

```python
# BEFORE (lines 1447-1472):
tus_products_list = list(tus_products_qs)  # Loads ALL products
for product in tus_products_list:
    if product.has_variations:
        variations = list(product.variations.all())  # N+1!

# AFTER:
combined_products = list(tus_products_qs) + list(wholesale_products_qs)
paginator = Paginator(combined_products, self.paginate_by)
page_obj = paginator.get_page(page)

# Only process products on CURRENT page
for product in page_obj.object_list:
    product.product_type = 'tusproduct' if isinstance(product, TUSProduct) else 'wholesaleproduct'
    if product.has_variations:
        variations = list(product.variations.all())  # Only N queries where N = products per page (24)
        product.variation_display = self._get_variation_display_data(variations, product.product_type)
```

**Files to Modify**:
- `quotations/views.py` - Lines 1447-1472 (Schools Tab)
- `quotations/views.py` - Lines 1604-1626 (Clubs Tab)

**Testing Steps**:
1. Test Schools Tab - verify variations display correctly
2. Test Clubs Tab - verify variations display correctly
3. Test pagination - verify variations on page 2, 3, etc.
4. Run performance test - confirm query count reduction

---

#### Solution 1B: Optimize Prefetch Strategy (Best Practice)
**Implementation Time**: 1 hour
**Expected Improvement**: 95% query reduction + better pagination

Use Django's `Prefetch` object to optimize variation fetching with filters.

```python
from django.db.models import Prefetch

# CLUBS TAB - Lines 1543-1556
sas_products_qs = SASProduct.objects.filter(
    club__in=sas_clubs,
    is_active=True
).annotate(
    has_stock_variation=has_stock_variation_sas,
    has_any_variation=has_any_variation_sas
).filter(
    Q(
        Q(has_any_variation=True, has_stock_variation=True) |
        Q(has_any_variation=False, stock_status__in=['instock', 'onbackorder'])
    )
).select_related('club').prefetch_related(
    Prefetch(
        'variations',
        queryset=SASProductVariation.objects.filter(is_active=True).only(
            'id', 'product_id', 'variation_type', 'variation_value',
            'stock_quantity', 'sku_suffix'
        )
    )
)
```

**Benefits**:
- Single query for all variations
- Filter applied at database level
- Only fetch needed fields (`only()`)
- Supports pagination better

---

### **PRIORITY 2: HIGH - Implement Smart Pagination**

**Impact**: 50% reduction in memory usage, enables further optimizations

#### Solution 2A: Defer Variation Data Until After Pagination
**Implementation Time**: 45 minutes
**Expected Improvement**: Minimal additional queries (24 instead of 1,104)

```python
# Step 1: Get products WITHOUT fetching variations
tus_products_qs = TUSProduct.objects.filter(...).defer('description')  # Defer heavy fields

# Step 2: Combine and paginate
combined_products = list(tus_products_qs) + list(wholesale_products_qs)
paginator = Paginator(combined_products, self.paginate_by)
page_obj = paginator.get_page(page)

# Step 3: Fetch variations ONLY for current page products
product_ids_on_page = [p.id for p in page_obj.object_list if isinstance(p, TUSProduct)]

if product_ids_on_page:
    variations_by_product = {}
    variations = TUSProductVariation.objects.filter(
        product_id__in=product_ids_on_page,
        is_active=True
    ).select_related('product')

    for variation in variations:
        if variation.product_id not in variations_by_product:
            variations_by_product[variation.product_id] = []
        variations_by_product[variation.product_id].append(variation)

    # Attach variations to products
    for product in page_obj.object_list:
        if isinstance(product, TUSProduct):
            product.variation_display = self._get_variation_display_data(
                variations_by_product.get(product.id, []),
                'tus'
            )
```

---

#### Solution 2B: Database-Level Pagination (Advanced)
**Implementation Time**: 2 hours
**Expected Improvement**: True database-level pagination

Create a unified products view/table or use PostgreSQL materialized views.

**Note**: This requires schema changes and is recommended for Phase 2.

---

### **PRIORITY 3: MEDIUM - Optimize Variation Display Logic**

**Impact**: 30% reduction in processing time

#### Solution 3A: Move Variation Parsing to Database
**Implementation Time**: 1 hour

Add computed fields or cached properties to variation models:

```python
# In SASProductVariation model
class SASProductVariation(models.Model):
    # ... existing fields ...

    @cached_property
    def parsed_size(self):
        """Extract size from variation_value."""
        if ' - ' in self.variation_value:
            return self.variation_value.split(' - ')[0].strip()
        return self.variation_value if self.variation_type in ['size', 'pa_size'] else ''

    @cached_property
    def parsed_color(self):
        """Extract color from variation_value."""
        if ' - ' in self.variation_value:
            return self.variation_value.split(' - ')[1].strip()
        return self.variation_value if self.variation_type in ['color', 'pa_color'] else ''
```

---

#### Solution 3B: Use Database Aggregation
**Implementation Time**: 1.5 hours

```python
from django.db.models import Count, Sum, JSONField
from django.contrib.postgres.aggregates import ArrayAgg

# Aggregate variation data at database level
products_with_variation_summary = SASProduct.objects.filter(
    club__in=sas_clubs
).annotate(
    variation_count=Count('variations', filter=Q(variations__is_active=True)),
    total_stock=Sum('variations__stock_quantity', filter=Q(variations__is_active=True)),
    variation_skus=ArrayAgg('variations__full_sku', filter=Q(variations__is_active=True)),
    variation_sizes=ArrayAgg('variations__variation_value', filter=Q(
        variations__is_active=True,
        variations__variation_type='size'
    ), distinct=True)
)
```

---

### **PRIORITY 4: MEDIUM - Implement Caching Strategy**

**Impact**: 90% reduction on subsequent loads

#### Solution 4A: View-Level Caching (Quick Win)
**Implementation Time**: 30 minutes

```python
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

class NewQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerMixin, View):

    @method_decorator(cache_page(60 * 5))  # 5 minutes
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
```

**Cache Invalidation Triggers**:
- Product update
- Variation update
- Stock update

---

#### Solution 4B: Query Result Caching (Recommended)
**Implementation Time**: 1 hour

```python
from django.core.cache import cache

def get_cached_products(cache_key, queryset, timeout=300):
    """Cache queryset results."""
    products = cache.get(cache_key)
    if products is None:
        products = list(queryset)
        cache.set(cache_key, products, timeout)
    return products

# Usage:
cache_key = f'quotation_products_schools_{user.id}_page_{page}'
products = get_cached_products(cache_key, combined_products_qs)
```

**Cache Keys**:
- `quotation_products_schools_{user_id}_page_{page}`
- `quotation_products_clubs_{user_id}_page_{page}`
- `quotation_search_{tab}_{search_query}_page_{page}`

---

#### Solution 4C: Template Fragment Caching
**Implementation Time**: 45 minutes

```django
{% load cache %}

{% cache 300 product_card product.id product.updated_at %}
<div class="product-box">
    <!-- Product card content -->
</div>
{% endcache %}
```

---

### **PRIORITY 5: LOW - Template Optimizations**

**Impact**: 10-15% reduction in rendering time

#### Solution 5A: Reduce Template Complexity
- Move inline styles to CSS files
- Use template fragments
- Lazy load images

#### Solution 5B: Optimize Image Loading
```html
<img loading="lazy"
     src="{{ product.image_url }}"
     width="200"
     height="200"
     alt="{{ product.name }}">
```

---

## Implementation Roadmap

### **Phase 1: Critical Fixes (Day 1-2)**

**Goal**: Reduce Clubs Tab from 2,873ms to ~500ms

**Tasks**:
1. ✅ Fix N+1 variation queries (Solution 1A) - 30 min
2. ✅ Implement lazy variation loading (Solution 2A) - 45 min
3. ✅ Test both tabs thoroughly - 1 hour
4. ✅ Run performance tests - 30 min

**Expected Results**:
- Clubs Tab: ~500ms (82% improvement)
- Schools Tab: ~300ms (71% improvement)
- Query Count: < 30 per page (97% improvement)

---

### **Phase 2: Performance Optimization (Day 3-5)**

**Goal**: Optimize query strategy and add caching

**Tasks**:
1. ✅ Implement optimized prefetch strategy (Solution 1B) - 1 hour
2. ✅ Implement query result caching (Solution 4B) - 1 hour
3. ✅ Add variation data caching - 45 min
4. ✅ Optimize variation display logic (Solution 3A) - 1 hour
5. ✅ Performance testing and validation - 1 hour

**Expected Results**:
- First Load: ~400ms
- Cached Load: ~100ms
- Query Count: < 20 per page

---

### **Phase 3: Advanced Optimizations (Week 2)**

**Goal**: Long-term performance and scalability

**Tasks**:
1. ⏳ Implement database-level pagination (Solution 2B) - 2 hours
2. ⏳ Database aggregation for variations (Solution 3B) - 1.5 hours
3. ⏳ Template fragment caching (Solution 4C) - 45 min
4. ⏳ Image optimization and lazy loading (Solution 5B) - 1 hour
5. ⏳ Comprehensive performance testing - 2 hours

**Expected Results**:
- First Load: ~250ms
- Cached Load: ~50ms
- Supports 1000+ products efficiently

---

## Code Changes Required

### **File 1: `quotations/views.py`**

#### Change 1: Fix Schools Tab N+1 (Lines 1447-1472)

**Before**:
```python
# Combine querysets for pagination
tus_products_list = list(tus_products_qs)
wholesale_products_list = list(wholesale_products_qs)

# Add product_type attribute and variation info
for product in tus_products_list:
    product.product_type = 'tusproduct'
    if product.has_variations:
        variations = list(product.variations.all())  # N+1!
        product.variation_display = self._get_variation_display_data(variations, 'tus')
```

**After**:
```python
# Combine querysets for pagination
combined_products = list(tus_products_qs) + list(wholesale_products_qs)

# Apply pagination
paginator = Paginator(combined_products, self.paginate_by)
try:
    page_obj = paginator.get_page(page)
except PageNotAnInteger:
    page_obj = paginator.get_page(1)
except EmptyPage:
    page_obj = paginator.get_page(paginator.num_pages)

# Process ONLY products on current page
for product in page_obj.object_list:
    if isinstance(product, TUSProduct):
        product.product_type = 'tusproduct'
        if product.has_variations:
            variations = list(product.variations.all())  # Only 24 queries max
            product.variation_display = self._get_variation_display_data(variations, 'tus')
    else:
        product.product_type = 'wholesaleproduct'
        if product.has_variations:
            variations = list(product.variations.filter(is_active=True))
            product.variation_display = self._get_variation_display_data(variations, 'wholesale')
```

---

#### Change 2: Fix Clubs Tab N+1 (Lines 1604-1626)

**Before**:
```python
# Combine querysets for pagination
sas_products_list = list(sas_products_qs)
lotto_products_list = list(lotto_products_qs)

# Add product_type attribute and variation info
for product in sas_products_list:
    product.product_type = 'sasproduct'
    if product.has_variations:
        variations = list(product.variations.filter(is_active=True))  # N+1!
        product.variation_display = self._get_variation_display_data(variations, 'sas')
```

**After**:
```python
# Combine querysets for pagination
combined_products = list(sas_products_qs) + list(lotto_products_qs)

# Apply pagination
paginator = Paginator(combined_products, self.paginate_by)
try:
    page_obj = paginator.get_page(page)
except PageNotAnInteger:
    page_obj = paginator.get_page(1)
except EmptyPage:
    page_obj = paginator.get_page(paginator.num_pages)

# Process ONLY products on current page
for product in page_obj.object_list:
    if isinstance(product, SASProduct):
        product.product_type = 'sasproduct'
        if product.has_variations:
            variations = list(product.variations.filter(is_active=True))  # Only 24 queries max
            product.variation_display = self._get_variation_display_data(variations, 'sas')
    else:
        product.product_type = 'lottoproduct'
        if product.has_variations:
            variations = list(product.variations.filter(is_active=True))
            product.variation_display = self._get_variation_display_data(variations, 'lotto')
```

---

#### Change 3: Optimize Prefetch (Lines 1376-1379, 1556-1592)

**Add after imports**:
```python
from django.db.models import Prefetch
```

**TUS Products (Line 1376)**:
```python
tus_products_qs = TUSProduct.objects.filter(
    category_assignments__school_category__school_id__in=tus_school_ids,
).annotate(
    has_stock_variation=has_stock_variation
).filter(
    Q(
        Q(type='variable', has_stock_variation=True) |
        Q(type='simple', stock_status__in=['instock', 'onbackorder'])
    )
).prefetch_related(
    'category_assignments__school_category__school',
    Prefetch(
        'variations',
        queryset=TUSProductVariation.objects.filter(is_active=True).only(
            'id', 'product_id', 'variation_type', 'variation_value',
            'stock_quantity', 'sku'
        )
    )
).distinct()
```

**SAS Products (Line 1556)**:
```python
sas_products_qs = SASProduct.objects.filter(
    club__in=sas_clubs,
    is_active=True
).annotate(
    has_stock_variation=has_stock_variation_sas,
    has_any_variation=has_any_variation_sas
).filter(
    Q(
        Q(has_any_variation=True, has_stock_variation=True) |
        Q(has_any_variation=False, stock_status__in=['instock', 'onbackorder'])
    )
).select_related('club').prefetch_related(
    Prefetch(
        'variations',
        queryset=SASProductVariation.objects.filter(is_active=True).only(
            'id', 'product_id', 'variation_type', 'variation_value',
            'stock_quantity', 'sku_suffix'
        )
    )
)
```

---

## Testing Checklist

### **Functional Testing**
- [ ] Schools Tab loads correctly
- [ ] Clubs Tab loads correctly
- [ ] Product variations display correctly
- [ ] Pagination works (page 1, 2, 3+)
- [ ] Search functionality works
- [ ] Stock status shows correctly
- [ ] Add to quotation works
- [ ] Variation selection works

### **Performance Testing**
- [ ] Run `test_quotation_performance_django.py`
- [ ] Verify query count < 30 per page
- [ ] Verify load time < 500ms per page
- [ ] Verify database time < 150ms
- [ ] Test with large product sets (100+)
- [ ] Test with products having many variations (20+)

### **Regression Testing**
- [ ] Test all product types (TUS, Wholesale, SAS, Lotto)
- [ ] Test with empty results
- [ ] Test with user having no assignments
- [ ] Test with admin vs sales rep users
- [ ] Test quotation session integration

---

## Performance Monitoring

### **Key Metrics to Track**

```python
# Add to view for monitoring
import logging
logger = logging.getLogger(__name__)

def get(self, request):
    import time
    from django.db import connection

    start_time = time.time()
    reset_queries()

    # ... view logic ...

    response_time = (time.time() - start_time) * 1000
    query_count = len(connection.queries)

    logger.info(
        f"NewQuotationView Performance: "
        f"tab={active_tab}, "
        f"response_time={response_time:.2f}ms, "
        f"queries={query_count}"
    )

    return render(request, self.template_name, context)
```

### **Performance Thresholds**

| Metric | Warning | Critical |
|--------|---------|----------|
| Load Time | > 500ms | > 1000ms |
| Query Count | > 30 | > 50 |
| DB Time | > 150ms | > 300ms |

---

## Expected Results Summary

### **Before Optimization**
- **Clubs Tab**: 2,873ms, 1,104 queries
- **Schools Tab**: 1,045ms, 77 queries

### **After Phase 1** (Critical Fixes)
- **Clubs Tab**: ~500ms, ~30 queries (82% faster, 97% fewer queries)
- **Schools Tab**: ~300ms, ~25 queries (71% faster, 68% fewer queries)

### **After Phase 2** (With Caching)
- **First Load**: ~400ms, ~25 queries
- **Cached Load**: ~100ms, ~10 queries

### **After Phase 3** (Full Optimization)
- **First Load**: ~250ms, ~15 queries
- **Cached Load**: ~50ms, ~5 queries

---

## Conclusion

The primary bottleneck is the **N+1 query problem with product variations**, causing 1,104 queries on the Clubs tab. The solution is straightforward:

1. **Defer variation processing until after pagination** (Quick fix)
2. **Optimize prefetch strategy** (Best practice)
3. **Add smart caching** (Performance boost)

**Implementation Priority**: Start with Priority 1 (Critical) fixes first, which will provide immediate 80%+ improvement with minimal code changes.

**Estimated Total Implementation Time**:
- Phase 1 (Critical): 2-3 hours
- Phase 2 (Optimization): 5-6 hours
- Phase 3 (Advanced): 7-8 hours

**Next Steps**:
1. Review and approve optimization plan
2. Create backup branch
3. Implement Phase 1 fixes
4. Run performance tests
5. Deploy to staging for validation
