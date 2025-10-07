# Admin vs Sales Rep Login Comparison

**Date:** 2025-10-07
**Purpose:** Side-by-side comparison of working admin login vs failing sales rep login

---

## User Credentials

| Role | Email | Password | Status |
|------|-------|----------|--------|
| Admin | srimalhs@gmail.com | imaliem123 | ✅ Works |
| Sales Rep | srimal@sascreative.co.nz | imaliem123 | ❌ Fails |

---

## User Model Field Comparison

| Field | Admin | Sales Rep | Impact |
|-------|-------|-----------|--------|
| `email` | srimalhs@gmail.com | srimal@sascreative.co.nz | - |
| `user_type` | `admin` | `sales_rep` | ✓ Determines middleware checks |
| `is_active` | `True` | `True` | ✓ Both active |
| `is_active_sales_rep` | N/A | `False` | ⚠️ **BLOCKS SALES REP** |
| `is_staff` | `True` | `False` | - |
| `is_superuser` | `True` | `False` | - |

---

## Login Flow Comparison

### Admin Login Flow (✅ Success)

```
Step 1: POST to /
  ├─ Username: srimalhs@gmail.com
  ├─ Password: imaliem123
  └─ Form submitted

Step 2: EmailBackend.authenticate()
  ├─ User found in database
  ├─ Password validated ✓
  └─ User returned

Step 3: login(request, user)
  ├─ Session created ✓
  └─ User marked as authenticated

Step 4: Redirect to /dashboard/
  └─ HTTP 302 redirect

Step 5: GET /dashboard/
  ├─ AuthenticationMiddleware.process_request()
  │   ├─ Check: user.is_authenticated? YES ✓
  │   ├─ Check: user.is_active? YES ✓
  │   ├─ Check: is sales_rep or account_manager? NO ✗
  │   └─ Skip line 52 check (not a sales rep)
  │
  └─ RoleBasedAccessMiddleware.check_access()
      ├─ Path: /dashboard/
      ├─ Public path? NO
      ├─ Authenticated? YES ✓
      └─ Allow access ✓

Step 6: GlobalDashboardView.dispatch()
  ├─ LoginRequiredMixin: User authenticated? YES ✓
  └─ Render admin dashboard

RESULT: ✅ Admin sees dashboard with all system data
```

---

### Sales Rep Login Flow (❌ Failure)

```
Step 1: POST to /
  ├─ Username: srimal@sascreative.co.nz
  ├─ Password: imaliem123
  └─ Form submitted

Step 2: EmailBackend.authenticate()
  ├─ User found in database
  ├─ Password validated ✓
  └─ User returned

Step 3: login(request, user)
  ├─ Session created ✓
  └─ User marked as authenticated

Step 4: Redirect to /dashboard/
  └─ HTTP 302 redirect

Step 5: GET /dashboard/
  ├─ AuthenticationMiddleware.process_request()
  │   ├─ Check: user.is_authenticated? YES ✓
  │   ├─ Check: user.is_active? YES ✓
  │   ├─ Check: is sales_rep or account_manager? YES ✓
  │   ├─ Check: is_active_sales_rep? NO ✗
  │   ├─ **logout(request)**  ← SESSION DESTROYED HERE
  │   └─ **return redirect('frontend-home')**  ← REDIRECT TO /
  │
  └─ RoleBasedAccessMiddleware: NEVER REACHED
      └─ (User already logged out)

Step 6: GET /
  ├─ User no longer authenticated
  └─ Show login page

RESULT: ❌ Sales rep sees login page again (no error message)
```

---

## Middleware Check Comparison

### AuthenticationMiddleware - Line 52

```python
# authentication/middleware.py - Lines 51-54
if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
    logout(request)
    return redirect('frontend-home')
```

| User | Condition Check | Result |
|------|----------------|--------|
| **Admin** | `is_sales_rep=False` | ✅ Skip check (not a sales rep) |
| **Sales Rep** | `is_sales_rep=True AND is_active_sales_rep=False` | ❌ Logout & redirect |

---

## Database Query Comparison

