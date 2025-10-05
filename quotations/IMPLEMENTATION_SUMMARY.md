# Quotation System Implementation Summary

## Files Created/Modified

### New Files Created

1. **`/Users/sas/Repos/SASKITUP/quotations/views.py`** (783 lines)
   - Complete quotation workflow views
   - 8 view classes and 4 helper functions
   - Session management utilities
   - AJAX endpoints for cart operations

2. **`/Users/sas/Repos/SASKITUP/quotations/urls.py`** (51 lines)
   - URL pattern configuration
   - 10 URL routes with proper namespacing

3. **`/Users/sas/Repos/SASKITUP/quotations/QUOTATION_WORKFLOW.md`** (Comprehensive documentation)
   - User workflow documentation
   - Session management details
   - AJAX API reference
   - Security and performance notes

### Modified Files

1. **`/Users/sas/Repos/SASKITUP/kitup/urls.py`**
   - Added `path('quotations/', include('quotations.urls'))` to main URL configuration

---

## Views Implemented

### 1. InstitutionSelectionView (Step 1)
**URL**: `/quotations/select-institution/`
**Method**: GET
**Purpose**: Display institutions accessible by user

**Features**:
- Gets user's accessible institutions via `get_user_institutions()`
- Groups by type: schools, wholesale_schools, lotto_clubs, sas_clubs
- Audit logging
- Permission-aware (sales reps see assigned, account managers see all)

**Template**: `quotations/select_institution.html`

---

### 2. ProductListingView (Step 2)
**URL**: `/quotations/products/<institution_type>/<institution_id>/`
**Method**: GET
**Purpose**: Display products for selected institution

**Features**:
- Permission verification via `user_can_access_institution()`
- Product mapping based on institution type:
  - School/WholesaleSchool → WholesaleProduct
  - LottoClub → LottoProduct
  - SASClub → SASProduct
- Search functionality (name, SKU, description)
- Pagination (20 items per page)
- Updates session with institution context
- Shows current quotation item count

**Template**: `quotations/product_listing.html`

---

### 3. QuotationCartView (Step 3)
**URL**: `/quotations/cart/`
**Method**: GET
**Purpose**: Display quotation cart

**Features**:
- Reads from session storage
- Enriches items with full product objects
- Calculates totals (subtotal, tax, total)
- Displays institution information
- Provides UI for quantity adjustment and item removal

**Template**: `quotations/quotation_cart.html`

---

### 4. AddToQuotationView (AJAX)
**URL**: `/quotations/add/`
**Method**: POST
**Purpose**: Add product to quotation

**Request Parameters**:
- `product_type`: Model name (wholesaleproduct, lottoproduct, sasproduct)
- `product_id`: Product primary key
- `quantity`: Item quantity (default 1)

**Response**:
```json
{
    "success": true,
    "item_count": 5,
    "subtotal": "199.98",
    "total": "229.97"
}
```

**Features**:
- Updates existing item quantity if already in cart
- Stores product snapshot
- Audit logging
- Error handling

---

### 5. UpdateQuotationItemView (AJAX)
**URL**: `/quotations/update/`
**Method**: POST
**Purpose**: Update item quantity

**Request Parameters**:
- `item_index`: Index in session items array
- `quantity`: New quantity (minimum 1)

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

### 6. RemoveQuotationItemView (AJAX)
**URL**: `/quotations/remove/`
**Method**: POST
**Purpose**: Remove item from quotation

**Request Parameters**:
- `item_index`: Index in session items array

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

### 7. ClearQuotationView (AJAX)
**URL**: `/quotations/clear/`
**Method**: POST
**Purpose**: Clear all quotation items

**Response**:
```json
{
    "success": true
}
```

---

### 8. SaveQuotationView (Step 4)
**URL**: `/quotations/save/`
**Method**: POST
**Purpose**: Save quotation to database

**Process**:
1. Validates quotation has items
2. Validates institution is set
3. Creates `Quotation` record
4. Creates `QuotationItem` records for each item
5. Calculates quotation totals
6. Clears session
7. Logs action
8. Returns JSON with redirect URL

