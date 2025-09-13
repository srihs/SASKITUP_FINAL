# Clubs App - Technical Documentation

## Overview

The clubs app is the core Django application that handles LOTTO and SAS club management, product synchronization, and WooCommerce integration. It provides models, views, management commands, and services for the complete club ecosystem.

## Data Model Architecture

### Entity Relationship Diagram

```
┌──────────────┐     1:N     ┌──────────────────┐     1:N     ┌─────────────┐
│     Club     │◄────────────┤   ClubCategory   │◄────────────┤   Product   │
│              │             │                  │             │             │
├──────────────┤             ├──────────────────┤             ├─────────────┤
│ id (PK)      │             │ id (PK)          │             │ id (PK)     │
│ name         │             │ club_id (FK)     │             │ category_id │
│ slug         │             │ name             │             │ name        │
│ club_type    │             │ slug             │             │ slug        │
│ sport_tag    │             │ woo_category_id  │             │ woo_prod_id │
│ woo_cat_id   │             │ description      │             │ price       │
│ contact_...  │             │ image            │             │ description │
│ logo         │             │ product_count    │             │ image       │
│ is_active    │             │ created_at       │             │ stock_stat  │
│ created_at   │             │ updated_at       │             │ sku         │
│ updated_at   │             └──────────────────┘             │ created_at  │
└──────────────┘                                              │ updated_at  │
                                                               └─────────────┘
```

### Multi-Category Architecture

The system supports WooCommerce's multi-category product architecture through a ProductCategoryAssignment through model:

```
┌─────────────┐     M:N     ┌──────────────────────────┐     M:N     ┌──────────────────┐
│   Product   │◄────────────┤ ProductCategoryAssignment │────────────►│   ClubCategory   │
└─────────────┘             └──────────────────────────┘             └──────────────────┘
```

**ProductCategoryAssignment Fields:**
- `is_primary`: Boolean marking the primary category
- `sort_order`: Integer for category ordering
- `woo_category_id`: WooCommerce category ID
- `date_assigned`: Timestamp of assignment
- `last_synced`: Last sync with WooCommerce

### Model Specifications

#### Club Model
Primary entity representing sports clubs with comprehensive metadata:

```python
class Club(models.Model):
    CLUB_TYPES = [('LOTTO', 'LOTTO'), ('SAS', 'SAS')]
    SPORT_TAGS = ['Football', 'Rugby', 'Cricket', 'Basketball', ...]
    
    # Core Fields
    name = CharField(max_length=255, unique=True)
    slug = SlugField(max_length=255, unique=True, auto-generated)
    club_type = CharField(choices=CLUB_TYPES, default='LOTTO')
    sport_tag = CharField(choices=SPORT_TAGS, default='Football')
    
    # Contact Information
    contact_person = CharField(max_length=100, optional)
    email = EmailField(optional)
    website = URLField(optional)
    address = TextField(optional)
    
    # Integration Fields
    woo_category_id = PositiveIntegerField(unique=True)
    logo = URLField(max_length=500, optional)  # URL-based storage
    is_active = BooleanField(default=True)
    
    # Properties
    @property
    def total_products(self) -> int
    @property
    def active_categories_count(self) -> int
```

#### ClubCategory Model
Intermediate entity organizing products within clubs:

```python
class ClubCategory(models.Model):
    club = ForeignKey(Club, related_name='categories')
    name = CharField(max_length=255)
    slug = SlugField(auto-generated from club.name + name)
    woo_category_id = PositiveIntegerField(unique=True)
    description = TextField(optional)
    image = URLField(max_length=500, optional)  # URL-based storage
    product_count = PositiveIntegerField(default=0)
    
    # Methods
    def update_product_count(self) -> None
```

#### Product Model
Detailed product information with WooCommerce integration and multi-category support:

```python
class Product(models.Model):
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder')
    ]
    
    # Multi-category relationship
    categories = ManyToManyField(
        ClubCategory,
        through='ProductCategoryAssignment',
        related_name='products'
    )
    
    name = CharField(max_length=255)
    woo_product_id = PositiveIntegerField(unique=True)
    
    # Pricing
    price = DecimalField(max_digits=10, decimal_places=2)
    regular_price = DecimalField(optional)
    sale_price = DecimalField(optional)
    
    # Product Details
    description = TextField(optional)
    short_description = TextField(optional)
    sku = CharField(max_length=100, optional)
    stock_status = CharField(choices=STOCK_STATUS_CHOICES)
    image = URLField(max_length=500, optional)  # URL-based storage
    
    # WooCommerce Fields
    weight = CharField(optional)
    dimensions = JSONField(optional)
    tags = JSONField(optional)
    attributes = JSONField(optional)
    
    # Variation Display Properties
    @property
    def available_sizes(self) -> List[str]:
        """Returns unique sizes like ['S', 'M', 'L', 'XL']"""
        
    @property
    def available_colors(self) -> List[str]:
        """Returns unique colors like ['Black', 'Red', 'Blue']"""
        
    @property
    def primary_category(self) -> ClubCategory:
        """Returns the primary category for this product"""
    
    # Properties
    @property
    def is_on_sale(self) -> bool
    @property
    def discount_percentage(self) -> float
```

