# Sales Rep Login Debug Report

**Date:** 2025-10-07
**Issue:** Sales rep redirected back to login screen when accessing /dashboard/
**Status:** ✅ ROOT CAUSE IDENTIFIED

---

## Issue Summary

**User:** srimal@sascreative.co.nz (Sales Rep)
**Password:** imaliem123
**Expected Behavior:** Login → Redirect to /dashboard/ → View sales rep dashboard
**Actual Behavior:** Login → Redirect to /dashboard/ → **Immediately logged out** → Redirect to /

---

## Test Results

### ✅ Login Flow Test
- **Form submission:** SUCCESS
- **Authentication:** SUCCESS (user authenticated correctly)
- **Session created:** YES
- **Final URL:** http://127.0.0.1:8000/ (back to login page)
- **Error messages:** None visible (silent logout)

### ✅ Middleware Analysis
- **Path checked:** /dashboard/
- **Middleware blocking:** YES - `AuthenticationMiddleware` (Line 52)
- **Specific middleware:** `authentication.middleware.AuthenticationMiddleware`
- **Reason:** `is_active_sales_rep` field is False

### ✅ View Permissions
- **View class:** `GlobalDashboardView`
- **Permission check:** `LoginRequiredMixin` only - no role-based blocking in view
- **Sales rep allowed:** YES (view supports all user types)

---

## Root Cause Analysis

### 🔴 ISSUE FOUND: Line 52 in `authentication/middleware.py`

```python
# authentication/middleware.py - Lines 51-54
if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
    logout(request)
    return redirect('frontend-home')
```

### User State
```python
User: srimal@sascreative.co.nz
User Type: sales_rep
Is Active: True  ✓
Is Active Sales Rep: False  ✗  ← THIS IS THE PROBLEM
Password Valid: True  ✓
```

### What Happens:
1. User successfully authenticates with `EmailBackend`
2. Django logs user in, creates session
3. User gets redirected to `/dashboard/` (successful login)
4. **Middleware runs BEFORE dashboard view**
5. Middleware checks line 52: User is `sales_rep` AND `is_active_sales_rep` is False
6. **Middleware logs user out immediately**
7. Middleware redirects to `frontend-home` (/)
8. User sees login page again

---

## Timeline of Events

```
1. POST /                       → Login form submitted
2. authenticate()               → User authenticated ✓
3. login(request, user)         → Session created ✓
4. redirect('global-dashboard') → Redirect to /dashboard/
5. GET /dashboard/              → Middleware runs
6. Line 52 check                → is_sales_rep=True, is_active_sales_rep=False
7. logout(request)              → Session destroyed ✗
8. redirect('frontend-home')    → Back to /
9. User sees login page         → Confused why login didn't work
```

---

## Comparison: Admin vs Sales Rep

### ✅ Admin Login (Works)
```python
Email: srimalhs@gmail.com
User Type: admin
is_active: True
is_active_sales_rep: N/A (not checked for admins)
Middleware line 52: SKIPPED (user is not sales_rep or account_manager)
Result: Successfully reaches /dashboard/
```

### ✗ Sales Rep Login (Fails)
```python
Email: srimal@sascreative.co.nz
User Type: sales_rep
is_active: True
is_active_sales_rep: False  ← BLOCKS ACCESS
Middleware line 52: TRIGGERED (user is sales_rep AND is_active_sales_rep is False)
Result: Logged out, redirected to /
```

---

## Why This Field Exists

The `is_active_sales_rep` field appears to be a separate activation flag specifically for sales reps and account managers, distinct from the general `is_active` flag.

**Possible use cases:**
- Temporarily suspend sales rep access without deactivating the entire account
- Separate HR status (active employee) from system access (active sales rep)
- Allow sales reps to exist in the system but not have access

**However:** This creates confusion because:
- `is_active=True` suggests the user should be able to log in
- `is_active_sales_rep=False` silently prevents access
- No error message is shown to the user
- The logout is invisible (happens in middleware)

---

## Fix Required

### Option 1: Activate the Sales Rep (Recommended)
**Update the user's `is_active_sales_rep` field to `True`**

```python
# Django shell
from authentication.models import User
sales_rep = User.objects.get(email='srimal@sascreative.co.nz')
sales_rep.is_active_sales_rep = True
sales_rep.save()
print(f"✓ {sales_rep.email} is now active_sales_rep={sales_rep.is_active_sales_rep}")
```

