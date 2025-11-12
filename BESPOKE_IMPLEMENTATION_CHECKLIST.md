# Bespoke Products - CIN7 Price Update Implementation Checklist

## Pre-Implementation Analysis ✅

- [x] Reviewed current CIN7 price update system
- [x] Identified bespoke products excluded from updates (1,906 products)
- [x] Confirmed bespoke models have required fields
- [x] Analyzed existing code patterns
- [x] Created comprehensive documentation

---

## Phase 1: Immediate Fix (Quick Solution)

### Option A: SQL Direct Update (5 minutes)

**File:** `bespoke_price_analysis_and_fix.sql`

- [ ] **Step 1:** Connect to database
  ```bash
  # PostgreSQL
  psql -U your_username -d your_database

  # Or use Django dbshell
  python manage.py dbshell
  ```

- [ ] **Step 2:** Run analysis section (Section 1-3)
  - Verify current state
  - Check how many products need updating
  - Review sample products

- [ ] **Step 3:** Review pre-update summary
  - Confirm expected update counts
  - Note any anomalies

- [ ] **Step 4:** Execute the fix (Section 4)
  - Uncomment Section 4
  - Run within transaction (BEGIN...COMMIT)
  - Verify success before COMMIT

- [ ] **Step 5:** Run post-update verification (Section 5)
  - Check success rate
  - Spot-check sample products
  - Confirm price = margin_75_price

**Expected Results:**
- All active bespoke products: `price = margin_75_price`
- All active bespoke variations: `price = margin_75_price`
- ~1,906+ records updated

---

### Option B: Django Management Command

**File to create:** `bespoke/management/commands/update_bespoke_prices_to_margin.py`

- [ ] **Step 1:** Create management command
  ```python
  from django.core.management.base import BaseCommand
  from django.db import transaction
  from bespoke.models import BespokeProduct, BespokeProductVariation

  class Command(BaseCommand):
      help = 'Set price = margin_75_price for all bespoke products'

      def add_arguments(self, parser):
          parser.add_argument(
              '--dry-run',
              action='store_true',
              help='Preview changes without applying'
          )

      def handle(self, *args, **options):
          dry_run = options['dry_run']

          # Count products needing update
          products_to_update = BespokeProduct.objects.filter(
              is_active=True,
              margin_75_price__gt=0
          ).exclude(price=models.F('margin_75_price'))

          variations_to_update = BespokeProductVariation.objects.filter(
              is_active=True,
              margin_75_price__gt=0
          ).exclude(price=models.F('margin_75_price'))

          self.stdout.write(
              f"Products to update: {products_to_update.count()}"
          )
          self.stdout.write(
              f"Variations to update: {variations_to_update.count()}"
          )

          if dry_run:
              self.stdout.write(
                  self.style.WARNING('DRY RUN - No changes made')
              )
              return

          # Update in transaction
          with transaction.atomic():
              # Update products
              updated_products = products_to_update.update(
                  price=models.F('margin_75_price')
              )

              # Update variations
              updated_variations = variations_to_update.update(
                  price=models.F('margin_75_price')
              )

          self.stdout.write(
              self.style.SUCCESS(
                  f'Updated {updated_products} products and '
                  f'{updated_variations} variations'
              )
          )
  ```

- [ ] **Step 2:** Test dry run
  ```bash
  python manage.py update_bespoke_prices_to_margin --dry-run
  ```

- [ ] **Step 3:** Execute actual update
  ```bash
  python manage.py update_bespoke_prices_to_margin
  ```

- [ ] **Step 4:** Verify in admin
  - Check random sample of products
  - Confirm price = margin_75_price

---

## Phase 2: Full CIN7 Integration (4-6 hours)

### File 1: `/Users/sas/Repos/SASKITUP/schools/views.py`

- [ ] **Change 1:** Fix BS product filtering (Line 3614-3618)
  ```python
  # OLD CODE (skips ALL BS products):
  if sku.upper().startswith('BS') or style_code.upper().startswith('BS'):
      skipped_bs_products += 1
      continue

  # NEW CODE (only skip BallStore, not Bespoke):
  # Check product category to differentiate BallStore from Bespoke
  category = cin7_product.get('category', '')
  if sku.upper().startswith('BS') or style_code.upper().startswith('BS'):
      # Allow Bespoke products through (Quotation Base Library)
      if 'BallStore' in category or 'Ball Store' in category:
          skipped_bs_products += 1
          continue
  ```

