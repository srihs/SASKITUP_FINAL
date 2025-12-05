# Quotations App Documentation

## Overview

The quotations app provides a comprehensive quotation management system for the SASKITUP project. It supports quotation creation and management for all user types (Sales Representatives, Account Managers, and Customers) across all institution types (Schools, Wholesale Schools, LOTTO Clubs, and SAS Clubs) and all product types (Wholesale, LOTTO, SAS, and TUS Retail products).

---

## Models

### 1. Quotation

Main quotation model supporting all institution types and user roles.

**Key Features:**
- Auto-generated quotation numbers (format: Q-YYYYMMDD-XXXX)
- Status workflow: draft → pending → approved/rejected/expired/cancelled
- Automatic expiry date calculation (30 days default)
- Flexible pricing with percentage or fixed discounts
- VAT calculation (default 15%)
- Version tracking for audit trail
- Generic relationship to institutions (School, WholesaleSchool, LottoClub, SASClub)

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| quotation_number | CharField | Auto-generated unique number |
| created_by | ForeignKey | User who created the quotation |
| institution_content_type | ForeignKey | Type of institution (ContentType) |
| institution_object_id | PositiveInteger | Institution ID |
| institution | GenericForeignKey | Institution reference |
| status | CharField | draft/pending/approved/rejected/expired/cancelled |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Last update timestamp |
| expires_at | DateTime | Expiry date |
| approved_at | DateTime | Approval timestamp |
| rejected_at | DateTime | Rejection timestamp |
| approved_by | ForeignKey | User who approved |
| rejected_by | ForeignKey | User who rejected |
| rejection_reason | TextField | Reason for rejection |
| subtotal | Decimal | Subtotal before tax and discount |
| discount_percentage | Decimal | Discount % (0-100) |
| discount_amount | Decimal | Fixed discount amount |
| tax_percentage | Decimal | Tax % (default 15%) |
| tax_amount | Decimal | Calculated tax amount |
| total | Decimal | Final total |
| notes | TextField | Internal notes |
| customer_notes | TextField | Customer-visible notes |
| terms_and_conditions | TextField | T&Cs for quotation |
| version | PositiveInteger | Version number |
| reference_number | CharField | External reference (PO, etc.) |
| is_locked | Boolean | Lock from editing |

**Properties:**
- `institution_name`: Get institution display name
- `institution_type`: Get readable institution type (School/Wholesale School/LOTTO Club/SAS Club)
- `is_expired`: Check if quotation expired
- `days_until_expiry`: Calculate days until expiry

**Methods:**
- `calculate_totals()`: Recalculate subtotal, tax, and total from items
- `approve(approved_by, notes='')`: Approve quotation
- `reject(rejected_by, reason='')`: Reject quotation
- `create_version_snapshot(description='')`: Create version history entry

**Custom Manager Methods:**
- `Quotation.objects.active()`: Get active (non-expired, non-rejected) quotations
- `Quotation.objects.by_user(user)`: Get quotations by user
- `Quotation.objects.for_institution(institution)`: Get quotations for institution
- `Quotation.objects.pending_approval()`: Get pending quotations
- `Quotation.objects.expired()`: Get expired quotations

**Permissions:**
- `can_approve_quotation`: Permission to approve quotations
- `can_reject_quotation`: Permission to reject quotations
- `can_view_all_quotations`: Permission to view all quotations

---

### 2. QuotationItem

Individual line items in quotations with product snapshot functionality.

**Key Features:**
- Generic relationship to all product types (WholesaleProduct, LottoProduct, SASProduct, TUSProduct)
- Product snapshot captures product data at quotation time
- Automatic line total calculation
- Support for product variations (size, color, etc.)
- Auto-updates quotation totals on save/delete

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| quotation | ForeignKey | Parent quotation |
| product_content_type | ForeignKey | Product type (ContentType) |
| product_object_id | PositiveInteger | Product ID |
| product | GenericForeignKey | Product reference |
| product_snapshot | JSONField | Product data snapshot |
| product_name | CharField | Product name (cached) |
| product_sku | CharField | Product SKU (cached) |
| product_image_url | URLField | Product image URL (cached) |
| quantity | PositiveInteger | Item quantity |
| unit_price | Decimal | Unit price at quote time |
| variations | JSONField | Product variations |
| line_total | Decimal | Calculated line total |
| notes | TextField | Item notes |
| sort_order | PositiveInteger | Display order |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Update timestamp |

**Properties:**
- `product_type`: Get readable product type (Wholesale/LOTTO/SAS/TUS Retail)

**Automatic Behavior:**
- Calculates line_total on save (quantity × unit_price)
- Creates product snapshot on first save
- Updates quotation totals after save/delete
- Caches product name, SKU, and image URL

