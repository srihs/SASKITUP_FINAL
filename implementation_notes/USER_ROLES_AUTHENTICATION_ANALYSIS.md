# User Roles and Authentication System Analysis

**Date:** 2025-10-07
**Project:** SASKITUP - Wholesale & Retail Management System
**Analyst:** Claude Code

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Role Definitions and Model Structure](#role-definitions-and-model-structure)
3. [Authentication Flow](#authentication-flow)
4. [Role-Based Redirect Mapping](#role-based-redirect-mapping)
5. [Permission and Access Control](#permission-and-access-control)
6. [Test User Database](#test-user-database)
7. [Code Snippets - Key Redirect Logic](#code-snippets---key-redirect-logic)
8. [Security Features](#security-features)
9. [Recommendations](#recommendations)

---

## Executive Summary

The SASKITUP application implements a sophisticated role-based authentication system with four distinct user types:

- **Admin** - Full system access with superuser privileges
- **Sales Representatives** - Assigned to specific schools/clubs
- **Account Managers** - Broader access to all schools/clubs
- **Customers** - Limited access to their own data

**Authentication Method:** Email-based login with custom backend
**Session Management:** Enhanced with IP tracking, audit logging, and security monitoring
**Redirect Strategy:** Role-based with explicit URL mapping after successful login

---

## Role Definitions and Model Structure

### User Model (`authentication/models.py`)

The custom `User` model extends Django's `AbstractUser` and includes:

```python
class User(AbstractUser):
    USER_TYPE_CHOICES = [
        ('admin', 'Admin'),
        ('sales_rep', 'Sales Representative'),
        ('account_manager', 'Account Manager'),
        ('customer', 'Customer'),
    ]

    # Email is unique and required (used for login)
    email = models.EmailField(unique=True, help_text="Email address - used for login")

    # User type determines role
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='sales_rep'
    )

    # Profile fields
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    employee_id = models.CharField(max_length=50, blank=True, unique=True, null=True)

    # Sales rep specific
    is_active_sales_rep = models.BooleanField(default=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
```

### Role Properties

Each role has convenience properties for checking permissions:

```python
@property
def is_admin(self):
    return self.user_type == 'admin' or self.is_superuser

@property
def is_sales_rep(self):
    return self.user_type == 'sales_rep'

@property
def is_account_manager(self):
    return self.user_type == 'account_manager'

@property
def is_customer(self):
    return self.user_type == 'customer'

@property
def can_access_admin_panel(self):
    return self.is_admin and self.is_superuser
```

### Assignment Models

**SalesRepSchoolAssignment:**
- Links sales reps/account managers to TUS schools or wholesale schools
- Each school can have only ONE active assignment
- Supports priority levels (high/medium/low)
- Tracks territory and notes

**SalesRepClubAssignment:**
- Links sales reps/account managers to clubs (LottoClub or SASClub)
- Uses GenericForeignKey for club polymorphism
- Each club can have only ONE active assignment
- Supports priority levels and territory tracking

---

## Authentication Flow

### 1. Login Process

```
User visits: / or /auth/login/
              ↓
    Login Form (Email + Password)
              ↓
    EmailBackend.authenticate()
              ↓
    Check email (case-insensitive)
              ↓
    Verify password
              ↓
    Check is_active status
              ↓
    Create UserSession record
              ↓
    Log to AuditLog
              ↓
    Role-based redirect
```

### 2. Email-Based Authentication

**Authentication Backend:** `/Users/sas/Repos/SASKITUP/authentication/backends.py`

```python
class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # username parameter actually contains email
        user = User.objects.get(
            Q(email__iexact=username) | Q(username=username)
        )

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
```

**Key Features:**
- Case-insensitive email lookup
- Backward compatible with username field
- Timing attack protection (runs password hasher even for non-existent users)
- Multi-user fallback (should not occur with unique constraint)

### 3. Session Management

After successful login, the system creates multiple tracking records:

**UserSession Model:**
- session_key: Django session identifier
- ip_address: Client IP from request
- user_agent: Browser/client info
- login_time: Timestamp of login
- last_activity: Updated on each request
- is_active: Boolean flag

**AuditLog Entry:**
- Records every login attempt (success or failure)
- Captures IP address, user agent, session key
- Enables security monitoring and compliance

### 4. Middleware Stack

**Order matters!** The middleware processes requests in this sequence:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',      # Must be early
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',   # Populates request.user
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'authentication.middleware.AuthenticationMiddleware',        # Custom: IP tracking, session tracking
    'authentication.middleware.RoleBasedAccessMiddleware',       # Custom: URL access control
    'authentication.middleware.SessionSecurityMiddleware',       # Custom: Security monitoring
]
```

**Custom Middleware Functions:**

1. **AuthenticationMiddleware:**
   - Updates last_login_ip on each request
   - Creates/updates UserSession records
   - Logs out inactive or deactivated users

2. **RoleBasedAccessMiddleware:**
   - Enforces role-based URL access
   - Redirects to access-denied page for unauthorized access
   - Logs permission violations to AuditLog

3. **SessionSecurityMiddleware:**
   - Detects session hijacking (IP changes)
   - Monitors user agent changes
   - Alerts on suspicious activity

---

## Role-Based Redirect Mapping

### Redirect Decision Tree

```
Login Successful
       ↓
  Check user.user_type
       ↓
       ├─→ 'admin' or is_superuser?
       │         ↓
       │    /dashboard/ (GlobalDashboardView)
       │
       ├─→ 'sales_rep'?
       │         ↓
       │    /profile/ (ProfileView → profile_sales.html)
       │
       ├─→ 'account_manager'?
       │         ↓
       │    /profile/ (ProfileView → profile_sales.html)
       │
       └─→ 'customer'?
                 ↓
            /profile/ (ProfileView → profile_customer.html)
```

### URL Mapping Table

| Role | Redirect URL | View Class | Template | Dashboard Features |
|------|-------------|------------|----------|-------------------|
| **Admin** | `/dashboard/` | `GlobalDashboardView` | `global_dashboard.html` | - User management<br>- Assignment management<br>- System settings<br>- Audit logs<br>- All schools/clubs access |
| **Sales Rep** | `/profile/` | `ProfileView` | `profile_sales.html` | - Assigned schools/clubs only<br>- Quotations (upcoming)<br>- Recent activity<br>- Assignment details |
| **Account Manager** | `/profile/` | `ProfileView` | `profile_customer.html` | - ALL schools/clubs access<br>- Quotations (upcoming)<br>- Recent activity<br>- Full assignment overview |
| **Customer** | `/profile/` | `ProfileView` | `profile_customer.html` | - Own organization data<br>- Orders (placeholder)<br>- Support access<br>- Activity history |

### Implementation Details

**File:** `/Users/sas/Repos/SASKITUP/authentication/views.py`

```python
class LoginView(FormView):
    template_name = 'authentication/login.html'
    form_class = EmailAuthenticationForm

    def get_redirect_url(self, user):
        """Get redirect URL based on user role"""
        # Admin and Superadmin → Global Dashboard
        if user.user_type in ['admin'] or user.is_superuser:
            return reverse_lazy('global-dashboard')

        # Sales Reps, Account Managers, Customers → Profile
        elif user.user_type in ['sales_rep', 'account_manager', 'customer']:
            return reverse_lazy('authentication:profile')

        # Default fallback
        return reverse_lazy('global-dashboard')

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)

        # Log successful login
        AuditLog.log_action(
            user=user,
            action_type='login',
            description=f'User {user.username} logged in successfully',
            request=self.request
        )

        messages.success(self.request, f'Welcome back, {user.get_full_name() or user.username}!')

        # Check for 'next' parameter first
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return redirect(next_url)

        # Role-based redirection
        redirect_url = self.get_redirect_url(user)
        return redirect(redirect_url)
```

### Profile View Routing

The unified `ProfileView` dynamically selects templates based on user role:

```python
class ProfileView(TemplateView):
    def get_template_names(self):
        """Return appropriate template based on user type"""
        user = self.request.user

        if user.user_type in ['sales_rep', 'account_manager']:
            return ['authentication/profile_sales.html']
        elif user.user_type == 'customer':
            return ['authentication/profile_customer.html']
        else:
            return ['authentication/access_denied.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Sales Rep/Account Manager specific context
        if user.user_type in ['sales_rep', 'account_manager']:
            context.update(self._get_sales_rep_context(user))

        # Customer specific context
        elif user.user_type == 'customer':
            context.update(self._get_customer_context(user))

        return context
```

---

## Permission and Access Control

### Access Control Layers

The application implements **three layers** of access control:

1. **Middleware-Level:** URL pattern restrictions
2. **View-Level:** Mixin-based permission checks
3. **Object-Level:** Assignment-based data filtering

### 1. Middleware-Level Access Control

**File:** `/Users/sas/Repos/SASKITUP/authentication/middleware.py`

```python
class RoleBasedAccessMiddleware:
    admin_only_paths = [
        '/admin/',
        '/auth/users/',
        '/auth/assignments/',
        '/auth/audit-logs/',
    ]

    sales_rep_restricted_paths = [
        '/admin/',
        '/auth/users/create/',
        '/auth/assignments/',
    ]

    account_manager_accessible_paths = [
        '/auth/assignments/',
        '/schools/',
        '/clubs/',
        '/wholesale/',
    ]

    public_paths = [
        '/',  # Frontend landing (login)
        '/profile/',
        '/auth/logout/',
        '/auth/signup/',
        '/accounts/',  # Password reset
        '/static/',
        '/media/',
    ]
```

**Behavior:**
- Public paths: No authentication required
- Admin-only paths: Only `user.is_admin` can access
- Sales rep restrictions: Sales reps blocked from user/assignment management
- Account managers: Broader access than sales reps (all schools/clubs)

### 2. View-Level Mixins

**File:** `/Users/sas/Repos/SASKITUP/authentication/permissions.py`

**Base Mixin:**
```python
class RoleRequiredMixin(UserPassesTestMixin):
    required_roles = []
    login_url = '/'
    permission_denied_message = "You don't have permission to access this page."

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        user = self.request.user

        # Admin users can access everything
        if user.is_admin:
            return True

        # Check if user has any of the required roles
        return user.user_type in self.required_roles

    def handle_no_permission(self):
        # Log unauthorized access attempts
        AuditLog.log_action(
            user=self.request.user,
            action_type='permission_denied',
            description=f'Attempted to access {self.request.path} without required role',
            request=self.request
        )
        return super().handle_no_permission()
```

**Available Mixins:**

| Mixin | Required Roles | Usage Example |
|-------|---------------|---------------|
| `AdminRequiredMixin` | `['admin']` | User management, audit logs |
| `SalesRepRequiredMixin` | `['admin', 'sales_rep']` | Sales rep dashboard |
| `AccountManagerRequiredMixin` | `['admin', 'account_manager']` | Account manager tools |
| `SalesRepOrAccountManagerMixin` | `['admin', 'sales_rep', 'account_manager']` | Shared tools |
| `CustomerRequiredMixin` | `['admin', 'customer']` | Customer portal |

**Usage in Views:**

```python
class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = 'authentication/user_list.html'
    # Only admins can access this view
```

### 3. Object-Level Access Control

**School Access:**

```python
def can_access_school(self, school):
    """Check if user can access a specific school"""
    if self.is_admin:
        return True

    # Account managers have access to ALL schools
    if self.is_account_manager:
        return True

    if self.is_sales_rep:
        return self.school_assignments.filter(
            models.Q(school=school) | models.Q(wholesale_school=school),
            is_active=True
        ).exists()

    return False
```

**Club Access:**

```python
def can_access_club(self, club):
    """Check if user can access a specific club"""
    if self.is_admin:
        return True

    # Account managers have access to ALL clubs
    if self.is_account_manager:
        return True

    if self.is_sales_rep:
        return self.club_assignments.filter(club=club, is_active=True).exists()

    return False
```

**Data Filtering:**

```python
def filter_schools_for_user(user, queryset):
    """Filter schools queryset based on user permissions"""
    if user.is_admin:
        return queryset

    # Account managers have access to all schools
    if user.is_account_manager:
        return queryset

    if user.is_sales_rep:
        # Get assigned school IDs
        school_assignments = user.school_assignments.filter(is_active=True)

        tus_school_ids = school_assignments.filter(
            tus_school__isnull=False
        ).values_list('tus_school_id', flat=True)

        wholesale_school_ids = school_assignments.filter(
            wholesale_school__isnull=False
        ).values_list('wholesale_school_id', flat=True)

        # Filter based on school type
        if queryset.model == TUSSchool:
            return queryset.filter(id__in=tus_school_ids)
        elif queryset.model == WholesaleSchool:
            return queryset.filter(id__in=wholesale_school_ids)

    return queryset.none()
```

### Permission Decision Matrix

| Action | Admin | Account Manager | Sales Rep | Customer |
|--------|-------|----------------|-----------|----------|
| View all users | ✅ | ❌ | ❌ | ❌ |
| Create users | ✅ | ❌ | ❌ | ❌ |
| Edit assignments | ✅ | ❌ | ❌ | ❌ |
| View audit logs | ✅ | ❌ | ❌ | ❌ |
| Access Django admin | ✅ | ❌ | ❌ | ❌ |
| View all schools | ✅ | ✅ | ❌ | ❌ |
| View all clubs | ✅ | ✅ | ❌ | ❌ |
| View assigned schools | ✅ | ✅ | ✅ | ❌ |
| View assigned clubs | ✅ | ✅ | ✅ | ❌ |
| Create quotations | ✅ | ✅ | ✅ | ❌ |
| View own profile | ✅ | ✅ | ✅ | ✅ |
| Update own profile | ✅ | ✅ | ✅ | ✅ |
| View own orders | ✅ | ✅ | ✅ | ✅ |
| View support | ✅ | ✅ | ✅ | ✅ |

---

## Test User Database

### Current User Inventory

**Database Query Results (as of analysis date):**

```
Total Users: 4

--- Users by Role ---
Admin:                1
Sales Representative: 1
Account Manager:      1
Customer:             1

--- User Details ---
Username             | Email                          | Role                 | Active
------------------------------------------------------------------------------------------
srimal               | srimalhs@gmail.com             | Admin                | True
srimal@saskitup.com  | srimal@saskitup.com            | Account Manager      | True
srimal@sascreative.co.nz | srimal@sascreative.co.nz   | Sales Representative | True
srimal@sas.co.nz     | srimal@sas.co.nz               | Customer             | True
```

### Test Login Credentials

**Note:** Passwords are hashed in the database. For testing, you'll need to:

1. **Use Django Admin** to reset passwords
2. **Use the shell** to create test passwords:

```bash
source env/bin/activate
python manage.py shell

from authentication.models import User

# Set password for admin user
admin_user = User.objects.get(email='srimalhs@gmail.com')
admin_user.set_password('YourTestPassword123!')
admin_user.save()

# Set password for sales rep
sales_rep = User.objects.get(email='srimal@sascreative.co.nz')
sales_rep.set_password('SalesRepPassword123!')
sales_rep.save()

# Set password for account manager
account_mgr = User.objects.get(email='srimal@saskitup.com')
account_mgr.set_password('AccountMgrPassword123!')
account_mgr.save()

# Set password for customer
customer = User.objects.get(email='srimal@sas.co.nz')
customer.set_password('CustomerPassword123!')
customer.save()
```

3. **Create Additional Test Users** (management command recommended):

```python
# Create additional test users
from authentication.models import User

# Admin user
User.objects.create_user(
    username='admin_test',
    email='admin@test.com',
    password='AdminTest123!',
    user_type='admin',
    first_name='Admin',
    last_name='Tester',
    is_superuser=True,
    is_staff=True
)

# Sales rep
User.objects.create_user(
    username='salesrep_test',
    email='salesrep@test.com',
    password='SalesTest123!',
    user_type='sales_rep',
    first_name='Sales',
    last_name='Representative'
)

# Account manager
User.objects.create_user(
    username='accountmgr_test',
    email='accountmgr@test.com',
    password='AccountTest123!',
    user_type='account_manager',
    first_name='Account',
    last_name='Manager'
)

# Customer
User.objects.create_user(
    username='customer_test',
    email='customer@test.com',
    password='CustomerTest123!',
    user_type='customer',
    first_name='Test',
    last_name='Customer'
)
```

### Expected Login Behavior by User

| Email | Role | Expected Redirect | Access Level |
|-------|------|-------------------|--------------|
| `srimalhs@gmail.com` | Admin | `/dashboard/` | Full system access |
| `srimal@saskitup.com` | Account Manager | `/profile/` | All schools/clubs, limited admin |
| `srimal@sascreative.co.nz` | Sales Rep | `/profile/` | Assigned schools/clubs only |
| `srimal@sas.co.nz` | Customer | `/profile/` | Own data, orders, support |

---

## Code Snippets - Key Redirect Logic

### 1. Login View Redirect Logic

**File:** `/Users/sas/Repos/SASKITUP/authentication/views.py` (Lines 33-94)

```python
class LoginView(FormView):
    """Custom login view with audit logging and email-based authentication"""
    template_name = 'authentication/login.html'
    form_class = EmailAuthenticationForm
    success_url = None  # Role-based redirection

    def get_redirect_url(self, user):
        """Get redirect URL based on user role"""
        # Admin and Superadmin → Global Dashboard
        if user.user_type in ['admin'] or user.is_superuser:
            return reverse_lazy('global-dashboard')

        # Sales Reps, Account Managers, Customers → Profile
        elif user.user_type in ['sales_rep', 'account_manager', 'customer']:
            return reverse_lazy('authentication:profile')

        # Default fallback
        return reverse_lazy('global-dashboard')

    def dispatch(self, request, *args, **kwargs):
        # Prevent already-authenticated users from seeing login page
        if request.user.is_authenticated:
            redirect_url = self.get_redirect_url(request.user)
            return redirect(redirect_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)

        # Log successful login
        AuditLog.log_action(
            user=user,
            action_type='login',
            description=f'User {user.username} logged in successfully',
            request=self.request
        )

        messages.success(self.request, f'Welcome back, {user.get_full_name() or user.username}!')

        # Redirect to next URL if provided (check POST and GET)
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return redirect(next_url)

        # Role-based redirection
        redirect_url = self.get_redirect_url(user)
        return redirect(redirect_url)

    def form_invalid(self, form):
        # Log failed login attempt
        email = form.data.get('username', 'Unknown')
        AuditLog.log_action(
            user=None,
            action_type='login',
            description=f'Failed login attempt for email: {email}',
            request=self.request,
            email=email
        )

        messages.error(self.request, 'Invalid email or password.')
        return super().form_invalid(form)
```

### 2. Profile View Template Selection

**File:** `/Users/sas/Repos/SASKITUP/authentication/views.py` (Lines 537-680)

```python
@method_decorator(login_required, name='dispatch')
class ProfileView(TemplateView):
    """
    Unified profile view that routes to different templates based on user type
    - Sales Reps/Account Managers → Sales Rep Profile
    - Customers → Customer Profile
    """

    def get_template_names(self):
        """Return appropriate template based on user type"""
        user = self.request.user

        if user.user_type in ['sales_rep', 'account_manager']:
            return ['authentication/profile_sales.html']
        elif user.user_type == 'customer':
            return ['authentication/profile_customer.html']
        else:
            # Fallback for other user types
            return ['authentication/access_denied.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Common context for all profiles
        context['user_obj'] = user
        context['recent_activities'] = AuditLog.objects.filter(
            user=user
        ).order_by('-timestamp')[:20]

        # Sales Rep/Account Manager specific context
        if user.user_type in ['sales_rep', 'account_manager']:
            context.update(self._get_sales_rep_context(user))

        # Customer specific context
        elif user.user_type == 'customer':
            context.update(self._get_customer_context(user))

        return context

    def _get_sales_rep_context(self, user):
        """Get context data for sales rep profile"""
        # Get assigned schools and clubs
        tus_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            tus_school_id__isnull=False
        ).select_related('sales_rep', 'tus_school')

        wholesale_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            wholesale_school__isnull=False
        ).select_related('sales_rep', 'wholesale_school')

        lotto_content_type = ContentType.objects.get_for_model(LottoClub)
        lotto_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            club_content_type=lotto_content_type
        )

        sas_content_type = ContentType.objects.get_for_model(SASClub)
        sas_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True,
            club_content_type=sas_content_type
        )

        return {
            'tus_schools': tus_schools,
            'wholesale_schools': wholesale_schools,
            'lotto_clubs': lotto_clubs,
            'sas_clubs': sas_clubs,
            'total_assignments': (
                len(tus_schools) + len(wholesale_schools) +
                len(lotto_clubs) + len(sas_clubs)
            ),
            'quotations': [],  # Placeholder for Phase 2
        }

    def _get_customer_context(self, user):
        """Get context data for customer profile"""
        return {
            'organization': None,  # Placeholder
            'assigned_sales_rep': None,  # Placeholder
            'quotations': [],  # Placeholder for Phase 2
        }
```

### 3. Middleware Access Control

**File:** `/Users/sas/Repos/SASKITUP/authentication/middleware.py` (Lines 181-217)

```python
class RoleBasedAccessMiddleware:
    def check_access(self, request):
        """Check if user has access to the requested path"""
        path = request.path

        # Allow public paths
        if any(path.startswith(public_path) for public_path in self.public_paths):
            return None

        # Require authentication for all other paths
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        # Check admin-only paths
        if any(path.startswith(admin_path) for admin_path in self.admin_only_paths):
            if not request.user.is_admin:
                AuditLog.log_action(
                    user=request.user,
                    action_type='permission_denied',
                    description=f'Attempted to access admin-only path: {path}',
                    request=request,
                    attempted_path=path
                )
                return redirect('authentication:access-denied')

        # Check sales rep restrictions
        if any(path.startswith(restricted_path) for restricted_path in self.sales_rep_restricted_paths):
            if request.user.is_sales_rep or request.user.is_account_manager:
                AuditLog.log_action(
                    user=request.user,
                    action_type='permission_denied',
                    description=f'{request.user.get_user_type_display()} attempted to access restricted path: {path}',
                    request=request,
                    attempted_path=path
                )
                return redirect('authentication:access-denied')

        return None
```

### 4. Email Backend Authentication

**File:** `/Users/sas/Repos/SASKITUP/authentication/backends.py` (Lines 11-56)

```python
class EmailBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using their email address
    instead of username. Also supports case-insensitive email matching.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user based on email address and password.
        """
        if username is None or password is None:
            return None

        try:
            # Try to find user by email (case-insensitive)
            # Also support username for backward compatibility
            user = User.objects.get(
                Q(email__iexact=username) | Q(username=username)
            )
        except User.DoesNotExist:
            # Run the default password hasher once to reduce timing difference
            # between existing and non-existent user
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # Should not happen with unique constraint
            user = User.objects.filter(
                Q(email__iexact=username) | Q(username=username)
            ).first()
            if not user:
                return None

        # Check password and if user is active
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
```

### 5. Assignment-Based Access Control

**File:** `/Users/sas/Repos/SASKITUP/authentication/models.py` (Lines 231-266)

```python
def can_access_school(self, school):
    """
    Check if user can access a specific school
    Account managers have access to ALL schools
    """
    if self.is_admin:
        return True

    # Account managers have access to all schools
    if self.is_account_manager:
        return True

    if self.is_sales_rep:
        return self.school_assignments.filter(
            models.Q(school=school) | models.Q(wholesale_school=school),
            is_active=True
        ).exists()

    return False

def can_access_club(self, club):
    """
    Check if user can access a specific club
    Account managers have access to ALL clubs
    """
    if self.is_admin:
        return True

    # Account managers have access to all clubs
    if self.is_account_manager:
        return True

    if self.is_sales_rep:
        return self.club_assignments.filter(club=club, is_active=True).exists()

    return False
```

---

## Security Features

### 1. Password Security

- **Hashing:** Django's PBKDF2 algorithm with SHA256
- **Minimum Length:** Enforced via validation (8+ characters recommended)
- **Password Change:** Audit logged with user/admin tracking

### 2. Session Security

**Session Hijacking Detection:**

```python
class SessionSecurityMiddleware:
    def check_session_security(self, request):
        # Check for IP changes
        if user_session.ip_address != current_ip:
            AuditLog.log_action(
                user=request.user,
                action_type='security_alert',
                description=f'Session IP changed from {user_session.ip_address} to {current_ip}',
                request=request
            )

        # Check for user agent changes
        if user_session.user_agent != current_user_agent:
            AuditLog.log_action(
                user=request.user,
                action_type='security_alert',
                description='Session user agent changed',
                request=request
            )
```

**Auto-Logout on Inactivity:**

```python
class AutoLogoutMiddleware:
    timeout = 3600  # 1 hour default

    def should_auto_logout(self, request):
        user_session = UserSession.objects.get(
            session_key=request.session.session_key,
            user=request.user,
            is_active=True
        )

        time_since_activity = timezone.now() - user_session.last_activity
        return time_since_activity.total_seconds() > self.timeout
```

### 3. Audit Logging

**Every security-relevant action is logged:**

- Login attempts (success and failure)
- Logout events
- Password changes
- Permission denials
- Session security alerts
- User creation/modification
- Assignment changes

**AuditLog Model Fields:**

```python
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
```

### 4. CSRF Protection

- Enabled via `CsrfViewMiddleware`
- Token validation on all POST/PUT/PATCH/DELETE requests
- Secure cookie settings for production

### 5. Content Security

- `X-Frame-Options: DENY` (prevent clickjacking)
- `X-Content-Type-Options: nosniff`
- HTTPS redirect in production
- HSTS headers for secure connections

---

## Recommendations

### 1. Password Policy Enhancements

**Current:** Basic password validation
**Recommended:**

```python
# settings.py
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Enforce password expiration
PASSWORD_EXPIRY_DAYS = 90  # Custom setting
```

### 2. Two-Factor Authentication (2FA)

**Recommended Implementation:**

```bash
pip install django-otp qrcode
```

```python
# settings.py
INSTALLED_APPS += [
    'django_otp',
    'django_otp.plugins.otp_totp',
]

MIDDLEWARE += [
    'django_otp.middleware.OTPMiddleware',
]
```

**Benefits:**
- Significantly increased account security
- Protection against credential theft
- Industry standard compliance

### 3. Rate Limiting for Login Attempts

**Recommended Implementation:**

```bash
pip install django-ratelimit
```

```python
from django_ratelimit.decorators import ratelimit

class LoginView(FormView):
    @method_decorator(ratelimit(key='ip', rate='5/h', method='POST'))
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
```

**Benefits:**
- Prevents brute-force attacks
- Reduces credential stuffing attempts
- Protects against automated attacks

### 4. Email Verification on Signup

**Current:** No email verification for customer signup
**Recommended:**

```python
# Add email verification field to User model
email_verified = models.BooleanField(default=False)
email_verification_token = models.CharField(max_length=100, blank=True)

# Send verification email on signup
def send_verification_email(user):
    token = generate_verification_token()
    user.email_verification_token = token
    user.save()

    verification_url = f"{settings.SITE_URL}/auth/verify/{token}/"
    send_mail(
        'Verify your email',
        f'Click here to verify: {verification_url}',
        settings.DEFAULT_FROM_EMAIL,
        [user.email]
    )
```

### 5. Session Management Dashboard

**Recommended Feature:**

Create a user-facing session management page showing:
- Active sessions (device, location, last activity)
- Option to revoke sessions
- Login history

```python
class SessionManagementView(LoginRequiredMixin, ListView):
    model = UserSession
    template_name = 'authentication/session_management.html'

    def get_queryset(self):
        return UserSession.objects.filter(
            user=self.request.user,
            is_active=True
        ).order_by('-last_activity')
```

### 6. Enhanced Audit Log Search

**Current:** Basic audit log listing
**Recommended:**

```python
# Add filtering and search capabilities
class AuditLogListView(AdminRequiredMixin, ListView):
    def get_queryset(self):
        queryset = AuditLog.objects.all()

        # Filter by user
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by action type
        action_type = self.request.GET.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)

        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)

        return queryset.order_by('-timestamp')
```

### 7. Role Transition Workflow

**Recommended:** Add proper workflow for changing user roles

```python
class ChangeUserRoleView(AdminRequiredMixin, UpdateView):
    model = User
    fields = ['user_type']

    def form_valid(self, form):
        old_role = self.object.user_type
        new_role = form.cleaned_data['user_type']

        # Log role change
        AuditLog.log_action(
            user=self.request.user,
            action_type='role_changed',
            description=f'Changed user {self.object.username} role from {old_role} to {new_role}',
            request=self.request,
            target_user_id=self.object.id,
            old_role=old_role,
            new_role=new_role
        )

        # Invalidate all user sessions to force re-login
        UserSession.objects.filter(user=self.object).update(is_active=False)

        messages.warning(
            self.request,
            f'User role changed. The user must log in again for changes to take effect.'
        )

        return super().form_valid(form)
```

### 8. API Token Authentication (Future)

For upcoming API development:

```python
# Use Django REST Framework Token Authentication
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}
```

---

## Appendix: URL Configuration

### Main URL Routing

**File:** `/Users/sas/Repos/SASKITUP/kitup/urls.py`

```python
urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication URLs
    path('auth/', include('authentication.urls')),
    path('accounts/', include('django.contrib.auth.urls')),

    # Core app URLs
    path('clubs/', include('clubs.urls')),
    path('schools/', include('schools.urls')),
    path('quotations/', include('quotations.urls')),
    path('dashboard/', GlobalDashboardView.as_view(), name='global-dashboard'),

    # Frontend pages
    path('', frontend_landing_view, name='frontend-home'),
    path('profile/', ProfileView.as_view(), name='profile'),
]
```

### Authentication URLs

**File:** `/Users/sas/Repos/SASKITUP/authentication/urls.py`

```python
app_name = 'authentication'

urlpatterns = [
    # Authentication
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.SignupView.as_view(), name='signup'),

    # Unified Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Dashboards
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('sales-rep-dashboard/', views.SalesRepDashboardView.as_view(), name='sales-rep-dashboard'),
    path('customer-dashboard/', views.CustomerDashboardView.as_view(), name='customer-dashboard'),

    # User Management (Admin Only)
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/create/', views.UserCreateView.as_view(), name='user-create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user-update'),

    # Assignment Management (Admin Only)
    path('assignments/', views.BulkAssignmentView.as_view(), name='bulk-assignment'),
    path('assignments/process/', views.ProcessBulkAssignmentView.as_view(), name='process-bulk-assignment'),

    # AJAX Endpoints
    path('ajax/users/search/', views.user_search_ajax, name='user-search-ajax'),
    path('change-password/', views.change_password_view, name='change-password'),
]
```

---

## Conclusion

The SASKITUP authentication system implements a robust, role-based access control system with:

1. **Clear role separation** with four distinct user types
2. **Email-based authentication** for improved security
3. **Role-specific redirects** to appropriate dashboards/profiles
4. **Multi-layer access control** (middleware, view, object-level)
5. **Comprehensive audit logging** for security and compliance
6. **Session security monitoring** with hijacking detection
7. **Assignment-based data filtering** for sales reps and account managers

The system is production-ready with room for enhancements like 2FA, rate limiting, and email verification.

---

**Analysis completed by:** Claude Code
**Date:** 2025-10-07
**File locations documented:** All paths use absolute references from `/Users/sas/Repos/SASKITUP/`
