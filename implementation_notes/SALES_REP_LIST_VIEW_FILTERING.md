# Sales Rep List View Filtering Implementation

## Overview

Implemented role-based filtering across all club and school list views to ensure sales representatives only see their assigned clients while admins and account managers retain full visibility.

**Implementation Date:** 2025-10-07

## Modified Views

### 1. LottoClubsView (`/clubs/lotto/`)

**File:** `/Users/sas/Repos/SASKITUP/clubs/views.py` (lines 172-215)

**Filtering Logic:**
```python
def get_queryset(self):
    from .models_lotto import LottoClub
    from authentication.models import SalesRepClubAssignment
    from django.contrib.contenttypes.models import ContentType

    queryset = LottoClub.objects.filter(is_active=True).prefetch_related('categories')
    user = self.request.user

    # Admin and Account Manager: See ALL clubs
    if user.is_admin or user.is_account_manager:
        pass  # No filtering needed, show all

    # Sales Rep: See ONLY assigned clubs
    elif user.is_sales_rep:
        # Get assigned LOTTO club IDs using ContentType
        lotto_content_type = ContentType.objects.get_for_model(LottoClub)
        assigned_ids = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            club_content_type=lotto_content_type
        ).values_list('club_object_id', flat=True)

        queryset = queryset.filter(id__in=assigned_ids)

    # Customer or other user types: No access
    else:
        return queryset.none()

    # Search and filter functionality remains intact
    # ...
```

**Key Points:**
- Uses `ContentType` to filter by `LottoClub` model type
- Filters by `club_object_id` from `SalesRepClubAssignment`
- Returns empty queryset for unauthorized user types

---

### 2. SASClubListView (`/clubs/sas/`)

**File:** `/Users/sas/Repos/SASKITUP/clubs/views.py` (lines 1310-1360)

**Filtering Logic:**
```python
def get_queryset(self):
    from authentication.models import SalesRepClubAssignment
    from django.contrib.contenttypes.models import ContentType

    # Use clubs_only() manager to exclude schools and generic categories
    queryset = SASClub.objects.clubs_only().select_related('sport')

    user = self.request.user

    # Admin and Account Manager: See ALL clubs
    if user.is_admin or user.is_account_manager:
        pass  # No filtering needed, show all

    # Sales Rep: See ONLY assigned clubs
    elif user.is_sales_rep:
        # Get assigned SAS club IDs using ContentType
        sas_content_type = ContentType.objects.get_for_model(SASClub)
        assigned_ids = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            club_content_type=sas_content_type
        ).values_list('club_object_id', flat=True)

        queryset = queryset.filter(id__in=assigned_ids)

    # Customer or other user types: No access
    else:
        return queryset.none()

    # Sport filter and search functionality remains intact
    # ...
```

**Key Points:**
- Uses `ContentType` to filter by `SASClub` model type
- Maintains existing `clubs_only()` manager logic
- Preserves sport filtering and search functionality

---

### 3. WholesaleSchoolsView (`/schools/wholesale/`)

**File:** `/Users/sas/Repos/SASKITUP/schools/views.py` (lines 198-242)

**Filtering Logic:**
```python
def get_queryset(self):
    try:
        from .models import WholesaleSchool
        from authentication.models import SalesRepSchoolAssignment

        queryset = WholesaleSchool.objects.filter(is_active=True)
        user = self.request.user

        # Admin and Account Manager: See ALL schools
        if user.is_admin or user.is_account_manager:
            pass  # No filtering needed, show all

        # Sales Rep: See ONLY assigned schools
        elif user.is_sales_rep:
            # Get assigned wholesale school IDs
            assigned_ids = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                wholesale_school__isnull=False  # Only wholesale assignments
            ).values_list('wholesale_school_id', flat=True)

            queryset = queryset.filter(id__in=assigned_ids)

        # Customer or other user types: No access
        else:
            return queryset.none()

        # Search functionality remains intact
        # ...

    except ImportError:
        # Wholesale models not available
        return models.QuerySet().none()
```

