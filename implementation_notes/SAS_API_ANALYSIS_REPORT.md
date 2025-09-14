# SAS WooCommerce API Structure Analysis Report

## Executive Summary

The SAS WooCommerce API has a fundamentally different structure from LOTTO, requiring separate models and sync logic. The hierarchy follows a **Sports → Clubs/Teams → Products** pattern, with clear distinctions between sports clubs and educational institutions.

## Key Findings

### 1. API Structure Overview

**Connection Status:** ✅ Successfully connected  
**Total Categories:** 301  
**Root Categories:** 50  
**API URL:** `https://www.sas.co.nz/wp-json/wc/v3/`

### 2. Hierarchy Structure

Unlike LOTTO's flat club structure, SAS follows a 3-level hierarchy:

```
ROOT SPORTS CATEGORIES
├── Basketball (ID: 46) → 139 products
│   ├── Franklin Basketball (ID: 73) → 37 products
│   ├── Maori Basketball (ID: 79) → 24 products
│   ├── Northland Basketball (ID: 482) → 20 products
│   └── ... (9 more basketball teams)
├── Rugby (ID: 60) → 99 products
│   ├── Papatoetoe Rugby (ID: 67) → 23 products
│   ├── Auckland Rugby Referees (ID: 429) → 17 products
│   └── ... (7 more rugby clubs)
├── Athletics (ID: 17) → 51 products
│   ├── Takapuna Athletics (ID: 69) → 17 products
│   ├── Athletics Auckland (ID: 519) → 15 products
│   └── ... (5 more athletics clubs)
└── Schools (ID: 98) → 40 products (EXCLUDE FROM SYNC)
    ├── Wellington College (ID: 529) → 8 products
    ├── Western Springs College (ID: 548) → 9 products
    └── ... (20 more schools)
```

### 3. Major Sport Categories

| Sport | Category ID | Teams/Clubs | Total Products | Note |
|-------|-------------|-------------|----------------|------|
| Basketball | 46 | 12 | 139 | Largest category |
| Rugby | 60 | 9 | 99 | Professional clubs |
| Athletics | 17 | 7 | 51 | Track & field clubs |
| Rugby League | 51 | 12 | 41 | Regional leagues |
| Schools | 98 | 22 | 40 | **EXCLUDE** |
| Tag | 116 | 13 | 33 | Touch rugby |
| Touch | 99 | Various | 28 | Touch rugby |

### 4. Club vs School Pattern Analysis

#### Clubs Found: 14 confirmed sports clubs
**Examples:**
- Tamaki Lightning American Football Club (4 products)
- Athletics Auckland (15 products)
- Franklin Basketball (37 products)
- Beachlands Maraetai Rugby Club (12 products)

**Club Identification Keywords:**
- "Club", "FC", "Athletics", "Rugby Club", "Football Club"
- Team location names (Auckland, Franklin, Papatoetoe)
- Sport-specific terms (Lightning, Eagles, Rams)

#### Schools Found: 23 educational institutions
**Examples:**
- Wellington College (8 products)
- Western Springs College (9 products)
- Matamata College (3 products)
- Green Bay High School (0 products)

**School Identification Keywords:**
- "College", "High School", "Grammar School"
- "Secondary School", "Boys High School"
- Educational institution names

### 5. Product Structure Analysis

**Sample Variable Product:**
- **Name:** Tamaki Lightning Royal blue long sleeve tee
- **ID:** 7699
- **Price:** $27
- **Type:** variable (has size variations)
- **Variations:** 9 (sizes: 5XL, 4XL, 3XL, etc.)
- **Attributes:** Size selection
- **Images:** 2 images available

**Common Product Types:**
- Jerseys/Singlets (team uniforms)
- Hoodies & T-shirts (casual wear)
- Caps & Accessories
- Training gear
- Team bundles/deals

## Recommended SAS Model Design

### Model Architecture

```python
# 1. SAS Sport Model (Top-level categories)
class SASSport(models.Model):
    name = models.CharField(max_length=255)  # "Basketball", "Rugby", etc.
    slug = models.SlugField(unique=True)
    woo_category_id = models.PositiveIntegerField(unique=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    product_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# 2. SAS Club Model (Teams under sports)
class SASClub(models.Model):
    sport = models.ForeignKey(SASSport, on_delete=models.CASCADE, related_name='clubs')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    woo_category_id = models.PositiveIntegerField(unique=True)
    
    # Contact fields
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    
    # SAS-specific fields
    club_type = models.CharField(
        max_length=20,
        choices=[('CLUB', 'Sports Club'), ('TEAM', 'Team')],
        default='CLUB'
    )
    region = models.CharField(max_length=100, blank=True)  # Auckland, Wellington, etc.
    
    # Image and status
    logo_url = models.URLField(blank=True)
    is_school = models.BooleanField(default=False)  # For debugging/filtering
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def total_products(self):
        return self.products.filter(stock_status__in=['instock', 'onbackorder']).count()

# 3. SAS Product Model
class SASProduct(models.Model):
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder')
    ]
    
    club = models.ForeignKey(SASClub, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    woo_product_id = models.PositiveIntegerField(unique=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Product details
    description = models.TextField(blank=True)
    short_description = models.TextField(blank=True)
    sku = models.CharField(max_length=100, blank=True)
    product_type = models.CharField(max_length=20, default='simple')  # simple/variable
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    
    # Images and media
    image_url = models.URLField(blank=True)
    gallery_urls = models.JSONField(default=list, blank=True)
    
    # Product attributes
    weight = models.CharField(max_length=50, blank=True)
    dimensions = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    attributes = models.JSONField(default=list, blank=True)
    
    # Variations (for variable products)
    has_variations = models.BooleanField(default=False)
    variation_data = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def is_on_sale(self):
        return self.sale_price and self.sale_price < self.regular_price
```

