# Performance Testing Framework - Summary

## Overview

A comprehensive automated testing framework for measuring and analyzing the performance of wholesale price upload operations. This framework provides multiple testing approaches, detailed metrics collection, and automated report generation.

---

## Created Files

### 1. Core Test Scripts

#### test_full_upload.py
**Purpose:** Main automated performance testing script

**Key Features:**
- Simulates real CSV upload (32MB file)
- Two modes: Direct (Django function calls) and HTTP (server requests)
- Captures all [PERF-*] tagged metrics
- Monitors database queries
- Supports both preview and apply phases
- Generates detailed markdown reports

**Usage:**
```bash
# Preview phase only
python test_full_upload.py --mode direct --category wholesale-schools

# Full test (preview + apply)
python test_full_upload.py --mode direct --category wholesale-schools --apply

# Custom CSV file
python test_full_upload.py --csv /path/to/file.csv --category wholesale-schools
```

**Output:** `PERFORMANCE_TEST_RESULTS.md`

---

#### analyze_performance_logs.py
**Purpose:** Parse and analyze Django logs for performance insights

**Key Features:**
- Extracts [PERF-*] tagged messages from logs
- Calculates statistics (avg, min, max, total)
- Identifies performance bottlenecks
- Compares multiple test runs
- Real-time log monitoring support
- JSON output support

**Usage:**
```bash
# Analyze log file
python analyze_performance_logs.py --log django.log

# Real-time monitoring
tail -f django.log | python analyze_performance_logs.py --stdin

# Compare multiple runs
python analyze_performance_logs.py --compare run1.log run2.log run3.log
```

**Output:** `PERFORMANCE_ANALYSIS.md`

---

### 2. Django Management Command

#### test_price_upload_performance.py
**Location:** `/schools/management/commands/test_price_upload_performance.py`

**Purpose:** Django management command for integrated performance testing

**Usage:**
```bash
# Basic test
python manage.py test_price_upload_performance

# Custom CSV
python manage.py test_price_upload_performance --csv /path/to/file.csv

# Test LOTTO category
python manage.py test_price_upload_performance --category lotto-clubs

# Full test with apply
python manage.py test_price_upload_performance --apply
```

**Advantages:**
- Full Django environment integration
- No HTTP overhead
- Direct database access
- Automatic user setup
- Built-in performance assessment

---

### 3. Convenience Scripts

#### run_performance_test.sh
**Purpose:** Quick one-command test runner

**Modes:**
- `preview` - Test preview phase only (default)
- `full` - Test both preview and apply
- `compare` - Compare recent test runs
- `analyze` - Analyze Django logs

**Usage:**
```bash
# Quick preview test
./run_performance_test.sh preview

# Full test
./run_performance_test.sh full

# Compare recent runs
./run_performance_test.sh compare
```

---

### 4. Documentation

#### PERFORMANCE_TEST_README.md
**Purpose:** Comprehensive testing guide

**Contents:**
- Quick start instructions
- Detailed script documentation
- Performance metric definitions
- Expected baselines and targets
- Troubleshooting guide
- Advanced usage examples
- CI/CD integration examples

#### PERFORMANCE_TEST_RESULTS.md
**Purpose:** Template for test results

**Sections:**
- Summary statistics
- Phase performance breakdown
- Database metrics
- Bottleneck analysis
- Recommendations
- Raw log output

---

## Performance Metrics Tracked

### Timing Metrics
- **PREVIEW-TOTAL**: Total preview phase duration
- **CSV-PARSE**: CSV file parsing time
- **PRODUCT-MATCH**: Product lookup/matching time
- **DATABASE-LOOKUP**: Database query time
- **VALIDATION**: Data validation time
- **RESPONSE-BUILD**: Response construction time
- **APPLY-TOTAL**: Total apply phase duration
- **DATABASE-UPDATE**: Database update time

### Throughput Metrics
- Items per second
- Bytes per second
- Matches per second
- Updates per second

### Database Metrics
- Total query count
- Queries per row
- Query execution time
- Transaction count

### Quality Metrics
- Match rate (successful matches / total rows)
- Error rate (errors / total rows)
- Success rate (successful updates / total updates)

---

## Expected Performance Baselines

### Preview Phase (32MB, ~5000 rows)

| Metric | Target | Acceptable | Poor |
|--------|--------|------------|------|
| Total Time | < 30s | 30-60s | > 60s |
| Throughput | > 150 items/s | 100-150 items/s | < 100 items/s |
| DB Queries | < 500 | 500-1000 | > 1000 |
| Match Rate | > 95% | 90-95% | < 90% |

### Apply Phase (~5000 updates)

| Metric | Target | Acceptable | Poor |
|--------|--------|------------|------|
| Total Time | < 15s | 15-30s | > 30s |
| Throughput | > 300 updates/s | 200-300 updates/s | < 200 updates/s |
| DB Queries | < 10 | 10-50 | > 50 |
| Success Rate | 100% | > 99% | < 99% |

---

## Quick Start Examples

### Example 1: Basic Performance Test
```bash
# Using management command (recommended)
python manage.py test_price_upload_performance

# Expected output:
================================================================================
Wholesale Price Upload Performance Test
================================================================================
CSV File: /Users/sas/Downloads/all products for price update.csv
File Size: 32.00 MB
Category: wholesale-schools
================================================================================

[1/2] Testing PREVIEW phase...
✓ Preview completed: 4850 items

================================================================================
Performance Summary
================================================================================
Total Duration: 28.45s
Database Queries: 487

Phase Breakdown:
  PREVIEW: 28.45s (100.0%)

Throughput: 170.5 items/second
Queries per row: 0.10
================================================================================

Performance Assessment
================================================================================
✓ Excellent: Total time < 30s
✓ Excellent: Throughput 170.5 items/s
✓ Excellent: Query count 487
```

