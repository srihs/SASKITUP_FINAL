# Quotation Workflow Documentation

## Overview

The quotation system provides a comprehensive workflow for sales representatives, account managers, and customers to create, manage, and track quotations for schools and clubs.

## User Types and Access

### Sales Representatives
- Can create quotations for **assigned institutions only**
- Access controlled by `SalesRepSchoolAssignment` and `SalesRepClubAssignment`
- View their own quotations

### Account Managers
- Can create quotations for **ALL institutions**
- Full access to entire quotation system
- View their own quotations

### Customers
- Can create quotations for **assigned institutions only**
- Access controlled by `CustomerInstitutionAssignment`
- View their own quotations

### Admin
- Full system access
- Can view all quotations

## Workflow Steps

### Step 1: Institution Selection (`/quotations/select-institution/`)

**Purpose**: User selects the institution (school or club) to create a quotation for.

**View**: `InstitutionSelectionView`

**Data Flow**:
1. System calls `get_user_institutions(user)` helper function
2. Returns institutions grouped by type:
   - `schools` - Regular TUS schools
   - `wholesale_schools` - Wholesale schools
   - `lotto_clubs` - LOTTO clubs
   - `sas_clubs` - SAS clubs

**Template Variables**:
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

**User Actions**:
- Click "Select" button on institution card
- Redirects to Product Listing for that institution

---

### Step 2: Product Listing (`/quotations/products/<institution_type>/<institution_id>/`)

**Purpose**: Browse and select products based on institution type.

**View**: `ProductListingView`

**Product Mapping**:
- **School** → `WholesaleProduct`
- **WholesaleSchool** → `WholesaleProduct`
- **LottoClub** → `LottoProduct`
- **SASClub** → `SASProduct`

**Features**:
- Pagination (20 items per page)
- Search functionality (name, SKU, description)
- Product filtering
- Current quotation item count badge

**Template Variables**:
```python
{
    'institution': institution_object,
    'institution_type': 'school|wholesaleschool|lottoclub|sasclub',
    'institution_id': 123,
    'products': paginated_products,
    'search_query': 'search text',
    'quotation_item_count': 5,
}
```

**User Actions**:
- Click "Add to Quotation" button (AJAX)
- Product added to session storage
- Badge updated with new count

---

### Step 3: Quotation Cart (`/quotations/cart/`)

**Purpose**: Review and manage quotation items before saving.

**View**: `QuotationCartView`

**Data Source**: Session storage (`request.session['quotation']`)

**Features**:
- Display all items with product details
- Adjust quantities (AJAX)
- Remove individual items (AJAX)
- Clear all items
- Calculate totals (subtotal, tax, total)
- Save quotation to database

**Template Variables**:
```python
{
    'items': [
        {
            'product_type': 'wholesaleproduct',
            'product_id': 123,
            'product_name': 'Product Name',
            'product_sku': 'SKU123',
            'quantity': 2,
            'unit_price': '99.99',
            'line_total': Decimal('199.98'),
            'product': product_object,  # Full product object for display
        },
        ...
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

**User Actions**:
- Adjust quantity: AJAX call to `/quotations/update/`
- Remove item: AJAX call to `/quotations/remove/`
- Clear all: AJAX call to `/quotations/clear/`
- Save quotation: AJAX call to `/quotations/save/`

---

### Step 4: Save Quotation (`/quotations/save/`)

**Purpose**: Convert session data to permanent database records.

**View**: `SaveQuotationView` (POST only)

**Process**:
1. Validate quotation has items
2. Validate institution is set
3. Create `Quotation` record with:
   - `created_by`: Current user
   - `institution_content_type`: Institution type
   - `institution_object_id`: Institution ID
   - `status`: 'draft'
   - `quotation_number`: Auto-generated (Q-YYYYMMDD-XXXX)
4. Create `QuotationItem` records for each item
5. Calculate quotation totals
6. Clear session data
7. Redirect to My Quotations

**AJAX Response**:
```json
{
    "success": true,
    "quotation_id": "uuid-string",
    "quotation_number": "Q-20250105-0001",
    "redirect_url": "/quotations/my-quotations/"
}
```

---

### Step 5: My Quotations (`/quotations/my-quotations/`)

**Purpose**: List all quotations created by the user.

**View**: `MyQuotationsListView`

**Features**:
- Pagination (20 per page)
- Filter by status (draft, pending, approved, rejected, expired, cancelled)
- Filter by date range
- Search by quotation number

**Template Variables**:
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

**User Actions**:
- View quotation: Click on quotation number
- Filter by status: Select dropdown
- Search: Enter quotation number
- Date range: Select dates

---

### Quotation Detail (`/quotations/detail/<pk>/`)

**Purpose**: View full quotation details.

**View**: `QuotationDetailView`

**Access Control**:
- Users can only view their own quotations
- Admin and account managers can view all quotations

**Template Variables**:
```python
{
    'quotation': quotation_object,
    'items': quotation_items_queryset,
}
```

---

## Session Management

### Session Structure

```python
request.session['quotation'] = {
    'items': [
        {
            'product_type': 'wholesaleproduct',  # Model name in lowercase
            'product_id': 123,                   # Product primary key
            'product_name': 'Product Name',
            'product_sku': 'SKU123',
            'quantity': 2,
            'unit_price': '99.99',               # Stored as string
            'variations': {},                     # Product variations (size, color, etc.)
        },
        ...
    ],
    'institution_type': 'school',  # Institution model name in lowercase
    'institution_id': 123,         # Institution primary key
}
```

### Session Helper Functions

```python
# Get quotation session data (creates if not exists)
quotation_data = get_quotation_session(request)

