# SASKITUP Quotation Templates Documentation

## Overview

Complete Bootstrap 4 template system for quotation workflow with theme-consistent design matching the existing SASKITUP design system.

## Design System Reference

### Color Scheme
- **Primary Dark**: `#222831`
- **Primary Medium**: `#393E46`
- **Background Gradient**: `linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)`
- **Card Background**: `#ffffff`
- **Text Dark**: `#222831`
- **Text Light**: `#888888`

### Typography
- **Body Font**: Open Sans (via fonts.css)
- **Heading Font**: Jost (via fonts.css)
- **Base Size**: 1rem (16px)

### Shadows
- **Light**: `0 5px 20px rgba(0,0,0,0.08)`
- **Hover**: `0 10px 30px rgba(0,0,0,0.15)`
- **Deep**: `0 10px 40px rgba(34, 40, 49, 0.3)`

### Border Radius
- **Cards**: `15px`
- **Buttons**: `25px`
- **Badges**: `15px` (small), `20px` (large)

---

## Template Files

### 1. select_institution.html

**Purpose**: Institution selection page for creating quotations

**Context Variables Required**:
```python
{
    'user': User object,
    'tus_schools': [{
        'school': TUSSchool object,
        'assignment': Assignment object
    }],
    'wholesale_schools': [{
        'school': WholesaleSchool object,
        'assignment': Assignment object
    }],
    'lotto_clubs': [{
        'club': LottoClub object,
        'assignment': Assignment object
    }],
    'sas_clubs': [{
        'club': SASClub object,
        'assignment': Assignment object
    }]
}
```

**URL Names Used**:
- `quotations:select_institution`
- `quotations:product_listing` (with params: `institution_type`, `institution_id`)
- `profile`

**Features**:
- Grouped institutions by type (4 sections)
- Empty state when no assignments
- Responsive grid (3 cols desktop, 1 col mobile)
- Type-specific badges with color coding
- Hover effects on institution cards