---

### 3. CustomerInstitutionAssignment

Assignment of customer users to institutions for quotation access control.

**Key Features:**
- Controls which institutions customers can create quotations for
- Generic relationship to all institution types
- Unique constraint ensures one active assignment per customer-institution pair
- Deactivation tracking with audit trail

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| customer | ForeignKey | Customer user |
| institution_content_type | ForeignKey | Institution type (ContentType) |
| institution_object_id | PositiveInteger | Institution ID |
| institution | GenericForeignKey | Institution reference |
| is_active | Boolean | Assignment status |
| assigned_date | DateTime | Assignment date |
| notes | TextField | Assignment notes |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Update timestamp |
| created_by | ForeignKey | User who created assignment |

**Methods:**
- `deactivate(deactivated_by=None)`: Deactivate assignment with audit

**Constraints:**
- Unique active customer-institution assignments

---

### 4. QuotationVersion

Version history tracking for quotations with complete state snapshots.

**Key Features:**
- Automatic version creation on key events (approval, rejection, modifications)
- JSON snapshot of complete quotation state
- Change description for audit trail
- Read-only in admin (cannot manually create/delete)

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| quotation | ForeignKey | Parent quotation |
| version_number | PositiveInteger | Version number |
| snapshot_data | JSONField | Complete quotation snapshot |
| change_description | TextField | Description of changes |
| created_at | DateTime | Version creation timestamp |
| created_by | ForeignKey | User who created version |

**Constraints:**
- Unique quotation-version_number pairs

---

## Database Schema

### Tables

```sql
-- Main quotation table
quotations (
    id UUID PRIMARY KEY,
    quotation_number VARCHAR(50) UNIQUE,
    created_by_id (FK to authentication_user),
    institution_content_type_id (FK to django_content_type),
    institution_object_id INTEGER,
    status VARCHAR(20),
    ... pricing and date fields ...
)

-- Quotation line items
quotation_items (
    id UUID PRIMARY KEY,
    quotation_id UUID (FK to quotations),
    product_content_type_id (FK to django_content_type),
    product_object_id INTEGER,
    product_snapshot JSONB,
    ... product details and pricing ...
)

-- Customer institution assignments
customer_institution_assignments (
    id UUID PRIMARY KEY,
    customer_id (FK to authentication_user),
    institution_content_type_id (FK to django_content_type),
    institution_object_id INTEGER,
    is_active BOOLEAN,
    ... assignment details ...
)

-- Version history
quotation_versions (
    id UUID PRIMARY KEY,
    quotation_id UUID (FK to quotations),
    version_number INTEGER,
    snapshot_data JSONB,
    ... metadata ...
)
```

### Indexes

**Quotation:**
- quotation_number (unique)
- (created_by, status)
- (institution_content_type, institution_object_id)
- (status, expires_at)
- created_at
- approved_at

**QuotationItem:**
- (quotation, sort_order)
- (product_content_type, product_object_id)

**CustomerInstitutionAssignment:**
- (customer, is_active)
- (institution_content_type, institution_object_id)
- assigned_date

**QuotationVersion:**
- (quotation, version_number) - unique
- created_at

---

## Model Relationships

### Quotation Relationships

```
Quotation
├── Created By → User (authentication.User)
├── Institution → School | WholesaleSchool | LottoClub | SASClub (GenericForeignKey)
├── Approved By → User (authentication.User)
├── Rejected By → User (authentication.User)
├── Items → QuotationItem (reverse: quotation.items.all())
└── Versions → QuotationVersion (reverse: quotation.versions.all())
```

### QuotationItem Relationships

```
QuotationItem
├── Quotation → Quotation
└── Product → WholesaleProduct | LottoProduct | SASProduct | TUSProduct (GenericForeignKey)
```

### Institution Support

All models use `GenericForeignKey` to support multiple institution types:

**Supported Institutions:**
1. **School** (`schools.School`) - Regular NZ schools
2. **WholesaleSchool** (`schools.WholesaleSchool`) - Wholesale schools from CIN7
3. **LottoClub** (`clubs.LottoClub`) - LOTTO sports clubs
4. **SASClub** (`clubs.SASClub`) - SAS sports clubs

### Product Support

QuotationItem supports all product types through `GenericForeignKey`:

**Supported Products:**
1. **WholesaleProduct** (`schools.WholesaleProduct`) - CIN7 wholesale products
2. **LottoProduct** (`clubs.LottoProduct`) - LOTTO WooCommerce products
3. **SASProduct** (`clubs.SASProduct`) - SAS WooCommerce products
4. **TUSProduct** (`clubs.TUSProduct`) - TUS Retail WooCommerce products

---

## Business Logic

