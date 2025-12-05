# Role-Based Dashboard and Navigation Implementation Plan

**Date:** 2025-10-07
**Project:** SASKITUP - Wholesale & Retail Management System
**Objective:** Unified dashboard redirect with role-based content and navigation

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Required Changes](#required-changes)
4. [Implementation Steps](#implementation-steps)
5. [File Modifications](#file-modifications)
6. [Testing Scenarios](#testing-scenarios)
7. [SQL Testing Queries](#sql-testing-queries)

---

## Executive Summary

### Current Behavior
- **Admins** → `/dashboard/` (GlobalDashboardView)
- **Sales Reps, Account Managers, Customers** → `/profile/` (ProfileView)

### Target Behavior
- **ALL ROLES** → `/dashboard/` with role-based content filtering
- Different navigation menus based on user role
- Quotations section added for all non-customer roles
- Settings restricted to "My Profile" for non-admins

### Key Benefits
1. Unified entry point for all users
2. Consistent user experience
3. Role-appropriate data filtering
4. Clearer navigation structure
5. Better quotation workflow integration

---

## Current State Analysis

### Authentication Flow

```python
# Current redirect logic in authentication/views.py
def get_redirect_url(self, user):
    # Admin → /dashboard/
    if user.user_type in ['admin'] or user.is_superuser:
        return reverse_lazy('global-dashboard')

    # All others → /profile/
    elif user.user_type in ['sales_rep', 'account_manager', 'customer']:
        return reverse_lazy('authentication:profile')
```

### Current Dashboard Implementation

**Location:** `/Users/sas/Repos/SASKITUP/kitup/views.py`

**GlobalDashboardView:**
- Currently accessible to all authenticated users
- Shows global stats without role filtering
- Template: `/Users/sas/Repos/SASKITUP/template/dashboard/global_dashboard.html`

### Navigation Template

**Location:** `/Users/sas/Repos/SASKITUP/template/base.html`

**Current Structure:**
```html
<ul class="metismenu list-unstyled" id="side-menu">
    <li class="menu-title">Menu</li>
    <li><a href="{% url 'global-dashboard' %}">Dashboard</a></li>

    <li class="menu-title">CLIENTS</li>
    <li><!-- Clubs submenu --></li>
    <li><!-- Schools submenu --></li>

    <li class="menu-title">SETTINGS</li>
    {% if user.is_admin %}
    <li><!-- User Management submenu --></li>
    {% endif %}
    <li><!-- Settings submenu --></li>
</ul>
```

### Quotations App

**Status:** EXISTS
**Location:** `/Users/sas/Repos/SASKITUP/quotations/`
**URL Namespace:** `quotations`

**Key URLs:**
- `/quotations/select-institution/` - Select institution
- `/quotations/products/<type>/<slug>/` - Product listing
- `/quotations/cart/` - Quotation cart
- `/quotations/my-quotations/` - User's quotations list
- `/quotations/detail/<uuid:pk>/` - Quotation detail

---

## Required Changes

### 1. Login Redirect (PRIORITY 1)

**File:** `/Users/sas/Repos/SASKITUP/authentication/views.py`

**Change:**
```python
# OLD
def get_redirect_url(self, user):
    if user.user_type in ['admin'] or user.is_superuser:
        return reverse_lazy('global-dashboard')
    elif user.user_type in ['sales_rep', 'account_manager', 'customer']:
        return reverse_lazy('authentication:profile')
    return reverse_lazy('global-dashboard')

# NEW
def get_redirect_url(self, user):
    # ALL users redirect to dashboard
    return reverse_lazy('global-dashboard')
```

### 2. Role-Based Dashboard View (PRIORITY 1)

**File:** `/Users/sas/Repos/SASKITUP/kitup/views.py`

**Requirements:**
- Keep existing GlobalDashboardView but add role-based filtering
- Admin sees ALL data
- Account Managers see ALL schools/clubs
- Sales Reps see ONLY assigned schools/clubs
- Customers see ONLY their own data

**Implementation:**
```python
@method_decorator(login_required, name='dispatch')
class GlobalDashboardView(TemplateView):
    template_name = 'dashboard/global_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Role-based stats
        if user.is_admin:
            context.update(self._get_admin_stats())
        elif user.is_account_manager:
            context.update(self._get_account_manager_stats(user))
        elif user.is_sales_rep:
            context.update(self._get_sales_rep_stats(user))
        elif user.is_customer:
            context.update(self._get_customer_stats(user))

        return context

    def _get_admin_stats(self):
        # Full system stats
        return {
            'total_schools': TUSSchool.objects.filter(is_active=True).count() +
                           WholesaleSchool.objects.filter(is_active=True).count(),
            'total_clubs': LottoClub.objects.filter(is_active=True).count() +
                         SASClub.objects.filter(is_active=True).count(),
            'total_quotations': Quotation.objects.count(),
            'pending_quotations': Quotation.objects.filter(status='pending').count(),
            # ... more stats
        }

    def _get_account_manager_stats(self, user):
        # ALL schools and clubs (account managers have full access)
        return {
            'total_schools': TUSSchool.objects.filter(is_active=True).count() +
                           WholesaleSchool.objects.filter(is_active=True).count(),
            'total_clubs': LottoClub.objects.filter(is_active=True).count() +
                         SASClub.objects.filter(is_active=True).count(),
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
            # ... more stats
        }

    def _get_sales_rep_stats(self, user):
        # ONLY assigned schools and clubs
        school_assignments = user.school_assignments.filter(is_active=True)
        club_assignments = user.club_assignments.filter(is_active=True)

        return {
            'my_schools': school_assignments.count(),
            'my_clubs': club_assignments.count(),
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
            'assigned_schools': school_assignments.select_related('tus_school', 'wholesale_school'),
            'assigned_clubs': club_assignments,
            # ... more stats
        }

    def _get_customer_stats(self, user):
        # Personal stats only
        return {
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
            # ... more stats
        }
```

### 3. Navigation Template Updates (PRIORITY 2)

**File:** `/Users/sas/Repos/SASKITUP/template/base.html`

**New Navigation Structure:**

**For Admins:**
```html
<ul class="metismenu list-unstyled" id="side-menu">
    <li class="menu-title">Menu</li>
    <li><a href="{% url 'global-dashboard' %}">Dashboard</a></li>

    <li class="menu-title">CLIENTS</li>
    <li><!-- Schools submenu (all) --></li>
    <li><!-- Clubs submenu (all) --></li>

    <li class="menu-title">QUOTATIONS</li>
    <li><a href="{% url 'quotations:select-institution' %}">New Quotation</a></li>
    <li><a href="{% url 'quotations:my-quotations' %}">All Quotations</a></li>

    <li class="menu-title">SETTINGS</li>
    <li><!-- User Management submenu --></li>
    <li><!-- Full Settings submenu --></li>
</ul>
```

**For Sales Reps / Account Managers:**
```html
<ul class="metismenu list-unstyled" id="side-menu">
    <li class="menu-title">Menu</li>
    <li><a href="{% url 'global-dashboard' %}">Dashboard</a></li>

    <li class="menu-title">MY CLIENTS</li>
    <li>
        <a href="javascript: void(0);" class="has-arrow">
            <i class="uil-briefcase"></i>
            <span>Schools</span>
        </a>
        <ul class="sub-menu">
            <li><a href="{% url 'schools:retail_schools' %}">Retail Schools</a></li>
            <li><a href="{% url 'schools:wholesale_schools' %}">Wholesale Schools</a></li>
        </ul>
    </li>
    <li>
        <a href="javascript: void(0);" class="has-arrow">
            <i class="uil-trophy"></i>
            <span>Clubs</span>
        </a>
        <ul class="sub-menu">
            <li><a href="{% url 'clubs:lotto-clubs' %}">LOTTO Clubs</a></li>
            <li><a href="{% url 'clubs:sas-clubs' %}">SAS Clubs</a></li>
        </ul>
    </li>

    <li class="menu-title">QUOTATIONS</li>
    <li><a href="{% url 'quotations:select-institution' %}">New Quotation</a></li>
    <li><a href="{% url 'quotations:my-quotations' %}">My Quotations</a></li>

    <li class="menu-title">SETTINGS</li>
    <li><a href="{% url 'authentication:user-detail' user.id %}">My Profile</a></li>
</ul>
```

**For Customers:**
```html
<ul class="metismenu list-unstyled" id="side-menu">
    <li class="menu-title">Menu</li>
    <li><a href="{% url 'global-dashboard' %}">Dashboard</a></li>

    <li class="menu-title">MY ACCOUNT</li>
    <li><a href="{% url 'quotations:my-quotations' %}">My Quotations</a></li>
    <li><a href="#">My Orders</a></li>

    <li class="menu-title">SETTINGS</li>
    <li><a href="{% url 'authentication:user-detail' user.id %}">My Profile</a></li>
</ul>
```

### 4. Settings/Profile Restrictions (PRIORITY 3)

**Current Issue:**
- Non-admins can see all settings options in the Settings submenu
- Need to restrict to "My Profile" only

**Implementation:**
Update `template/base.html` Settings section:

```html
<li class="menu-title">SETTINGS</li>

{% if user.is_authenticated and user.is_admin %}
<!-- Full admin settings -->
<li>
    <a href="javascript: void(0);" class="has-arrow waves-effect">
        <i class="uil-users-alt"></i>
        <span>User Management</span>
    </a>
    <ul class="sub-menu" aria-expanded="false">
        <li><a href="{% url 'authentication:user-list' %}">All Users</a></li>
        <li><a href="{% url 'authentication:user-create' %}">Add User</a></li>
        <li><a href="{% url 'authentication:bulk-assignment' %}">Assignments</a></li>
        <li><a href="{% url 'authentication:audit-log-list' %}">Audit Logs</a></li>
    </ul>
</li>
<li>
    <a href="javascript: void(0);" class="has-arrow waves-effect">
        <i class="uil-setting"></i>
        <span>Settings</span>
    </a>
    <ul class="sub-menu" aria-expanded="false">
        <li><a href="{% url 'authentication:settings-dashboard' %}">Settings Dashboard</a></li>
        <li><a href="{% url 'clubs:sync-management' %}">Sync Management</a></li>
        <li><a href="{% url 'schools:wholesale-price-update-settings' %}">Price Update</a></li>
        <li><a href="{% url 'authentication:user-detail' user.id %}">My Profile</a></li>
    </ul>
</li>
{% elif user.is_authenticated and user.id %}
<!-- Non-admin: Only My Profile -->
<li>
    <a href="{% url 'authentication:user-detail' user.id %}">
        <i class="uil-user-circle"></i>
        <span>My Profile</span>
    </a>
</li>
{% endif %}
```

### 5. Dashboard Template Updates (PRIORITY 2)

**File:** `/Users/sas/Repos/SASKITUP/template/dashboard/global_dashboard.html`

**Requirements:**
- Add role-based conditional rendering
- Show different stats based on user role
- Display "My Clients" section for Sales Reps/Account Managers
- Show personal stats for Customers

**Implementation Approach:**
```django
{% extends "base.html" %}

{% block content %}
<div class="row">
    <div class="col-12">
        <div class="page-title-box d-flex align-items-center justify-content-between">
            <h4 class="mb-0">Dashboard</h4>
            {% if user.is_sales_rep or user.is_account_manager %}
            <div class="page-title-right">
                <a href="{% url 'quotations:select-institution' %}" class="btn btn-primary">
                    <i class="uil-plus me-1"></i> New Quotation
                </a>
            </div>
            {% endif %}
        </div>
    </div>
</div>

<!-- Admin Dashboard -->
{% if user.is_admin %}
    <div class="row">
        <div class="col-xl-3 col-md-6">
            <!-- Total Schools Card -->
            <div class="card mini-stat">
                <div class="card-body">
                    <div class="mb-4">
                        <h5 class="font-size-16 text-uppercase mt-0 text-muted">Total Schools</h5>
                        <h2 class="fw-medium mb-0">{{ total_schools }}</h2>
                    </div>
                    <div class="pt-2">
                        <div class="float-end">
                            <a href="{% url 'schools:school_list' %}" class="text-primary">View all <i class="mdi mdi-arrow-right"></i></a>
                        </div>
                        <p class="text-muted mb-0 mt-1">Active institutions</p>
                    </div>
                </div>
            </div>
        </div>
        <!-- More admin cards... -->
    </div>
{% endif %}

<!-- Sales Rep / Account Manager Dashboard -->
{% if user.is_sales_rep or user.is_account_manager %}
    <div class="row">
        <div class="col-xl-3 col-md-6">
            <!-- My Schools Card -->
            <div class="card mini-stat bg-primary text-white">
                <div class="card-body">
                    <div class="mb-4">
                        <h5 class="font-size-16 text-uppercase mt-0 text-white-50">My Schools</h5>
                        <h2 class="fw-medium mb-0 text-white">{{ my_schools }}</h2>
                    </div>
                    <div class="pt-2">
                        <div class="float-end">
                            <a href="{% url 'schools:retail_schools' %}" class="text-white">View <i class="mdi mdi-arrow-right"></i></a>
                        </div>
                        <p class="text-white-50 mb-0 mt-1">Assigned schools</p>
                    </div>
                </div>
            </div>
        </div>
        <!-- More sales rep cards... -->
    </div>

    <!-- My Assigned Clients Section -->
    <div class="row">
        <div class="col-12">
            <div class="card">
                <div class="card-body">
                    <h4 class="card-title mb-4">My Assigned Clients</h4>
                    <!-- List of assigned schools and clubs -->
                </div>
            </div>
        </div>
    </div>
{% endif %}

<!-- Customer Dashboard -->
{% if user.is_customer %}
    <div class="row">
        <div class="col-xl-4 col-md-6">
            <!-- My Quotations Card -->
            <div class="card mini-stat">
                <div class="card-body">
                    <div class="mb-4">
                        <h5 class="font-size-16 text-uppercase mt-0 text-muted">My Quotations</h5>
                        <h2 class="fw-medium mb-0">{{ my_quotations }}</h2>
                    </div>
                    <div class="pt-2">
                        <div class="float-end">
                            <a href="{% url 'quotations:my-quotations' %}" class="text-primary">View all <i class="mdi mdi-arrow-right"></i></a>
                        </div>
                        <p class="text-muted mb-0 mt-1">Total quotations</p>
                    </div>
                </div>
            </div>
        </div>
        <!-- More customer cards... -->
    </div>
{% endif %}
{% endblock %}
```

---

## Implementation Steps

### Phase 1: Login Redirect (10 minutes)
1. Update `authentication/views.py` LoginView.get_redirect_url()
2. Test login for each role
3. Verify all users go to `/dashboard/`

### Phase 2: Dashboard View Logic (30 minutes)
1. Update `kitup/views.py` GlobalDashboardView
2. Add role-based context methods
3. Implement data filtering for each role
4. Test stats accuracy for each role

### Phase 3: Navigation Updates (40 minutes)
1. Update `template/base.html` sidebar navigation
2. Add role-based conditional rendering
3. Add "My Clients" section for Sales Reps/Account Managers
4. Add "Quotations" section
5. Restrict Settings menu for non-admins
6. Test navigation visibility for each role

### Phase 4: Dashboard Template (30 minutes)
1. Update `template/dashboard/global_dashboard.html`
2. Add role-based content sections
3. Style stats cards appropriately
4. Test display for each role

### Phase 5: Testing & Validation (20 minutes)
1. Test login → dashboard redirect for all roles
2. Test dashboard stats for each role
3. Test navigation menu for each role
4. Test quotations workflow
5. Test settings access restrictions

**Total Estimated Time:** 2-3 hours

---

## File Modifications

### 1. `/Users/sas/Repos/SASKITUP/authentication/views.py`

**Line 39-50: Update get_redirect_url method**

```python
def get_redirect_url(self, user):
    """Get redirect URL based on user role - ALL users go to dashboard"""
    # All authenticated users redirect to unified dashboard
    # Dashboard view handles role-based content filtering
    return reverse_lazy('global-dashboard')
```

### 2. `/Users/sas/Repos/SASKITUP/kitup/views.py`

**Add comprehensive role-based dashboard view:**

```python
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.db.models import Q, Count
from authentication.models import User, SalesRepSchoolAssignment, SalesRepClubAssignment
from schools.models import WholesaleSchool
from clubs.models_lotto import LottoClub
from clubs.models_sas import SASClub
from clubs.models_tus import TUSSchool
from quotations.models import Quotation


@method_decorator(login_required, name='dispatch')
class GlobalDashboardView(TemplateView):
    """
    Unified dashboard for all user roles.
    Content and stats filtered based on user.user_type.
    """
    template_name = 'dashboard/global_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Add user info to context
        context['user_role'] = user.get_user_type_display()
        context['user_full_name'] = user.get_full_name() or user.username

        # Get role-specific stats and data
        if user.is_admin:
            context.update(self._get_admin_context())
        elif user.is_account_manager:
            context.update(self._get_account_manager_context(user))
        elif user.is_sales_rep:
            context.update(self._get_sales_rep_context(user))
        elif user.is_customer:
            context.update(self._get_customer_context(user))

        return context

    def _get_admin_context(self):
        """Admin sees ALL system data"""
        return {
            # Schools
            'total_tus_schools': TUSSchool.objects.filter(is_active=True).count(),
            'total_wholesale_schools': WholesaleSchool.objects.filter(is_active=True).count(),
            'total_schools': TUSSchool.objects.filter(is_active=True).count() +
                           WholesaleSchool.objects.filter(is_active=True).count(),

            # Clubs
            'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
            'total_sas_clubs': SASClub.objects.filter(is_active=True).count(),
            'total_clubs': LottoClub.objects.filter(is_active=True).count() +
                         SASClub.objects.filter(is_active=True).count(),

            # Quotations
            'total_quotations': Quotation.objects.count(),
            'pending_quotations': Quotation.objects.filter(status='pending').count(),
            'approved_quotations': Quotation.objects.filter(status='approved').count(),
            'draft_quotations': Quotation.objects.filter(status='draft').count(),

            # Users
            'total_users': User.objects.filter(is_active=True).count(),
            'total_sales_reps': User.objects.filter(user_type='sales_rep', is_active=True).count(),
            'total_account_managers': User.objects.filter(user_type='account_manager', is_active=True).count(),
            'total_customers': User.objects.filter(user_type='customer', is_active=True).count(),

            # Recent quotations
            'recent_quotations': Quotation.objects.select_related('created_by').order_by('-created_at')[:5],
        }

    def _get_account_manager_context(self, user):
        """Account Managers see ALL schools and clubs (same as admin for clients)"""
        return {
            # Schools (ALL)
            'total_tus_schools': TUSSchool.objects.filter(is_active=True).count(),
            'total_wholesale_schools': WholesaleSchool.objects.filter(is_active=True).count(),
            'total_schools': TUSSchool.objects.filter(is_active=True).count() +
                           WholesaleSchool.objects.filter(is_active=True).count(),

            # Clubs (ALL)
            'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
            'total_sas_clubs': SASClub.objects.filter(is_active=True).count(),
            'total_clubs': LottoClub.objects.filter(is_active=True).count() +
                         SASClub.objects.filter(is_active=True).count(),

            # Quotations (Own)
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
            'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
            'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),

            # Recent quotations (Own)
            'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],
        }

    def _get_sales_rep_context(self, user):
        """Sales Reps see ONLY assigned schools and clubs"""
        # Get assignments
        school_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('tus_school', 'wholesale_school')

        club_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('club_content_type')

        # Count by type
        tus_count = school_assignments.filter(tus_school__isnull=False).count()
        wholesale_count = school_assignments.filter(wholesale_school__isnull=False).count()

        from django.contrib.contenttypes.models import ContentType
        lotto_ct = ContentType.objects.get_for_model(LottoClub)
        sas_ct = ContentType.objects.get_for_model(SASClub)

        lotto_count = club_assignments.filter(club_content_type=lotto_ct).count()
        sas_count = club_assignments.filter(club_content_type=sas_ct).count()

        return {
            # Assigned Schools
            'my_tus_schools': tus_count,
            'my_wholesale_schools': wholesale_count,
            'my_schools': school_assignments.count(),

            # Assigned Clubs
            'my_lotto_clubs': lotto_count,
            'my_sas_clubs': sas_count,
            'my_clubs': club_assignments.count(),

            # Quotations (Own)
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
            'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
            'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),

            # Detailed assignments for display
            'assigned_schools': school_assignments[:10],  # Limit for dashboard
            'assigned_clubs': club_assignments[:10],

            # Recent quotations (Own)
            'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],
        }

    def _get_customer_context(self, user):
        """Customers see ONLY their own data"""
        return {
            # Quotations (Own)
            'my_quotations': Quotation.objects.filter(created_by=user).count(),
            'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
            'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
            'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),

            # Recent quotations (Own)
            'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],

            # Placeholder for future customer features
            'my_orders': 0,
            'pending_orders': 0,
        }
```

### 3. `/Users/sas/Repos/SASKITUP/template/base.html`

**Lines 384-463: Replace entire sidebar navigation**

```html
<div data-simplebar class="sidebar-menu-scroll">
    <!--- Sidemenu -->
    <div id="sidebar-menu">
        <!-- Left Menu Start -->
        <ul class="metismenu list-unstyled" id="side-menu">
            <li class="menu-title">Menu</li>

            <!-- Dashboard (All Roles) -->
            <li>
                <a href="{% url 'global-dashboard' %}">
                    <i class="uil-home-alt"></i>
                    <span>Dashboard</span>
                </a>
            </li>

            <!-- ADMIN & ACCOUNT MANAGER: Full Client Access -->
            {% if user.is_admin or user.is_account_manager %}
            <li class="menu-title">CLIENTS</li>

            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-calender"></i>
                    <span>Clubs</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'clubs:lotto-clubs' %}">LOTTO Clubs</a></li>
                    <li><a href="{% url 'clubs:sas-clubs' %}">SAS Clubs</a></li>
                    {% if user.is_staff %}
                    <li>
                        <a href="javascript: void(0);" class="has-arrow">Data Sync</a>
                        <ul class="sub-menu" aria-expanded="false">
                            <li><a href="{% url 'clubs:sync-lotto-clubs-page' %}">LOTTO Sync</a></li>
                        </ul>
                    </li>
                    {% endif %}
                </ul>
            </li>

            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-graduation-cap"></i>
                    <span>Schools</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'schools:school_list' %}">School Database</a></li>
                    <li><a href="{% url 'schools:retail_schools' %}">Retail Schools</a></li>
                    <li><a href="{% url 'schools:wholesale_schools' %}">Wholesale Schools</a></li>
                </ul>
            </li>
            {% endif %}

            <!-- SALES REP: My Clients Only -->
            {% if user.is_sales_rep %}
            <li class="menu-title">MY CLIENTS</li>

            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-briefcase"></i>
                    <span>Schools</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'schools:retail_schools' %}">Retail Schools</a></li>
                    <li><a href="{% url 'schools:wholesale_schools' %}">Wholesale Schools</a></li>
                </ul>
            </li>

            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-trophy"></i>
                    <span>Clubs</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'clubs:lotto-clubs' %}">LOTTO Clubs</a></li>
                    <li><a href="{% url 'clubs:sas-clubs' %}">SAS Clubs</a></li>
                </ul>
            </li>
            {% endif %}

            <!-- QUOTATIONS (Sales Reps, Account Managers, Customers) -->
            {% if user.is_sales_rep or user.is_account_manager or user.is_customer %}
            <li class="menu-title">QUOTATIONS</li>

            {% if not user.is_customer %}
            <!-- Sales Reps and Account Managers can create quotations -->
            <li>
                <a href="{% url 'quotations:select-institution' %}">
                    <i class="uil-plus-circle"></i>
                    <span>New Quotation</span>
                </a>
            </li>
            {% endif %}

            <li>
                <a href="{% url 'quotations:my-quotations' %}">
                    <i class="uil-file-alt"></i>
                    <span>{% if user.is_customer %}My Quotations{% else %}My Quotations{% endif %}</span>
                </a>
            </li>
            {% endif %}

            <!-- CUSTOMER: My Account -->
            {% if user.is_customer %}
            <li class="menu-title">MY ACCOUNT</li>
            <li>
                <a href="#">
                    <i class="uil-shopping-cart"></i>
                    <span>My Orders</span>
                </a>
            </li>
            {% endif %}

            <!-- SETTINGS -->
            <li class="menu-title">SETTINGS</li>

            {% if user.is_admin %}
            <!-- Admin: Full User Management -->
            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-users-alt"></i>
                    <span>User Management</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'authentication:user-list' %}">All Users</a></li>
                    <li><a href="{% url 'authentication:user-create' %}">Add User</a></li>
                    <li><a href="{% url 'authentication:bulk-assignment' %}">Assignments</a></li>
                    <li><a href="{% url 'authentication:audit-log-list' %}">Audit Logs</a></li>
                </ul>
            </li>

            <!-- Admin: Full Settings -->
            <li>
                <a href="javascript: void(0);" class="has-arrow waves-effect">
                    <i class="uil-setting"></i>
                    <span>Settings</span>
                </a>
                <ul class="sub-menu" aria-expanded="false">
                    <li><a href="{% url 'authentication:settings-dashboard' %}">Settings Dashboard</a></li>
                    <li><a href="{% url 'clubs:sync-management' %}">Sync Management</a></li>
                    <li><a href="{% url 'schools:wholesale-price-update-settings' %}">Price Update</a></li>
                    {% if user.id %}
                    <li><a href="{% url 'authentication:user-detail' user.id %}">My Profile</a></li>
                    {% endif %}
                </ul>
            </li>
            {% else %}
            <!-- Non-Admin: Only My Profile -->
            {% if user.id %}
            <li>
                <a href="{% url 'authentication:user-detail' user.id %}">
                    <i class="uil-user-circle"></i>
                    <span>My Profile</span>
                </a>
            </li>
            {% endif %}
            {% endif %}

        </ul>
    </div>
    <!-- Sidebar -->
</div>
```

### 4. `/Users/sas/Repos/SASKITUP/template/dashboard/global_dashboard.html`

**Create/update comprehensive dashboard template:**

```django
{% extends "base.html" %}
{% load static %}

{% block content %}
<!-- Page Title -->
<div class="row">
    <div class="col-12">
        <div class="page-title-box d-flex align-items-center justify-content-between">
            <h4 class="mb-0">
                {% if user.is_admin %}
                    Admin Dashboard
                {% elif user.is_account_manager %}
                    Account Manager Dashboard
                {% elif user.is_sales_rep %}
                    Sales Representative Dashboard
                {% elif user.is_customer %}
                    My Dashboard
                {% else %}
                    Dashboard
                {% endif %}
            </h4>
            {% if user.is_sales_rep or user.is_account_manager %}
            <div class="page-title-right">
                <a href="{% url 'quotations:select-institution' %}" class="btn btn-primary">
                    <i class="uil-plus me-1"></i> New Quotation
                </a>
            </div>
            {% endif %}
        </div>
    </div>
</div>

<!-- Welcome Message -->
<div class="row">
    <div class="col-12">
        <div class="alert alert-success" role="alert">
            <i class="uil-check me-2"></i>
            <strong>Welcome back, {{ user_full_name }}!</strong>
            You are logged in as {{ user_role }}.
        </div>
    </div>
</div>

<!-- ADMIN DASHBOARD -->
{% if user.is_admin %}
<div class="row">
    <!-- Total Schools -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-primary text-primary rounded">
                            <i class="uil-graduation-cap"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Total Schools</div>
                        <h4 class="mt-1 mb-0">{{ total_schools }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-success me-1">
                                <i class="mdi mdi-arrow-up-bold me-1"></i>TUS: {{ total_tus_schools }}
                            </span>
                            <span class="badge badge-soft-info">
                                Wholesale: {{ total_wholesale_schools }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Total Clubs -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-success text-success rounded">
                            <i class="uil-trophy"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Total Clubs</div>
                        <h4 class="mt-1 mb-0">{{ total_clubs }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-warning me-1">
                                LOTTO: {{ total_lotto_clubs }}
                            </span>
                            <span class="badge badge-soft-danger">
                                SAS: {{ total_sas_clubs }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Total Quotations -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-warning text-warning rounded">
                            <i class="uil-file-alt"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Quotations</div>
                        <h4 class="mt-1 mb-0">{{ total_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-warning me-1">
                                Pending: {{ pending_quotations }}
                            </span>
                            <span class="badge badge-soft-success">
                                Approved: {{ approved_quotations }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Total Users -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-info text-info rounded">
                            <i class="uil-users-alt"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Active Users</div>
                        <h4 class="mt-1 mb-0">{{ total_users }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-primary me-1">
                                Sales: {{ total_sales_reps }}
                            </span>
                            <span class="badge badge-soft-info">
                                Customers: {{ total_customers }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endif %}

<!-- ACCOUNT MANAGER DASHBOARD -->
{% if user.is_account_manager %}
<div class="row">
    <!-- Total Schools (ALL - Account Manager Access) -->
    <div class="col-xl-3 col-md-6">
        <div class="card bg-primary text-white">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-white bg-soft-light text-primary rounded">
                            <i class="uil-graduation-cap"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2 text-white-50">All Schools</div>
                        <h4 class="mt-1 mb-0 text-white">{{ total_schools }}</h4>
                        <p class="mb-0 mt-3 text-white-50">Full access</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Total Clubs (ALL) -->
    <div class="col-xl-3 col-md-6">
        <div class="card bg-success text-white">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-white bg-soft-light text-success rounded">
                            <i class="uil-trophy"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2 text-white-50">All Clubs</div>
                        <h4 class="mt-1 mb-0 text-white">{{ total_clubs }}</h4>
                        <p class="mb-0 mt-3 text-white-50">Full access</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- My Quotations -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-warning text-warning rounded">
                            <i class="uil-file-alt"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">My Quotations</div>
                        <h4 class="mt-1 mb-0">{{ my_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-warning">
                                Pending: {{ my_pending_quotations }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Quick Actions -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body text-center">
                <i class="uil-plus-circle font-size-24 text-primary mb-2"></i>
                <h5 class="mb-3">Quick Actions</h5>
                <a href="{% url 'quotations:select-institution' %}" class="btn btn-primary btn-sm">
                    Create Quotation
                </a>
            </div>
        </div>
    </div>
</div>
{% endif %}

<!-- SALES REP DASHBOARD -->
{% if user.is_sales_rep %}
<div class="row">
    <!-- My Schools -->
    <div class="col-xl-3 col-md-6">
        <div class="card bg-primary text-white">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-white bg-soft-light text-primary rounded">
                            <i class="uil-graduation-cap"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2 text-white-50">My Schools</div>
                        <h4 class="mt-1 mb-0 text-white">{{ my_schools }}</h4>
                        <p class="mb-0 mt-3 text-white-50">
                            <span class="badge badge-soft-light me-1">
                                TUS: {{ my_tus_schools }}
                            </span>
                            <span class="badge badge-soft-light">
                                Wholesale: {{ my_wholesale_schools }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- My Clubs -->
    <div class="col-xl-3 col-md-6">
        <div class="card bg-success text-white">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-white bg-soft-light text-success rounded">
                            <i class="uil-trophy"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2 text-white-50">My Clubs</div>
                        <h4 class="mt-1 mb-0 text-white">{{ my_clubs }}</h4>
                        <p class="mb-0 mt-3 text-white-50">
                            <span class="badge badge-soft-light me-1">
                                LOTTO: {{ my_lotto_clubs }}
                            </span>
                            <span class="badge badge-soft-light">
                                SAS: {{ my_sas_clubs }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- My Quotations -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-warning text-warning rounded">
                            <i class="uil-file-alt"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">My Quotations</div>
                        <h4 class="mt-1 mb-0">{{ my_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <span class="badge badge-soft-warning">
                                Pending: {{ my_pending_quotations }}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Quick Actions -->
    <div class="col-xl-3 col-md-6">
        <div class="card">
            <div class="card-body text-center">
                <i class="uil-plus-circle font-size-24 text-primary mb-2"></i>
                <h5 class="mb-3">Quick Actions</h5>
                <a href="{% url 'quotations:select-institution' %}" class="btn btn-primary btn-sm">
                    Create Quotation
                </a>
            </div>
        </div>
    </div>
</div>

<!-- My Assigned Clients -->
<div class="row">
    <div class="col-12">
        <div class="card">
            <div class="card-body">
                <h4 class="card-title mb-4">My Assigned Clients</h4>

                <!-- Schools Tab -->
                <ul class="nav nav-tabs nav-tabs-custom" role="tablist">
                    <li class="nav-item">
                        <a class="nav-link active" data-bs-toggle="tab" href="#schools-tab" role="tab">
                            <span class="d-none d-sm-block">Schools ({{ my_schools }})</span>
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" data-bs-toggle="tab" href="#clubs-tab" role="tab">
                            <span class="d-none d-sm-block">Clubs ({{ my_clubs }})</span>
                        </a>
                    </li>
                </ul>

                <div class="tab-content p-3 text-muted">
                    <!-- Schools List -->
                    <div class="tab-pane active" id="schools-tab" role="tabpanel">
                        {% if assigned_schools %}
                        <div class="table-responsive">
                            <table class="table table-centered table-nowrap mb-0">
                                <thead class="table-light">
                                    <tr>
                                        <th>School Name</th>
                                        <th>Type</th>
                                        <th>Territory</th>
                                        <th>Priority</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for assignment in assigned_schools %}
                                    <tr>
                                        <td>
                                            {% if assignment.tus_school %}
                                                {{ assignment.tus_school.name }}
                                            {% elif assignment.wholesale_school %}
                                                {{ assignment.wholesale_school.name }}
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if assignment.tus_school %}
                                                <span class="badge badge-soft-success">TUS School</span>
                                            {% else %}
                                                <span class="badge badge-soft-info">Wholesale</span>
                                            {% endif %}
                                        </td>
                                        <td>{{ assignment.territory_name|default:"Not specified" }}</td>
                                        <td>
                                            {% if assignment.priority_level == 'high' %}
                                                <span class="badge badge-soft-danger">High</span>
                                            {% elif assignment.priority_level == 'medium' %}
                                                <span class="badge badge-soft-warning">Medium</span>
                                            {% else %}
                                                <span class="badge badge-soft-success">Low</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if assignment.tus_school %}
                                                <a href="#" class="btn btn-sm btn-primary">View</a>
                                            {% elif assignment.wholesale_school %}
                                                <a href="#" class="btn btn-sm btn-primary">View</a>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% if my_schools > 10 %}
                        <div class="mt-3 text-center">
                            <a href="{% url 'schools:school_list' %}" class="btn btn-sm btn-link">
                                View All {{ my_schools }} Schools <i class="uil-arrow-right"></i>
                            </a>
                        </div>
                        {% endif %}
                        {% else %}
                        <div class="text-center py-4">
                            <i class="uil-folder-open font-size-48 text-muted mb-3"></i>
                            <p class="text-muted">No schools assigned yet</p>
                        </div>
                        {% endif %}
                    </div>

                    <!-- Clubs List -->
                    <div class="tab-pane" id="clubs-tab" role="tabpanel">
                        {% if assigned_clubs %}
                        <div class="table-responsive">
                            <table class="table table-centered table-nowrap mb-0">
                                <thead class="table-light">
                                    <tr>
                                        <th>Club Name</th>
                                        <th>Type</th>
                                        <th>Territory</th>
                                        <th>Priority</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for assignment in assigned_clubs %}
                                    <tr>
                                        <td>{{ assignment.club.name }}</td>
                                        <td>
                                            {% if 'lotto' in assignment.club_content_type.model %}
                                                <span class="badge badge-soft-warning">LOTTO Club</span>
                                            {% else %}
                                                <span class="badge badge-soft-danger">SAS Club</span>
                                            {% endif %}
                                        </td>
                                        <td>{{ assignment.territory_name|default:"Not specified" }}</td>
                                        <td>
                                            {% if assignment.priority_level == 'high' %}
                                                <span class="badge badge-soft-danger">High</span>
                                            {% elif assignment.priority_level == 'medium' %}
                                                <span class="badge badge-soft-warning">Medium</span>
                                            {% else %}
                                                <span class="badge badge-soft-success">Low</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <a href="#" class="btn btn-sm btn-primary">View</a>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        {% if my_clubs > 10 %}
                        <div class="mt-3 text-center">
                            <a href="{% url 'clubs:lotto-clubs' %}" class="btn btn-sm btn-link">
                                View All {{ my_clubs }} Clubs <i class="uil-arrow-right"></i>
                            </a>
                        </div>
                        {% endif %}
                        {% else %}
                        <div class="text-center py-4">
                            <i class="uil-folder-open font-size-48 text-muted mb-3"></i>
                            <p class="text-muted">No clubs assigned yet</p>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endif %}

<!-- CUSTOMER DASHBOARD -->
{% if user.is_customer %}
<div class="row">
    <!-- My Quotations -->
    <div class="col-xl-4 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-primary text-primary rounded">
                            <i class="uil-file-alt"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">My Quotations</div>
                        <h4 class="mt-1 mb-0">{{ my_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">
                            <a href="{% url 'quotations:my-quotations' %}">View all <i class="uil-arrow-right"></i></a>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Pending Approvals -->
    <div class="col-xl-4 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-warning text-warning rounded">
                            <i class="uil-clock"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Pending</div>
                        <h4 class="mt-1 mb-0">{{ my_pending_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">Awaiting approval</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Approved Quotations -->
    <div class="col-xl-4 col-md-6">
        <div class="card">
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="avatar-sm font-size-20 me-3">
                        <span class="avatar-title bg-soft-success text-success rounded">
                            <i class="uil-check-circle"></i>
                        </span>
                    </div>
                    <div class="flex-1">
                        <div class="font-size-16 mt-2">Approved</div>
                        <h4 class="mt-1 mb-0">{{ my_approved_quotations }}</h4>
                        <p class="mb-0 mt-3 text-muted">Ready to order</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endif %}

<!-- Recent Quotations (All Roles) -->
{% if recent_quotations %}
<div class="row">
    <div class="col-12">
        <div class="card">
            <div class="card-body">
                <h4 class="card-title mb-4">Recent Quotations</h4>
                <div class="table-responsive">
                    <table class="table table-centered table-nowrap mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>Quotation #</th>
                                <th>Institution</th>
                                <th>Created</th>
                                <th>Status</th>
                                <th>Total</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for quotation in recent_quotations %}
                            <tr>
                                <td>
                                    <a href="{% url 'quotations:quotation-detail' quotation.pk %}">
                                        {{ quotation.quotation_number }}
                                    </a>
                                </td>
                                <td>{{ quotation.institution_name }}</td>
                                <td>{{ quotation.created_at|date:"M d, Y" }}</td>
                                <td>
                                    {% if quotation.status == 'draft' %}
                                        <span class="badge badge-soft-secondary">Draft</span>
                                    {% elif quotation.status == 'pending' %}
                                        <span class="badge badge-soft-warning">Pending</span>
                                    {% elif quotation.status == 'approved' %}
                                        <span class="badge badge-soft-success">Approved</span>
                                    {% elif quotation.status == 'rejected' %}
                                        <span class="badge badge-soft-danger">Rejected</span>
                                    {% endif %}
                                </td>
                                <td>${{ quotation.total }}</td>
                                <td>
                                    <a href="{% url 'quotations:quotation-detail' quotation.pk %}" class="btn btn-sm btn-primary">
                                        View
                                    </a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                <div class="mt-3 text-center">
                    <a href="{% url 'quotations:my-quotations' %}" class="btn btn-sm btn-link">
                        View All Quotations <i class="uil-arrow-right"></i>
                    </a>
                </div>
            </div>
        </div>
    </div>
</div>
{% endif %}

{% endblock %}
```

---

## Testing Scenarios

### Test 1: Admin Login

**Steps:**
1. Login as admin (`srimalhs@gmail.com`)
2. Verify redirect to `/dashboard/`
3. Check navigation menu shows:
   - CLIENTS section with Schools and Clubs (all)
   - QUOTATIONS section
   - User Management submenu
   - Full Settings submenu
4. Check dashboard stats show all system data
5. Verify can access all sections

**Expected Result:** Admin sees full system access

### Test 2: Account Manager Login

**Steps:**
1. Login as account manager (`srimal@saskitup.com`)
2. Verify redirect to `/dashboard/`
3. Check navigation menu shows:
   - CLIENTS section with Schools and Clubs (all)
   - QUOTATIONS section with "New Quotation" and "My Quotations"
   - Only "My Profile" in settings
4. Check dashboard stats show ALL schools/clubs
5. Verify can create quotations

**Expected Result:** Account Manager sees all clients but own quotations

### Test 3: Sales Rep Login

**Steps:**
1. Login as sales rep (`srimal@sascreative.co.nz`)
2. Verify redirect to `/dashboard/`
3. Check navigation menu shows:
   - MY CLIENTS section with Schools and Clubs (assigned only)
   - QUOTATIONS section
   - Only "My Profile" in settings
4. Check dashboard stats show ONLY assigned schools/clubs
5. Check "My Assigned Clients" section shows correct assignments
6. Verify can create quotations for assigned clients only

**Expected Result:** Sales Rep sees only assigned clients

### Test 4: Customer Login

**Steps:**
1. Login as customer (`srimal@sas.co.nz`)
2. Verify redirect to `/dashboard/`
3. Check navigation menu shows:
   - Dashboard
   - MY ACCOUNT with "My Quotations" and "My Orders"
   - Only "My Profile" in settings
4. Check dashboard stats show personal data only
5. Verify can view own quotations

**Expected Result:** Customer sees only own data

### Test 5: Quotation Workflow

**Steps:**
1. Login as sales rep
2. Click "New Quotation" from dashboard or navigation
3. Select institution (should show only assigned schools/clubs)
4. Add products to cart
5. Save quotation
6. View in "My Quotations"
7. Verify quotation appears on dashboard

**Expected Result:** Quotation workflow works smoothly

### Test 6: Settings Access

**Steps:**
1. Login as sales rep
2. Navigate to settings
3. Verify only "My Profile" is accessible
4. Try to access `/auth/users/` directly
5. Should be redirected to access denied

**Expected Result:** Non-admins cannot access admin settings

---

## SQL Testing Queries

### Check User Roles

```sql
-- View all users and their roles
SELECT
    id,
    username,
    email,
    user_type,
    is_active,
    is_superuser
FROM authentication_user
ORDER BY user_type, username;
```

### Check Sales Rep Assignments

```sql
-- Check school assignments for a sales rep
SELECT
    sr.email AS sales_rep_email,
    sr.user_type,
    COALESCE(ts.name, ws.name) AS school_name,
    CASE
        WHEN a.tus_school_id IS NOT NULL THEN 'TUS School'
        WHEN a.wholesale_school_id IS NOT NULL THEN 'Wholesale School'
    END AS school_type,
    a.territory_name,
    a.priority_level,
    a.is_active
FROM sales_rep_school_assignments a
JOIN authentication_user sr ON a.sales_rep_id = sr.id
LEFT JOIN clubs_tusschool ts ON a.tus_school_id = ts.id
LEFT JOIN schools_wholesaleschool ws ON a.wholesale_school_id = ws.id
WHERE a.is_active = TRUE
ORDER BY sr.email, school_name;
```

### Check Club Assignments

```sql
-- Check club assignments for a sales rep
SELECT
    sr.email AS sales_rep_email,
    sr.user_type,
    COALESCE(lc.name, sc.name) AS club_name,
    CASE
        WHEN ct.model = 'lottoclub' THEN 'LOTTO Club'
        WHEN ct.model = 'sasclub' THEN 'SAS Club'
    END AS club_type,
    a.territory_name,
    a.priority_level,
    a.is_active
FROM sales_rep_club_assignments a
JOIN authentication_user sr ON a.sales_rep_id = sr.id
JOIN django_content_type ct ON a.club_content_type_id = ct.id
LEFT JOIN clubs_lottoclub lc ON (ct.model = 'lottoclub' AND a.club_object_id = lc.id)
LEFT JOIN clubs_sasclub sc ON (ct.model = 'sasclub' AND a.club_object_id = sc.id)
WHERE a.is_active = TRUE
ORDER BY sr.email, club_name;
```

### Check Quotations

```sql
-- View quotations with user and institution info
SELECT
    q.quotation_number,
    u.email AS created_by,
    u.user_type,
    ct.model AS institution_type,
    q.status,
    q.total,
    q.created_at
FROM quotations q
JOIN authentication_user u ON q.created_by_id = u.id
JOIN django_content_type ct ON q.institution_content_type_id = ct.id
ORDER BY q.created_at DESC
LIMIT 20;
```

### Create Test Assignment (SQL)

```sql
-- Assign a school to a sales rep for testing
-- Replace IDs with actual values from your database

INSERT INTO sales_rep_school_assignments (
    id,
    sales_rep_id,
    tus_school_id,
    is_active,
    assigned_date,
    territory_name,
    priority_level,
    created_at,
    updated_at
)
VALUES (
    UUID(),  -- Or use a specific UUID
    (SELECT id FROM authentication_user WHERE email = 'srimal@sascreative.co.nz' LIMIT 1),
    (SELECT id FROM clubs_tusschool WHERE is_active = TRUE LIMIT 1),
    TRUE,
    NOW(),
    'Test Territory',
    'medium',
    NOW(),
    NOW()
);
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Run migrations if any new models added
- [ ] Test all user roles in development
- [ ] Verify quotations workflow works
- [ ] Test navigation menu for each role
- [ ] Check dashboard stats accuracy

### Deployment Steps
1. [ ] Backup database
2. [ ] Deploy code changes
3. [ ] Run `python manage.py migrate`
4. [ ] Run `python manage.py collectstatic --noinput`
5. [ ] Restart web server

### Post-Deployment
- [ ] Test login for each role in production
- [ ] Verify dashboard redirect works
- [ ] Check navigation menus render correctly
- [ ] Test quotation creation
- [ ] Monitor error logs

---

## Rollback Plan

If issues are encountered:

1. **Revert authentication/views.py:**
   ```python
   # Restore original redirect logic
   def get_redirect_url(self, user):
       if user.user_type in ['admin'] or user.is_superuser:
           return reverse_lazy('global-dashboard')
       elif user.user_type in ['sales_rep', 'account_manager', 'customer']:
           return reverse_lazy('authentication:profile')
       return reverse_lazy('global-dashboard')
   ```

2. **Revert template/base.html to Git version**
3. **Clear Django cache:** `python manage.py clear_cache` (if caching enabled)
4. **Restart web server**

---

## Future Enhancements

1. **Dashboard Widgets:**
   - Recent activity timeline
   - Quick stats charts
   - Upcoming quotation expiries

2. **Enhanced Filtering:**
   - Filter schools/clubs by region
   - Sort by priority
   - Search functionality

3. **Notifications:**
   - Quotation approval alerts
   - New assignment notifications
   - Expiring quotations warnings

4. **Mobile Responsive:**
   - Optimize dashboard for mobile
   - Touch-friendly navigation
   - Mobile quotation workflow

5. **Performance:**
   - Cache dashboard stats
   - Optimize queries with select_related()
   - Add pagination for large datasets

---

**Document Version:** 1.0
**Last Updated:** 2025-10-07
**Author:** Claude Code
**Status:** Implementation Ready
