# CSV Optimization Implementation Checklist

**Target:** Optimize `schools/views.py:wholesale_price_preview` for 80K+ row CSV files
**Expected Results:** 10x faster, 61% less memory, production-ready in 1 week

---

## Phase 1: Setup & Dependencies (15 minutes)

### Step 1.1: Install Pandas
- [ ] Install pandas library
  ```bash
  pip install pandas==2.2.0
  ```
- [ ] Verify installation
  ```bash
  python -c "import pandas; print(pandas.__version__)"
  # Expected output: 2.2.0
  ```

### Step 1.2: Update Requirements File
- [ ] Add pandas to `requirements.txt`
  ```bash
  echo "pandas==2.2.0" >> requirements.txt
  echo "numpy==1.26.0  # Pandas dependency" >> requirements.txt
  ```

### Step 1.3: Verify Files Created
- [ ] Confirm `schools/views_optimized.py` exists (685 lines)
- [ ] Confirm `OPTIMIZATION_GUIDE.md` exists (comprehensive docs)
- [ ] Confirm `CSV_OPTIMIZATION_SUMMARY.md` exists (executive summary)
- [ ] Confirm `PERFORMANCE_COMPARISON.txt` exists (visual benchmarks)

**Estimated Time:** 15 minutes
**Status:** ⬜ Not Started | ⬛ In Progress | ✅ Complete

---

## Phase 2: Code Integration (20 minutes)

### Step 2.1: Import Optimized Module
- [ ] Open `schools/views.py`
- [ ] Add import statement (around line 10):
  ```python
  from schools.views_optimized import process_csv_with_pandas
  ```
- [ ] Verify no import errors
  ```bash
  python manage.py check
  ```

### Step 2.2: Add Feature Flag
- [ ] Add to `settings.py` or `.env`:
  ```python
  # Feature flag for gradual rollout
  USE_PANDAS_CSV_PROCESSING = os.getenv('USE_PANDAS_CSV_PROCESSING', 'false').lower() == 'true'
  ```

### Step 2.3: Implement Feature Toggle
- [ ] Find CSV processing loop in `schools/views.py` (lines 2436-2700)
- [ ] Wrap in feature flag:
  ```python
  if settings.USE_PANDAS_CSV_PROCESSING:
      # New optimized implementation
      try:
          preview_data, valid_rows, errors = process_csv_with_pandas(
              csv_file_path=temp_file_path,
              category=category,
              matcher=matcher,
              products_by_sku=products_by_sku,
              products_by_barcode=products_by_barcode,
              variations_by_key=variations_by_key,
              variations_by_normalized_key=variations_by_normalized_key,
              chunk_size=5000
          )
          row_count = len(preview_data)
      except Exception as e:
          logger.error(f"Pandas CSV processing failed: {str(e)}", exc_info=True)
          return JsonResponse({
              'success': False,
              'error': f'Failed to process CSV file: {str(e)}',
              'traceback': traceback.format_exc(),
              'file_name': csv_file.name
          }, status=500)
  else:
      # Original row-by-row implementation (keep as fallback)
      with open(temp_file_path, 'r', encoding='utf-8-sig') as file:
          # ... (existing implementation lines 2436-2700)
  ```

### Step 2.4: Verify Code Syntax
- [ ] Run Django check
  ```bash
  python manage.py check
  # Expected: System check identified no issues
  ```
- [ ] Run linter (if available)
  ```bash
  flake8 schools/views.py schools/views_optimized.py
  ```

**Estimated Time:** 20 minutes
**Status:** ⬜ Not Started | ⬛ In Progress | ✅ Complete

---

## Phase 3: Testing (2 hours)

### Step 3.1: Unit Tests

- [ ] Create test file `tests/test_csv_optimization.py`
- [ ] Implement test cases:
  ```python
  def test_column_detection()
  def test_vectorized_product_lookup()
  def test_vectorized_price_calculations()
  def test_vectorized_status_assignment()
  def test_chunked_processing()
  ```
- [ ] Run unit tests
  ```bash
  pytest tests/test_csv_optimization.py -v
  # Expected: All tests pass
  ```
- [ ] Verify 100% test coverage for critical functions

### Step 3.2: Integration Tests

- [ ] Create sample CSV files:
  - Small: 100 rows
  - Medium: 10,000 rows
  - Large: 80,000 rows
- [ ] Test with feature flag OFF (original implementation)
  ```bash
  export USE_PANDAS_CSV_PROCESSING=false
  python manage.py test schools.tests.test_wholesale_price_preview
  ```