### Admin Query Result
```sql
SELECT * FROM authentication_user WHERE email = 'srimalhs@gmail.com';
```

```python
User {
    id: 1,
    email: 'srimalhs@gmail.com',
    username: 'admin',
    user_type: 'admin',
    is_active: True,
    is_staff: True,
    is_superuser: True,
    is_active_sales_rep: <not applicable>  # Field ignored for admins
}
```

### Sales Rep Query Result
```sql
SELECT * FROM authentication_user WHERE email = 'srimal@sascreative.co.nz';
```

```python
User {
    id: 2,
    email: 'srimal@sascreative.co.nz',
    username: 'srimal',
    user_type: 'sales_rep',
    is_active: True,
    is_staff: False,
    is_superuser: False,
    is_active_sales_rep: False  # ← THIS BLOCKS ACCESS
}
```

---

## Request/Response Comparison

### Admin Request Cycle

```http
POST / HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=srimalhs@gmail.com&password=imaliem123

---

HTTP/1.1 302 Found
Location: /dashboard/
Set-Cookie: sessionid=abc123xyz...

---

GET /dashboard/ HTTP/1.1
Cookie: sessionid=abc123xyz...

---

HTTP/1.1 200 OK
Content-Type: text/html

[Dashboard HTML for admin]
```

---

### Sales Rep Request Cycle

```http
POST / HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=srimal@sascreative.co.nz&password=imaliem123

---

HTTP/1.1 302 Found
Location: /dashboard/
Set-Cookie: sessionid=def456uvw...

---

GET /dashboard/ HTTP/1.1
Cookie: sessionid=def456uvw...

---

HTTP/1.1 302 Found  ← MIDDLEWARE REDIRECT
Location: /
Set-Cookie: sessionid=; expires=Thu, 01-Jan-1970 00:00:00 GMT  ← SESSION DELETED

---

GET / HTTP/1.1

---

HTTP/1.1 200 OK
Content-Type: text/html

[Login page HTML]
```

---

## Middleware Execution Order

### Admin Middleware Stack
```
1. SecurityMiddleware
2. SessionMiddleware
3. CommonMiddleware
4. CsrfViewMiddleware
5. AuthenticationMiddleware (Django's built-in)
6. authentication.middleware.AuthenticationMiddleware
   └─ process_request(): Checks line 52
      └─ user.is_sales_rep = False → SKIP CHECK ✓
7. RoleBasedAccessMiddleware
   └─ check_access(): /dashboard/ is not in restricted paths ✓
8. MessageMiddleware
9. ClickjackingMiddleware

VIEW: GlobalDashboardView renders admin dashboard ✓
```

---

### Sales Rep Middleware Stack
```
1. SecurityMiddleware
2. SessionMiddleware
3. CommonMiddleware
4. CsrfViewMiddleware
5. AuthenticationMiddleware (Django's built-in)
6. authentication.middleware.AuthenticationMiddleware
   └─ process_request(): Checks line 52
      └─ user.is_sales_rep = True AND is_active_sales_rep = False
         └─ logout(request) ✗
         └─ return redirect('frontend-home') ✗

MIDDLEWARE CHAIN STOPS HERE - View is never reached
```

---

## Browser Behavior Comparison

### Admin Login (Browser Perspective)
```
1. User fills in login form
2. User clicks "Login"
3. Page briefly shows loading
4. Browser navigates to /dashboard/
5. User sees admin dashboard
6. URL bar shows: http://127.0.0.1:8000/dashboard/
```

### Sales Rep Login (Browser Perspective)
```
1. User fills in login form
2. User clicks "Login"
3. Page briefly shows loading
4. Browser navigates to /dashboard/ (for a split second)
5. Browser immediately redirects back to /
6. User sees login page again
7. URL bar shows: http://127.0.0.1:8000/
8. No error message shown
9. User confused about what happened
```

---

## Network Activity Comparison

### Admin Login (Network Tab)
```
POST    /                200 OK     (Login form submission)
↓
GET     /dashboard/      200 OK     (Dashboard loaded successfully)
↓
GET     /static/...      200 OK     (Dashboard assets loaded)
```