**Key Points:**
- Filters using `wholesale_school__isnull=False` to ensure only wholesale assignments
- Uses `wholesale_school_id` field from `SalesRepSchoolAssignment`
- Handles ImportError gracefully if models unavailable

---

### 4. TUSRetailSchoolsView (`/schools/retail/`)

**File:** `/Users/sas/Repos/SASKITUP/schools/views.py` (lines 324-370)

**Filtering Logic:**
```python
def get_queryset(self):
    from authentication.models import SalesRepSchoolAssignment

    # Use utility function to get locations with stats
    queryset = get_tus_locations_with_stats()
    user = self.request.user

    # Admin and Account Manager: See ALL locations
    if user.is_admin or user.is_account_manager:
        pass  # No filtering needed, show all

    # Sales Rep: See ONLY locations that contain assigned schools
    elif user.is_sales_rep:
        # Get assigned TUS school IDs
        assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            tus_school__isnull=False  # Only TUS school assignments
        ).values_list('tus_school_id', flat=True)

        # Filter locations that contain these schools
        queryset = queryset.filter(schools__id__in=assigned_school_ids).distinct()

    # Customer or other user types: No access
    else:
        return queryset.none()

    # Search and location filter functionality remains intact
    # ...
```

**Key Points:**
- Filters using `tus_school__isnull=False` to ensure only TUS school assignments
- Uses `tus_school_id` field from `SalesRepSchoolAssignment`
- Filters `TUSLocation` objects by schools they contain
- Uses `.distinct()` to avoid duplicate locations

---

## Assignment Models Used

### SalesRepClubAssignment

**Model:** `authentication.models.SalesRepClubAssignment`

**Relevant Fields:**
- `sales_rep` (ForeignKey to User)
- `club_content_type` (ForeignKey to ContentType)
- `club_object_id` (PositiveIntegerField)
- `club` (GenericForeignKey)
- `is_active` (BooleanField)

**Usage:**
```python
from django.contrib.contenttypes.models import ContentType

# For LOTTO clubs
lotto_content_type = ContentType.objects.get_for_model(LottoClub)
assigned_ids = SalesRepClubAssignment.objects.filter(
    sales_rep=user,
    is_active=True,
    club_content_type=lotto_content_type
).values_list('club_object_id', flat=True)

# For SAS clubs
sas_content_type = ContentType.objects.get_for_model(SASClub)
assigned_ids = SalesRepClubAssignment.objects.filter(
    sales_rep=user,
    is_active=True,
    club_content_type=sas_content_type
).values_list('club_object_id', flat=True)
```

### SalesRepSchoolAssignment

**Model:** `authentication.models.SalesRepSchoolAssignment`

**Relevant Fields:**
- `sales_rep` (ForeignKey to User)
- `tus_school` (ForeignKey to TUSSchool, nullable)
- `wholesale_school` (ForeignKey to WholesaleSchool, nullable)
- `is_active` (BooleanField)

**Usage:**
```python
# For wholesale schools
assigned_ids = SalesRepSchoolAssignment.objects.filter(
    sales_rep=user,
    is_active=True,
    wholesale_school__isnull=False
).values_list('wholesale_school_id', flat=True)

# For TUS retail schools
assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
    sales_rep=user,
    is_active=True,
    tus_school__isnull=False
).values_list('tus_school_id', flat=True)
```

---

## User Role Properties

**Model:** `authentication.models.User`

**Role Checking Properties:**
- `user.is_admin` - Returns `True` for admins and superusers
- `user.is_account_manager` - Returns `True` for account managers
- `user.is_sales_rep` - Returns `True` for sales representatives
- `user.is_customer` - Returns `True` for customers

**Access Matrix:**

| User Type         | LOTTO Clubs | SAS Clubs | Wholesale Schools | TUS Retail Schools |
|-------------------|-------------|-----------|-------------------|--------------------|
| Admin             | ALL         | ALL       | ALL               | ALL                |
| Account Manager   | ALL         | ALL       | ALL               | ALL                |
| Sales Rep         | ASSIGNED    | ASSIGNED  | ASSIGNED          | ASSIGNED           |
| Customer          | NONE        | NONE      | NONE              | NONE               |

---

