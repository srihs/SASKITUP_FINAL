# SASKITUP Quotation Templates - Integration Guide

## File Locations (Absolute Paths)

### Templates (5 HTML files)
All templates use Bootstrap 4 (NOT Bootstrap 5) with `data-toggle` attributes.

1. **Institution Selection**
   - Path: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/select_institution.html`
   - URL Name: `quotations:select_institution`
   - Purpose: Sales rep selects institution to create quotation for

2. **Product Listing**
   - Path: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/product_listing.html`
   - URL Name: `quotations:product_listing`
   - Purpose: Browse and add products to quotation cart

3. **Quotation Cart**
   - Path: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/quotation_cart.html`
   - URL Name: `quotations:cart`
   - Purpose: Review cart items and save quotation

4. **My Quotations List**
   - Path: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/my_quotations.html`
   - URL Name: `quotations:my_quotations`
   - Purpose: View all quotations with filtering and DataTables

5. **Quotation Detail**
   - Path: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/quotation_detail.html`
   - URL Name: `quotations:quotation_detail`
   - Purpose: View complete quotation details and perform actions

### JavaScript

**Quotation System**
- Path: `/Users/sas/Repos/SASKITUP/static/frontend/js/quotation.js`
- Size: ~450 lines
- Functions: Cart management, AJAX operations, validation, toast notifications

### CSS

**Custom Quotation Styles**
- Path: `/Users/sas/Repos/SASKITUP/static/frontend/css/quotation.css`
- Size: ~600 lines
- Includes: Type badges, status badges, responsive styles, accessibility

### Documentation

**Template Documentation**
- Path: `/Users/sas/Repos/SASKITUP/quotations/TEMPLATE_DOCUMENTATION.md`
- Contains: Context variables, features, JavaScript functions, AJAX endpoints

**Integration Guide** (this file)
- Path: `/Users/sas/Repos/SASKITUP/quotations/INTEGRATION_GUIDE.md`

---

## Design System Summary

### Colors
```css
Primary Dark:    #222831
Primary Medium:  #393E46
Background:      linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)
Text Dark:       #222831
Text Light:      #888888
```

### Type Badges
```css
TUS School:       Blue   (#e3f2fd / #1976d2)
Wholesale School: Green  (#e8f5e9 / #388e3c)
LOTTO Club:       Orange (#fff3e0 / #f57c00)
SAS Club:         Purple (#f3e5f5 / #7b1fa2)
```

### Status Badges
```css
Draft:     Blue   (#e3f2fd / #1976d2)
Pending:   Orange (#fff3e0 / #f57c00)
Approved:  Green  (#e8f5e9 / #388e3c)
Rejected:  Red    (#ffebee / #c62828)
```

### Typography
- Body: Open Sans
- Headings: Jost
- Loaded via: `/Users/sas/Repos/SASKITUP/static/frontend/css/fonts.css`

---

## URL Structure Required

### View URLs
```python
# quotations/urls.py
from django.urls import path
from . import views

app_name = 'quotations'

urlpatterns = [
    # Page views
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

### Main URLs Include
```python
# main urls.py
urlpatterns = [
    # ...
    path('quotations/', include('quotations.urls', namespace='quotations')),
    # ...
]
```

---

## Context Variables Reference

### select_institution.html
```python
context = {
    'user': request.user,
    'tus_schools': [
        {'school': school_obj, 'assignment': assignment_obj}
    ],
    'wholesale_schools': [...],
    'lotto_clubs': [...],
    'sas_clubs': [...]
}
```

### product_listing.html
```python
context = {
    'user': request.user,
    'institution': institution_obj,  # TUSSchool/WholesaleSchool/LottoClub/SASClub
    'institution_type': 'tus|wholesale|lotto|sas',
    'products': paginated_products,  # Paginator object
    'categories': Category.objects.all()
}
```

### quotation_cart.html
```python
context = {
    'user': request.user,
    'institution': institution_obj,
    'institution_type': 'tus|wholesale|lotto|sas',
    'cart_items': [
        {'product': product_obj, 'quantity': 5}
    ],
    'subtotal': Decimal('1250.00'),
    'discount': Decimal('0.00'),
    'tax': Decimal('187.50'),
    'total': Decimal('1437.50')
}
```

### my_quotations.html
```python
context = {
    'user': request.user,
    'quotations': Quotation.objects.filter(created_by=request.user)
}
```

### quotation_detail.html
```python
context = {
    'user': request.user,
    'quotation': quotation_obj  # With related items, versions
}
```

---

## AJAX Endpoint Specifications

### POST /quotations/add/
**Request**:
```python
{
    'product_id': int,
    'quantity': int (1-100),
    'institution_type': str,
    'institution_id': int,
    'csrfmiddlewaretoken': str
}
```
**Response**:
```json
{
    "success": true,
    "message": "Product added to quotation!",
    "cart_count": 5
}
```

### POST /quotations/update/
**Request**:
```python
{
    'product_id': int,
    'quantity': int (1-100),
    'csrfmiddlewaretoken': str
}
```
**Response**:
```json
{
    "success": true,
    "cart_summary": {
        "subtotal": "1250.00",
        "discount": "0.00",
        "tax": "187.50",
        "total": "1437.50"
    }
}
```

### POST /quotations/remove/
**Request**:
```python
{
    'product_id': int,
    'csrfmiddlewaretoken': str
}
```
**Response**:
```json
{
    "success": true,
    "cart_count": 4,
    "cart_summary": {...}
}
```

### POST /quotations/clear/
**Request**:
```python
{
    'csrfmiddlewaretoken': str
}
```
**Response**:
```json
{
    "success": true,
    "message": "Cart cleared successfully"
}
```

### POST /quotations/save/
**Request**:
```python
{
    'csrfmiddlewaretoken': str
}
```
**Response**:
```json
{
    "success": true,
    "message": "Quotation saved successfully!",
    "redirect_url": "/quotations/my-quotations/",
    "quotation_id": 123
}
```

### GET /quotations/cart-count/
**Response**:
```json
{
    "success": true,
    "count": 5
}
```

---

## Session Cart Structure (Suggested)

```python
# Store in request.session
request.session['quotation_cart'] = {
    'institution_type': 'tus',
    'institution_id': 123,
    'items': {
        'product_1': {'quantity': 5},
        'product_2': {'quantity': 10}
    },
    'created_at': '2025-10-05T12:00:00'
}
```

---

## Static Files Loading Order

In all templates, files are loaded in this order:

1. **Fonts**
   - `/static/frontend/css/fonts.css`

2. **Bootstrap 4**
   - `/static/frontend/vendor/bootstrap/css/bootstrap.min.css`

3. **Icons**
   - `/static/frontend/fonts/font-awesome-4.7.0/css/font-awesome.min.css`
   - `/static/frontend/fonts/iconic/css/material-design-iconic-font.min.css`

4. **Vendor CSS**
   - `/static/frontend/vendor/animate/animate.css`
   - `/static/frontend/vendor/animsition/css/animsition.min.css`

5. **DataTables** (my_quotations.html only)
   - CDN: `https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css`

6. **Custom CSS**
   - `/static/frontend/css/util.css`
   - `/static/frontend/css/main.css`
   - `/static/frontend/css/quotation.css`

**JavaScript Loading Order**:

1. jQuery 3.2.1
2. Animsition
3. Popper.js
4. Bootstrap 4 JS
5. DataTables (if needed)
6. Main.js
7. Quotation.js

---

## JavaScript Functions Reference

### Cart Operations
```javascript
addToQuotation(productId)           // Add product to cart
updateCartQuantity(productId, change) // Update quantity (+1 or -1)
removeFromCart(productId)            // Remove item from cart
clearQuotationCart()                 // Clear entire cart
saveQuotation()                      // Save cart as quotation
```

### UI Updates
```javascript
updateCartCount(count)               // Update cart badge
updateCartSummary(summary)           // Update pricing display
showToast(message, type)            // Show notification toast
```

### Utilities
```javascript
getCsrfToken()                       // Get CSRF token
validateQuotationForm(selector)      // Validate form
formatCurrency(amount)               // Format as 'R 1,234.56'
calculateCartTotals(items)           // Calculate subtotal/tax/total
```

---

## Template Customization Points

### Header Navigation
Located in each template around line 170-210. Update menu items:
```html
<ul class="main-menu">
    <li><a href="{% url 'profile' %}">My Profile</a></li>
    <li class="active-menu"><a href="{% url 'quotations:select_institution' %}">Quotations</a></li>
    <li><a href="#">Reports</a></li>
</ul>
```

### Footer
Located around line 450-465. Update copyright year or text:
```html
<footer class="bg3 p-t-75 p-b-32">
    <div class="container">
        <p class="stext-107 cl6 txt-center">
            Copyright &copy; SASKITUP. All rights reserved.
        </p>
    </div>
</footer>
```

### Logo
Located around line 190-195:
```html
<a href="/" class="logo">
    <img src="{% static 'images/saskitup-logo.png' %}" alt="SASKITUP Logo" style="height: 60px;">
</a>
```

---

## Responsive Breakpoints

### Mobile (< 576px)
- Single column layouts
- Stacked forms
- Full-width buttons
- Smaller images (150px)

### Tablet (< 768px)
- 2 columns for product grid
- Cart summary becomes static (not sticky)
- Reduced padding

### Desktop (> 768px)
- 3-4 columns for grids
- Sticky cart summary
- Full feature set

---

## Accessibility Compliance

### WCAG 2.1 AA Features
- ✓ Semantic HTML5 elements
- ✓ ARIA labels on interactive elements
- ✓ Keyboard navigation support
- ✓ Focus indicators visible
- ✓ Color contrast ratios meet standards
- ✓ Form labels properly associated
- ✓ Error messages descriptive
- ✓ Alt text on images

### Testing Recommendations
- Use WAVE browser extension
- Test with NVDA/JAWS screen readers
- Validate keyboard-only navigation
- Check color contrast with tools

---

## Browser Testing Checklist

- [ ] Chrome (latest 2 versions)
- [ ] Firefox (latest 2 versions)
- [ ] Safari (latest 2 versions)
- [ ] Edge (latest 2 versions)
- [ ] Mobile Safari (iOS)
- [ ] Chrome Mobile (Android)

---

## Performance Considerations

### Page Load Optimization
- Minify CSS/JS for production
- Enable gzip compression
- Use CDN for static assets
- Implement browser caching

### Database Optimization
```python
# Use select_related for foreign keys
products = Product.objects.select_related('category').prefetch_related('images')

# Paginate product listings
from django.core.paginator import Paginator
paginator = Paginator(products, 20)  # 20 per page
```

### Session Management
- Set session expiry appropriately
- Clear cart sessions periodically
- Implement cart migration on login

---

## Security Checklist

- [ ] CSRF tokens on all POST requests
- [ ] User authentication required for all views
- [ ] Institution assignment validation
- [ ] Product availability checks
- [ ] Quotation ownership verification
- [ ] SQL injection prevention (use ORM)
- [ ] XSS prevention (Django auto-escapes)
- [ ] Rate limiting on AJAX endpoints

---

## Testing Scenarios

### Manual Testing
1. **Select Institution**
   - Verify all assigned institutions appear
   - Test empty state when no assignments
   - Check type badge colors

2. **Product Listing**
   - Test search functionality
   - Test category filter
   - Test stock filter
   - Add products with various quantities
   - Verify cart count updates

3. **Cart Management**
   - Update quantities
   - Remove items
   - Clear cart (with confirmation)
   - Save quotation

4. **Quotation List**
   - Filter by status
   - Search quotations
   - Sort columns
   - Test pagination

5. **Quotation Detail**
   - View all sections
   - Test status-specific actions
   - Verify version history (if applicable)

### Automated Testing
```python
# Sample test structure
from django.test import TestCase, Client
from django.urls import reverse

class QuotationTests(TestCase):
    def test_select_institution(self):
        response = self.client.get(reverse('quotations:select_institution'))
        self.assertEqual(response.status_code, 200)

    def test_add_to_cart(self):
        response = self.client.post(reverse('quotations:add_to_cart'), {
            'product_id': 1,
            'quantity': 5
        })
        self.assertEqual(response.json()['success'], True)
```

---

## Deployment Steps

1. **Collect Static Files**
   ```bash
   python manage.py collectstatic
   ```

2. **Verify Templates Directory**
   ```python
   # settings.py
   TEMPLATES = [{
       'DIRS': [BASE_DIR / 'templates'],
       # ...
   }]
   ```

3. **Check Static Files Configuration**
   ```python
   # settings.py
   STATIC_URL = '/static/'
   STATIC_ROOT = BASE_DIR / 'staticfiles'
   STATICFILES_DIRS = [BASE_DIR / 'static']
   ```

4. **Test All URLs**
   ```bash
   python manage.py show_urls  # If django-extensions installed
   ```

5. **Run Migrations**
   ```bash
   python manage.py makemigrations quotations
   python manage.py migrate
   ```

---

## Common Issues & Solutions

### Issue: Modals not opening
**Solution**: Verify Bootstrap 4 JS is loaded and using `data-toggle="modal"` (NOT `data-bs-toggle`)

### Issue: AJAX 403 Forbidden
**Solution**: Ensure CSRF token is included in all POST requests

### Issue: Cart count not updating
**Solution**: Check `cart_count` is returned in AJAX responses

### Issue: Styles not applying
**Solution**:
1. Check quotation.css is loaded AFTER Bootstrap
2. Clear browser cache
3. Run collectstatic

### Issue: DataTables not initializing
**Solution**:
1. Ensure table has `id="quotationsTable"`
2. Check DataTables JS is loaded
3. Verify jQuery is loaded first

---

## Next Steps

1. Implement Django views for all pages
2. Create AJAX endpoint views
3. Set up session-based cart storage
4. Implement quotation model and save logic
5. Add PDF generation functionality
6. Configure URL routing
7. Test thoroughly
8. Deploy to staging environment

---

## Support & Resources

### Documentation
- Full template docs: `/Users/sas/Repos/SASKITUP/quotations/TEMPLATE_DOCUMENTATION.md`
- Django docs: https://docs.djangoproject.com/
- Bootstrap 4: https://getbootstrap.com/docs/4.6/

### Code Locations
- Templates: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/`
- JavaScript: `/Users/sas/Repos/SASKITUP/static/frontend/js/quotation.js`
- CSS: `/Users/sas/Repos/SASKITUP/static/frontend/css/quotation.css`

---

**Created**: 2025-10-05
**Version**: 1.0.0
**Bootstrap**: 4.6 (NOT 5.x)
**jQuery**: 3.2.1
**DataTables**: 1.13.6