#### ProductVariation Model
Handles product variations with multi-dimensional support:

```python
class ProductVariation(models.Model):
    product = ForeignKey(Product, related_name='variations')
    woo_variation_id = PositiveIntegerField(unique=True)
    variation_type = CharField(max_length=50)  # 'size', 'color', etc.
    variation_value = CharField(max_length=255)  # 'XL - Black', 'Medium', etc.
    price = DecimalField(max_digits=10, decimal_places=2)
    stock_status = CharField(choices=Product.STOCK_STATUS_CHOICES)
    image = URLField(max_length=500, optional)  # URL-based storage
    
    class Meta:
        unique_together = ['product', 'variation_type', 'variation_value']
```

### Database Indexing Strategy

```python
# Optimized indexes for performance
class Meta:
    indexes = [
        # Club model
        models.Index(fields=['club_type', 'is_active']),
        models.Index(fields=['woo_category_id']),
        
        # ClubCategory model
        models.Index(fields=['club', 'product_count']),
        models.Index(fields=['woo_category_id']),
        
        # Product model
        models.Index(fields=['stock_status']),
        models.Index(fields=['woo_product_id']),
        models.Index(fields=['sku']),
        models.Index(fields=['price']),
        
        # ProductCategoryAssignment model
        models.Index(fields=['product', 'is_primary']),
        models.Index(fields=['category', 'sort_order']),
        models.Index(fields=['woo_category_id']),
        
        # ProductVariation model
        models.Index(fields=['product', 'variation_type']),
        models.Index(fields=['woo_variation_id']),
    ]
```

## WooCommerce Integration

### WooCommerceService Class

The core integration service provides a robust API client with comprehensive error handling and retry logic:

```python
class WooCommerceService:
    def __init__(self, store_type: str = 'LOTTO'):
        # Initialize with store-specific credentials
        # Setup retry strategy with exponential backoff
        # Configure authentication
        
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        # Authenticated API requests with rate limiting
        # Automatic retry on failures
        # Comprehensive error handling
        
    def get_categories_with_products(self, parent_id: int = 23) -> List[Dict]:
        # Paginated category retrieval
        # Filter by product count > 0
        
    def get_products_by_category(self, category_id: int) -> List[Dict]:
        # Paginated product retrieval
        # Published products only
        
    def download_image(self, image_url: str, folder: str) -> Optional[Tuple[str, ContentFile]]:
        # Automatic image download (deprecated - now uses URL storage)
        # Django ContentFile creation
        # Error handling and validation
```

### Data Mapping Strategy

```python
# WooCommerce Category → Django Club
category_data = {
    'id': 100,
    'name': 'Kaizer Chiefs FC',
    'count': 45,  # Products in this category
    'image': {'src': 'https://...'},
    'description': 'Official merchandise'
}

# Maps to Django Club instance
club = Club(
    name=category_data['name'],
    woo_category_id=category_data['id'],
    club_type='LOTTO',  # Based on store_type
    logo=category_data['image']['src'],  # Direct URL storage
)

# WooCommerce Subcategory → Django ClubCategory  
subcategory_data = {
    'id': 101,
    'parent': 100,
    'name': 'Jerseys',
    'count': 12
}

# Maps to Django ClubCategory instance
category = ClubCategory(
    club=club,
    name=subcategory_data['name'],
    woo_category_id=subcategory_data['id'],
    product_count=subcategory_data['count']
)
```

## Synchronization Process

### Management Command: sync_lotto_clubs

The synchronization process is handled by a Django management command that provides comprehensive options for data import and updates.

#### Command Structure

```bash
python manage.py sync_lotto_clubs [OPTIONS]

Options:
--store-type {LOTTO,SAS}     # Store type to sync (default: LOTTO)
--parent-category-id INT     # Parent category ID (default: 23)
--dry-run                    # Preview changes without database updates
--force-update               # Force update existing records
--limit INT                  # Limit number of clubs to process
```