### Quotation Lifecycle

```
Draft → Pending → Approved
                → Rejected
                → Expired (auto after expires_at)
                → Cancelled
```

### Quotation Number Generation

Format: `Q-YYYYMMDD-XXXX`

Example: `Q-20251005-0001`

- YYYYMMDD: Date created
- XXXX: Sequential number for that day (0001, 0002, etc.)

### Pricing Calculation

```python
# Subtotal
subtotal = sum(item.line_total for item in quotation.items.all())

# Discount
if discount_percentage:
    discount = subtotal * (discount_percentage / 100)
else:
    discount = discount_amount

# Tax
taxable_amount = subtotal - discount
tax = taxable_amount * (tax_percentage / 100)

# Total
total = taxable_amount + tax
```

### Permissions & Access Control

**Sales Representatives:**
- Can create quotations for assigned institutions only
- Can view their own quotations
- Cannot approve quotations

**Account Managers:**
- Can create quotations for all institutions
- Can approve/reject quotations
- Can view all quotations

**Customers:**
- Can create quotations for their assigned institutions only (via CustomerInstitutionAssignment)
- Can view their own quotations only
- Cannot approve quotations

**Admins:**
- Full access to all quotations
- Can override all permissions

### Automatic Behaviors

1. **Quotation Number**: Auto-generated on save if not set
2. **Expiry Date**: Auto-set to 30 days from creation
3. **Status**: Auto-updated to 'expired' if past expires_at
4. **Totals**: Auto-calculated when items added/removed/updated
5. **Line Total**: Auto-calculated on QuotationItem save
6. **Product Snapshot**: Auto-created on first QuotationItem save
7. **Version Tracking**: Auto-created on approve/reject

---

## Admin Interface

### Quotation Admin

**List Display:**
- Quotation number
- Institution name and type
- Created by
- Status (colored badge)
- Total amount (formatted)
- Creation and expiry dates

**Filters:**
- Status
- Created date
- Expiry date
- Approved date

**Search:**
- Quotation number
- User email/name
- Reference number
- Notes

**Inline Editing:**
- QuotationItem inline (tabular)
- QuotationVersion inline (read-only tabular)

**Actions:**
- Bulk approve quotations
- Bulk reject quotations
- Bulk cancel quotations
- Recalculate totals

### QuotationItem Admin

**List Display:**
- Quotation number (linked)
- Product name and type
- Quantity
- Unit price (formatted)
- Line total (formatted)

**Filters:**
- Product type
- Created date

**Search:**
- Quotation number
- Product name
- Product SKU

### CustomerInstitutionAssignment Admin

**List Display:**
- Customer name (linked)
- Institution name and type
- Active status
- Assignment date
- Created by

**Filters:**
- Active status
- Assignment date
- Institution type

**Search:**
- Customer email/name

**Actions:**
- Bulk activate assignments
- Bulk deactivate assignments

### QuotationVersion Admin

**List Display:**
- Quotation number (linked)
- Version number
- Created date
- Created by

**Features:**
- Read-only (cannot create/delete manually)
- Snapshot data viewable

---

## Usage Examples

### Creating a Quotation

```python
from quotations.models import Quotation, QuotationItem
from authentication.models import User
from schools.models import WholesaleSchool, WholesaleProduct
from django.contrib.contenttypes.models import ContentType

# Get user and institution
sales_rep = User.objects.get(email='sales@example.com')
school = WholesaleSchool.objects.get(cin7_id='12345')

# Create quotation
quotation = Quotation.objects.create(
    created_by=sales_rep,
    institution_content_type=ContentType.objects.get_for_model(school),
    institution_object_id=school.id,
    status='draft',
    discount_percentage=Decimal('10.00'),  # 10% discount
)

# Add items
product = WholesaleProduct.objects.get(cin7_id='67890')
item = QuotationItem.objects.create(
    quotation=quotation,
    product_content_type=ContentType.objects.get_for_model(product),
    product_object_id=product.id,
    quantity=10,
    unit_price=product.wholesale_price,
)

# Totals are automatically calculated
print(f"Quotation {quotation.quotation_number}")
print(f"Subtotal: R {quotation.subtotal}")
print(f"Tax: R {quotation.tax_amount}")
print(f"Total: R {quotation.total}")
```

### Approving a Quotation

```python
from authentication.models import User

manager = User.objects.get(email='manager@example.com')
quotation.approve(manager, 'Approved for standard pricing')

# This creates a version snapshot and updates status
print(f"Status: {quotation.status}")  # 'approved'
print(f"Version: {quotation.version}")  # incremented
```

### Querying Quotations

