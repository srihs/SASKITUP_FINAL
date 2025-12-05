# SAS Clubs Sync Fix - Comprehensive Plan

**Created**: 2025-10-02
**Status**: Awaiting Approval
**Priority**: Critical

---

## 1. Problem Summary

### Current Issue
The SAS clubs sync is syncing **non-club entities** to the `sas_clubs` table:
- **Total entries**: 72
- **Valid clubs**: ~40 (estimated)
- **Invalid entries**: ~32 (products, events, apparel, generic categories)

### Invalid Entry Examples
- **Products/Accessories** (Sport ID 1): Bags, Balls, Beanie, Bottle, Clearance, DEALS (30%-40% off)
- **Events** (Sport ID 17): Tag Nationals 2018, Tag Nationals 2019, Tag Nationals 2020, Trans Tasman
- **Apparel** (Sport ID 21): NATIONAL REFEREE APPAREL, REFEREE COACH APPAREL
- **Generic Categories** (Sport ID 16): Basketball, Cricket, Football | Hockey, Netball, Rugby | League
- **Uniform Categories** (Sport ID 23): Kids, Mens, Unisex, Womens
- **Misc** (Sport ID 19): Singlet Packs

### Root Cause
**File**: `/Users/sas/Repos/SASKITUP/clubs/management/commands/sync_sas_clubs.py`
**Lines**: 195-294

**Current Logic** (INCORRECT):
```python
# Line 195: Fetches ALL root categories (parent=0)
categories = self.woo_service.get_categories(parent_id=0, per_page=100)

# Lines 207-210: Only filters out Schools category (ID 98)
if skip_schools and category_id == self.SCHOOLS_CATEGORY_ID:
    continue

# Lines 213-216: Filters by school keywords but NOT product keywords
if skip_schools and self._is_school_related(category_name):
    continue

# Lines 286-294: Treats ALL subcategories as clubs
clubs = self.woo_service.get_categories(parent_id=sport_id, per_page=100)
```

**Problem**: This logic assumes ALL root categories are sports and ALL subcategories are clubs, which is incorrect.

---

## 2. WooCommerce Structure Analysis

### Root Categories (Parent ID = 0)
Total: 49 root categories analyzed

#### ✅ Valid Sports (13 categories) - INCLUDE THESE
| ID | Name | Product Count | Clubs |
|----|------|--------------|-------|
| 17 | Athletics | 51 | 7 |
| 46 | Basketball | 139 | 12 |
| 358 | American Flag Football | 4 | 1 |
| 462 | Cricket | 7 | 1 |
| 48 | Hockey | 6 | 1 |
| 120 | Netball | 5 | 1 |
| 60 | Rugby | 99 | 9 |
| 51 | Rugby League | 42 | 7 |
| 384 | Softball | 0 | 0 |
| 328 | Taranaki Hockey | 2 | 0 |
| 383 | Tennis | 0 | 0 |
| 99 | Touch | 26 | 3 |
| 319 | Touch NZ - Referee | 18 | 0 |

**Total Valid Clubs**: ~40 clubs across these sports

#### ❌ Products/Apparel (2 categories) - EXCLUDE THESE
| ID | Name | Product Count |
|----|------|--------------|
| 94 | Accessories | 44 |
| 406 | Uniforms | 53 |

#### ❌ Schools/Events (3 categories) - EXCLUDE THESE
| ID | Name | Product Count |
|----|------|--------------|
| 389 | School Leavers | 0 |
| 571 | School Name | 0 |
| 98 | Schools | 51 |

#### ⚠️ Unclear/Mixed (31 categories) - NEED EXCLUSION
Examples: Bibs Numbers, Corporate, Nickname Option, Number Option, Offers, Tournament, etc.

**Key Insight**: Most unclear categories are WooCommerce configuration options (ID Option, Number Option, etc.) or one-off events/corporate deals that should be excluded.

---

## 3. Proposed Solution

### Approach: Whitelist Valid Sports
Instead of trying to exclude everything invalid, **only include known valid sports**.

### Implementation Strategy