**Pros:**
- Simplest fix
- Allows the user to log in immediately
- Maintains the dual-activation system

**Cons:**
- Need to do this for every new sales rep

---

### Option 2: Auto-Activate on Creation
**Modify user creation to set `is_active_sales_rep=True` by default**

```python
# authentication/models.py or wherever users are created
def create_sales_rep(email, **kwargs):
    user = User.objects.create(
        email=email,
        user_type='sales_rep',
        is_active=True,
        is_active_sales_rep=True,  # ← Add this
        **kwargs
    )
    return user
```

**Pros:**
- Prevents future issues
- Consistent behavior

**Cons:**
- Need to update user creation code
- Still need to fix existing users

---

### Option 3: Change Middleware Logic
**Modify middleware to show error message instead of silent logout**

```python
# authentication/middleware.py - Lines 51-58 (MODIFIED)
if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
    # Show error message instead of silent logout
    messages.warning(
        request,
        'Your sales rep account is inactive. Please contact your administrator.'
    )
    logout(request)
    return redirect('frontend-home')
```

**Pros:**
- User sees why they can't log in
- Better UX than silent failure

**Cons:**
- Still prevents login
- Need to enable `messages` framework

---

### Option 4: Remove the Check (Not Recommended)
**Remove or comment out lines 51-54 in middleware**

```python
# authentication/middleware.py - Lines 51-54 (COMMENTED OUT)
# if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
#     logout(request)
#     return redirect('frontend-home')
```

**Pros:**
- Simple fix
- Sales reps can log in

**Cons:**
- Removes the intended access control
- May break intended security model

---

## Recommended Solution

**Combination approach:**

1. **Immediate fix:** Activate the current user
```bash
python manage.py shell -c "
from authentication.models import User
sales_rep = User.objects.get(email='srimal@sascreative.co.nz')
sales_rep.is_active_sales_rep = True
sales_rep.save()
print('✓ Sales rep activated')
"
```

2. **Long-term fix:** Update user creation to set `is_active_sales_rep=True` by default

3. **UX improvement:** Add error message to middleware for better feedback

---

## Code Locations

### Files Involved:
- **Middleware:** `/Users/sas/Repos/SASKITUP/authentication/middleware.py` (Line 52)
- **User Model:** `/Users/sas/Repos/SASKITUP/authentication/models.py`
- **Dashboard View:** `/Users/sas/Repos/SASKITUP/kitup/views.py` (GlobalDashboardView)
- **Login View:** `/Users/sas/Repos/SASKITUP/kitup/views.py` (frontend_landing_view)

### Middleware Code:
```python
# File: authentication/middleware.py
# Lines: 46-54

def process_request(self, request):
    """Process incoming request"""
    if request.user.is_authenticated:
        # ... other checks ...

        # Check if sales rep or account manager is still active
        if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
            logout(request)  # ← THIS LOGS OUT THE USER
            return redirect('frontend-home')  # ← THIS REDIRECTS TO /
```

---

## Verification Steps

After applying the fix:

1. **Check user status:**
```bash
python manage.py shell -c "
from authentication.models import User
user = User.objects.get(email='srimal@sascreative.co.nz')
print(f'is_active: {user.is_active}')
print(f'is_active_sales_rep: {user.is_active_sales_rep}')
"
```

2. **Test login:**
- Navigate to http://127.0.0.1:8000/
- Enter email: srimal@sascreative.co.nz
- Enter password: imaliem123
- Click login
- **Expected:** Should stay on /dashboard/ and see sales rep dashboard

3. **Check session:**
```python
from django.contrib.sessions.models import Session
from authentication.models import UserSession
# Verify session exists for the user
```

---

## Additional Notes

### Silent Failure Pattern
This is a **silent failure** pattern that causes poor UX:
- User enters correct credentials
- Login appears to succeed (no error shown)
- User immediately redirected back to login
- No explanation given

### Better Error Handling
Should show a clear message:
> "Your account is pending activation. Please contact your administrator."

Or:
> "Your sales rep access has been deactivated. Please contact HR."

---

## Summary

**Problem:** `is_active_sales_rep=False` causes middleware to log out sales reps immediately after login
**Location:** `authentication/middleware.py` line 52
**Fix:** Set `is_active_sales_rep=True` for the user
**Long-term:** Auto-activate sales reps on creation and improve error messages