# Save quotation data to session
save_quotation_session(request, quotation_data)

# Clear quotation session
clear_quotation_session(request)

# Calculate totals from session data
totals = calculate_quotation_totals(quotation_data)
```

---

## AJAX Endpoints

### Add to Quotation (`POST /quotations/add/`)

**Request**:
```javascript
{
    product_type: 'wholesaleproduct',
    product_id: 123,
    quantity: 2
}
```

**Response**:
```json
{
    "success": true,
    "item_count": 5,
    "subtotal": "199.98",
    "total": "229.97"
}
```

---

### Update Item Quantity (`POST /quotations/update/`)

**Request**:
```javascript
{
    item_index: 0,  // Index in session items array
    quantity: 3
}
```

**Response**:
```json
{
    "success": true,
    "line_total": "299.97",
    "subtotal": "299.97",
    "tax_amount": "44.99",
    "total": "344.96"
}
```

---

### Remove Item (`POST /quotations/remove/`)

**Request**:
```javascript
{
    item_index: 0
}
```

**Response**:
```json
{
    "success": true,
    "item_count": 4,
    "subtotal": "199.98",
    "tax_amount": "29.99",
    "total": "229.97"
}
```

---

### Clear Quotation (`POST /quotations/clear/`)

**Request**: Empty body

**Response**:
```json
{
    "success": true
}
```

---

## Permission Helper Functions

### `user_can_access_institution(user, institution_type, institution_id)`

Checks if user has permission to access the specified institution.

**Returns**: `True` if user can access, `False` otherwise

**Logic**:
1. Admin/Account Manager → Always `True`
2. Sales Rep → Check assignments
3. Customer → Check assignments

---

### `get_user_institutions(user)`

Get all institutions accessible by the user.

**Returns**:
```python
{
    'schools': [...],
    'wholesale_schools': [...],
    'lotto_clubs': [...],
    'sas_clubs': [...],
}
```

**Logic**:
- Admin/Account Manager → All active institutions
- Sales Rep → Assigned institutions from `SalesRepSchoolAssignment` and `SalesRepClubAssignment`
- Customer → Assigned institutions from `CustomerInstitutionAssignment`

---

### `get_product_by_type_and_id(product_type, product_id)`

Get product object by type and ID.

**Supported Types**:
- `wholesaleproduct` → `WholesaleProduct`
- `lottoproduct` → `LottoProduct`
- `sasproduct` → `SASProduct`

**Returns**: Product object or `None` if not found

---

## URL Patterns

```python
app_name = 'quotations'

