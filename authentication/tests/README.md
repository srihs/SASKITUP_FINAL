# Customer Product Access Test Suite

## Overview

This test suite provides comprehensive coverage for customer product viewing functionality, testing customer access to:
- TUS Retail Schools (auto-assigned to all retail schools)
- LOTTO Clubs (auto-assigned to generic shops)
- SAS Clubs (auto-assigned to generic categories)

## Test Files

- `test_customer_product_access.py` - Main test suite with 27 comprehensive tests

## Test Coverage

### 1. Customer Auto-Assignment Tests (`CustomerAutoAssignmentTestCase`)

**Purpose**: Verify that new customers are automatically assigned to the correct institutions during registration.

**Tests**:
- `test_customer_auto_assigned_to_tus_retail_schools` - Verifies assignment to all TUS retail schools
- `test_customer_auto_assigned_to_lotto_generic_shops` - Verifies assignment to LOTTO generic shops only
- `test_customer_auto_assigned_to_sas_generic_categories` - Verifies assignment to SAS generic categories only
- `test_customer_assignment_records_created` - Verifies CustomerInstitutionAssignment records exist

**Status**: ⚠️ **FAILING** - Auto-assignment functionality not yet implemented

### 2. Retail School Customer Access Tests (`RetailSchoolCustomerAccessTestCase`)

**Purpose**: Test customer access to TUS retail schools with proper filtering.

**Tests**:
- `test_customer_can_access_retail_schools_page` - Customer can view /schools/retail/
- `test_customer_sees_only_assigned_schools` - Filtering works correctly
- `test_customer_sees_correct_stats` - Stats reflect only assigned schools
- `test_customer_can_access_location_detail` - Location detail page access
- `test_customer_cannot_see_unassigned_schools` - Unassigned schools are hidden
- `test_admin_sees_all_schools` - Admin has full access
- `test_account_manager_sees_all_schools` - Account manager has full access

**Status**: ✅ **MOSTLY PASSING** (depends on auto-assignment)

### 3. LOTTO Club Customer Access Tests (`LottoClubCustomerAccessTestCase`)

**Purpose**: Test customer access to LOTTO clubs with generic shop filtering.

**Tests**:
- `test_customer_can_access_lotto_clubs_page` - Customer can view /clubs/lotto/
- `test_customer_sees_only_generic_shops` - Only generic shops visible
- `test_customer_cannot_see_regular_lotto_clubs` - Regular clubs hidden
- `test_customer_sees_correct_lotto_stats` - Stats show generic shops only
- `test_admin_sees_all_lotto_clubs` - Admin has full access

**Status**: ⚠️ **FAILING** - Auto-assignment needed, queryset filtering returns empty

### 4. SAS Club Customer Access Tests (`SASClubCustomerAccessTestCase`)

**Purpose**: Test customer access to SAS clubs with generic category filtering.

**Tests**:
- `test_customer_can_access_sas_clubs_page` - Customer can view /clubs/sas/
- `test_customer_sees_only_generic_categories` - Only generic categories visible
- `test_customer_cannot_see_regular_sas_clubs` - Regular clubs hidden
- `test_customer_sees_correct_sas_stats` - Stats show generic categories only
- `test_admin_sees_all_sas_clubs` - Admin has full access

**Status**: ⚠️ **FAILING** - Auto-assignment needed, queryset filtering returns empty

### 5. Customer Permission Tests (`CustomerPermissionTestCase`)

**Purpose**: Verify permission boundaries for customers.

**Tests**:
- `test_unauthenticated_user_gets_error` - Unauthenticated access fails
- `test_customer_cannot_access_admin_panel` - Customers blocked from admin
- `test_customer_has_correct_user_type` - User type properties work

**Status**: ⚠️ **PARTIAL** - Known bug: views missing LoginRequiredMixin

### 6. Integration Tests (`CustomerProductIntegrationTestCase`)

**Purpose**: Test complete customer journey from login to product viewing.

**Tests**:
- `test_complete_customer_journey_register_to_view_products` - Full workflow
- `test_customer_can_view_products_in_assigned_institutions` - Product access

**Status**: ⚠️ **FAILING** - TUSSchoolCategory model structure mismatch

### 7. Quotation Creation Tests (`CustomerQuotationCreationTestCase`)

**Purpose**: Test quotation creation from customer-accessible products.

**Tests**:
- `test_customer_can_create_quotation_from_assigned_product` - Quotation workflow

**Status**: ✅ **PASSING**

## Implementation Requirements

### Critical: Auto-Assignment Signal Handler

The tests expect customers to be automatically assigned to institutions when created. This requires implementing a `post_save` signal handler for the `User` model.

**File**: `/Users/sas/Repos/SASKITUP/authentication/signals.py` (or similar)

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from authentication.models import User
from quotations.models import CustomerInstitutionAssignment
from schools.models_tus import TUSSchool
from clubs.models_lotto import LottoClub
from clubs.models_sas import SASClub


