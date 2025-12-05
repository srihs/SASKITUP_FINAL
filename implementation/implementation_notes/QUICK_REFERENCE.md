# Quotation System - Quick Reference Guide

## URL Quick Reference

```
Step 1: /quotations/select-institution/          → Select institution
Step 2: /quotations/products/<type>/<id>/        → Browse products
Step 3: /quotations/cart/                        → View cart
AJAX:   /quotations/add/                         → Add item
AJAX:   /quotations/update/                      → Update quantity
AJAX:   /quotations/remove/                      → Remove item
AJAX:   /quotations/clear/                       → Clear cart
Step 4: /quotations/save/                        → Save quotation
Step 5: /quotations/my-quotations/               → My quotations
Detail: /quotations/detail/<uuid>/               → View quotation
```

---

## Session Structure

```python
request.session['quotation'] = {
    'items': [
        {
            'product_type': 'wholesaleproduct|lottoproduct|sasproduct',
            'product_id': 123,
            'product_name': 'Name',
            'product_sku': 'SKU',
            'quantity': 1,
            'unit_price': '99.99',
            'variations': {},
        }
    ],
    'institution_type': 'school|wholesaleschool|lottoclub|sasclub',
    'institution_id': 123,
}
```

---

## Helper Functions Cheat Sheet

```python
# Session Management
quotation_data = get_quotation_session(request)
save_quotation_session(request, quotation_data)
clear_quotation_session(request)

# Calculations
totals = calculate_quotation_totals(quotation_data)
# Returns: {'subtotal', 'tax_percentage', 'tax_amount', 'total', 'item_count'}

# Product Retrieval
product = get_product_by_type_and_id('wholesaleproduct', 123)

# Permission Checks
can_access = user_can_access_institution(user, 'school', 123)

# Institution Retrieval
institutions = get_user_institutions(user)
# Returns: {'schools', 'wholesale_schools', 'lotto_clubs', 'sas_clubs'}
```

---

## AJAX Request Examples

### Add to Quotation
```javascript
$.ajax({
    url: '/quotations/add/',
    method: 'POST',
    data: {
        product_type: 'wholesaleproduct',
        product_id: 123,
        quantity: 2,
        csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
    },
    success: function(response) {
        console.log(response.item_count);
    }
});
```

### Update Quantity
```javascript
$.ajax({
    url: '/quotations/update/',
    method: 'POST',
    data: {
        item_index: 0,
        quantity: 3,
        csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
    },
    success: function(response) {
        console.log(response.line_total);
    }
});
```

### Remove Item
```javascript
$.ajax({
    url: '/quotations/remove/',
    method: 'POST',
    data: {
        item_index: 0,
        csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
    },
    success: function(response) {
        console.log(response.item_count);
    }
});
```

### Save Quotation
```javascript
$.ajax({
    url: '/quotations/save/',
    method: 'POST',
    data: {
        csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
    },
    success: function(response) {
        window.location.href = response.redirect_url;
    }
});
```

---

## Institution Type → Product Type Mapping

```
School          → WholesaleProduct
WholesaleSchool → WholesaleProduct
LottoClub       → LottoProduct
SASClub         → SASProduct
```

---

## User Type Permissions

```
Sales Rep:
  - View: Assigned institutions only
  - Create: Quotations for assigned institutions
  - Access: Own quotations

Account Manager:
  - View: ALL institutions
  - Create: Quotations for any institution
  - Access: Own quotations

Customer:
  - View: Assigned institutions only
  - Create: Quotations for assigned institutions
  - Access: Own quotations

Admin:
  - View: ALL institutions
  - Create: Quotations for any institution
  - Access: ALL quotations
```

---

## Quotation Status Flow

```
draft → pending → approved ✓
               → rejected ✗
               → expired ⏱
               → cancelled ✗
```

---

## Template Variable Reference

### select_institution.html
```python
{
    'institutions': {
        'schools': [...],
        'wholesale_schools': [...],
        'lotto_clubs': [...],
        'sas_clubs': [...],
    },
    'total_count': 123,
}
```

### product_listing.html
```python
{
    'institution': institution_object,
    'institution_type': 'school',
    'institution_id': 123,
    'products': paginated_products,  # Django paginator object
    'search_query': 'search text',
    'quotation_item_count': 5,
}
```

### quotation_cart.html
```python
{
    'items': [
        {
            'product_type': 'wholesaleproduct',
            'product_id': 123,
            'product_name': 'Name',
            'product_sku': 'SKU',
            'quantity': 2,
            'unit_price': '99.99',
            'line_total': Decimal('199.98'),
            'product': product_object,  # Full object
        },
    ],
    'totals': {
        'subtotal': Decimal('199.98'),
        'tax_percentage': Decimal('15.00'),
        'tax_amount': Decimal('29.99'),
        'total': Decimal('229.97'),
        'item_count': 2,
    },
    'institution': institution_object,
    'institution_type': 'school',
    'institution_id': 123,
}
```

### my_quotations.html
```python
{
    'quotations': paginated_quotations,
    'status_choices': Quotation.STATUS_CHOICES,
    'current_status': 'draft',
    'search_query': 'Q-2025',
    'date_from': '2025-01-01',
    'date_to': '2025-12-31',
}
```

### quotation_detail.html
```python
{
    'quotation': quotation_object,
    'items': quotation_items_queryset,
}
```

---

## Calculation Formulas

```python
# Line Total
line_total = quantity × unit_price

# Subtotal
subtotal = sum(line_total for all items)

# Tax Amount
tax_amount = subtotal × 0.15  # 15% VAT

# Total
total = subtotal + tax_amount
```

---

## Common Django Template Tags