**Response**:
```json
{
    "success": true,
    "quotation_id": "uuid-string",
    "quotation_number": "Q-20250105-0001",
    "redirect_url": "/quotations/my-quotations/"
}
```

---

### 9. MyQuotationsListView (Step 5)
**URL**: `/quotations/my-quotations/`
**Method**: GET
**Purpose**: List user's quotations

**Features**:
- Pagination (20 per page)
- Filter by status (draft, pending, approved, etc.)
- Filter by date range
- Search by quotation number
- Optimized queries with select_related and prefetch_related

**Template**: `quotations/my_quotations.html`

---

### 10. QuotationDetailView
**URL**: `/quotations/detail/<uuid:pk>/`
**Method**: GET
**Purpose**: View quotation details

**Features**:
- Permission check (user's own quotations or admin/account manager)
- Full quotation details with items
- Institution information
- Status and approval tracking

**Template**: `quotations/quotation_detail.html`

---

## Helper Functions

### 1. get_quotation_session(request)
**Purpose**: Get or create quotation session data
**Returns**: Session dictionary

**Session Structure**:
```python
{
    'items': [],
    'institution_type': None,
    'institution_id': None,
}
```

---

### 2. save_quotation_session(request, quotation_data)
**Purpose**: Save quotation data to session
**Parameters**: request, quotation_data dict

---

### 3. clear_quotation_session(request)
**Purpose**: Clear quotation session data
**Parameters**: request

---

### 4. calculate_quotation_totals(quotation_data)
**Purpose**: Calculate totals from session data
**Returns**:
```python
{
    'subtotal': Decimal,
    'tax_percentage': Decimal('15.00'),
    'tax_amount': Decimal,
    'total': Decimal,
    'item_count': int,
}
```

**Logic**:
- Subtotal = sum of (quantity × unit_price) for all items
- Tax = subtotal × 15%
- Total = subtotal + tax

---

### 5. get_product_by_type_and_id(product_type, product_id)
**Purpose**: Get product object by type and ID
**Parameters**: product_type (string), product_id (int)
**Returns**: Product object or None

**Supported Types**:
- `wholesaleproduct` → `WholesaleProduct`
- `lottoproduct` → `LottoProduct`
- `sasproduct` → `SASProduct`

---

### 6. user_can_access_institution(user, institution_type, institution_id)
**Purpose**: Check if user can access institution
**Parameters**: user, institution_type (string), institution_id (int)
**Returns**: Boolean

**Logic**:
1. Admin/Account Manager → Always True
2. Sales Rep → Check `SalesRepSchoolAssignment` or `SalesRepClubAssignment`
3. Customer → Check `CustomerInstitutionAssignment`

---

### 7. get_user_institutions(user)
**Purpose**: Get all institutions accessible by user
**Parameters**: user
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
- Sales Rep → Assigned institutions
- Customer → Assigned institutions

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

## Session Management

### Session Key: `request.session['quotation']`

### Session Data Structure:
```python
{
    'items': [
        {
            'product_type': 'wholesaleproduct',  # Model name
            'product_id': 123,                   # Product PK
            'product_name': 'Product Name',
            'product_sku': 'SKU123',
            'quantity': 2,
            'unit_price': '99.99',               # String
            'variations': {},                     # Product variations
        },
    ],
    'institution_type': 'school',  # Institution model name
    'institution_id': 123,         # Institution PK
}
```

### Session Operations:
- **Get**: `get_quotation_session(request)`
- **Save**: `save_quotation_session(request, data)`
- **Clear**: `clear_quotation_session(request)`

---

## Permission Model

### User Type Matrix

| User Type | Institution Access | Product Access | Quotation Access |
|-----------|-------------------|----------------|------------------|
| Sales Rep | Assigned only | All products for assigned institutions | Own quotations |
| Account Manager | All institutions | All products | Own quotations |
| Customer | Assigned only | All products for assigned institutions | Own quotations |
| Admin | All institutions | All products | All quotations |

### Assignment Models

1. **SalesRepSchoolAssignment**
   - Links sales reps to schools (regular or wholesale)
   - `is_active` flag for active assignments

2. **SalesRepClubAssignment**
   - Links sales reps to clubs (LOTTO or SAS)
   - Uses GenericForeignKey for club reference
   - `is_active` flag for active assignments

3. **CustomerInstitutionAssignment**
   - Links customers to institutions (any type)
   - Uses GenericForeignKey for institution reference
   - `is_active` flag for active assignments

---

## Database Models

### Quotation Model (from models.py)

**Key Fields**:
- `id`: UUID primary key
- `quotation_number`: Auto-generated (Q-YYYYMMDD-XXXX)
- `created_by`: User (ForeignKey)
- `institution_content_type`: GenericForeignKey type
- `institution_object_id`: GenericForeignKey ID
- `status`: draft | pending | approved | rejected | expired | cancelled
- `subtotal`, `tax_amount`, `total`: Decimal amounts
- `expires_at`: DateTimeField (default 30 days)

**Methods**:
- `calculate_totals()`: Recalculate all totals from items
- `approve(user, notes)`: Approve quotation
- `reject(user, reason)`: Reject quotation

---

### QuotationItem Model (from models.py)

**Key Fields**:
- `id`: UUID primary key
- `quotation`: ForeignKey to Quotation
- `product_content_type`: GenericForeignKey type
- `product_object_id`: GenericForeignKey ID
- `product_name`, `product_sku`: Cached strings
- `quantity`: Integer
- `unit_price`: Decimal
- `line_total`: Decimal (auto-calculated)
- `variations`: JSONField

**Auto-Calculation**:
- `line_total` calculated on save
- Triggers `quotation.calculate_totals()` on save/delete

---

## Security Features

1. **Authentication**: All views require login (`LoginRequiredMixin`)
2. **Permission Checks**: Institution access verified before operations
3. **CSRF Protection**: All POST requests require CSRF token
4. **User Isolation**: Users can only view their own data (except admin)
5. **Audit Logging**: All actions logged via `AuditLog.log_action()`
6. **Input Validation**: All user inputs validated
7. **SQL Injection Prevention**: Django ORM used throughout
8. **XSS Prevention**: Template auto-escaping enabled

---

## Audit Logging

All operations logged with:
- **User**: Who performed action
- **Action Type**: `data_access`, `permission_denied`
- **Description**: Human-readable description
- **Request**: IP address, user agent, session key
- **Metadata**: Additional context (product IDs, quotation numbers, etc.)

**Logged Operations**:
- Institution selection viewed
- Product listing viewed
- Product added to quotation
- Product removed from quotation
- Quotation cleared
- Quotation saved
- Permission denied attempts

---

## Error Handling

### Permission Errors
```python
if not user_can_access_institution(...):
    AuditLog.log_action(...)
    raise PermissionDenied("You don't have permission...")
```

### AJAX Errors
```json
{
    "success": false,
    "error": "Error message"
}
```

### Validation Errors
- Empty quotation: 400 Bad Request
- No institution: 400 Bad Request
- Invalid quantity: 400 Bad Request
- Product not found: 404 Not Found
- Invalid item index: 400 Bad Request

---

## Performance Optimizations

1. **Query Optimization**:
   - `select_related()` for ForeignKey lookups
   - `prefetch_related()` for reverse relationships
   - Database indexes on frequently filtered fields

2. **Session Storage**:
   - Cart items stored in session (not database)
   - Reduces database writes
   - Faster cart operations

3. **Pagination**:
   - 20 items per page
   - Reduces query size and page load time

4. **AJAX Operations**:
   - No full page reloads for cart operations
   - Better user experience

5. **Caching**:
   - Product details cached in session items
   - Reduces repeated database queries

---

## Frontend Integration Requirements

### Templates to Create

1. **`quotations/select_institution.html`**
   - Display institution cards grouped by type
   - "Select" buttons linking to product listing

2. **`quotations/product_listing.html`**
   - Product grid/list with pagination
   - Search bar
   - "Add to Quotation" buttons (AJAX)
   - Quotation item count badge

3. **`quotations/quotation_cart.html`**
   - Cart items table
   - Quantity adjustment controls (AJAX)
   - Remove item buttons (AJAX)
   - Totals display
   - "Save Quotation" button (AJAX)
   - "Clear All" button (AJAX)

4. **`quotations/my_quotations.html`**
   - Quotations table with pagination
   - Status filter dropdown
   - Date range filters
   - Search bar
   - Links to quotation details

5. **`quotations/quotation_detail.html`**
   - Full quotation details
   - Items table
   - Institution information
   - Status and approval information

### JavaScript Requirements

```javascript
// Add to quotation (AJAX)
function addToQuotation(productType, productId, quantity) {
    // POST to /quotations/add/
    // Update badge on success
}

// Update quantity (AJAX)
function updateQuantity(itemIndex, quantity) {
    // POST to /quotations/update/
    // Update line total and totals on success
}

// Remove item (AJAX)
function removeItem(itemIndex) {
    // POST to /quotations/remove/
    // Remove row and update totals on success
}

// Clear cart (AJAX)
function clearCart() {
    // POST to /quotations/clear/
    // Clear UI on success
}

// Save quotation (AJAX)
function saveQuotation() {
    // POST to /quotations/save/
    // Redirect to my-quotations on success
}
```

---

## Testing Checklist

### Unit Tests
- [ ] Helper functions (session management, calculations)
- [ ] Permission functions
- [ ] Product type mapping

### Integration Tests
- [ ] Institution selection flow
- [ ] Product listing with filters
- [ ] Cart operations (add, update, remove, clear)
- [ ] Save quotation process
- [ ] Quotation list and detail views

### Permission Tests
- [ ] Sales rep can only see assigned institutions
- [ ] Account manager can see all institutions
- [ ] Customer can only see assigned institutions
- [ ] Users can only view their own quotations
- [ ] Admin can view all quotations

### AJAX Tests
- [ ] Add to quotation
- [ ] Update quantity
- [ ] Remove item
- [ ] Clear cart
- [ ] Save quotation

### Edge Cases
- [ ] Empty cart save attempt
- [ ] No institution selected
- [ ] Invalid product ID
- [ ] Invalid item index
- [ ] Quantity < 1
- [ ] Permission denied scenarios

---

## Next Steps

1. **Create Templates** (5 templates required)
2. **Add JavaScript** (AJAX functionality)
3. **Create Migrations** (if models modified)
4. **Run Migrations** (`python manage.py migrate`)
5. **Create Test Data** (institutions, products, assignments)
6. **Test Workflow** (end-to-end testing)
7. **Style Templates** (CSS/Bootstrap)
8. **Add Validation** (client-side validation)
9. **Add Loading Indicators** (for AJAX operations)
10. **Add Success Messages** (Toast/alert notifications)

---

## Future Enhancements

1. **PDF Generation**: Export quotations as PDF
2. **Email Notifications**: Send quotations via email
3. **Quotation Templates**: Save frequently used quotations
4. **Bulk Add**: Add multiple products at once
5. **Price Negotiation**: Back-and-forth pricing
6. **Approval Workflow**: Multi-level approval process
7. **Expiry Notifications**: Email alerts before expiry
8. **Analytics**: Quotation metrics dashboard
9. **Product Recommendations**: AI-based suggestions
10. **Mobile App**: Dedicated mobile interface

---

## Troubleshooting

### Common Issues

1. **Session not persisting**:
   - Ensure `request.session.modified = True` is set
   - Check session middleware is enabled

2. **Permission denied errors**:
   - Verify user has proper assignments
   - Check `is_active` flag on assignments
   - Verify institution exists

3. **Product not found**:
   - Check product type matches institution type
   - Verify product is active (`is_active=True`)
   - Check product ID is correct

4. **AJAX errors**:
   - Verify CSRF token is included in POST requests
   - Check request data format
   - Verify URL patterns are correct

5. **Quotation totals incorrect**:
   - Verify `calculate_totals()` is called after item changes
   - Check decimal precision (2 decimal places)
   - Verify tax percentage (15%)

---

## Contact and Support

For questions or issues:
- Review `/Users/sas/Repos/SASKITUP/quotations/QUOTATION_WORKFLOW.md`
- Check Django logs: `/Users/sas/Repos/SASKITUP/django.log`
- Review audit logs: `AuditLog` model in database