- [ ] Test with feature flag ON (optimized implementation)
  ```bash
  export USE_PANDAS_CSV_PROCESSING=true
  python manage.py test schools.tests.test_wholesale_price_preview
  ```
- [ ] Compare results:
  - [ ] Same number of rows processed
  - [ ] Same product matches
  - [ ] Same price calculations (within 0.01)
  - [ ] Same status assignments

### Step 3.3: Performance Tests

- [ ] Run benchmark script
  ```bash
  python schools/views_optimized.py
  # Expected output: Benchmark tables for 10K, 50K, 80K, 100K rows
  ```
- [ ] Verify performance targets:
  - [ ] 80K rows in < 15 seconds
  - [ ] Peak memory < 150 MB
  - [ ] Throughput > 5,000 rows/sec
- [ ] Profile memory usage
  ```python
  import tracemalloc
  tracemalloc.start()
  # ... run processing ...
  current, peak = tracemalloc.get_traced_memory()
  print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
  ```

### Step 3.4: Category-Specific Tests

- [ ] Test `wholesale-schools` category
- [ ] Test `retail-schools` category (TUS variations)
- [ ] Test `sas-clubs` category (SAS variations)
- [ ] Test `lotto-clubs` category (LOTTO variations)
- [ ] Verify variation matching for all categories
- [ ] Verify price field selection per category

### Step 3.5: Edge Case Tests

- [ ] Empty CSV file (0 rows)
- [ ] CSV with only headers (1 row)
- [ ] CSV with missing columns
- [ ] CSV with malformed data
- [ ] CSV with special characters (UTF-8)
- [ ] CSV with extremely large cells (>1MB)
- [ ] All products not found
- [ ] All products with cost=0
- [ ] All products with stock=0 and cost=0

**Estimated Time:** 2 hours
**Status:** ⬜ Not Started | ⬛ In Progress | ✅ Complete

---

## Phase 4: Pilot Deployment (1 week)

### Step 4.1: Enable for Test Users

- [ ] Identify 5-10 pilot users
- [ ] Enable feature flag for pilot environment
  ```bash
  # In .env or environment variable
  export USE_PANDAS_CSV_PROCESSING=true
  ```
- [ ] Restart application server
  ```bash
  sudo systemctl restart gunicorn  # Or your server
  ```

### Step 4.2: Monitoring Setup

- [ ] Add performance logging
  ```python
  import time
  start_time = time.time()
  preview_data, valid_rows, errors = process_csv_with_pandas(...)
  elapsed = time.time() - start_time
  logger.info(f"CSV processing: {len(preview_data)} rows in {elapsed:.2f}s "
             f"({len(preview_data)/elapsed:.0f} rows/sec)")
  ```
- [ ] Set up alerts for:
  - Processing time > 20 seconds
  - Memory usage > 200 MB
  - Error rate > 1%
- [ ] Create monitoring dashboard (optional)

### Step 4.3: Collect Metrics (Daily)

- [ ] Day 1: Monitor processing times, memory usage, errors
- [ ] Day 2: Compare with baseline (feature flag OFF)
- [ ] Day 3: Review error logs and edge cases
- [ ] Day 4: Gather user feedback
- [ ] Day 5: Performance analysis and tuning
- [ ] Day 6: Final validation and approval
- [ ] Day 7: Go/No-Go decision for full rollout

### Step 4.4: Success Criteria

- [ ] Processing time < 15s for 80K rows (target: 8s)
- [ ] Memory usage < 150 MB (target: 90 MB)
- [ ] Zero data discrepancies vs original
- [ ] Error rate < 0.1%
- [ ] Positive user feedback (faster uploads)

**Estimated Time:** 1 week (with daily monitoring)
**Status:** ⬜ Not Started | ⬛ In Progress | ✅ Complete

---

## Phase 5: Production Rollout (1 day)

### Step 5.1: Pre-Rollout Checks

- [ ] All pilot tests passed
- [ ] No critical issues found
- [ ] Performance targets met
- [ ] User feedback positive
- [ ] Rollback plan ready

### Step 5.2: Enable for All Users

- [ ] Set feature flag to ON globally
  ```python
  # In settings.py (permanent)
  USE_PANDAS_CSV_PROCESSING = True
  ```
- [ ] Deploy to production
  ```bash
  git add .
  git commit -m "Enable Pandas CSV optimization for all users"
  git push origin main
  # Deploy via CI/CD or manual deployment
  ```
