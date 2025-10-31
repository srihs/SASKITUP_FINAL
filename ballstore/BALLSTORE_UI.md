# BallStore UI Integration

Complete UI system for browsing BallStore categories and products within the SASKITUP platform.

## Features Implemented

### 1. Category Browser
- **URL**: `/ballstore/`
- **View**: `category_list`
- **Template**: `ballstore/category_list.html`
- **Features**:
  - Grid layout showing all top-level categories
  - Product count per category
  - Sport-specific gradient colors
  - Sport icons (football, basketball, rugby, etc.)
  - Hover effects with smooth transitions
  - Responsive design (mobile-friendly)

### 2. Category Detail / Product Listing
- **URL**: `/ballstore/<category-slug>/`
- **View**: `category_detail`
- **Template**: `ballstore/category_detail.html`
- **Features**:
  - Product grid with Bootstrap cards
  - Search functionality (name, SKU, description)
  - Filters:
    - Stock status (In Stock, Out of Stock)
    - Product type (Simple, Variable)
    - Sale items
  - Breadcrumb navigation
  - Subcategory pills (if parent category)
  - Product information:
    - Featured image
    - Name
    - Price (regular and sale)
    - Stock status indicators
    - SKU
    - Variation count for variable products
    - Sale badges
  - External link to WooCommerce product page

## File Structure

```
ballstore/
├── views.py                                    # View logic
├── urls.py                                     # URL routing
├── models.py                                   # Existing models
├── templates/
│   └── ballstore/
│       ├── category_list.html                  # Category browser
│       └── category_detail.html                # Product listing
└── BALLSTORE_UI.md                             # This file
```

## Navigation Integration

The BallStore is accessible through the main navigation menu:

**Location**: Sidebar → Equipments → Ball Store

**Template**: `template/base.html` (line 326)

## URL Configuration

**Main URLs** (`kitup/urls.py`):
```python
path('ballstore/', include('ballstore.urls')),
```

**BallStore URLs** (`ballstore/urls.py`):
```python
path('', views.category_list, name='category-list'),
path('<slug:category_slug>/', views.category_detail, name='category-detail'),
```

## Design System

### Styling
- Bootstrap 5 framework
- Consistent with existing SASKITUP design
- Custom CSS for:
  - Product cards with hover effects
  - Category tiles with gradient backgrounds
  - Stock status badges
  - Sale indicators
  - Responsive grid layouts

### Color Scheme
- **Primary**: #556ee6 (brand color)
- **Success**: #0f5132 (in stock)
- **Danger**: #842029 (out of stock)
- **Warning**: #664d03 (backorder)
- **Sport Gradients**: Custom gradients per sport category

### Icons
Using Unicons icon set (already loaded in base template):
- `uil-football` - Soccer
- `uil-basketball` - Basketball
- `uil-football-american` - Rugby
- `uil-basketball-hoop` - Cricket
- `uil-volleyball` - Volleyball
- `uil-circle` - Netball
- `uil-box` - Generic products
- `uil-shopping-cart-alt` - Empty state
- `uil-external-link-alt` - External links

## Data Flow

### Category List View
1. Query active parent categories (no parent)
2. Annotate with product count
3. Order by name
4. Render category tiles

### Category Detail View
1. Get category by slug (with parent relationship)
2. Query active products in category
3. Prefetch product variations
4. Apply search filter (if provided)
5. Apply stock/type/sale filters
6. Get child categories (if parent)
7. Render product grid

## Search & Filter Features

### Search
- Searches across: name, SKU, description, short_description
- Case-insensitive partial matching
- Real-time filter via query parameter `?q=`

### Filters
- **Stock Status**: `?stock=instock|outofstock`
- **Product Type**: `?type=simple|variable`
- **Sale Items**: `?sale=true`

### Example URLs
```
/ballstore/                                      # All categories
/ballstore/soccer/                               # Soccer products
/ballstore/soccer/?q=ball                        # Search soccer balls
/ballstore/soccer/?stock=instock                 # In-stock soccer items
/ballstore/soccer/?stock=instock&sale=true       # In-stock sale items
```

## Product Information Display

### Simple Products
- Single price
- Stock status
- Direct purchase link

### Variable Products
- Badge showing number of variations
- Price range or "from" price
- Link to full product page for variation selection
- Each variation has: attributes (size, color), price, stock

## External Integration

Products link to WooCommerce store via `permalink` field:
- Opens in new tab/window
- Full product page with purchase options
- Maintains sync with WooCommerce data

## Responsive Design

### Breakpoints
- **XL** (≥1200px): 4 columns
- **LG** (≥992px): 3 columns
- **MD** (≥768px): 2 columns
- **SM** (<768px): 1 column

### Mobile Optimizations
- Touch-friendly card sizes
- Responsive search/filter bar
- Collapsible filters
- Optimized image loading

## Performance Considerations

### Database Optimization
- `select_related()` for parent category
- `prefetch_related()` for categories and variations
- `distinct()` for M2M category queries
- Annotated counts to reduce queries

### Frontend Optimization
- CSS transitions for smooth interactions
- Lazy loading considerations (future)
- Optimized image sizes from WooCommerce
- Session storage for scroll position

## Future Enhancements

### Potential Features
1. **Pagination**: For categories with many products
2. **Product Quick View**: Modal preview without leaving page
3. **Comparison**: Compare multiple products
4. **Favorites**: Save products for later
5. **Price Alerts**: Notify when prices drop
6. **Reviews**: Display WooCommerce reviews
7. **Related Products**: Cross-sell suggestions
8. **Advanced Filters**: Price range, brand, size, color
9. **Sort Options**: Price, popularity, newest
10. **Quotation Integration**: Add products to quotations

### API Integration
- Product availability real-time check
- Price updates from WooCommerce
- Inventory sync
- Order placement (future)

## Testing URLs

After running the development server:

```bash
python manage.py runserver
```

Visit:
- http://localhost:8000/ballstore/
- http://localhost:8000/ballstore/soccer/
- http://localhost:8000/ballstore/basketball/

## Dependencies

### Required Models
- `BallStoreCategory`: Categories with hierarchy
- `BallStoreProduct`: Products with pricing
- `BallStoreProductVariation`: Product options

### Required Data
Run sync command to populate database:
```bash
python manage.py sync_ballstore
```

## Template Inheritance

Both templates extend `base.html`:
- Header with navigation
- Sidebar menu
- Footer
- Common CSS/JS libraries
- User authentication state
- Shopping cart indicator

## Accessibility Features

- Semantic HTML structure
- ARIA labels on interactive elements
- Keyboard navigation support
- Screen reader friendly
- High contrast colors
- Focus indicators
- Alt text on images

## Browser Compatibility

Tested and compatible with:
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Maintenance

### Updating Styles
Edit CSS in template `{% block extra_css %}` sections

### Adding Categories
Categories sync automatically from WooCommerce

### Updating Products
Products sync automatically via management command

### Modifying Layout
- Category grid: `category_list.html`
- Product cards: `category_detail.html`
- Responsive columns: CSS classes in templates

## Support

For issues or questions:
1. Check Django logs: `django.log`
2. Check WooCommerce sync logs: Admin → BallStore → Sync Logs
3. Verify URL configuration: `python manage.py show_urls`
4. Check template rendering: Django Debug Toolbar (if installed)