### Database Indexes

```python
class Meta:
    indexes = [
        # SASSport
        models.Index(fields=['is_active', 'product_count']),
        models.Index(fields=['woo_category_id']),
        
        # SASClub
        models.Index(fields=['sport', 'is_active']),
        models.Index(fields=['is_school', 'club_type']),
        models.Index(fields=['woo_category_id']),
        models.Index(fields=['region']),
        
        # SASProduct
        models.Index(fields=['club', 'stock_status']),
        models.Index(fields=['woo_product_id']),
        models.Index(fields=['product_type', 'has_variations']),
        models.Index(fields=['price']),
    ]
```

## Sync Logic Recommendations

### 1. School Filtering Logic

```python
SCHOOL_KEYWORDS = [
    'school', 'college', 'university', 'academy', 
    'high school', 'grammar school', 'boys school', 'girls school',
    'secondary', 'primary', 'prep', 'campus', 'institute'
]

def is_school_category(category_name: str) -> bool:
    name_lower = category_name.lower()
    return any(keyword in name_lower for keyword in SCHOOL_KEYWORDS)

# In sync process:
if is_school_category(category_data['name']):
    logger.info(f"Skipping school category: {category_data['name']}")
    continue
```

### 2. Sport Category Identification

```python
SPORT_ROOT_CATEGORIES = {
    46: 'Basketball',
    60: 'Rugby', 
    17: 'Athletics',
    51: 'Rugby League',
    116: 'Tag',
    99: 'Touch',
    48: 'Hockey',
    462: 'Cricket',
    120: 'Netball'
}

# Exclude from sync:
EXCLUDE_CATEGORIES = [98]  # Schools category
```

### 3. Sync Command Structure

```python
# New management command: sync_sas_clubs.py
class Command(BaseCommand):
    help = 'Sync SAS clubs from WooCommerce API'
    
    def add_arguments(self, parser):
        parser.add_argument('--sport-id', type=int, help='Sync specific sport only')
        parser.add_argument('--exclude-schools', action='store_true', default=True)
        parser.add_argument('--dry-run', action='store_true', help='Preview changes')
        
    def handle(self, *args, **options):
        # 1. Connect to SAS API
        # 2. Sync sports (root categories)
        # 3. For each sport, sync clubs (subcategories)
        # 4. Filter out schools
        # 5. For each club, sync products
        # 6. Handle product variations
```

## Implementation Priority

### Phase 1: Core Models (HIGH PRIORITY)
- Create `SASSport`, `SASClub`, `SASProduct` models
- Set up migrations
- Configure admin interface

### Phase 2: Sync Logic (HIGH PRIORITY)
- Implement school filtering
- Create `sync_sas_clubs` management command
- Add sport-specific sync logic

### Phase 3: UI Integration (MEDIUM PRIORITY)
- Add SAS section to dashboard
- Sport-based navigation
- Club listings by sport

### Phase 4: Advanced Features (LOW PRIORITY)
- Product variation handling
- Image optimization
- Performance monitoring

## Technical Specifications

### Key Category IDs

**Major Sports to Sync:**
- Basketball: 46 (12 teams, 139 products)
- Rugby: 60 (9 clubs, 99 products)  
- Athletics: 17 (7 clubs, 51 products)
- Rugby League: 51 (12 teams, 41 products)

**Categories to Exclude:**
- Schools: 98 (22 schools, 40 products)

### API Rate Limiting
- Current: 0.5-1 second delays between requests
- No rate limiting encountered during analysis
- Connection time: ~0.37 seconds

### Product Variations
- 6/6 analyzed products had variations (sizes)
- Common variations: Size (5XL, 4XL, 3XL, etc.)
- Price variations: Generally same price across sizes
- Image handling: Most variations use parent product image

## Conclusion

The SAS API analysis reveals a well-structured sports organization system that requires dedicated models separate from LOTTO. The clear separation between sports clubs and schools, combined with the hierarchical sport-based organization, provides a solid foundation for implementing comprehensive SAS integration.

**Next Steps:**
1. Implement the recommended SAS models
2. Create the sync command with school filtering
3. Set up sport-based UI navigation
4. Test with Basketball category (largest dataset)
5. Roll out to other major sports progressively

This analysis provides the complete technical foundation needed to implement robust SAS integration while maintaining clear separation from the existing LOTTO system.