#### Step 1: Define Valid Sport Category IDs
Create a whitelist of the 13 valid sport categories:
```python
VALID_SPORT_CATEGORIES = [
    17,   # Athletics
    46,   # Basketball
    358,  # American Flag Football
    462,  # Cricket
    48,   # Hockey
    120,  # Netball
    60,   # Rugby
    51,   # Rugby League
    384,  # Softball
    328,  # Taranaki Hockey
    383,  # Tennis
    99,   # Touch
    319,  # Touch NZ - Referee
]
```

#### Step 2: Update Sync Logic
Replace lines 195-294 in `sync_sas_clubs.py`:

**BEFORE** (fetches all root categories):
```python
categories = self.woo_service.get_categories(parent_id=0, per_page=100)
```

**AFTER** (only process whitelisted sports):
```python
# Only sync clubs from whitelisted sport categories
for sport_id in self.VALID_SPORT_CATEGORIES:
    # Get sport category details
    sport_category = self.woo_service.get_category_by_id(sport_id)
    if not sport_category:
        continue

    sport_name = sport_category.get('name', '')
    self.stdout.write(f"\nProcessing sport: {sport_name} (ID: {sport_id})")

    # Get clubs under this sport
    clubs = self.woo_service.get_categories(parent_id=sport_id, per_page=100)

    # Process clubs (existing logic continues here)
    for club in clubs:
        # ... existing club processing logic ...
```

#### Step 3: Additional Filtering (Optional)
Even within valid sports, exclude subcategories that are clearly products/apparel:
```python
# Exclude keywords for subcategories
EXCLUDE_CLUB_KEYWORDS = [
    'APPAREL', 'GARMENT', 'UNIFORM', 'CLOTHING', 'PRODUCT',
    'REFEREE', 'DEALS', 'Clearance', 'Range', 'Option',
    'Pack', 'Nationals', 'Tournament'  # Events
]

# In club processing loop:
if any(keyword in club_name for keyword in self.EXCLUDE_CLUB_KEYWORDS):
    continue  # Skip this subcategory
```

---

## 4. Database Cleanup Strategy

### Current Invalid Entries to Remove

#### By Sport ID:
- **Sport ID 1** (Accessories parent): 10 entries - Bags, Balls, Beanie, etc.
- **Sport ID 16** (Generic categories): 7 entries - Basketball, Cricket, Netball, etc.
- **Sport ID 17** (Tag events): 5 entries - Tag Nationals 2018-2020, Trans Tasman
- **Sport ID 21** (Referee apparel): 2 entries - NATIONAL REFEREE APPAREL, REFEREE COACH APPAREL
- **Sport ID 23** (Uniform categories): 4 entries - Kids, Mens, Unisex, Womens
- **Sport ID 13** (Deals): 1 entry - DEALS (30%-40% off)
- **Sport ID 19** (Singlet Packs): 1 entry

**Total to Remove**: ~30 invalid entries

### Cleanup Method
```python
# Create management command: cleanup_invalid_sas_clubs.py
from clubs.models_sas import SASClub

# Delete by specific WooCommerce category IDs (invalid entries)
invalid_woo_ids = [
    286, 288, 403, 402, 511, 401, 292, 404, 439, 405,  # Accessories (Sport 1)
    367, 375, 377, 374, 373, 378, 376,  # Generic categories (Sport 16)
    204, 206, 213, 227, 205,  # Tag events (Sport 17)
    320, 327,  # Referee apparel (Sport 21)
    410, 408, 407, 409,  # Uniform categories (Sport 23)
    507,  # DEALS (Sport 13)
    432,  # Singlet Packs (Sport 19)
]

deleted_count = SASClub.objects.filter(woo_category_id__in=invalid_woo_ids).delete()
```

---

## 5. Implementation Steps

### Phase 1: Code Changes
1. ✅ **Analysis Complete** - Identified 13 valid sports and invalid entries
2. ⏳ **Update sync_sas_clubs.py**:
   - Add `VALID_SPORT_CATEGORIES` constant
   - Replace root category fetch logic with whitelist iteration
   - Add optional `EXCLUDE_CLUB_KEYWORDS` filtering
3. ⏳ **Create cleanup script**: `cleanup_invalid_sas_clubs.py` management command