```python
# Get active quotations for a sales rep
active_quotes = Quotation.objects.active().by_user(sales_rep)

# Get quotations for a school
school_quotes = Quotation.objects.for_institution(school)

# Get pending approvals
pending = Quotation.objects.pending_approval()

# Get expired quotations
expired = Quotation.objects.expired()
```

### Assigning Customer to Institution

```python
from quotations.models import CustomerInstitutionAssignment

customer = User.objects.get(email='customer@example.com', user_type='customer')

assignment = CustomerInstitutionAssignment.objects.create(
    customer=customer,
    institution_content_type=ContentType.objects.get_for_model(school),
    institution_object_id=school.id,
    created_by=sales_rep,
    notes='Primary customer for this school'
)
```

---

## Integration with Existing Models

### User Model Integration

The quotations app integrates with `authentication.User` model:

```python
# Access user's quotations
user.quotations_created.all()  # Created quotations
user.quotations_approved.all()  # Approved quotations
user.quotations_rejected.all()  # Rejected quotations

# For customers
user.institution_assignments.filter(is_active=True)  # Assigned institutions
```

### Institution Model Integration

The GenericForeignKey allows seamless integration with all institution types:

```python
# From School
school.quotations  # Via GenericRelation (if added)

# From WholesaleSchool
wholesale_school.quotations  # Via GenericRelation (if added)

# From LottoClub
lotto_club.quotations  # Via GenericRelation (if added)

# From SASClub
sas_club.quotations  # Via GenericRelation (if added)
```

### Product Model Integration

Similar GenericForeignKey integration with product models:

```python
# From WholesaleProduct
product.quotation_items  # Via GenericRelation (if added)

# Access from QuotationItem
item.product  # Returns the actual product object
item.product_type  # Returns readable type name
```

---

## Migration Details

Migration file: `quotations/migrations/0001_initial.py`

**Created:**
- Quotation model with all fields and indexes
- QuotationItem model with GenericForeignKey to products
- QuotationVersion model
- CustomerInstitutionAssignment model
- All indexes and constraints

**Indexes Created:**
- 6 indexes on Quotation
- 2 indexes on QuotationItem
- 3 indexes on CustomerInstitutionAssignment
- 2 indexes on QuotationVersion

**Constraints:**
- unique_quotation_version on QuotationVersion
- unique_active_customer_institution on CustomerInstitutionAssignment

---

## Security Considerations

1. **Access Control:** Enforced through model validation and permission checks
2. **Data Protection:** User can only access quotations they created or have permission to view
3. **Audit Trail:** Complete version history with change descriptions
4. **GenericForeignKey Validation:** Restricted to specific model types via `limit_choices_to`
5. **Price Integrity:** Product snapshots preserve pricing at quotation time

---

## Performance Optimization

1. **Indexes:** Strategic indexes on frequently queried fields
2. **Calculated Fields:** Cached product details (name, SKU, image) for fast access
3. **Batch Operations:** Custom manager methods for efficient queries
4. **Lazy Loading:** Related objects loaded only when needed

---

## Future Enhancements

1. **PDF Generation:** Generate printable quotation PDFs
2. **Email Notifications:** Automated emails on status changes
3. **Quotation Templates:** Reusable quotation templates
4. **Conversion to Orders:** Convert approved quotations to orders
5. **Analytics Dashboard:** Quotation statistics and reporting
6. **API Endpoints:** REST API for quotation management
7. **Workflow Automation:** Configurable approval workflows
8. **Multi-currency Support:** Support for different currencies

---

## Troubleshooting

### Common Issues

**Issue:** Totals not calculating correctly
**Solution:** Run `quotation.calculate_totals()` to recalculate

**Issue:** Product snapshot not created
**Solution:** Ensure product exists before saving QuotationItem

**Issue:** User cannot create quotation for institution
**Solution:** Check user has assignment to that institution (sales reps/customers)

**Issue:** Version not created
**Solution:** Version created automatically only on approve/reject, call `create_version_snapshot()` manually if needed

---

## File Locations

- **Models:** `/Users/sas/Repos/SASKITUP/quotations/models.py`
- **Admin:** `/Users/sas/Repos/SASKITUP/quotations/admin.py`
- **Migrations:** `/Users/sas/Repos/SASKITUP/quotations/migrations/0001_initial.py`
- **Settings:** Updated `/Users/sas/Repos/SASKITUP/kitup/settings.py`

---

## Summary

The quotations app provides a complete, production-ready quotation management system with:

- 4 models covering quotations, items, assignments, and version history
- Support for all 4 product types and 2 institution categories
- Comprehensive admin interface with bulk actions
- Automatic calculations and validation
- Complete audit trail and version tracking
- Permission-based access control
- GenericForeignKey for maximum flexibility
- Well-indexed database schema for performance
- Following Django best practices and project patterns