- [ ] **Change 2:** Add bespoke category mapping (Line 4362)
  ```python
  # Add 'Bespoke': 'bespoke' to category_map
  category_map = {
      'TUS': 'retail-schools',
      'LOTTO': 'lotto-clubs',
      'SAS': 'sas-clubs',
      'Wholesale': 'wholesale-schools',
      'BallStore': 'ballstore',
      'Bespoke': 'bespoke',  # ADD THIS LINE
  }
  ```

- [ ] **Change 3:** Ensure price = margin_75_price for bespoke (Line 4342)
  ```python
  # When preparing valid_items for bespoke category:
  if category == 'bespoke':
      # For bespoke, set price to margin_75_price (not retail_price)
      valid_items.append({
          'cin7_id': cp.cin7_id,
          'product_code': cp.code,
          'barcode': cp.barcode,
          'style_code': cp.style_code,
          'product_name': cp.name,
          'cost': cost_nzd,
          'current_retail_nzd_incl': margin_75_price,  # Use margin as price
          'margin_75_price': margin_75_price,
          'discount_percentage': 0,  # No discount
          'match_method': cp.match_method,
          'product_id': cp.matched_product_id,
          'variation_id': cp.matched_variation_id,
          'status': 'valid'
      })
  ```

---

### File 2: `/Users/sas/Repos/SASKITUP/schools/services/product_matcher.py`

- [ ] **Change 1:** Add bespoke to category models (Line 28-34)
  ```python
  CATEGORY_MODELS = {
      'wholesale-schools': 'schools.WholesaleProduct',
      'retail-schools': 'schools.TUSProduct',
      'sas-clubs': 'clubs.SASProduct',
      'lotto-clubs': 'clubs.LottoProduct',
      'ballstore': 'ballstore.BallStoreProduct',
      'bespoke': 'bespoke.BespokeProduct',  # ADD THIS LINE
  }
  ```

- [ ] **Change 2:** Add `_match_bespoke` method (After line 850)
  ```python
  def _match_bespoke(self, product_code, barcode, style_code):
      """Match Bespoke products by SKU/barcode"""
      from bespoke.models import BespokeProduct, BespokeProductVariation

      # Try variation match first
      if product_code:
          try:
              product, match_method, variation = self._match_variation_with_instance(
                  BespokeProductVariation, product_code, field_name='sku'
              )
              if product and variation:
                  return product, variation, match_method
          except Exception as e:
              logger.error(f"Bespoke variation SKU match error: {e}")

      if barcode:
          try:
              product, match_method, variation = self._match_variation_with_instance(
                  BespokeProductVariation, barcode, field_name='barcode'
              )
              if product and variation:
                  return product, variation, match_method
          except Exception as e:
              logger.error(f"Bespoke variation barcode match error: {e}")

      # Try product match
      if product_code:
          products = BespokeProduct.objects.filter(sku=product_code, is_active=True)
          if products.count() == 1:
              return products.first(), None, 'product_sku'

      if barcode:
          products = BespokeProduct.objects.filter(barcode=barcode, is_active=True)
          if products.count() == 1:
              return products.first(), None, 'product_barcode'

      return None, None, 'no_match'
  ```

- [ ] **Change 3:** Add category dispatch (Around line 320)
  ```python
  elif category == 'bespoke':
      product, variation, match_method = self._match_bespoke(
          product_code, barcode, style_code
      )
  ```

---

### File 3: `/Users/sas/Repos/SASKITUP/schools/services/bulk_price_updater.py`

- [ ] **Change 1:** Add bespoke variation preload (After line 260)
  ```python
  def _preload_bespoke_variations(self):
      """Pre-load Bespoke product variations."""
      from bespoke.models import BespokeProductVariation

      logger.info("[BESPOKE] Loading variations...")
      variations = BespokeProductVariation.objects.select_related(
          'parent_product'
      ).filter(is_active=True)

      count = 0
      for variation in variations:
          count += 1
          if variation.sku:
              self.variation_cache[variation.sku.upper()] = variation
          if variation.barcode:
              self.variation_cache[variation.barcode.upper()] = variation

      logger.info(f"[BESPOKE] Loaded {count} variations")
      return count
  ```

