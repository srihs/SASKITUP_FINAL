from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from functools import wraps
from .models import AuditLog


class RoleRequiredMixin(UserPassesTestMixin):
    """
    Mixin to require specific user roles for class-based views
    """
    required_roles = []  # List of roles required to access this view
    login_url = '/auth/login/'
    permission_denied_message = "You don't have permission to access this page."

    def test_func(self):
        """Test if user has required role"""
        if not self.request.user.is_authenticated:
            return False

        if not self.required_roles:
            return True  # No specific roles required

        user = self.request.user

        # Admin users can access everything
        if user.is_admin:
            return True

        # Check if user has any of the required roles
        return user.user_type in self.required_roles

    def handle_no_permission(self):
        """Log unauthorized access attempts"""
        if self.request.user.is_authenticated:
            AuditLog.log_action(
                user=self.request.user,
                action_type='permission_denied',
                description=f'Attempted to access {self.request.path} without required role',
                request=self.request,
                required_roles=self.required_roles,
                user_role=self.request.user.user_type if self.request.user.is_authenticated else 'anonymous'
            )

        return super().handle_no_permission()


class AdminRequiredMixin(RoleRequiredMixin):
    """Mixin to require admin role"""
    required_roles = ['admin']


class SalesRepRequiredMixin(RoleRequiredMixin):
    """Mixin to require sales rep role (or admin)"""
    required_roles = ['admin', 'sales_rep']


class AccountManagerRequiredMixin(RoleRequiredMixin):
    """Mixin to require account manager role (or admin)"""
    required_roles = ['admin', 'account_manager']


class SalesRepOrAccountManagerMixin(RoleRequiredMixin):
    """Mixin to require sales rep or account manager role (or admin)"""
    required_roles = ['admin', 'sales_rep', 'account_manager']


class CustomerRequiredMixin(RoleRequiredMixin):
    """Mixin to require customer role (or admin)"""
    required_roles = ['admin', 'customer']


class SchoolAccessMixin:
    """
    Mixin to check if user can access a specific school
    Requires the view to have a school object or school_id
    """

    def dispatch(self, request, *args, **kwargs):
        """Check school access before processing request"""
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        # Get school object
        school = self.get_school_object()

        if not request.user.can_access_school(school):
            AuditLog.log_action(
                user=request.user,
                action_type='permission_denied',
                description=f'Attempted to access school {school} without permission',
                request=request,
                school_id=school.id if hasattr(school, 'id') else str(school),
                school_name=getattr(school, 'org_name', getattr(school, 'name', str(school)))
            )
            raise PermissionDenied("You don't have permission to access this school")

        return super().dispatch(request, *args, **kwargs)

    def get_school_object(self):
        """
        Get the school object for access checking
        Override this method in your view to specify how to get the school
        """
        # Try to get school from URL parameters
        if 'school_id' in self.kwargs:
            from schools.models import School
            return get_object_or_404(School, school_id=self.kwargs['school_id'])
        elif 'pk' in self.kwargs:
            from schools.models import School
            return get_object_or_404(School, pk=self.kwargs['pk'])
        elif hasattr(self, 'object') and self.object:
            return self.object
        else:
            raise NotImplementedError("get_school_object must be implemented")


class ClubAccessMixin:
    """
    Mixin to check if user can access a specific club
    Requires the view to have a club object or club_id
    """

    def dispatch(self, request, *args, **kwargs):
        """Check club access before processing request"""
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        # Get club object
        club = self.get_club_object()

        if not request.user.can_access_club(club):
            AuditLog.log_action(
                user=request.user,
                action_type='permission_denied',
                description=f'Attempted to access club {club} without permission',
                request=request,
                club_id=club.id if hasattr(club, 'id') else str(club),
                club_name=getattr(club, 'name', str(club))
            )
            raise PermissionDenied("You don't have permission to access this club")

        return super().dispatch(request, *args, **kwargs)

    def get_club_object(self):
        """
        Get the club object for access checking
        Override this method in your view to specify how to get the club

        TODO: Update to use GenericForeignKey or specific LottoClub/SASClub models
        The unified Club model has been removed. This method needs to be updated
        to handle LottoClub (from clubs.models_lotto) and SASClub (from clubs.models_sas)
        or use a GenericForeignKey approach.
        """
        # DISABLED - unified Club model removed
        # Try to get club from URL parameters
        # if 'club_id' in self.kwargs:
        #     from clubs.models import Club
        #     return get_object_or_404(Club, id=self.kwargs['club_id'])
        # elif 'slug' in self.kwargs:
        #     from clubs.models import Club
        #     return get_object_or_404(Club, slug=self.kwargs['slug'])
        # elif 'pk' in self.kwargs:
        #     from clubs.models import Club
        #     return get_object_or_404(Club, pk=self.kwargs['pk'])
        # elif hasattr(self, 'object') and self.object:
        #     return self.object
        # else:
        raise NotImplementedError("get_club_object must be updated to use LottoClub/SASClub models")