urlpatterns = [
    # Step 1: Institution Selection
    path('select-institution/', InstitutionSelectionView, name='select-institution'),

    # Step 2: Product Listing
    path('products/<str:institution_type>/<int:institution_id>/', ProductListingView, name='product-listing'),

    # Step 3: Quotation Cart
    path('cart/', QuotationCartView, name='cart'),

    # AJAX Endpoints
    path('add/', AddToQuotationView, name='add-item'),
    path('update/', UpdateQuotationItemView, name='update-item'),
    path('remove/', RemoveQuotationItemView, name='remove-item'),
    path('clear/', ClearQuotationView, name='clear'),

    # Step 4: Save Quotation
    path('save/', SaveQuotationView, name='save'),

    # Step 5: My Quotations
    path('my-quotations/', MyQuotationsListView, name='my-quotations'),

    # Quotation Detail
    path('detail/<uuid:pk>/', QuotationDetailView, name='quotation-detail'),
]
```

---

## Calculation Logic

### Totals Calculation

```python
subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
tax_amount = subtotal * 0.15  # 15% VAT
total = subtotal + tax_amount
```

### Quotation Model Calculation

The `Quotation.calculate_totals()` method:
1. Calculates subtotal from all `QuotationItem` objects
2. Applies discount (percentage or fixed amount)
3. Calculates tax (15% on discounted subtotal)
4. Calculates final total
5. Saves to database

---

## Database Models

### Quotation

**Key Fields**:
- `id` (UUID): Primary key
- `quotation_number`: Auto-generated (Q-YYYYMMDD-XXXX)
- `created_by`: User who created quotation
- `institution_content_type`: GenericForeignKey type
- `institution_object_id`: GenericForeignKey ID
- `status`: draft | pending | approved | rejected | expired | cancelled
- `subtotal`, `tax_amount`, `total`: Calculated amounts
- `expires_at`: Quotation expiry date (default 30 days)

**Methods**:
- `calculate_totals()`: Recalculate all totals
- `approve(user, notes)`: Approve quotation
- `reject(user, reason)`: Reject quotation
- `create_version_snapshot(description)`: Create version snapshot

---

### QuotationItem

**Key Fields**:
- `id` (UUID): Primary key
- `quotation`: ForeignKey to Quotation
- `product_content_type`: GenericForeignKey type
- `product_object_id`: GenericForeignKey ID
- `product_name`, `product_sku`: Cached from product
- `quantity`: Item quantity
- `unit_price`: Price at time of quotation
- `line_total`: Calculated (quantity × unit_price)
- `variations`: JSON field for product variations

**Auto-Calculation**:
- `line_total` calculated on save
- `product_snapshot` created on first save
- Quotation totals updated on save/delete

---

### CustomerInstitutionAssignment

**Key Fields**:
- `id` (UUID): Primary key
- `customer`: ForeignKey to User (customer type)
- `institution_content_type`: GenericForeignKey type
- `institution_object_id`: GenericForeignKey ID
- `is_active`: Assignment status

**Purpose**: Allow customers to create quotations for assigned institutions

---

## Frontend Integration

### JavaScript Example (Add to Quotation)

```javascript
function addToQuotation(productType, productId, quantity) {
    $.ajax({
        url: '/quotations/add/',
        method: 'POST',
        data: {
            product_type: productType,
            product_id: productId,
            quantity: quantity,
            csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
        },
        success: function(response) {
            if (response.success) {
                // Update badge
                $('.quotation-badge').text(response.item_count);
                // Show success message
                alert('Product added to quotation');
            }
        },
        error: function(xhr) {
            alert('Error: ' + xhr.responseJSON.error);
        }
    });
}
```

---

### Template Example (Product Card)

```html
<div class="product-card">
    <img src="{{ product.image_url }}" alt="{{ product.name }}">
    <h3>{{ product.name }}</h3>
    <p>SKU: {{ product.cin7_sku }}</p>
    <p>Price: ${{ product.wholesale_price }}</p>
    <button onclick="addToQuotation('wholesaleproduct', {{ product.id }}, 1)">
        Add to Quotation
    </button>
</div>
```

---

## Audit Logging

All quotation operations are logged via `AuditLog.log_action()`:

- **Institution Selection**: `data_access` - Viewed institution selection
- **Product Listing**: `data_access` - Viewed product listing
- **Add Item**: `data_access` - Added product to quotation
- **Remove Item**: `data_access` - Removed product from quotation
- **Clear Cart**: `data_access` - Cleared quotation cart
- **Save Quotation**: `data_access` - Saved quotation
- **Permission Denied**: `permission_denied` - Attempted unauthorized access

---

## Error Handling

### Permission Denied

```python
if not user_can_access_institution(user, institution_type, institution_id):
    AuditLog.log_action(user, 'permission_denied', ...)
    raise PermissionDenied("You don't have permission...")
```

### AJAX Errors

All AJAX endpoints return consistent error responses:

```json
{
    "success": false,
    "error": "Error message here"
}
```

### Validation Errors

- Empty quotation: "Quotation is empty"
- No institution: "No institution selected"
- Invalid quantity: "Quantity must be at least 1"
- Invalid item index: "Invalid item index"

---

## Security Considerations

1. **Authentication Required**: All views use `LoginRequiredMixin`
2. **Permission Checks**: Institution access verified before displaying products
3. **CSRF Protection**: All POST requests require CSRF token
4. **User Isolation**: Users can only view their own quotations (except admin/account managers)
5. **Audit Logging**: All actions logged for compliance
6. **Input Validation**: All user inputs validated before processing

---

## Performance Optimization

1. **Database Queries**:
   - `select_related()` for ForeignKey lookups
   - `prefetch_related()` for reverse relationships
   - Indexed fields for common filters

2. **Session Storage**:
   - Quotation items stored in session (not database) until saved
   - Reduces database writes
   - Faster cart operations

3. **Pagination**:
   - 20 items per page for product listings and quotations
   - Reduces page load time

4. **AJAX Operations**:
   - Cart operations use AJAX for better UX
   - No full page reloads

---

## Future Enhancements

1. **PDF Generation**: Generate PDF quotations for download
2. **Email Notifications**: Email quotations to customers
3. **Quotation Templates**: Save frequently used quotations as templates
4. **Bulk Operations**: Add multiple products at once
5. **Price Negotiations**: Allow back-and-forth price adjustments
6. **Approval Workflow**: Multi-level approval process
7. **Quote Expiry Notifications**: Email alerts before expiry
8. **Analytics Dashboard**: Track quotation metrics
