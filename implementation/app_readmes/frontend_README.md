# SASKITUP Frontend

This directory contains the complete frontend application for the SASKITUP project, built using the CozaStore e-commerce template and customized for school merchandise.

## Structure

```
frontend/
├── index.html              # Original user choice page (School/Club vs Customer)
├── home.html               # Main CozaStore-based home page
├── products.html           # Product listing page with advanced filtering
├── product-detail.html     # Product detail page with customization options
├── cart.html               # Shopping cart with bulk pricing and multi-school support
├── css/
│   ├── main.css           # CozaStore main styles
│   ├── util.css           # CozaStore utility classes
│   ├── styles.css         # Original SASKITUP styles
│   └── cart.css           # Custom cart styling
├── js/
│   ├── main.js            # CozaStore core functionality
│   ├── slick-custom.js    # Carousel/slider functionality
│   ├── map-custom.js      # Google Maps integration
│   └── cart.js            # Advanced cart functionality
├── vendor/                # Complete vendor library ecosystem
├── fonts/                 # Typography assets (Font Awesome, Poppins, etc.)
└── images/                # CozaStore image assets and placeholders
```

## Pages Overview

### 1. Home Page (`/`)
**File**: `home.html`
- **SASKITUP-branded e-commerce homepage** with school-focused sections
- **Featured schools/clubs showcase** with partnership highlights
- **Product categories** (Uniforms, Spirit Wear, Sports Equipment)
- **Trust indicators** (500+ partner schools, 10K+ students)
- **Testimonials** from principals, parents, and coaches

### 2. User Choice Page (`/choose/`)
**File**: `index.html`
- **Original role selection page** for School/Club Admin vs Customer choice
- **Simple, professional design** with clear navigation options
- **Sales team access** link at bottom

### 3. Products Listing (`/products/`)
**File**: `products.html`
- **Advanced filtering** by school, category, grade level, price range
- **Saskatchewan school integration** (U of S, U of R, WMCI, etc.)
- **Bulk pricing indicators** and wholesale vs retail pricing
- **Search functionality** with school and product suggestions
- **Isotope grid filtering** with multiple view options

### 4. Product Detail (`/product-detail/`)
**File**: `product-detail.html`
- **Multi-tier pricing system** (individual, bulk, institutional)
- **Customization options** (embroidery, numbers, logos)
- **School-specific information** and approval status
- **Size charts** tailored for school uniforms
- **Delivery options** (school vs home delivery)
- **Reviews system** with parent/student feedback

### 5. Shopping Cart (`/cart/`)
**File**: `cart.html`
- **Multi-school order management** with intelligent grouping
- **Dynamic bulk pricing** with real-time calculations
- **Custom item previews** and approval workflows
- **Delivery optimization** suggestions
- **Payment options** (school accounts, PO, credit cards)

## Key Features

### 🏫 School-Specific Features
- **Multi-school support** with school badges and logos
- **Grade-level filtering** (Elementary, Middle, High School, College)
- **Bulk pricing tiers** for classroom and team orders
- **Custom personalization** (names, numbers, logos)
- **School delivery coordination** with contact management
- **Approval workflows** for custom and bulk orders

### 💰 Advanced Commerce Features
- **Dynamic pricing** based on quantity and customization
- **Real-time inventory** checking and availability status
- **Wishlist functionality** with persistent storage
- **Quick reorder** for returning customers
- **Promo code support** with validation
- **Tax calculations** for educational purchases

### 🎨 Design System
- **SASKITUP color palette** with CSS custom properties
- **Responsive design** optimized for mobile and desktop
- **Accessibility compliance** (WCAG 2.1 AA)
- **Professional typography** using Poppins and modern fonts
- **Smooth animations** and micro-interactions

### ⚡ Technical Features
- **jQuery-based interactions** with modern ES6+ patterns
- **Bootstrap grid system** for responsive layouts
- **Isotope filtering** for product grids
- **Select2 dropdowns** for enhanced form controls
- **SweetAlert modals** for user feedback
- **Local storage** for cart persistence

## URL Structure

```
/                      → CozaStore home page (home.html)
/choose/               → User choice page (index.html)
/products/             → Product listing (products.html)
/product-detail/       → Product detail (product-detail.html)
/cart/                 → Shopping cart (cart.html)
/dashboard/            → Django admin dashboard
/admin/                → Django admin interface
/auth/                 → Authentication system
/clubs/                → Clubs management
/schools/              → Schools management
```

## Asset Integration

### CSS Files
- **main.css**: Complete CozaStore framework with responsive grid
- **util.css**: Utility classes for spacing, colors, and layout
- **cart.css**: Custom styling for cart functionality
- **styles.css**: Original SASKITUP brand styles

### JavaScript Files
- **main.js**: Core CozaStore functionality (navigation, modals, animations)
- **slick-custom.js**: Carousel and slider functionality
- **cart.js**: Advanced cart management with bulk pricing
- **map-custom.js**: Google Maps integration for store locations

### Vendor Libraries
- **Bootstrap**: Grid system and responsive utilities
- **jQuery**: DOM manipulation and AJAX
- **Select2**: Enhanced dropdowns and multi-select
- **Isotope**: Grid filtering and layout
- **SweetAlert**: Beautiful modal dialogs
- **Magnific Popup**: Image galleries and lightboxes

## Configuration

The frontend is fully integrated with Django through:

1. **Views**: `kitup/views.py` with dedicated view functions for each page
2. **URLs**: `kitup/urls.py` with clean URL routing
3. **Static Files**: Assets served at `/frontend/` path
4. **Authentication**: Public access configured in middleware

## Development

### Local Development
```bash
# Start Django server
python manage.py runserver

# Access pages
http://localhost:8001/           # Home page
http://localhost:8001/choose/    # User choice
http://localhost:8001/products/  # Products
http://localhost:8001/cart/      # Shopping cart
```

### Customization
1. **Brand Colors**: Update CSS custom properties in `main.css`
2. **Content**: Modify HTML content in respective page files
3. **Functionality**: Extend JavaScript in existing or new JS files
4. **Images**: Replace placeholder images with school-specific assets

## Browser Support

- **Modern Browsers**: Chrome 80+, Firefox 75+, Safari 13+, Edge 80+
- **Mobile**: iOS Safari 13+, Chrome Mobile 80+
- **Features**: ES6+, CSS Grid, Flexbox, CSS Custom Properties
- **Fallbacks**: Graceful degradation for older browsers

## Performance

- **Optimized Assets**: Compressed CSS and JavaScript
- **Image Optimization**: WebP support with JPEG fallbacks
- **Lazy Loading**: Images and content loaded on demand
- **Caching**: Browser caching headers for static assets
- **CDN Ready**: Assets structured for CDN deployment

The frontend is now **production-ready** and fully functional for the SASKITUP school merchandise platform!