### Example 2: Full Test with Apply
```bash
python manage.py test_price_upload_performance --apply

# WARNING: This modifies the database!
```

### Example 3: Log Analysis
```bash
# Run test (creates logs)
python manage.py test_price_upload_performance

# Analyze logs
python analyze_performance_logs.py --log django.log --output analysis.md

# View analysis
cat analysis.md
```

### Example 4: Compare Multiple Runs
```bash
# Run test 3 times
./run_performance_test.sh preview  # Creates preview_20251009_143000.md
./run_performance_test.sh preview  # Creates preview_20251009_143100.md
./run_performance_test.sh preview  # Creates preview_20251009_143200.md

# Compare results
./run_performance_test.sh compare

# Output: comparison_20251009_143300.md
```

---

## Testing Workflow

### Standard Testing Process

1. **Run Performance Test**
   ```bash
   python manage.py test_price_upload_performance
   ```

2. **Review Results**
   - Check total duration
   - Verify throughput
   - Review database query count
   - Check for errors

3. **Analyze Logs** (if needed)
   ```bash
   python analyze_performance_logs.py --log django.log
   ```

4. **Compare with Baselines**
   - Total time < 30s ✓
   - Throughput > 150 items/s ✓
   - Queries < 500 ✓

5. **Investigate Issues** (if any)
   - Identify slow phases
   - Check query patterns
   - Review error logs
   - Optimize bottlenecks

### Continuous Monitoring

```bash
# Terminal 1: Run test
python manage.py test_price_upload_performance

# Terminal 2: Monitor logs
tail -f django.log | python analyze_performance_logs.py --stdin
```

---

## Troubleshooting Common Issues

### Issue 1: Slow Performance (> 60s)

**Investigation:**
```bash
python analyze_performance_logs.py --log django.log
```

**Common Causes:**
- CSV parsing inefficient → Check [PERF-CSV-PARSE]
- Product matching slow → Check [PERF-PRODUCT-MATCH]
- Too many database queries → Check query count

**Solutions:**
- Use pandas for CSV parsing
- Implement caching for product lookups
- Add database indexes
- Use select_related/prefetch_related

### Issue 2: High Query Count (> 1000)

**Investigation:**
```bash
# Check query patterns
grep "SELECT" django.log | head -20
```

**Common Causes:**
- N+1 query problem
- Missing database indexes
- Inefficient lookups in loops

**Solutions:**
- Pre-load products into memory
- Use bulk queries
- Add database indexes
- Implement query caching

### Issue 3: Memory Issues

**Symptoms:**
- Process killed
- Slow performance
- High swap usage

**Solutions:**
- Use streaming CSV parser
- Implement batch processing
- Clear caches between batches
- Process in chunks

---

## Integration Examples

### CI/CD Integration

```yaml
# .github/workflows/performance-test.yml
name: Performance Tests

on: [push, pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run performance tests
        run: python manage.py test_price_upload_performance
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: performance-report
          path: performance_results/
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Run quick performance test before commit
python manage.py test_price_upload_performance --dry-run

# Check performance threshold
DURATION=$(grep "Total Duration:" PERFORMANCE_TEST_RESULTS.md | grep -oE "[0-9.]+")
if (( $(echo "$DURATION > 60" | bc -l) )); then
    echo "❌ Performance regression detected!"
    exit 1
fi
```

---

## File Locations

```
/Users/sas/Repos/SASKITUP/
├── test_full_upload.py                    # Main test script
├── analyze_performance_logs.py            # Log analyzer
├── run_performance_test.sh                # Convenience runner
├── PERFORMANCE_TEST_README.md             # Detailed documentation
├── PERFORMANCE_TEST_RESULTS.md            # Results template
├── TESTING_SUMMARY.md                     # This file
└── schools/management/commands/
    └── test_price_upload_performance.py   # Django command
```

---

## Next Steps

1. **Run Initial Test**
   ```bash
   python manage.py test_price_upload_performance
   ```

2. **Establish Baseline**
   - Record current performance metrics
   - Set performance targets
   - Document acceptable ranges

3. **Implement Monitoring**
   - Add to CI/CD pipeline
   - Set up automated alerts
   - Track trends over time

4. **Optimize**
   - Identify bottlenecks
   - Implement improvements
   - Re-test and compare

5. **Document**
   - Record optimization attempts
   - Track performance improvements
   - Share learnings

---

## Support Resources

- **Django Logs:** `tail -f django.log`
- **Database Queries:** Enable `DEBUG=True` in settings
- **Memory Profiling:** Use `memory_profiler` package
- **Code Profiling:** Use `cProfile` module

---

## Success Criteria

✅ **Test Framework Complete:**
- [x] Main test script created
- [x] Log analyzer created
- [x] Django management command created
- [x] Convenience runner script created
- [x] Documentation complete

✅ **Testing Capabilities:**
- [x] Simulates real CSV upload
- [x] Captures performance metrics
- [x] Monitors database queries
- [x] Generates detailed reports
- [x] Supports multiple test modes

✅ **Documentation:**
- [x] Quick start guide
- [x] Detailed usage instructions
- [x] Troubleshooting guide
- [x] Expected baselines
- [x] Integration examples

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-09 | Initial performance testing framework |

---

**Ready to use!** Start with:
```bash
python manage.py test_price_upload_performance
```