### Phase 2: Database Cleanup
1. ⏳ **Backup database** (safety measure)
2. ⏳ **Run cleanup script** to remove ~30 invalid entries
3. ⏳ **Verify remaining clubs** are valid

### Phase 3: Re-sync
1. ⏳ **Run updated sync command**: `python manage.py sync_sas_clubs --store-type SAS`
2. ⏳ **Verify sync results**: Should have ~40 valid clubs
3. ⏳ **Test frontend display**: Ensure only valid clubs show on home page

### Phase 4: Validation
1. ⏳ **Database verification**: Count clubs by sport, verify all are legitimate
2. ⏳ **Frontend testing**: Check home page rotation with new clubs
3. ⏳ **Documentation**: Update sync documentation with whitelist approach

---

## 6. Expected Results

### Before Fix
- **Total entries**: 72
- **Valid clubs**: ~40
- **Invalid entries**: ~32 (44% invalid rate)
- **Sports represented**: 24 (many invalid)

### After Fix
- **Total entries**: ~40
- **Valid clubs**: ~40
- **Invalid entries**: 0 (0% invalid rate)
- **Sports represented**: 13 (all valid)

### Frontend Impact
- Home page will show only legitimate clubs (no products/events/apparel)
- Auto-rotation will cycle through ~40 valid clubs
- No more "NATIONAL REFEREE APPAREL" or "DEALS (30%-40% off)" in club section

---

## 7. Risks and Mitigation

### Risk 1: Missing Valid Clubs
**Risk**: Whitelist might exclude some valid clubs if their parent category wasn't identified
**Mitigation**:
- Cross-reference with https://www.sas.co.nz/clubs/ to verify all major sports covered
- Manual review of final club list before production deployment

### Risk 2: Database Cleanup Removes Valid Clubs
**Risk**: Cleanup script might accidentally remove valid clubs
**Mitigation**:
- Database backup before cleanup
- Dry-run mode to preview deletions
- Manual review of invalid_woo_ids list before execution

### Risk 3: WooCommerce Structure Changes
**Risk**: Future WooCommerce category reorganization could break whitelist
**Mitigation**:
- Add logging to detect new root categories
- Periodic review of WooCommerce structure
- Consider dynamic validation (API check for category types)

---

## 8. Testing Plan

### Unit Tests
- Test sync command with whitelisted categories
- Test exclusion of known invalid categories
- Test cleanup script with sample data

### Integration Tests
- Full sync with production WooCommerce data
- Verify club count matches expected ~40 clubs
- Verify no invalid entries after sync

### Frontend Tests
- Home page displays only valid clubs
- Auto-rotation works with cleaned data
- Mobile slider functions correctly

---

## 9. Rollback Plan

If issues arise after implementation:

1. **Restore database backup** from before cleanup
2. **Revert code changes** to original sync logic
3. **Re-run original sync** to restore 72 entries
4. **Analyze failures** and adjust plan
5. **Re-test in staging** before production retry

---

## 10. Timeline Estimate

- **Phase 1 (Code Changes)**: 2 hours
- **Phase 2 (Database Cleanup)**: 1 hour
- **Phase 3 (Re-sync)**: 30 minutes
- **Phase 4 (Validation)**: 1 hour
- **Total**: ~4.5 hours

---

## 11. Success Criteria

✅ Database contains only legitimate sports clubs (~40 entries)
✅ No products, events, or apparel in sas_clubs table
✅ All 13 valid sports represented with their clubs
✅ Frontend displays only valid clubs with proper rotation
✅ No errors during sync process
✅ Documentation updated with new approach

---

## 12. Approval Required

**Question for User**: Does this plan align with your requirements? Specifically:

1. **Whitelist Approach**: Is using a whitelist of 13 valid sports acceptable?
2. **Cleanup Strategy**: Are you comfortable removing ~30 invalid entries?
3. **Implementation Order**: Should we proceed with Phase 1 (code changes) first?

**Alternative Approaches** (if preferred):
- **Option A**: Blacklist approach (exclude known invalid categories instead of whitelist valid ones)
- **Option B**: Hierarchical markers (tag categories in WooCommerce as club/product/event)
- **Option C**: Manual curation (one-time manual cleanup, keep current sync logic)

---

**Awaiting your approval to proceed with implementation.**