#### Synchronization Workflow

```python
def handle(self, *args, **options):
    """
    Main synchronization workflow:
    1. Initialize WooCommerce service
    2. Test API connection
    3. Fetch categories with products
    4. Process each category as a club
    5. Sync subcategories and products with multi-category support
    6. Generate comprehensive reports
    """
    
    # Phase 1: Initialization
    woo_service = WooCommerceService(store_type=store_type)
    if not woo_service.test_connection():
        raise CommandError(f'Failed to connect to {store_type} WooCommerce API')
    
    # Phase 2: Data Retrieval
    categories = woo_service.get_categories_with_products(parent_id=parent_category_id)
    
    # Phase 3: Processing Loop with Multi-Category Support
    for category_data in categories:
        with transaction.atomic():
            # Process club
            club, created = self._process_club(category_data, store_type, woo_service)
            
            # Process categories
            subcategories = woo_service.get_categories(parent_id=category_data['id'])
            for subcat in subcategories:
                category, created = self._process_club_category(club, subcat, woo_service)
                
                # Process products with multi-category assignment
                products = woo_service.get_products_by_category(subcat['id'])
                for product in products:
                    self._process_product(category, product, woo_service)
```

### Multi-Category Product Processing

```python
def _process_product(self, category, product_data, woo_service, dry_run, force_update):
    """
    Process WooCommerce product with multi-category support:
    - Create or update product record
    - Handle ProductCategoryAssignment relationships
    - Process variations with multi-dimensional support
    """
    
    # Create or get product
    product, created = Product.objects.get_or_create(
        woo_product_id=product_data['id'],
        defaults=product_defaults
    )
    
    # Ensure category assignment
    assignment, created = ProductCategoryAssignment.objects.get_or_create(
        product=product,
        category=category,
        defaults={
            'is_primary': not ProductCategoryAssignment.objects.filter(product=product).exists(),
            'woo_category_id': category.woo_category_id,
            'sort_order': 0
        }
    )
    
    # Process variations with improved deduplication
    variations_data = woo_service.get_product_variations(product_data['id'])
    for variation_data in variations_data:
        self._process_individual_variation(product, variation_data, woo_service)
```

### Enhanced Variation Processing

```python
def _process_individual_variation(self, product, variation_data, woo_service):
    """
    Process individual variation with multi-dimensional support and duplicate prevention:
    - Extract size, color, and other attributes
    - Create composite variation values (e.g., "XL - Black")
    - Use get_or_create to prevent duplicates
    - Handle WooCommerce ID conflicts
    """
    
    # Check for existing variation by WooCommerce ID
    existing_variation = ProductVariation.objects.filter(
        woo_variation_id=variation_data['id']
    ).first()
    
    if existing_variation:
        return existing_variation, False
    
    # Extract multi-dimensional variation data
    variation_info = self._extract_multi_dimensional_variation_data(variation_data)
    
    # Use get_or_create based on unique constraint
    variation, created = ProductVariation.objects.get_or_create(
        product=product,
        variation_type=variation_info['type'],
        variation_value=variation_info['value'],
        defaults={
            'woo_variation_id': variation_data['id'],
            'price': variation_info['price'],
            'stock_status': variation_data.get('stock_status', 'instock'),
            'image': variation_data.get('image', {}).get('src', '') if variation_data.get('image') else ''
        }
    )
    
    # Handle WooCommerce ID conflicts
    if not created and variation.woo_variation_id != variation_data['id']:
        # Resolve conflict by updating WooCommerce ID
        self._resolve_variation_id_conflict(variation, variation_data['id'])
    
    return variation, created
```

## View Architecture

### Django View Classes

The application uses Django's class-based views for consistent, maintainable code:

#### Dashboard View
```python
class ClubDashboardView(ListView):
    """
    Main dashboard showing:
    - Total statistics (clubs, categories, products)
    - Top performing clubs by product count
    - Recent products across all clubs
    - Quick action buttons for navigation
    """
    model = Club
    template_name = 'clubs/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Dashboard statistics
        context['total_clubs'] = Club.objects.filter(is_active=True).count()
        context['total_lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
        context['total_products'] = Product.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
        
        # Top performing clubs with annotations
        context['top_clubs'] = Club.objects.filter(is_active=True).annotate(
            total_categories=Count('categories', filter=Q(categories__product_count__gt=0)),
            total_products=Count('categories__products', filter=Q(categories__products__stock_status__in=['instock', 'onbackorder']))
        ).order_by('-total_products', 'name')[:10]
        
        return context
```