- [ ] Verify deployment
  ```bash
  # Check application logs for new logging statements
  tail -f /var/log/app/app.log | grep "CSV processing"
  ```

### Step 5.3: Monitor Production (First 24 Hours)

- [ ] Hour 1-2: Watch for immediate errors
- [ ] Hour 2-4: Verify performance metrics
- [ ] Hour 4-8: Check memory usage patterns
- [ ] Hour 8-24: Monitor error rates and user feedback

### Step 5.4: Post-Rollout Validation

- [ ] Compare metrics before/after:
  - Average processing time
  - Peak memory usage
  - Error rates
  - User satisfaction
- [ ] Document improvements
- [ ] Update internal documentation

### Step 5.5: Cleanup (Optional - After 2 Weeks)

- [ ] Remove feature flag (make optimization default)
- [ ] Remove original row-by-row implementation
- [ ] Archive backup of original code
- [ ] Update code comments and documentation

**Estimated Time:** 1 day (plus 24h monitoring)
**Status:** ⬜ Not Started | ⬛ In Progress | ✅ Complete

---

## Rollback Plan (Emergency Use Only)

### If Issues Arise During Pilot or Rollout

**Option 1: Quick Toggle (30 seconds)**
```bash
# Disable optimization via environment variable
export USE_PANDAS_CSV_PROCESSING=false
sudo systemctl restart gunicorn
```

**Option 2: Git Revert (2 minutes)**
```bash
git log --oneline -10  # Find optimization commit
git revert <commit-hash>
git push origin main
# Redeploy application
```

**Option 3: Manual Code Restore (5 minutes)**
```bash
# Restore from backup
cp schools/views_backup.py schools/views.py
git add schools/views.py
git commit -m "Rollback CSV optimization"
git push origin main
# Redeploy application
```

### Rollback Triggers
- Processing time > 30s for 80K rows
- Memory usage > 300 MB
- Error rate > 5%
- Data discrepancies detected
- Critical user complaints

---

## Verification Checklist

### Before Marking Complete

- [ ] All tests pass (unit, integration, performance)
- [ ] Code reviewed by peer
- [ ] Documentation updated
- [ ] Performance benchmarks met
- [ ] No data discrepancies
- [ ] Feature flag works correctly
- [ ] Rollback plan tested
- [ ] Monitoring in place
- [ ] User communication prepared

### Final Sign-Off

- [ ] Technical Lead Approval: ________________  Date: ________
- [ ] QA Approval: ________________  Date: ________
- [ ] Product Owner Approval: ________________  Date: ________

---

## Contact & Support

**For Questions:**
- Technical Implementation: See `OPTIMIZATION_GUIDE.md`
- Performance Benchmarks: See `PERFORMANCE_COMPARISON.txt`
- Executive Summary: See `CSV_OPTIMIZATION_SUMMARY.md`
- Code Details: Review `schools/views_optimized.py`

**For Issues:**
1. Check error logs: `/var/log/app/app.log`
2. Verify feature flag: `echo $USE_PANDAS_CSV_PROCESSING`
3. Run diagnostics: `python manage.py check`
4. Review unit tests: `pytest tests/test_csv_optimization.py -v`
5. Rollback if needed (see Rollback Plan above)

---

## Progress Tracking

**Overall Project Status:**
- [ ] Phase 1: Setup & Dependencies (15 min)
- [ ] Phase 2: Code Integration (20 min)
- [ ] Phase 3: Testing (2 hours)
- [ ] Phase 4: Pilot Deployment (1 week)
- [ ] Phase 5: Production Rollout (1 day)

**Total Timeline:** ~1 week (including pilot testing)
**Estimated Effort:** ~3 hours hands-on work + 1 week monitoring

**Progress:**
- 0% - Not Started
- 25% - Setup Complete
- 50% - Code Integration & Testing Complete
- 75% - Pilot Successful
- 100% - Production Rollout Complete ✅

---

## Success Metrics

| Metric | Baseline | Target | Achieved |
|--------|----------|--------|----------|
| Processing Time (80K rows) | 80s | < 15s | ___s |
| Memory Usage | 230 MB | < 150 MB | ___MB |
| Throughput | 1K rows/s | > 5K rows/s | ___rows/s |
| Error Rate | < 0.1% | < 0.1% | ___%  |
| User Satisfaction | 3/5 | 4.5/5 | ___/5 |

**Completion Date:** ________________

**Final Notes:**
_____________________________________________________________________________
_____________________________________________________________________________
_____________________________________________________________________________