## Testing Instructions

### 1. Admin Testing

**Steps:**
1. Log in as admin user
2. Navigate to `/clubs/lotto/`
3. Verify ALL 34 LOTTO clubs are visible
4. Navigate to `/clubs/sas/`
5. Verify ALL SAS clubs are visible
6. Navigate to `/schools/wholesale/`
7. Verify ALL wholesale schools are visible
8. Navigate to `/schools/retail/`
9. Verify ALL TUS locations are visible

**Expected Result:** Admin sees all entities without any filtering

### 2. Account Manager Testing

**Steps:**
1. Log in as account manager user
2. Repeat steps 2-9 from Admin Testing

**Expected Result:** Account manager sees all entities (same as admin)

### 3. Sales Rep Testing

**Setup:**
- Create/use a sales rep user
- Assign 5 LOTTO clubs via `SalesRepClubAssignment`
- Assign 3 SAS clubs via `SalesRepClubAssignment`
- Assign 2 wholesale schools via `SalesRepSchoolAssignment`
- Assign 4 TUS schools via `SalesRepSchoolAssignment`

**Steps:**
1. Log in as sales rep user
2. Navigate to `/clubs/lotto/`
3. Verify ONLY 5 assigned LOTTO clubs are visible
4. Check club count in UI matches assignment count
5. Navigate to `/clubs/sas/`
6. Verify ONLY 3 assigned SAS clubs are visible
7. Navigate to `/schools/wholesale/`
8. Verify ONLY 2 assigned wholesale schools are visible
9. Navigate to `/schools/retail/`
10. Verify ONLY locations containing assigned TUS schools are visible

**Expected Result:** Sales rep sees ONLY their assigned entities

### 4. No Assignments Testing

**Steps:**
1. Log in as sales rep with NO assignments
2. Navigate to `/clubs/lotto/`
3. Verify message "No clubs found" or empty list
4. Repeat for other list views

**Expected Result:** Sales rep with no assignments sees empty lists

### 5. Customer Testing

**Steps:**
1. Log in as customer user
2. Navigate to `/clubs/lotto/`
3. Verify empty list or access denied
4. Repeat for other list views

**Expected Result:** Customers see no clubs/schools (empty queryset)

### 6. Search Testing for Sales Reps

**Steps:**
1. Log in as sales rep with assignments
2. Navigate to `/clubs/lotto/`
3. Search for a club they ARE assigned to
4. Verify club appears in results
5. Search for a club they are NOT assigned to
6. Verify no results

**Expected Result:** Search respects assignment filtering

---

## Edge Cases Handled

### 1. Inactive Assignments
- Only active assignments (`is_active=True`) are considered
- Deactivated assignments do not grant access

### 2. Multiple Content Types
- `SalesRepClubAssignment` uses `ContentType` to distinguish between `LottoClub` and `SASClub`
- Each club type is filtered independently

### 3. School Type Separation
- `SalesRepSchoolAssignment` handles both TUS and wholesale schools
- Uses `__isnull` checks to separate assignment types
- TUS assignments filter by `tus_school__isnull=False`
- Wholesale assignments filter by `wholesale_school__isnull=False`

### 4. Location Filtering for TUS Schools
- `TUSRetailSchoolsView` shows `TUSLocation` objects (collections of schools)
- Locations are filtered to show only those containing assigned schools
- Uses `.distinct()` to avoid duplicate locations

### 5. Empty Assignment Lists
- Sales reps with no assignments see empty lists (not error pages)
- `queryset.filter(id__in=[])` returns empty queryset gracefully

### 6. Unknown User Types
- Any user type not matching admin/account_manager/sales_rep returns empty queryset
- Prevents unauthorized access by default

---

## Database Queries

### Optimized Query Patterns

**LOTTO Clubs:**
```sql
-- Sales rep query
SELECT * FROM lotto_club
WHERE is_active = true
  AND id IN (
    SELECT club_object_id
    FROM sales_rep_club_assignment
    WHERE sales_rep_id = ?
      AND is_active = true
      AND club_content_type_id = ?  -- ContentType for LottoClub
  )
ORDER BY name;
```

