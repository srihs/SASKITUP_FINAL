# Performance Testing Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PERFORMANCE TESTING FRAMEWORK                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CSV File (32MB)                                                │
│  ┌─────────────────────────────────────────┐                   │
│  │ all products for price update.csv       │                   │
│  │ • ~5000 rows                             │                   │
│  │ • SKU, Barcode, Price columns           │                   │
│  │ • Multiple product categories           │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TESTING LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐  ┌────────────────────┐                │
│  │  Django Command    │  │  Standalone Script │                │
│  │                    │  │                    │                │
│  │  test_price_       │  │  test_full_        │                │
│  │  upload_           │  │  upload.py         │                │
│  │  performance.py    │  │                    │                │
│  │                    │  │  • Direct Mode     │                │
│  │  ✓ Integrated      │  │  • HTTP Mode       │                │
│  │  ✓ Simple          │  │  • Custom Reports  │                │
│  │  ✓ Fast            │  │  ✓ Flexible        │                │
│  └────────────────────┘  └────────────────────┘                │
│           │                        │                             │
│           └────────┬───────────────┘                             │
│                    ▼                                             │
│  ┌──────────────────────────────────────────┐                  │
│  │      run_performance_test.sh             │                  │
│  │      (Convenience Wrapper)               │                  │
│  │                                          │                  │
│  │  • preview  - Preview only               │                  │
│  │  • full     - Preview + Apply            │                  │
│  │  • compare  - Compare runs               │                  │
│  │  • analyze  - Analyze logs               │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXECUTION LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Django Views Layer                      │       │
│  │                                                      │       │
│  │  wholesale_price_preview()                          │       │
│  │  ├─ CSV Parse                                       │       │
│  │  ├─ Product Matching (ProductMatcherService)       │       │
│  │  ├─ Validation                                      │       │
│  │  └─ Response Build                                  │       │
│  │                                                      │       │
│  │  wholesale_price_apply()                            │       │
│  │  ├─ Batch Updates                                   │       │
│  │  ├─ Database Transaction                            │       │
│  │  └─ Response Build                                  │       │
│  └─────────────────────────────────────────────────────┘       │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────┐       │
│  │          ProductMatcherService                       │       │
│  │                                                      │       │
│  │  • Category-aware matching                          │       │
│  │  • Cached product lookups                           │       │
│  │  • Composite SKU parsing (LOTTO)                    │       │
│  │  • Barcode fallback                                 │       │
│  └─────────────────────────────────────────────────────┘       │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Database Layer                          │       │
│  │                                                      │       │
│  │  • WholesaleProduct                                 │       │
│  │  • WholesaleSchool                                  │       │
│  │  • LOTTOProduct                                     │       │
│  │  • LOTTOClub                                        │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MONITORING LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │         Performance Logger                           │       │
│  │                                                      │       │
│  │  Captures:                                          │       │
│  │  • Phase durations ([PERF-*] tags)                 │       │
│  │  • Database query counts                            │       │
│  │  • Memory usage                                     │       │
│  │  • Throughput metrics                               │       │
│  └─────────────────────────────────────────────────────┘       │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Django Logs                             │       │
│  │                                                      │       │
│  │  • django.log                                       │       │
│  │  • Console output                                   │       │
│  │  • Query logs (DEBUG mode)                          │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ANALYSIS LAYER                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │    analyze_performance_logs.py           │                  │
│  │                                          │                  │
│  │  • Parse [PERF-*] tags                   │                  │
│  │  • Calculate statistics                  │                  │
│  │  • Identify bottlenecks                  │                  │
│  │  • Compare test runs                     │                  │
│  │  • Generate reports                      │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OUTPUT LAYER                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐  ┌────────────────────┐                │
│  │  Console Output    │  │  Report Files      │                │
│  │                    │  │                    │                │
│  │  • Real-time       │  │  • Markdown (.md)  │                │
│  │  • Summary         │  │  • JSON (.json)    │                │
│  │  • Assessments     │  │  • Comparisons     │                │
│  └────────────────────┘  └────────────────────┘                │
│                                                                  │
│  Generated Files:                                               │
│  • PERFORMANCE_TEST_RESULTS.md                                  │
│  • PERFORMANCE_ANALYSIS.md                                      │
│  • performance_results/*.md                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
CSV Upload (32MB)
       │
       ├─────────────────────────┐
       │                         │
       ▼                         ▼
  [Direct Mode]            [HTTP Mode]
       │                         │
       │                         │
       ▼                         ▼
Django Function Call      HTTP POST Request
       │                         │
       └──────────┬──────────────┘
                  │
                  ▼
        wholesale_price_preview()
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
CSV Parse   Product Match  Validation
  (2.3s)       (8.7s)       (1.2s)
    │             │             │
    └─────────────┼─────────────┘
                  │
                  ▼
         Response Build (0.5s)
                  │
                  ▼
         JSON Response (4850 items)
                  │
    ┌─────────────┼─────────────┐
    │                           │
    ▼                           ▼
Performance Metrics      (Optional) Apply Phase
• Total: 12.5s                  │
• Queries: 487                  ▼
• Throughput: 390/s     wholesale_price_apply()
    │                           │
    └───────────┬───────────────┘
                │
                ▼
        Report Generation
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
 Console    Markdown      JSON
 Output      Report       Data
```

---

## Metrics Collection Flow

```
┌──────────────────────────────────────────────────────┐
│              Phase Performance Tracking               │
├──────────────────────────────────────────────────────┤
│                                                       │
│  START: time.time()                                  │
│    │                                                  │
│    ├─► [PERF-CSV-PARSE]                             │
│    │   • Start: T0                                   │
│    │   • Read CSV chunks                             │
│    │   • Parse rows                                  │
│    │   • End: T1                                     │
│    │   • Duration: T1 - T0                           │
│    │                                                  │
│    ├─► [PERF-PRODUCT-MATCH]                         │
│    │   • Start: T1                                   │
│    │   • Pre-load products (cache)                  │
│    │   • Match by SKU/barcode                       │
│    │   • Track hit rate                             │
│    │   • End: T2                                     │
│    │   • Duration: T2 - T1                           │
│    │                                                  │
│    ├─► [PERF-VALIDATION]                            │
│    │   • Start: T2                                   │
│    │   • Validate prices                            │
│    │   • Check business rules                        │
│    │   • End: T3                                     │
│    │   • Duration: T3 - T2                           │
│    │                                                  │
│    ├─► [PERF-RESPONSE-BUILD]                        │
│    │   • Start: T3                                   │
│    │   • Build JSON response                        │
│    │   • End: T4                                     │
│    │   • Duration: T4 - T3                           │
│    │                                                  │
│    ▼                                                  │
│  END: T4                                             │
│  TOTAL: T4 - T0                                      │
│                                                       │
│  Database Metrics:                                    │
│  • len(connection.queries)                           │
│  • Query execution times                             │
│  • Transaction count                                 │
│                                                       │
└──────────────────────────────────────────────────────┘
```

---

## Component Interactions

```
┌────────────────────────────────────────────────────────────┐
│                    Test Runner                              │
│  (test_full_upload.py or management command)               │
└────────────────────────────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
    ┌──────────────────┐        ┌──────────────────┐
    │ Request Factory  │        │ Performance      │
    │                  │        │ Logger           │
    │ • Create mock    │        │                  │
    │   request        │        │ • Start timer    │
    │ • Attach CSV     │        │ • Track phases   │
    │ • Set user       │        │ • Count queries  │
    └──────────────────┘        └──────────────────┘
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   wholesale_price_      │
              │   preview()             │
              │                         │
              │  Calls                  │
              │    ↓                    │
              │  ProductMatcherService  │
              │    ↓                    │
              │  Database Queries       │
              │    ↓                    │
              │  Validation             │
              │    ↓                    │
              │  Response Build         │
              └─────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
    ┌──────────────────┐        ┌──────────────────┐
    │ JSON Response    │        │ Performance      │
    │                  │        │ Metrics          │
    │ • preview[]      │        │                  │
    │ • errors[]       │        │ • phases{}       │
    │ • total_rows     │        │ • queries        │
    │ • valid_rows     │        │ • throughput     │
    └──────────────────┘        └──────────────────┘
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   Report Generator      │
              │                         │
              │  • Format metrics       │
              │  • Calculate stats      │
              │  • Generate markdown    │
              │  • Save to file         │
              └─────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │ PERFORMANCE_TEST_       │
              │ RESULTS.md              │
              └─────────────────────────┘
```

---

## File Organization

```
/Users/sas/Repos/SASKITUP/
│
├── 📁 Testing Scripts (Root Level)
│   ├── test_full_upload.py              ⭐ Main test script
│   ├── analyze_performance_logs.py      ⭐ Log analyzer
│   └── run_performance_test.sh          ⭐ Quick runner
│
├── 📁 Documentation
│   ├── PERFORMANCE_TESTING_QUICKSTART.md  📘 Quick start
│   ├── TESTING_SUMMARY.md                 📘 Overview
│   ├── PERFORMANCE_TEST_README.md         📘 Detailed guide
│   ├── TESTING_ARCHITECTURE.md            📘 This file
│   └── PERFORMANCE_TEST_RESULTS.md        📄 Template
│
├── 📁 Django Integration
│   └── schools/management/commands/
│       └── test_price_upload_performance.py  ⚙️ Django command
│
└── 📁 Output (Generated at Runtime)
    └── performance_results/
        ├── preview_20251009_143000.md
        ├── full_20251009_143100.md
        ├── comparison_20251009_143200.md
        └── log_analysis_20251009_143300.md
```

---

## Execution Modes Comparison

```
┌──────────────────────────────────────────────────────────────┐
│                    DIRECT MODE                                │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Test Script                                                 │
│       │                                                       │
│       ├─► Create Django Request                             │
│       ├─► Call wholesale_price_preview()                    │
│       └─► Capture Response                                  │
│                                                               │
│  Advantages:                                                 │
│  ✓ No HTTP overhead                                         │
│  ✓ Faster execution                                         │
│  ✓ Direct function access                                   │
│  ✓ Easy debugging                                           │
│                                                               │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                     HTTP MODE                                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Test Script                                                 │
│       │                                                       │
│       ├─► HTTP POST to /api/price-preview/                  │
│       │   (requires running server)                          │
│       └─► Parse HTTP Response                               │
│                                                               │
│  Advantages:                                                 │
│  ✓ Real-world simulation                                    │
│  ✓ Tests full request/response cycle                        │
│  ✓ Includes middleware overhead                            │
│  ✓ Production-like testing                                  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Performance Monitoring Strategy

```
┌────────────────────────────────────────────────────────┐
│            CONTINUOUS MONITORING                        │
├────────────────────────────────────────────────────────┤
│                                                         │
│  Development Phase                                      │
│  ├─► Run test before commits                          │
│  ├─► Compare with baseline                            │
│  └─► Catch regressions early                          │
│                                                         │
│  Testing Phase                                          │
│  ├─► Full test suite                                  │
│  ├─► Multiple test runs                               │
│  └─► Performance report generation                    │
│                                                         │
│  Pre-Production                                         │
│  ├─► Load testing                                      │
│  ├─► Stress testing                                    │
│  └─► Baseline establishment                           │
│                                                         │
│  Production Monitoring                                  │
│  ├─► Real-time log analysis                           │
│  ├─► Performance trending                             │
│  └─► Alert on degradation                             │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## Key Components Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **test_full_upload.py** | Main test runner | • Direct/HTTP modes<br>• Full metrics collection<br>• Report generation |
| **analyze_performance_logs.py** | Log analyzer | • Parse [PERF-*] tags<br>• Statistics calculation<br>• Comparison reports |
| **test_price_upload_performance.py** | Django command | • Integrated testing<br>• Built-in assessment<br>• Simple usage |
| **run_performance_test.sh** | Quick runner | • One-command testing<br>• Multiple modes<br>• Result summaries |
| **ProductMatcherService** | Core logic | • Category-aware matching<br>• Caching<br>• Composite SKU support |

---

This architecture provides a comprehensive, flexible, and maintainable performance testing framework for the wholesale price upload system.
