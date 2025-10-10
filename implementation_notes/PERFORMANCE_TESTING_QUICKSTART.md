# Performance Testing - Quick Start Guide

## 🚀 Fastest Way to Test

```bash
# Option 1: Django management command (RECOMMENDED)
python manage.py test_price_upload_performance

# Option 2: Shell script
./run_performance_test.sh preview

# Option 3: Python script
python test_full_upload.py --mode direct
```

---

## 📊 What Gets Tested

- ✅ CSV file parsing (32MB file)
- ✅ Product matching/lookup
- ✅ Database queries
- ✅ Validation
- ✅ Response building
- ✅ Apply phase (optional)

---

## 📈 Expected Results

**Good Performance:**
```
Total Duration: 28.45s
Database Queries: 487
Throughput: 170.5 items/second
✓ Excellent: All metrics in target range
```

**Poor Performance:**
```
Total Duration: 65.23s
Database Queries: 1243
Throughput: 76.7 items/second
✗ Poor: Performance needs optimization
```

---

## 🛠️ Available Tools

### 1. Django Management Command
**File:** `schools/management/commands/test_price_upload_performance.py`
```bash
python manage.py test_price_upload_performance [OPTIONS]

Options:
  --csv PATH        CSV file path
  --category TYPE   wholesale-schools or lotto-clubs
  --apply           Test apply phase (modifies database!)
```

**Best for:** Integrated Django testing, quick tests

---

### 2. Standalone Test Script
**File:** `test_full_upload.py`
```bash
python test_full_upload.py [OPTIONS]

Options:
  --mode {direct,http}  Test mode
  --csv PATH            CSV file path
  --category TYPE       Product category
  --apply               Test apply phase
  --output FILE         Report output file
```

**Best for:** Detailed testing, HTTP simulation, custom reports

---

### 3. Log Analyzer
**File:** `analyze_performance_logs.py`
```bash
# Analyze log file
python analyze_performance_logs.py --log django.log

# Real-time monitoring
tail -f django.log | python analyze_performance_logs.py --stdin

# Compare runs
python analyze_performance_logs.py --compare run1.log run2.log run3.log
```

**Best for:** Post-test analysis, comparing runs, troubleshooting

---

### 4. Quick Runner Script
**File:** `run_performance_test.sh`
```bash
# Preview only
./run_performance_test.sh preview

# Full test
./run_performance_test.sh full

# Compare recent runs
./run_performance_test.sh compare

# Analyze logs
./run_performance_test.sh analyze
```

**Best for:** One-command testing, batch operations

---

## 📝 Sample Output

### Console Output
```
================================================================================
Wholesale Price Upload Performance Test
================================================================================
CSV File: /Users/sas/Downloads/all products for price update.csv
File Size: 32.00 MB
Category: wholesale-schools
================================================================================

[1/2] Testing PREVIEW phase...

[INFO] === WHOLESALE PRICE PREVIEW STARTED ===
[INFO] Processing CSV file: all products for price update.csv (33554432 bytes)
[INFO] Pre-loading wholesale-schools products for faster matching...
[INFO] [PERF-CSV-PARSE] CSV parsing took 2.34s
[INFO] [PERF-PRODUCT-MATCH] Product matching took 8.67s
[INFO] [PERF-VALIDATION] Validation took 1.23s
[INFO] [PERF-RESPONSE-BUILD] Response build took 0.45s
[INFO] [PERF-PREVIEW-TOTAL] Preview completed in 12.45s

✓ Preview completed: 4850 items

================================================================================
Performance Summary
================================================================================
Total Duration: 12.45s
Database Queries: 487

Phase Breakdown:
  PREVIEW: 12.45s (100.0%)

Throughput: 389.6 items/second
Queries per row: 0.10
================================================================================

Performance Assessment
================================================================================
✓ Excellent: Total time < 30s
✓ Excellent: Throughput 389.6 items/s
✓ Excellent: Query count 487
================================================================================
```