#### Club List View with Advanced Filtering
```python
class ClubListView(ListView):
    """
    Comprehensive club listing with:
    - Search by name, contact person, sport
    - Filter by club type (LOTTO/SAS)
    - Filter by sport category
    - Pagination with 12 clubs per page
    - Statistics summary
    """
    model = Club
    paginate_by = 12
    
    def get_queryset(self):
        queryset = Club.objects.filter(is_active=True).prefetch_related('categories')
        
        # Club type filter
        club_type = self.request.GET.get('type')
        if club_type in ['LOTTO', 'SAS']:
            queryset = queryset.filter(club_type=club_type)
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(sport_tag__icontains=search_query)
            )
        
        # Sport filter
        sport = self.request.GET.get('sport')
        if sport:
            queryset = queryset.filter(sport_tag=sport)
        
        return queryset.order_by('name')
```

### Template Integration

Templates are located in `/template/clubs/` and use the base template structure with Bootstrap components. Key templates:

- `dashboard.html` - Main dashboard with statistics
- `club_list.html` - Club listing with filters
- `club_detail.html` - Individual club details
- `category_detail.html` - Category with products

## URL Patterns

### Clubs App URLs
```python
# clubs/urls.py
app_name = 'clubs'

urlpatterns = [
    # Dashboard and main views
    path('', views.ClubListView.as_view(), name='club-list'),
    path('dashboard/', views.ClubDashboardView.as_view(), name='dashboard'),
    
    # Club type specific views
    path('lotto/', views.LottoClubsView.as_view(), name='lotto-clubs'),
    path('sas/', views.SASClubsView.as_view(), name='sas-clubs'),
    
    # Detail views
    path('club/<slug:slug>/', views.ClubDetailView.as_view(), name='club-detail'),
    path('category/<slug:slug>/', views.ClubCategoryDetailView.as_view(), name='category-detail'),
    
    # AJAX endpoints
    path('ajax/search/', views.club_search_ajax, name='club-search-ajax'),
]
```

## Template Tags

### Custom Template Tags

Located in `clubs/templatetags/club_extras.py`:

```python
@register.filter
def proxy_image_url(image_url):
    """
    Proxy image URLs through local server to handle Cloudflare protection
    """
    if not image_url:
        return ''
    
    # Handle already proxied URLs
    if '/clubs/proxy-image/' in image_url:
        return image_url
        
    # Create proxy URL
    encoded_url = quote(image_url, safe='')
    return f'/clubs/proxy-image/?url={encoded_url}'
```

## Admin Configuration

### Enhanced Admin Interface

```python
# clubs/admin.py
@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ['name', 'club_type', 'sport_tag', 'total_products', 'is_active']
    list_filter = ['club_type', 'sport_tag', 'is_active']
    search_fields = ['name', 'contact_person']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'primary_category', 'price', 'stock_status']
    list_filter = ['stock_status', 'categories__club__club_type']
    search_fields = ['name', 'sku']
    filter_horizontal = ['categories']
    
    def primary_category(self, obj):
        return obj.primary_category
    primary_category.short_description = 'Primary Category'

@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = ['product', 'variation_type', 'variation_value', 'price']
    list_filter = ['variation_type', 'stock_status']
    search_fields = ['product__name', 'variation_value']
```

## Testing

### Model Tests
Located in `clubs/tests.py`:

```python
class ClubModelTests(TestCase):
    def test_club_creation(self):
        """Test club creation with multi-category support"""
        
    def test_product_category_assignment(self):
        """Test ProductCategoryAssignment relationships"""
        
    def test_variation_parsing(self):
        """Test multi-dimensional variation parsing"""
```

## Key Features

### 1. Multi-Category Product Support
- Products can belong to multiple categories
- Primary/secondary category designation
- Proper relationship management through ProductCategoryAssignment

### 2. Enhanced Variation Handling
- Multi-dimensional variations (size + color)
- Composite variation values ("XL - Black")
- Duplicate prevention and conflict resolution
- Base variation display (unique sizes/colors)

### 3. URL-Based Image Storage
- Direct storage of image URLs instead of downloading
- Cloudflare bypass through proxy system
- Improved performance and reduced storage

### 4. Robust Sync Process
- Transaction-based processing
- Comprehensive error handling
- Detailed logging and reporting
- Force update and dry-run modes

### 5. Advanced Search and Filtering
- Full-text search across multiple fields
- Category-based filtering
- AJAX-powered search suggestions
- Performance-optimized queries