# Decorator functions for function-based views

def admin_required(view_func):
    """Decorator to require admin role for function-based views"""
    def check_admin(user):
        return user.is_authenticated and user.is_admin

    actual_decorator = user_passes_test(check_admin, login_url='/auth/login/')
    return actual_decorator(view_func)


def sales_rep_required(view_func):
    """Decorator to require sales rep role (or admin) for function-based views"""
    def check_sales_rep(user):
        return user.is_authenticated and (user.is_admin or user.is_sales_rep)

    actual_decorator = user_passes_test(check_sales_rep, login_url='/auth/login/')
    return actual_decorator(view_func)


def account_manager_required(view_func):
    """Decorator to require account manager role (or admin) for function-based views"""
    def check_account_manager(user):
        return user.is_authenticated and (user.is_admin or user.is_account_manager)

    actual_decorator = user_passes_test(check_account_manager, login_url='/auth/login/')
    return actual_decorator(view_func)


def sales_rep_or_account_manager_required(view_func):
    """Decorator to require sales rep or account manager role (or admin) for function-based views"""
    def check_sales_rep_or_account_manager(user):
        return user.is_authenticated and (user.is_admin or user.is_sales_rep or user.is_account_manager)

    actual_decorator = user_passes_test(check_sales_rep_or_account_manager, login_url='/auth/login/')
    return actual_decorator(view_func)


def customer_required(view_func):
    """Decorator to require customer role (or admin) for function-based views"""
    def check_customer(user):
        return user.is_authenticated and (user.is_admin or user.is_customer)

    actual_decorator = user_passes_test(check_customer, login_url='/auth/login/')
    return actual_decorator(view_func)


def school_access_required(view_func):
    """
    Decorator to check school access for function-based views
    The view function should accept a school parameter or have school_id in kwargs
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        # Try to get school from different sources
        school = None

        # Check if school_id is in URL kwargs
        if 'school_id' in kwargs:
            from schools.models import School
            school = get_object_or_404(School, school_id=kwargs['school_id'])
        elif 'pk' in kwargs:
            from schools.models import School
            school = get_object_or_404(School, pk=kwargs['pk'])

        if school and not request.user.can_access_school(school):
            AuditLog.log_action(
                user=request.user,
                action_type='permission_denied',
                description=f'Attempted to access school {school} without permission',
                request=request,
                school_id=school.id,
                school_name=getattr(school, 'org_name', getattr(school, 'name', str(school)))
            )
            raise PermissionDenied("You don't have permission to access this school")

        return view_func(request, *args, **kwargs)

    return wrapper


def club_access_required(view_func):
    """
    Decorator to check club access for function-based views
    The view function should accept a club parameter or have club_id in kwargs

    TODO: Update to use GenericForeignKey or specific LottoClub/SASClub models
    The unified Club model has been removed. This decorator needs to be updated
    to handle LottoClub (from clubs.models_lotto) and SASClub (from clubs.models_sas)
    or use a GenericForeignKey approach.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")

        # DISABLED - unified Club model removed
        # Try to get club from different sources
        # club = None
        #
        # # Check if club_id or slug is in URL kwargs
        # if 'club_id' in kwargs:
        #     from clubs.models import Club
        #     club = get_object_or_404(Club, id=kwargs['club_id'])
        # elif 'slug' in kwargs:
        #     from clubs.models import Club
        #     club = get_object_or_404(Club, slug=kwargs['slug'])
        # elif 'pk' in kwargs:
        #     from clubs.models import Club
        #     club = get_object_or_404(Club, pk=kwargs['pk'])
        #
        # if club and not request.user.can_access_club(club):
        #     AuditLog.log_action(
        #         user=request.user,
        #         action_type='permission_denied',
        #         description=f'Attempted to access club {club} without permission',
        #         request=request,
        #         club_id=club.id,
        #         club_name=club.name
        #     )
        #     raise PermissionDenied("You don't have permission to access this club")

        # For now, raise NotImplementedError until updated to use new club models
        raise NotImplementedError("club_access_required decorator must be updated to use LottoClub/SASClub models")

    return wrapper