### Sales Rep Login (Network Tab)
```
POST    /                200 OK     (Login form submission)
↓
GET     /dashboard/      302 Found  (Middleware redirect)
↓
GET     /                200 OK     (Back to login page)
↓
GET     /static/...      200 OK     (Login page assets loaded)
```

---

## Session Lifecycle Comparison

### Admin Session
```
1. Session created:    sessionid=abc123xyz...
2. Session persists:   User stays logged in
3. Session used:       Dashboard loads with user context
4. Session continues:  User can navigate the site
```

### Sales Rep Session
```
1. Session created:    sessionid=def456uvw...
2. Session exists:     For ~50ms (middleware execution time)
3. Session destroyed:  logout(request) called in middleware
4. Session ended:      User no longer authenticated
```

---

## Error Messages Comparison

### Admin Login
- **Success message:** "Welcome back, Admin User!" (if using messages framework)
- **No errors:** Smooth login experience

### Sales Rep Login
- **No success message:** Login appears to succeed
- **No error message:** No explanation for why they're back at login
- **Silent failure:** User has no idea what went wrong

---

## Code Execution Comparison

### Admin - Middleware Process Request
```python
def process_request(self, request):
    if request.user.is_authenticated:
        # Update last login IP
        current_ip = self.get_client_ip(request)
        if request.user.last_login_ip != current_ip:
            request.user.last_login_ip = current_ip
            request.user.save(update_fields=['last_login_ip'])

        # Check if user is still active
        if not request.user.is_active:
            logout(request)
            return redirect('frontend-home')

        # Check if sales rep is active
        # For admin: is_sales_rep = False, so this entire block is SKIPPED
        if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
            logout(request)  # NOT EXECUTED for admin
            return redirect('frontend-home')  # NOT EXECUTED for admin
```

### Sales Rep - Middleware Process Request
```python
def process_request(self, request):
    if request.user.is_authenticated:  # TRUE
        # Update last login IP
        current_ip = self.get_client_ip(request)  # Gets IP
        if request.user.last_login_ip != current_ip:  # Possibly TRUE
            request.user.last_login_ip = current_ip  # Updates IP
            request.user.save(update_fields=['last_login_ip'])  # Saves

        # Check if user is still active
        if not request.user.is_active:  # FALSE (user is active)
            logout(request)  # NOT EXECUTED
            return redirect('frontend-home')  # NOT EXECUTED

        # Check if sales rep is active
        # For sales rep: is_sales_rep = TRUE, is_active_sales_rep = FALSE
        if (request.user.is_sales_rep or request.user.is_account_manager) and not request.user.is_active_sales_rep:
            # TRUE: is_sales_rep=TRUE AND is_active_sales_rep=FALSE
            logout(request)  # ✗ EXECUTED - Session destroyed
            return redirect('frontend-home')  # ✗ EXECUTED - Redirect to /
```

---

## Key Differences Summary

| Aspect | Admin | Sales Rep |
|--------|-------|-----------|
| **Authentication** | ✅ Successful | ✅ Successful |
| **Session Creation** | ✅ Created | ✅ Created |
| **Middleware Check** | ✅ Passed | ❌ Failed |
| **Line 52 Executed** | ❌ No (not sales rep) | ✅ Yes (is sales rep) |
| **Logout Called** | ❌ No | ✅ Yes |
| **Final URL** | /dashboard/ | / (login page) |
| **User Experience** | ✅ Success | ❌ Silent failure |
| **Error Message** | None needed | ⚠️ None shown (should be) |

---

## Conclusion

**The ONLY difference that matters:**

```python
# Admin
user.user_type = 'admin'
# Line 52 is NOT checked because user is not a sales_rep or account_manager

# Sales Rep
user.user_type = 'sales_rep'
user.is_active_sales_rep = False  ← THIS IS THE PROBLEM
# Line 52 IS checked because user is sales_rep
# Result: logout(request) and redirect back to login
```

**Fix:** Set `is_active_sales_rep=True` for the sales rep user.