```django
{% url 'quotations:select-institution' %}
{% url 'quotations:product-listing' institution_type=type institution_id=id %}
{% url 'quotations:cart' %}
{% url 'quotations:my-quotations' %}
{% url 'quotations:quotation-detail' pk=quotation.id %}
```

---

## Model Methods Quick Reference

### Quotation Model
```python
# Create quotation
quotation = Quotation.objects.create(
    created_by=user,
    institution_content_type=content_type,
    institution_object_id=institution.id,
    status='draft'
)

# Calculate totals
quotation.calculate_totals()

# Approve quotation
quotation.approve(user, notes='Approved')

# Reject quotation
quotation.reject(user, reason='Price too high')

# Properties
quotation.institution_name    # Get institution name
quotation.institution_type    # Get institution type
quotation.is_expired          # Check if expired
quotation.days_until_expiry   # Days until expiry
```

### QuotationItem Model
```python
# Create item
item = QuotationItem.objects.create(
    quotation=quotation,
    product_content_type=content_type,
    product_object_id=product.id,
    product_name=product.name,
    product_sku=product.cin7_sku,
    quantity=2,
    unit_price=Decimal('99.99')
)

# Properties
item.product_type  # Get product type
```

---

## Error Messages

```python
# Validation Errors
"Quotation is empty"
"No institution selected"
"Quantity must be at least 1"
"Invalid item index"
"Product not found"

# Permission Errors
"You don't have permission to access this institution"
"You don't have permission to view this quotation"
```

---

## Testing Commands

```bash
# Run all quotation tests
python manage.py test quotations

# Run specific test
python manage.py test quotations.tests.test_views

# Create test data
python manage.py shell
>>> from quotations.tests.factories import create_test_data
>>> create_test_data()

# Check quotations in DB
python manage.py shell
>>> from quotations.models import Quotation
>>> Quotation.objects.count()
```

---

## Debugging Tips

```python
# Check session data
print(request.session.get('quotation'))

# Check user permissions
print(user.is_sales_rep, user.is_account_manager, user.is_customer)

# Check assignments
print(SalesRepSchoolAssignment.objects.filter(sales_rep=user, is_active=True).count())

# Check quotation totals
quotation.calculate_totals()
print(quotation.subtotal, quotation.tax_amount, quotation.total)
```

---

## Audit Log Queries

```python
# View quotation-related logs
from authentication.models import AuditLog

# All quotation actions
logs = AuditLog.objects.filter(
    description__icontains='quotation'
).order_by('-timestamp')

# Specific user's actions
logs = AuditLog.objects.filter(
    user=user,
    action_type='data_access'
).order_by('-timestamp')

# Permission denied attempts
logs = AuditLog.objects.filter(
    action_type='permission_denied'
).order_by('-timestamp')
```

---

## Common Queries

```python
# Get user's quotations
Quotation.objects.filter(created_by=user)

# Get quotations for institution
content_type = ContentType.objects.get_for_model(institution)
Quotation.objects.filter(
    institution_content_type=content_type,
    institution_object_id=institution.id
)

# Get active quotations
Quotation.objects.active()

# Get pending quotations
Quotation.objects.pending_approval()

# Get expired quotations
Quotation.objects.expired()
```

---

## File Locations

```
Views:          /Users/sas/Repos/SASKITUP/quotations/views.py
URLs:           /Users/sas/Repos/SASKITUP/quotations/urls.py
Models:         /Users/sas/Repos/SASKITUP/quotations/models.py
Templates:      /Users/sas/Repos/SASKITUP/quotations/templates/quotations/
Static Files:   /Users/sas/Repos/SASKITUP/static/quotations/
Docs:           /Users/sas/Repos/SASKITUP/quotations/QUOTATION_WORKFLOW.md
Main URLs:      /Users/sas/Repos/SASKITUP/kitup/urls.py
```

---

## Important Constants

```python
# Tax rate
TAX_PERCENTAGE = Decimal('15.00')  # 15% VAT

# Pagination
ITEMS_PER_PAGE = 20

# Quotation number format
"Q-YYYYMMDD-XXXX"  # Example: Q-20250105-0001

# Default expiry
30 days from creation
```

---

## Environment Setup

```bash
# Install dependencies
pip install django

# Make migrations
python manage.py makemigrations quotations

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver

# Access quotation system
http://localhost:8000/quotations/select-institution/
```

---

## Browser Console Debugging

```javascript
// Check CSRF token
console.log($('[name=csrfmiddlewaretoken]').val());

// Test AJAX request
$.ajax({
    url: '/quotations/add/',
    method: 'POST',
    data: {
        product_type: 'wholesaleproduct',
        product_id: 1,
        quantity: 1,
        csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
    },
    success: console.log,
    error: console.error
});

// Check session storage
console.log(sessionStorage);
console.log(localStorage);
```

---

## Useful Django Shell Commands

```python
# Import models
from quotations.models import Quotation, QuotationItem, CustomerInstitutionAssignment
from authentication.models import User
from schools.models import School, WholesaleSchool
from clubs.models_lotto import LottoClub
from clubs.models_sas import SASClub

# Create test user
user = User.objects.create_user(
    username='testuser',
    email='test@example.com',
    password='testpass',
    user_type='sales_rep'
)

# Create test quotation
from django.contrib.contenttypes.models import ContentType
school = School.objects.first()
ct = ContentType.objects.get_for_model(school)
quotation = Quotation.objects.create(
    created_by=user,
    institution_content_type=ct,
    institution_object_id=school.id
)

# View quotation
print(quotation.quotation_number)
print(quotation.institution_name)
print(quotation.get_status_display())
```