@receiver(post_save, sender=User)
def auto_assign_customer_institutions(sender, instance, created, **kwargs):
    """
    Automatically assign new customers to:
    - All TUS retail schools
    - LOTTO generic shops (is_generic_shop=True)
    - SAS generic categories (is_generic_category=True)
    """
    if not created or instance.user_type != 'customer':
        return

    assignments = []

    # Assign to all TUS retail schools
    tus_content_type = ContentType.objects.get_for_model(TUSSchool)
    for school in TUSSchool.objects.filter(is_active=True):
        assignments.append(
            CustomerInstitutionAssignment(
                customer=instance,
                institution_content_type=tus_content_type,
                institution_object_id=school.id,
                is_active=True
            )
        )

    # Assign to LOTTO generic shops
    lotto_content_type = ContentType.objects.get_for_model(LottoClub)
    for shop in LottoClub.objects.filter(is_active=True, is_generic_shop=True):
        assignments.append(
            CustomerInstitutionAssignment(
                customer=instance,
                institution_content_type=lotto_content_type,
                institution_object_id=shop.id,
                is_active=True
            )
        )

    # Assign to SAS generic categories
    sas_content_type = ContentType.objects.get_for_model(SASClub)
    for category in SASClub.objects.filter(is_active=True, is_generic_category=True):
        assignments.append(
            CustomerInstitutionAssignment(
                customer=instance,
                institution_content_type=sas_content_type,
                institution_object_id=category.id,
                is_active=True
            )
        )

    # Bulk create all assignments
    if assignments:
        CustomerInstitutionAssignment.objects.bulk_create(assignments)
```

**Registration**: Add to `authentication/apps.py`:

```python
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'authentication'

    def ready(self):
        import authentication.signals  # Import signals to register them
```

### Bug Fix: Add LoginRequiredMixin to Views

The following views need `LoginRequiredMixin` to prevent AnonymousUser errors:

**File**: `/Users/sas/Repos/SASKITUP/schools/views.py`

```python
# Add LoginRequiredMixin to:
class TUSRetailSchoolsView(LoginRequiredMixin, TUSAuditMixin, SearchAuditMixin, ListView):
    # ...

class TUSSchoolDetailView(LoginRequiredMixin, TUSAuditMixin, DetailView):
    # ...

class TUSSchoolCategoryDetailView(LoginRequiredMixin, TUSAuditMixin, DetailView):
    # ...

class TUSGeneralCategoryDetailView(LoginRequiredMixin, TUSAuditMixin, DetailView):
    # ...

class TUSProductDetailView(LoginRequiredMixin, TUSAuditMixin, DetailView):
    # ...
```

**File**: `/Users/sas/Repos/SASKITUP/clubs/views.py`

```python
# Add LoginRequiredMixin to:
class LottoClubsView(LoginRequiredMixin, ListView):
    # ...

class SASClubListView(LoginRequiredMixin, ListView):
    # ...
```

### Test Data Model Updates

The tests currently have some model structure mismatches that need to be corrected:

1. **TUSSchoolCategory** - Remove `general_category` field references (already fixed in latest code)
2. **TUSLocation** - Requires `woo_category_id` (already fixed in tests)

## Running the Tests

### Run All Tests

```bash
source env/bin/activate
python manage.py test authentication.tests.test_customer_product_access --settings=kitup.settings --keepdb
```

### Run Specific Test Class

```bash
python manage.py test authentication.tests.test_customer_product_access.CustomerAutoAssignmentTestCase --settings=kitup.settings --keepdb
```

### Run Specific Test Method

```bash
python manage.py test authentication.tests.test_customer_product_access.CustomerAutoAssignmentTestCase.test_customer_auto_assigned_to_tus_retail_schools --settings=kitup.settings --keepdb
```

### Run with Verbosity

```bash
python manage.py test authentication.tests.test_customer_product_access --settings=kitup.settings --keepdb -v 2
```

## Expected Results After Implementation

After implementing the auto-assignment signal handler and adding LoginRequiredMixin to views:

- **CustomerAutoAssignmentTestCase**: 4/4 tests passing ✅
- **RetailSchoolCustomerAccessTestCase**: 7/7 tests passing ✅
- **LottoClubCustomerAccessTestCase**: 5/5 tests passing ✅
- **SASClubCustomerAccessTestCase**: 5/5 tests passing ✅
- **CustomerPermissionTestCase**: 3/3 tests passing ✅
- **CustomerProductIntegrationTestCase**: 2/2 tests passing ✅
- **CustomerQuotationCreationTestCase**: 1/1 test passing ✅

**Total**: 27/27 tests passing ✅

## Test Database

Tests use `--keepdb` flag to preserve the test database between runs for faster execution.

To reset the test database:

```bash
python manage.py test authentication.tests.test_customer_product_access --settings=kitup.settings
```

## Current Test Status

As of the last run:
- **Total Tests**: 27
- **Passing**: 18
- **Failing**: 6 (auto-assignment not implemented)
- **Errors**: 3 (model structure, view authentication)

## Next Steps

1. Implement auto-assignment signal handler
2. Add LoginRequiredMixin to all customer-facing views
3. Re-run tests to verify all pass
4. Add additional tests for edge cases:
   - Customer assigned to inactive schools
   - Customer assignment deactivation
   - Multiple customers accessing same schools
   - Permission checks for product detail pages
   - Quotation creation with different product types
