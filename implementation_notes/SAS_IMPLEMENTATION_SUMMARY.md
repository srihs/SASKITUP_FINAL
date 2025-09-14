# SAS WooCommerce API Implementation Summary

## Key Findings for Model Design

### 1. API Connection Status
✅ **Successfully connected** to SAS WooCommerce API  
🔗 **API URL:** `https://www.sas.co.nz/wp-json/wc/v3/`  
⏱️ **Connection time:** 0.37 seconds  
📊 **Total categories:** 301

### 2. Hierarchy Structure (DIFFERENT from LOTTO)

**SAS Structure:** `Sports → Clubs/Teams → Products`  
**LOTTO Structure:** `Clubs → Categories → Products`

**Key Insight:** SAS requires completely separate models due to different hierarchy

### 3. Specific Category IDs and Data

#### Major Sport Categories (Root Level)
| Sport | ID | Teams | Products | Status |
|-------|----|----|----------|--------|
| Basketball | 46 | 12 | 139 | ✅ Sync |
| Rugby | 60 | 9 | 99 | ✅ Sync |
| Athletics | 17 | 7 | 51 | ✅ Sync |
| Rugby League | 51 | 12 | 41 | ✅ Sync |
| **Schools** | **98** | **22** | **40** | **❌ EXCLUDE** |
| Tag | 116 | 13 | 33 | ✅ Sync |
| Touch | 99 | Various | 28 | ✅ Sync |

#### Example Club Structure Under Basketball (ID: 46)
```
Basketball (46) → 139 products
├── Franklin Basketball (73) → 37 products ✅
├── Maori Basketball (79) → 24 products ✅  
├── Northland Basketball (482) → 20 products ✅
├── Tauranga Basketball (84) → 15 products ✅
├── Harbour Basketball (75) → 10 products ✅
└── [7 more teams...]
```

#### Schools Category Structure (MUST EXCLUDE)
```
Schools (98) → 40 products ❌ EXCLUDE ALL
├── Wellington College (529) → 8 products
├── Western Springs College (548) → 9 products  
├── Matamata College (518) → 3 products
├── Pakuranga College (298) → 5 products
└── [18 more schools with 0-8 products each]
```

### 4. School vs Club Identification Patterns

#### ✅ Club Keywords (INCLUDE)
- "Club", "FC", "Athletics", "Rugby Club", "Football Club"
- Location names: "Auckland", "Franklin", "Papatoetoe", "Wellington"
- Team names: "Lightning", "Eagles", "Rams", "Bears"

#### ❌ School Keywords (EXCLUDE)
- "College", "High School", "Grammar School", "Boys High School"
- "Secondary School", "University", "Academy", "Institute"

#### Examples Found:
**✅ Confirmed Clubs (14 total):**
- Tamaki Lightning American Football Club (4 products)
- Franklin Basketball (37 products) 
- Athletics Auckland (15 products)
- Beachlands Maraetai Rugby Club (12 products)

**❌ Confirmed Schools (23 total):**
- Wellington College (8 products)
- Green Bay High School (0 products)
- Mount Albert Grammar School (0 products)

### 5. Product Data Structure

#### Sample Variable Product Analysis
```json
{
  "name": "Tamaki Lightning Royal blue long sleeve tee",
  "id": 7699,
  "price": "$27",
  "type": "variable",
  "variations": 9,
  "attributes": ["Size"],
  "sizes": ["5XL", "4XL", "3XL", "2XL", "XL", "L", "M", "S", "XS"],
  "images": 2
}
```

#### Product Types Found:
- Team jerseys/singlets (most common)
- Hoodies and T-shirts  
- Caps and accessories
- Training gear
- Team bundle deals

### 6. Recommended Model Structure

```python
# THREE separate models needed:

1. SASSport (replaces LOTTO's flat club structure)
   - Maps to root sport categories (Basketball, Rugby, etc.)
   - woo_category_id links to sport category ID

2. SASClub (maps to teams under sports)  
   - Links to SASSport via foreign key
   - woo_category_id links to team/club category ID
   - is_school field for filtering

3. SASProduct (similar to LOTTO Product)
   - Links to SASClub via foreign key
   - Handles product variations (sizes)
```

### 7. Critical Implementation Details

#### School Filtering Logic
```python
EXCLUDE_PARENT_CATEGORIES = [98]  # Schools category
SCHOOL_KEYWORDS = [
    'college', 'high school', 'grammar school',  
    'secondary school', 'boys school', 'girls school'
]
```

#### Sync Strategy
1. **Start with Basketball (ID: 46)** - largest dataset with 139 products
2. **Test with Franklin Basketball (ID: 73)** - 37 products, good test size
3. **Exclude entire Schools category (ID: 98)**
4. **Process sports in order of product count**

### 8. Technical Requirements

#### Database Indexes Needed:
```python
# SASSport: woo_category_id, is_active
# SASClub: sport_id, is_school, woo_category_id  
# SASProduct: club_id, stock_status, woo_product_id
```

#### API Configuration:
- Same WooCommerceService class works
- Use `store_type='SAS'` parameter
- Rate limiting: 0.5-1 second delays sufficient

### 9. Implementation Priority

**Phase 1 (HIGH):** Core models + Basketball sync  
**Phase 2 (HIGH):** School filtering + remaining sports  
**Phase 3 (MED):** UI integration + sport navigation  
**Phase 4 (LOW):** Advanced features + optimization

## Summary

SAS has a fundamentally different structure requiring separate models. The hierarchy is Sports→Clubs→Products vs LOTTO's Clubs→Categories→Products. Clear school filtering is critical (23 schools to exclude). Basketball category (139 products) provides the best testing ground. All technical details confirmed through live API analysis.