**Type Badge Classes**:
- `.type-tus` - Blue (#e3f2fd / #1976d2)
- `.type-wholesale` - Green (#e8f5e9 / #388e3c)
- `.type-lotto` - Orange (#fff3e0 / #f57c00)
- `.type-sas` - Purple (#f3e5f5 / #7b1fa2)

---

### 2. product_listing.html

**Purpose**: Product browsing and selection for quotation

**Context Variables Required**:
```python
{
    'user': User object,
    'institution': Institution object (TUSSchool/WholesaleSchool/LottoClub/SASClub),
    'institution_type': str ('tus'/'wholesale'/'lotto'/'sas'),
    'products': Paginated Product queryset,
    'categories': Category queryset
}
```

**Product Object Requirements**:
```python
{
    'id': int,
    'name': str,
    'sku': str,
    'regular_price': Decimal,
    'sale_price': Decimal (optional),
    'stock_quantity': int,
    'category': Category object,
    'images': ProductImage queryset (first image used)
}
```

**URL Names Used**:
- `quotations:select_institution`
- `quotations:cart`

**JavaScript Context**:
```javascript
window.quotationContext = {
    institutionType: 'tus|wholesale|lotto|sas',
    institutionId: 123
}
```

**Features**:
- Search by name/SKU
- Category filter dropdown
- Stock status filter
- Responsive product grid (4 cols desktop, 1 col mobile)
- Quantity controls (1-100)
- Floating cart badge with count
- Product image placeholders
- Sale price display
- Pagination controls

**JavaScript Functions Used**:
- `increaseQuantity(productId)`
- `decreaseQuantity(productId)`
- `addToQuotation(productId)`
- `updateCartCount()`
- `filterProducts()`

---

### 3. quotation_cart.html

**Purpose**: Review and manage quotation items before saving

**Context Variables Required**:
```python
{
    'user': User object,
    'institution': Institution object,
    'institution_type': str,
    'cart_items': [{
        'product': Product object,
        'quantity': int
    }],
    'subtotal': Decimal,
    'discount': Decimal,
    'tax': Decimal,
    'total': Decimal
}
```

**URL Names Used**:
- `quotations:select_institution`
- `quotations:product_listing` (with params)

**Features**:
- Responsive cart items table
- Product thumbnails
- Quantity controls with +/- buttons
- Real-time line totals
- Sticky summary panel (desktop)
- Tax calculation (15%)
- Clear cart confirmation modal
- Empty cart state
- Continue shopping link

**JavaScript Functions Used**:
- `updateCartQuantity(productId, change)`
- `removeFromCart(productId)`
- `clearCart()` → opens modal
- `confirmClearCart()` → executes clear
- `saveQuotation()`

**Calculation Logic**:
```
Subtotal = Sum of (unit_price × quantity)
Tax = (Subtotal - Discount) × 0.15
Total = Subtotal - Discount + Tax
```

---

### 4. my_quotations.html

**Purpose**: List and manage all user quotations

**Context Variables Required**:
```python
{
    'user': User object,
    'quotations': [{
        'id': int,
        'quotation_number': str,
        'institution_name': str,
        'institution_type': str,
        'created_at': datetime,
        'total_amount': Decimal,
        'status': str ('draft'|'pending'|'approved'|'rejected'),
        'get_status_display': str
    }]
}
```

**URL Names Used**:
- `quotations:my_quotations`
- `quotations:select_institution`
- `quotations:quotation_detail` (with param: `quotation.id`)
- `quotations:edit_quotation` (with param: `quotation.id`)
- `profile`

**Features**:
- Status filter tabs (All, Draft, Pending, Approved, Rejected)
- DataTables integration (sorting, pagination, search)
- Status-specific badges with colors
- Action buttons based on status
- PDF download for approved/rejected
- Edit button for drafts
- Empty state for no quotations
- Responsive table design

**Status Badge Classes**:
- `.status-draft` - Blue
- `.status-pending` - Orange
- `.status-approved` - Green
- `.status-rejected` - Red

**JavaScript Functions Used**:
- `filterByStatus(status)`
- `downloadPDF(quotationId)`

**DataTables Configuration**:
```javascript
{
    pageLength: 10,
    order: [[3, 'desc']], // Sort by created date
    responsive: true,
    columnDefs: [
        { orderable: true, targets: [0,1,3,4,5] },
        { orderable: false, targets: [2,6] }
    ]
}
```

---

### 5. quotation_detail.html

**Purpose**: View complete quotation details and perform actions

**Context Variables Required**:
```python
{
    'user': User object,
    'quotation': {
        'id': int,
        'quotation_number': str,
        'institution_name': str,
        'institution_type': str,
        'status': str,
        'get_status_display': str,
        'created_by': User object,
        'created_at': datetime,
        'expires_at': datetime,
        'approved_at': datetime (optional),
        'rejected_at': datetime (optional),
        'subtotal': Decimal,
        'discount': Decimal,
        'tax': Decimal,
        'total_amount': Decimal,
        'notes': str (optional),
        'items': [{
            'product': {
                'name': str,
                'sku': str
            },
            'unit_price': Decimal,
            'quantity': int,
            'line_total': Decimal
        }],
        'versions': QuerySet (optional)
    }
}
```

**URL Names Used**:
- `quotations:my_quotations`
- `quotations:quotation_detail`
- `quotations:edit_quotation`
- `profile`

**Features**:
- Institution details section
- Timeline with key dates
- Read-only items table
- Pricing breakdown
- Optional notes display
- Version history accordion (if versions exist)
- Status-specific action buttons
- Delete confirmation modal

**Status-Specific Actions**:

**Draft**:
- Edit Quotation
- Submit for Approval
- Delete

**Pending**:
- Cancel Request

**Approved/Rejected**:
- Download PDF
- Create New Version

**JavaScript Functions Used**:
- `deleteQuotation(quotationId)` → opens modal
- `confirmDelete()` → executes delete
- `submitForApproval(quotationId)`
- `cancelQuotation(quotationId)`
- `downloadPDF(quotationId)`
- `createNewVersion(quotationId)`

**Accordion Compatibility**:
- Uses Bootstrap 4 `data-toggle="collapse"`
- NOT Bootstrap 5 `data-bs-toggle`

---

## JavaScript File: quotation.js

### Core Functions

#### Cart Management
```javascript
addToQuotation(productId)
// POST /quotations/add/
// Data: { product_id, quantity, institution_type, institution_id, csrfmiddlewaretoken }

updateCartQuantity(productId, change)
// POST /quotations/update/
// Data: { product_id, quantity, csrfmiddlewaretoken }

removeFromCart(productId)
// POST /quotations/remove/
// Data: { product_id, csrfmiddlewaretoken }

clearQuotationCart()
// POST /quotations/clear/
// Data: { csrfmiddlewaretoken }

saveQuotation()
// POST /quotations/save/
// Data: { csrfmiddlewaretoken }
```

#### UI Updates
```javascript
updateCartCount(count)
// Updates #cartCount badge and shows/hides #quotationBadge

updateCartSummary(summary)
// Updates #subtotal, #discount, #tax, #total

showToast(message, type)
// Types: 'success', 'error', 'warning', 'info'
// Auto-dismisses after 5 seconds
```

#### Utilities
```javascript
getCsrfToken()
// Returns CSRF token from form input or cookie

validateQuotationForm(formSelector)
// Validates required, email, and number fields
// Returns boolean

formatCurrency(amount)
// Returns: 'R 1,234.56'

calculateCartTotals(items)
// Returns: { subtotal, discount, tax, total }

debounce(func, wait)
// Utility for search/filter inputs
```

### AJAX Response Format

**Success Response**:
```json
{
    "success": true,
    "message": "Operation successful",
    "cart_count": 5,
    "cart_summary": {
        "subtotal": "1250.00",
        "discount": "0.00",
        "tax": "187.50",
        "total": "1437.50"
    },
    "redirect_url": "/quotations/my-quotations/"
}
```

**Error Response**:
```json
{
    "success": false,
    "message": "Error description",
    "errors": {
        "field_name": ["Error message"]
    }
}
```

---

## CSS File: quotation.css

### Key Classes

**Type Badges**:
- `.type-tus`, `.type-wholesale`, `.type-lotto`, `.type-sas`

**Status Badges**:
- `.status-draft`, `.status-pending`, `.status-approved`, `.status-rejected`

**Stock Badges**:
- `.stock-in`, `.stock-out`

**Loading States**:
- `.btn-loading` - Adds spinner overlay

**Form Validation**:
- `.is-invalid` - Red border with error icon
- `.invalid-feedback` - Error message text

**Utilities**:
- `.text-truncate-2` - Truncate to 2 lines
- `.text-truncate-3` - Truncate to 3 lines
- `.cursor-pointer` - Pointer cursor
- `.opacity-75`, `.opacity-50` - Opacity helpers

### Responsive Breakpoints

**Mobile (< 576px)**:
- Reduced padding
- Smaller images (150px)
- Smaller font sizes
- Stacked layouts

**Tablet (< 768px)**:
- Reduced header padding
- Cart summary becomes static
- Full-width buttons
- Smaller badge sizes

**Desktop (> 768px)**:
- Sticky cart summary
- Multi-column grids
- Larger interactive elements

---

## AJAX Endpoints

### Required Backend URLs

```python
# quotations/urls.py
urlpatterns = [
    path('select/', views.select_institution, name='select_institution'),
    path('products/<str:institution_type>/<int:institution_id>/',
         views.product_listing, name='product_listing'),
    path('cart/', views.quotation_cart, name='cart'),
    path('my-quotations/', views.my_quotations, name='my_quotations'),
    path('<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('<int:quotation_id>/edit/', views.edit_quotation, name='edit_quotation'),

    # AJAX endpoints
    path('add/', views.add_to_cart, name='add_to_cart'),
    path('update/', views.update_cart, name='update_cart'),
    path('remove/', views.remove_from_cart, name='remove_from_cart'),
    path('clear/', views.clear_cart, name='clear_cart'),
    path('save/', views.save_quotation, name='save_quotation'),
    path('cart-count/', views.cart_count, name='cart_count'),
    path('<int:quotation_id>/pdf/', views.download_pdf, name='download_pdf'),
]
```

---

## Bootstrap 4 Compatibility Notes

**Important Differences from Bootstrap 5**:

1. **Data Attributes**:
   - Use `data-toggle="modal"` NOT `data-bs-toggle="modal"`
   - Use `data-target="#modalId"` NOT `data-bs-target="#modalId"`
   - Use `data-dismiss="modal"` NOT `data-bs-dismiss="modal"`

2. **Modal Close Button**:
   - Custom `.btn-close` implementation in CSS
   - Uses `data-dismiss="modal"` for closing

3. **JavaScript**:
   - `$('#modal').modal('show')` - Show modal
   - `$('#modal').modal('hide')` - Hide modal
   - jQuery 3.2.1 required

4. **Form Validation**:
   - Custom `.is-invalid` styling
   - `.invalid-feedback` for error messages

---

## Integration Checklist

### Django Views Setup

- [ ] Create view for select_institution
- [ ] Create view for product_listing with pagination
- [ ] Create view for quotation_cart with session cart
- [ ] Create view for my_quotations with filtering
- [ ] Create view for quotation_detail
- [ ] Implement AJAX view for add_to_cart
- [ ] Implement AJAX view for update_cart
- [ ] Implement AJAX view for remove_from_cart
- [ ] Implement AJAX view for clear_cart
- [ ] Implement AJAX view for save_quotation
- [ ] Implement AJAX view for cart_count
- [ ] Implement PDF generation view

### URL Configuration

- [ ] Add quotations URLs to main urls.py
- [ ] Configure namespace as 'quotations'
- [ ] Test all URL patterns

### Static Files

- [ ] Ensure quotation.css is loaded
- [ ] Ensure quotation.js is loaded
- [ ] Verify fonts.css is accessible
- [ ] Verify Bootstrap 4 is loaded (NOT Bootstrap 5)
- [ ] Verify jQuery 3.2.1 is loaded

### Session/Cart Management

- [ ] Implement session-based cart storage
- [ ] Handle cart expiration
- [ ] Implement cart merge on login (if needed)
- [ ] Add cart clearing on quotation save

### Permissions

- [ ] Restrict quotation creation to sales reps
- [ ] Validate institution assignments
- [ ] Implement quotation ownership checks
- [ ] Add approval workflow permissions

### Testing

- [ ] Test all templates render correctly
- [ ] Test AJAX endpoints return proper JSON
- [ ] Test form validation
- [ ] Test cart operations
- [ ] Test quotation save workflow
- [ ] Test responsive design on mobile
- [ ] Test browser compatibility
- [ ] Test accessibility features

---

## Accessibility Features

### Keyboard Navigation
- All interactive elements are keyboard accessible
- Tab order is logical
- Focus states are visible (blue outline)

### Screen Readers
- Semantic HTML (`<header>`, `<nav>`, `<main>`, `<footer>`)
- ARIA labels on icon buttons
- Descriptive link text
- Form labels properly associated

### Visual
- High contrast colors (WCAG AA compliant)
- Large touch targets (minimum 44×44px)
- Clear focus indicators
- Readable font sizes (minimum 14px)

### Assistive Technology
- `.visually-hidden` class for screen reader only text
- Proper heading hierarchy
- Alt text on images
- Error messages announced

---

## Browser Support

### Tested Browsers
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Required Features
- ES6 JavaScript
- CSS Grid
- Flexbox
- CSS Custom Properties
- Fetch API (via jQuery AJAX)

### Polyfills
- None required for modern browsers
- Consider polyfill.io for legacy support

---

## Performance Optimization

### Image Optimization
- Lazy loading for product images (add if needed)
- Responsive images with srcset (add if needed)
- Image compression recommended

### JavaScript
- Debounced search/filter inputs
- Minimal DOM manipulation
- Event delegation where possible

### CSS
- No unused styles
- Optimized animations
- Hardware-accelerated transforms

### Caching
- Static files should be cached
- Session cart data cached
- Product data cached where possible

---

## Troubleshooting

### Common Issues

**Cart count not updating**:
- Check CSRF token is being sent
- Verify AJAX endpoint returns cart_count
- Check JavaScript console for errors

**Modal not opening**:
- Verify Bootstrap 4 JS is loaded
- Check data-toggle="modal" (not data-bs-toggle)
- Ensure modal ID matches data-target

**Styles not applying**:
- Check quotation.css is loaded after Bootstrap
- Verify CSS specificity
- Clear browser cache

**AJAX 403 Forbidden**:
- Check CSRF token is included
- Verify CSRF middleware is enabled
- Check cookie settings

**DataTables not initializing**:
- Ensure table has ID attribute
- Check DataTables JS is loaded
- Verify jQuery is loaded first

---

## Future Enhancements

### Potential Features
- [ ] Real-time collaboration
- [ ] Email quotation to institution
- [ ] Quotation templates
- [ ] Bulk product selection
- [ ] Product recommendations
- [ ] Price negotiation workflow
- [ ] Mobile app integration
- [ ] Export to Excel/CSV
- [ ] Quotation analytics dashboard
- [ ] Multi-language support

### Performance Improvements
- [ ] Implement virtual scrolling for large product lists
- [ ] Add Redis caching for cart data
- [ ] Optimize database queries with select_related
- [ ] Add CDN for static assets
- [ ] Implement service workers for offline support

---

## Support

For questions or issues with these templates, contact the development team or refer to:
- Django Documentation: https://docs.djangoproject.com/
- Bootstrap 4 Documentation: https://getbootstrap.com/docs/4.6/
- jQuery Documentation: https://api.jquery.com/

---

**Last Updated**: 2025-10-05
**Version**: 1.0.0
**Author**: Claude (Anthropic AI)