- [ ] **Change 2:** Update variation model lookup (Line 1010-1018)
  ```python
  elif self.category == 'bespoke':
      from bespoke.models import BespokeProductVariation
      variation_model = BespokeProductVariation
  ```

- [ ] **Change 3:** Update preload dispatch (Around line 230)
  ```python
  elif self.category == 'bespoke':
      variation_count = self._preload_bespoke_variations()
  ```

---

### File 4: `/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/cin7_price_update_settings.html`

- [ ] **Change 1:** Add bespoke option to dropdown (Line 109)
  ```html
  <select class="form-select form-select-lg" id="priceType">
      <option value="Wholesale" selected>Wholesale (Schools)</option>
      <option value="TUS">TUS (Retail Schools)</option>
      <option value="LOTTO">LOTTO (Clubs)</option>
      <option value="SAS">SAS (Clubs)</option>
      <option value="BallStore">BallStore</option>
      <option value="Bespoke">Bespoke (Base Garments & Addons)</option>
  </select>
  ```

---

## Phase 3: Testing

### Unit Testing

- [ ] Test bespoke product matching
  ```python
  # Test file: tests/test_bespoke_price_updates.py
  def test_bespoke_product_matching():
      # Create test bespoke product
      product = BespokeProduct.objects.create(
          cin7_id='TEST001',
          sku='BS-TEST-001',
          name='Test Base Garment',
          cost_price=Decimal('10.00'),
          is_active=True
      )

      # Test matcher
      matcher = ProductMatcherService()
      matched, variation, method = matcher.match_product(
          category='bespoke',
          product_code='BS-TEST-001',
          barcode='',
          style_code=''
      )

      assert matched == product
      assert method == 'product_sku'
  ```

- [ ] Test price calculation
  ```python
  def test_bespoke_price_equals_margin():
      product = BespokeProduct.objects.create(
          cin7_id='TEST002',
          sku='BS-TEST-002',
          cost_price=Decimal('10.00'),
          is_active=True
      )
      product.save()  # Trigger margin_75_price calculation

      assert product.margin_75_price == Decimal('40.00')

      # Update price to margin
      product.price = product.margin_75_price
      product.save()

      assert product.price == product.margin_75_price
  ```

---

### Integration Testing

- [ ] **Test 1:** Fetch bespoke products from CIN7
  1. Login: http://localhost:8000/
  2. Navigate to: /schools/wholesale/cin7-price-update/
  3. Select "Bespoke" from dropdown
  4. Click "Fetch Prices from Cin7"
  5. Verify: Products fetched successfully
  6. Verify: Bespoke products NOT skipped
  7. Check logs for "skipped_bs_products" count

- [ ] **Test 2:** Match bespoke products
  1. After fetch, click "Match Existing Products"
  2. Verify: Matching statistics show numbers
  3. Verify: "Matched Products" count > 0
  4. Check preview table
  5. Verify: SKUs match database records
  6. Verify: Prices show margin_75_price

- [ ] **Test 3:** Apply price updates
  1. Review preview carefully
  2. Click "Apply Updates"
  3. Wait for completion
  4. Verify: Success message
  5. Check database:
     ```sql
     SELECT COUNT(*) as correct_pricing
     FROM bespoke_product
     WHERE is_active = true
       AND ABS(price - margin_75_price) < 0.01;
     ```

- [ ] **Test 4:** Verify variations
  ```sql
  SELECT
      p.name,
      v.sku,
      v.cost_price,
      v.margin_75_price,
      v.price,
      CASE
          WHEN ABS(v.price - v.margin_75_price) < 0.01 THEN 'CORRECT'
          ELSE 'INCORRECT'
      END as status
  FROM bespoke_product_variation v
  JOIN bespoke_product p ON p.id = v.parent_product_id
  WHERE v.is_active = true
  LIMIT 20;
  ```

---

### User Acceptance Testing

- [ ] **UAT 1:** Test with 10 sample products
  - Select 10 bespoke products manually
  - Note their current prices
  - Run price update
  - Verify all 10 updated correctly