# Utility functions for checking permissions

def can_user_manage_assignments(user):
    """Check if user can manage sales rep assignments"""
    return user.is_authenticated and user.is_admin


def can_user_create_users(user):
    """Check if user can create new users"""
    return user.is_authenticated and user.is_admin


def can_user_view_audit_logs(user):
    """Check if user can view audit logs"""
    return user.is_authenticated and user.is_admin


def can_user_access_admin_panel(user):
    """Check if user can access admin panel"""
    return user.is_authenticated and user.can_access_admin_panel


def can_user_manage_customers(user):
    """Check if user can manage customers"""
    return user.is_authenticated and user.is_admin


def can_customer_access_data(user, data_owner=None):
    """Check if customer can access specific data"""
    if not user.is_authenticated:
        return False

    # Admin can access all customer data
    if user.is_admin:
        return True

    # Customer can only access their own data
    if user.is_customer:
        if data_owner:
            return user == data_owner
        return True  # General customer data access

    return False


def filter_schools_for_user(user, queryset):
    """
    Filter schools queryset based on user permissions

    Args:
        user: User instance
        queryset: Schools queryset to filter

    Returns:
        Filtered queryset based on user's assignments
    """
    if user.is_admin:
        return queryset

    # Account managers have access to all schools
    if user.is_account_manager:
        return queryset

    if user.is_sales_rep:
        # Get assigned school IDs
        school_assignments = user.school_assignments.filter(is_active=True)

        regular_school_ids = school_assignments.filter(
            school__isnull=False
        ).values_list('school_id', flat=True)

        wholesale_school_ids = school_assignments.filter(
            wholesale_school__isnull=False
        ).values_list('wholesale_school_id', flat=True)

        # Filter queryset based on school type
        from schools.models import School, WholesaleSchool

        if hasattr(queryset.model, '_meta') and queryset.model == School:
            return queryset.filter(id__in=regular_school_ids)
        elif hasattr(queryset.model, '_meta') and queryset.model == WholesaleSchool:
            return queryset.filter(id__in=wholesale_school_ids)

    return queryset.none()


def filter_clubs_for_user(user, queryset):
    """
    Filter clubs queryset based on user permissions

    Args:
        user: User instance
        queryset: Clubs queryset to filter

    Returns:
        Filtered queryset based on user's assignments

    TODO: Update to handle LottoClub and SASClub models with GenericForeignKey
    The unified Club model has been removed. This function needs to be updated
    to handle different club types (LottoClub, SASClub) using GenericForeignKey
    or polymorphic queries.
    """
    if user.is_admin:
        return queryset

    # Account managers have access to all clubs
    if user.is_account_manager:
        return queryset

    if user.is_sales_rep:
        # Get assigned club IDs
        club_assignments = user.club_assignments.filter(is_active=True)
        club_ids = club_assignments.values_list('club_id', flat=True)
        return queryset.filter(id__in=club_ids)

    return queryset.none()


class AssignmentPermissionMixin:
    """
    Mixin for views that deal with assignments
    Ensures users can only manage assignments they have permission for
    """

    def get_queryset(self):
        """Filter assignments based on user permissions"""
        queryset = super().get_queryset()

        # Admin users can see all assignments
        if self.request.user.is_admin:
            return queryset

        # Sales reps and account managers can only see their own assignments
        if self.request.user.is_sales_rep or self.request.user.is_account_manager:
            return queryset.filter(sales_rep=self.request.user)

        return queryset.none()

    def form_valid(self, form):
        """Set created_by field for new assignments"""
        if hasattr(form.instance, 'created_by') and not form.instance.created_by:
            form.instance.created_by = self.request.user
        return super().form_valid(form)