### Generated Report (PERFORMANCE_TEST_RESULTS.md)
```markdown
# Wholesale Price Upload Performance Test Report

**Test Date:** 2025-10-09 23:52:15

## Summary

- **Total Duration:** 12.45s
- **Database Queries:** 487
- **CSV Rows Processed:** 5000
- **Valid Matches:** 4850
- **Errors:** 150
- **Throughput:** 389.6 items/second

## Phase Performance

| Phase | Duration (s) | Percentage |
|-------|--------------|------------|
| CSV-PARSE | 2.34 | 18.8% |
| PRODUCT-MATCH | 8.67 | 69.6% |
| VALIDATION | 1.23 | 9.9% |
| RESPONSE-BUILD | 0.45 | 3.6% |

## Results Breakdown

- **Success:** True
- **Preview Items:** 4850
- **Errors:** 150
...
```

---

## 🔍 Understanding Metrics

### Phase Durations
- **CSV-PARSE**: Time to read and parse CSV file
- **PRODUCT-MATCH**: Time to lookup/match products in database
- **VALIDATION**: Time to validate pricing data
- **RESPONSE-BUILD**: Time to construct JSON response

### Performance Thresholds

| Metric | Target | Acceptable | Poor |
|--------|--------|------------|------|
| **Total Time** | < 30s | 30-60s | > 60s |
| **Throughput** | > 150 items/s | 100-150 | < 100 |
| **DB Queries** | < 500 | 500-1000 | > 1000 |
| **Match Rate** | > 95% | 90-95% | < 90% |

---

## 🚨 Troubleshooting

### Problem: Test fails with "CSV file not found"
```bash
# Solution: Specify correct path
python manage.py test_price_upload_performance --csv /correct/path/to/file.csv
```

### Problem: Slow performance (> 60s)
```bash
# Solution: Analyze logs to find bottleneck
python analyze_performance_logs.py --log django.log

# Look for slowest phase
grep "\[PERF-" django.log
```

### Problem: High database query count (> 1000)
```bash
# Solution: Check for N+1 queries
grep "SELECT" django.log | head -20

# Recommendation: Add database indexes, use caching
```

### Problem: Low throughput (< 100 items/s)
```bash
# Solution: Check phase breakdown
python analyze_performance_logs.py --log django.log

# Common fixes:
# - Use pandas for CSV parsing
# - Implement product lookup caching
# - Optimize validation logic
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `PERFORMANCE_TESTING_QUICKSTART.md` | This file - quick reference |
| `TESTING_SUMMARY.md` | Comprehensive overview |
| `PERFORMANCE_TEST_README.md` | Detailed guide with examples |
| `PERFORMANCE_TEST_RESULTS.md` | Results template |

---

## ⚡ Pro Tips

1. **First Time?** Use Django management command:
   ```bash
   python manage.py test_price_upload_performance
   ```

2. **Comparing Performance?** Run multiple times and compare:
   ```bash
   ./run_performance_test.sh preview  # Run 1
   ./run_performance_test.sh preview  # Run 2
   ./run_performance_test.sh compare  # Compare
   ```

3. **Debugging Issues?** Monitor logs in real-time:
   ```bash
   # Terminal 1
   python manage.py test_price_upload_performance

   # Terminal 2
   tail -f django.log | python analyze_performance_logs.py --stdin
   ```

4. **Testing Changes?** Save baseline first:
   ```bash
   # Before changes
   python manage.py test_price_upload_performance > baseline.log

   # After changes
   python manage.py test_price_upload_performance > after.log

   # Compare
   python analyze_performance_logs.py --compare baseline.log after.log
   ```

---

## 🎯 Next Steps

1. **Run your first test:**
   ```bash
   python manage.py test_price_upload_performance
   ```

2. **Review results** in console output

3. **Check generated report** in `PERFORMANCE_TEST_RESULTS.md`

4. **If performance is poor**, use log analyzer:
   ```bash
   python analyze_performance_logs.py --log django.log
   ```

5. **Optimize** based on identified bottlenecks

6. **Re-test** to verify improvements

---

## ✅ Success Criteria

Your test is successful if:
- ✅ Total time < 60 seconds
- ✅ No errors during execution
- ✅ Report generated successfully
- ✅ Metrics within acceptable ranges

**Need Help?** Check `PERFORMANCE_TEST_README.md` for detailed troubleshooting.