- [ ] **UAT 2:** Test category filtering
  - Verify "Base Garments" updated
  - Verify "Addons" updated
  - Verify other categories NOT affected

- [ ] **UAT 3:** Test error handling
  - Try with invalid SKU
  - Try with missing cost price
  - Verify error messages clear
  - Verify partial success handled

- [ ] **UAT 4:** Performance test
  - Time full update of 1,906 products
  - Should complete in < 5 minutes
  - Check server resource usage
  - Verify no timeouts

---

## Phase 4: Deployment

### Pre-Deployment

- [ ] Code review completed
- [ ] All tests passing
- [ ] Database backup created
- [ ] Rollback plan documented
- [ ] Stakeholders notified

### Deployment Steps

- [ ] **Step 1:** Deploy to staging
  ```bash
  git checkout staging
  git merge feature/bespoke-price-updates
  # Deploy to staging server
  ```

- [ ] **Step 2:** Run staging tests
  - Full integration test
  - Performance test
  - Verify with real data

- [ ] **Step 3:** Production deployment
  ```bash
  git checkout main
  git merge feature/bespoke-price-updates
  git tag v1.x.x-bespoke-prices
  git push origin main --tags
  # Deploy to production
  ```

- [ ] **Step 4:** Post-deployment verification
  - Check application logs
  - Verify bespoke option visible
  - Test single product update
  - Monitor for errors

### Post-Deployment

- [ ] **Step 1:** Run first full price update
  - Select "Bespoke" category
  - Fetch all products
  - Match with database
  - Review preview thoroughly
  - Apply updates
  - Verify success

- [ ] **Step 2:** Database verification
  ```sql
  -- Run full verification
  SELECT
      'Products' as type,
      COUNT(*) as total,
      COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as correct,
      ROUND(AVG(price)::numeric, 2) as avg_price
  FROM bespoke_product
  WHERE is_active = true AND cost_price > 0

  UNION ALL

  SELECT
      'Variations' as type,
      COUNT(*) as total,
      COUNT(CASE WHEN ABS(price - margin_75_price) < 0.01 THEN 1 END) as correct,
      ROUND(AVG(price)::numeric, 2) as avg_price
  FROM bespoke_product_variation
  WHERE is_active = true AND cost_price > 0;
  ```

- [ ] **Step 3:** Audit trail check
  - Verify audit logs created
  - Check update timestamps
  - Review any error logs

- [ ] **Step 4:** User communication
  - Notify team of new feature
  - Provide quick start guide
  - Schedule training session

---

## Documentation

- [ ] Update user manual
  - Add bespoke category instructions
  - Document price calculation
  - Add troubleshooting section

- [ ] Update technical documentation
  - Document code changes
  - Update architecture diagrams
  - Add developer notes

- [ ] Create training materials
  - Quick reference guide
  - Video walkthrough
  - FAQ document

---

## Rollback Plan

If issues occur:

### Immediate Rollback (Price Data)
```sql
-- If backup was created, restore prices
BEGIN;

-- Restore from backup table (if created)
UPDATE bespoke_product p
SET price = b.price
FROM bespoke_product_backup b
WHERE p.id = b.id;

UPDATE bespoke_product_variation v
SET price = b.price
FROM bespoke_product_variation_backup b
WHERE v.id = b.id;

COMMIT;
```

### Code Rollback
```bash
# Revert to previous version
git revert <commit-hash>
git push origin main

# Redeploy previous version
```

---

## Success Metrics

- [ ] All 1,906+ bespoke products have `price = margin_75_price`
- [ ] All bespoke variations have `price = margin_75_price`
- [ ] Zero manual price updates required
- [ ] Price update process < 5 minutes
- [ ] No errors in production logs
- [ ] User satisfaction confirmed

---

## Sign-Off

**Developer:** _________________ Date: _______
**QA Tester:** _________________ Date: _______
**Product Owner:** _____________ Date: _______
**DevOps:** ___________________ Date: _______

---

**Status:** Ready for implementation
**Priority:** High
**Estimated Time:** Phase 1: 5 min | Phase 2: 4-6 hours | Phase 3-4: 2-3 hours