**SAS Clubs:**
```sql
-- Sales rep query
SELECT * FROM sas_club
WHERE is_active = true
  AND is_school = false
  AND is_generic_category = false
  AND id IN (
    SELECT club_object_id
    FROM sales_rep_club_assignment
    WHERE sales_rep_id = ?
      AND is_active = true
      AND club_content_type_id = ?  -- ContentType for SASClub
  )
ORDER BY name;
```

**Wholesale Schools:**
```sql
-- Sales rep query
SELECT * FROM wholesale_school
WHERE is_active = true
  AND id IN (
    SELECT wholesale_school_id
    FROM sales_rep_school_assignment
    WHERE sales_rep_id = ?
      AND is_active = true
      AND wholesale_school_id IS NOT NULL
  )
ORDER BY name;
```

**TUS Retail Schools (Locations):**
```sql
-- Sales rep query
SELECT DISTINCT location.*
FROM tus_location location
WHERE location.is_active = true
  AND EXISTS (
    SELECT 1 FROM tus_school school
    WHERE school.location_id = location.id
      AND school.id IN (
        SELECT tus_school_id
        FROM sales_rep_school_assignment
        WHERE sales_rep_id = ?
          AND is_active = true
          AND tus_school_id IS NOT NULL
      )
  );
```

---

## Performance Considerations

1. **ContentType Caching:**
   - `ContentType.objects.get_for_model()` is called once per request
   - Django caches ContentType instances automatically

2. **Subquery Optimization:**
   - Uses `values_list('id', flat=True)` to create efficient IN clauses
   - Database optimizers handle IN clauses efficiently for small-medium lists

3. **Index Usage:**
   - Assignments indexed on `sales_rep + is_active`
   - Clubs/schools indexed on `id` (primary key)
   - Optimal query performance for typical assignment counts (1-50 per sales rep)

4. **Prefetch Related:**
   - Existing `prefetch_related()` calls maintained
   - No additional N+1 query issues introduced

---

## Future Enhancements

1. **Assignment Count Display:**
   - Show "Viewing X of Y total clubs" for sales reps
   - Add assignment statistics to dashboard

2. **Admin Assignment Management:**
   - Quick assign/unassign from list views
   - Bulk assignment operations

3. **Territory-Based Filtering:**
   - Add territory filter dropdown
   - Group assignments by territory

4. **Assignment Audit Trail:**
   - Log when assignments change
   - Track access to assigned entities

---

## Rollback Instructions

If issues arise, revert these changes:

1. **clubs/views.py:**
   - `LottoClubsView.get_queryset()` (lines 172-215)
   - `SASClubListView.get_queryset()` (lines 1310-1360)

2. **schools/views.py:**
   - `WholesaleSchoolsView.get_queryset()` (lines 198-242)
   - `TUSRetailSchoolsView.get_queryset()` (lines 324-370)

**Git Revert:**
```bash
# If changes committed
git revert <commit-hash>

# Or manual revert by removing role-based filtering logic
# Keep only the original queryset construction and search/filter logic
```

---

## Related Documentation

- `/Users/sas/Repos/SASKITUP/implementation_notes/USER_ROLES_AUTHENTICATION_ANALYSIS.md`
- `/Users/sas/Repos/SASKITUP/authentication/models.py` (User, SalesRepClubAssignment, SalesRepSchoolAssignment)
- `/Users/sas/Repos/SASKITUP/clubs/CLAUDE.md` (Clubs app documentation)

---

## Summary

Successfully implemented role-based filtering across all club and school list views:

- **4 views modified:** LottoClubsView, SASClubListView, WholesaleSchoolsView, TUSRetailSchoolsView
- **3 user roles handled:** Admin (full access), Account Manager (full access), Sales Rep (filtered)
- **2 assignment models used:** SalesRepClubAssignment, SalesRepSchoolAssignment
- **Security improved:** Customers and unknown user types get empty querysets
- **Search preserved:** All existing search and filter functionality maintained
- **Performance optimized:** Efficient subqueries with indexed fields

All views now properly respect user role assignments while maintaining backward compatibility for admins and account managers.
