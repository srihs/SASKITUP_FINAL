from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView
)
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .forms import (
    UserForm, UserSearchForm, UserProfileForm,
    PasswordChangeForm, BulkUserActionForm
)
from django.utils import timezone

from .models import (
    User, SalesRepSchoolAssignment, SalesRepClubAssignment,
    UserSession, AuditLog
)
from .permissions import (
    AdminRequiredMixin, SalesRepRequiredMixin, CustomerRequiredMixin, AssignmentPermissionMixin,
    can_user_manage_assignments, can_user_create_users, can_customer_access_data
)
from clubs.models import Club
from schools.models import School, WholesaleSchool


class LoginView(FormView):
    """Custom login view with audit logging"""
    template_name = 'authentication/login.html'
    form_class = AuthenticationForm
    success_url = reverse_lazy('global-dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
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

        # Redirect to next URL if provided
        next_url = self.request.GET.get('next')
        if next_url:
            return redirect(next_url)

        # Redirect all users to global dashboard
        return redirect('global-dashboard')

    def form_invalid(self, form):
        # Log failed login attempt
        username = form.data.get('username', 'Unknown')
        AuditLog.log_action(
            user=None,
            action_type='login',
            description=f'Failed login attempt for username: {username}',
            request=self.request,
            username=username
        )

        messages.error(self.request, 'Invalid username or password.')
        return super().form_invalid(form)


@login_required
def logout_view(request):
    """Custom logout view with audit logging"""
    user = request.user

    # Log logout
    AuditLog.log_action(
        user=user,
        action_type='logout',
        description=f'User {user.username} logged out',
        request=request
    )

    # Deactivate user session
    session_key = request.session.session_key
    if session_key:
        UserSession.objects.filter(
            session_key=session_key,
            user=user
        ).update(is_active=False)

    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('authentication:login')


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """Dashboard for admin users"""
    template_name = 'authentication/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Statistics
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['sales_reps'] = User.objects.filter(user_type='sales_rep').count()
        context['customers'] = User.objects.filter(user_type='customer').count()
        context['active_customers'] = User.objects.filter(user_type='customer', is_active=True).count()
        context['total_school_assignments'] = SalesRepSchoolAssignment.objects.filter(is_active=True).count()
        context['total_club_assignments'] = SalesRepClubAssignment.objects.filter(is_active=True).count()

        # Recent users
        context['recent_users'] = User.objects.order_by('-date_joined')[:5]

        # Recent assignments
        context['recent_school_assignments'] = SalesRepSchoolAssignment.objects.select_related(
            'sales_rep', 'school', 'wholesale_school'
        ).order_by('-assigned_date')[:5]

        context['recent_club_assignments'] = SalesRepClubAssignment.objects.select_related(
            'sales_rep', 'club'
        ).order_by('-assigned_date')[:5]

        # Combine assignments for template
        recent_assignments = []
        for assignment in context['recent_school_assignments']:
            recent_assignments.append(assignment)
        for assignment in context['recent_club_assignments']:
            recent_assignments.append(assignment)

        # Sort by assigned_date and limit to 5
        context['recent_assignments'] = sorted(recent_assignments, key=lambda x: x.assigned_date, reverse=True)[:5]

        # Recent audit logs
        context['recent_audit_logs'] = AuditLog.objects.select_related('user').order_by('-timestamp')[:10]

        return context


class SalesRepDashboardView(SalesRepRequiredMixin, TemplateView):
    """Dashboard for sales representatives"""
    template_name = 'authentication/sales_rep_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # User's assignments
        context['school_assignments'] = user.school_assignments.filter(
            is_active=True
        ).select_related('school', 'wholesale_school')

        context['club_assignments'] = user.club_assignments.filter(
            is_active=True
        ).select_related('club')

        # Statistics
        context['total_schools'] = context['school_assignments'].count()
        context['total_clubs'] = context['club_assignments'].count()

        # Recent activity
        context['recent_activities'] = AuditLog.objects.filter(
            user=user
        ).order_by('-timestamp')[:10]

        return context


class UserListView(AdminRequiredMixin, ListView):
    """List all users"""
    model = User
    template_name = 'authentication/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.prefetch_related(
            'school_assignments', 'club_assignments'
        ).order_by('-date_joined')

        # Filter by user type
        user_type = self.request.GET.get('user_type')
        if user_type:
            queryset = queryset.filter(user_type=user_type)

        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(employee_id__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_types'] = User.USER_TYPE_CHOICES
        context['current_filters'] = {
            'user_type': self.request.GET.get('user_type', ''),
            'is_active': self.request.GET.get('is_active', ''),
            'search': self.request.GET.get('search', ''),
        }
        return context


# UserForm is now imported from forms.py


class UserCreateView(AdminRequiredMixin, CreateView):
    """Create new user"""
    model = User
    form_class = UserForm
    template_name = 'authentication/user_form.html'
    success_url = reverse_lazy('authentication:user-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['is_edit'] = False
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log user creation
        AuditLog.log_action(
            user=self.request.user,
            action_type='user_created',
            description=f'Created user: {self.object.username} ({self.object.get_user_type_display()})',
            request=self.request,
            created_user_id=self.object.id,
            created_username=self.object.username
        )

        messages.success(self.request, f'User {self.object.username} created successfully.')
        return response


class UserDetailView(AdminRequiredMixin, DetailView):
    """View user details"""
    model = User
    template_name = 'authentication/user_detail.html'
    context_object_name = 'user_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object

        # Get assignments
        context['school_assignments'] = user.school_assignments.select_related(
            'school', 'wholesale_school'
        ).order_by('-assigned_date')

        context['club_assignments'] = user.club_assignments.select_related(
            'club'
        ).order_by('-assigned_date')

        # Get recent sessions
        context['recent_sessions'] = user.user_sessions.order_by('-login_time')[:5]

        # Get recent audit logs
        context['recent_audit_logs'] = user.audit_logs.order_by('-timestamp')[:10]

        return context


class UserUpdateView(AdminRequiredMixin, UpdateView):
    """Update user"""
    model = User
    form_class = UserForm
    template_name = 'authentication/user_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['is_edit'] = True
        return kwargs

    def get_success_url(self):
        return reverse('authentication:user-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log user update
        AuditLog.log_action(
            user=self.request.user,
            action_type='user_updated',
            description=f'Updated user: {self.object.username}',
            request=self.request,
            updated_user_id=self.object.id,
            updated_username=self.object.username
        )

        messages.success(self.request, f'User {self.object.username} updated successfully.')
        return response


class AccessDeniedView(TemplateView):
    """Access denied page"""
    template_name = 'authentication/access_denied.html'


# AJAX Views

@login_required
def user_search_ajax(request):
    """AJAX search for users"""
    if not can_user_manage_assignments(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query),
        is_active=True
    )[:10]

    results = []
    for user in users:
        results.append({
            'id': user.id,
            'text': f"{user.get_full_name() or user.username} ({user.get_user_type_display()})",
            'username': user.username,
            'user_type': user.user_type,
        })

    return JsonResponse({'results': results})


# =====================================
# CUSTOMER VIEWS
# =====================================

class CustomerDashboardView(CustomerRequiredMixin, TemplateView):
    """Dashboard for customer users"""
    template_name = 'authentication/customer_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Order statistics (placeholder - will be implemented when order system is added)
        context['order_stats'] = {
            'total_orders': 0,
            'total_spent': 0,
            'pending_orders': 0,
            'recent_order': None,
        }

        # Notifications (placeholder)
        context['notifications'] = []

        # Recent activities for this customer
        context['recent_activities'] = AuditLog.objects.filter(
            user=user
        ).order_by('-timestamp')[:5]

        # Last activity date
        context['last_activity_date'] = user.last_login or user.date_joined

        return context


class CustomerProfileView(CustomerRequiredMixin, UpdateView):
    """Customer profile management view"""
    model = User
    template_name = 'authentication/customer_profile.html'
    fields = ['first_name', 'last_name', 'email', 'phone']

    def get_object(self):
        """Ensure customers can only edit their own profile"""
        return self.request.user

    def get_success_url(self):
        return reverse('authentication:customer-profile')

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log profile update
        AuditLog.log_action(
            user=self.request.user,
            action_type='user_updated',
            description=f'Customer {self.request.user.username} updated their profile',
            request=self.request,
            updated_fields=list(form.changed_data)
        )

        messages.success(self.request, 'Your profile has been updated successfully.')
        return response


class CustomerOrdersView(CustomerRequiredMixin, TemplateView):
    """Customer orders view - placeholder for future order system"""
    template_name = 'authentication/customer_orders.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Placeholder for orders - will be implemented when order system is added
        context['orders'] = []
        return context


class CustomerSupportView(CustomerRequiredMixin, TemplateView):
    """Customer support view"""
    template_name = 'authentication/customer_support.html'


class CustomerNotificationsView(CustomerRequiredMixin, TemplateView):
    """Customer notifications view"""
    template_name = 'authentication/customer_notifications.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Placeholder for notifications - will be implemented when notification system is added
        context['notifications'] = []
        return context


class CustomerActivityView(CustomerRequiredMixin, ListView):
    """Customer activity history view"""
    model = AuditLog
    template_name = 'authentication/customer_activity.html'
    context_object_name = 'activities'
    paginate_by = 20

    def get_queryset(self):
        """Only show activities for the current customer"""
        return AuditLog.objects.filter(
            user=self.request.user
        ).order_by('-timestamp')


class CustomerFAQView(TemplateView):
    """Customer FAQ view - publicly accessible"""
    template_name = 'authentication/customer_faq.html'


# =====================================
# CUSTOMER MANAGEMENT VIEWS (Admin Only)
# =====================================

class CustomerManagementView(AdminRequiredMixin, ListView):
    """Admin view to manage customers"""
    model = User
    template_name = 'authentication/customer_management.html'
    context_object_name = 'customers'
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.filter(user_type='customer').order_by('-date_joined')

        # Search functionality
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        # Status filter
        is_active = self.request.GET.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_customers'] = User.objects.filter(user_type='customer').count()
        context['active_customers'] = User.objects.filter(user_type='customer', is_active=True).count()
        context['current_filters'] = {
            'search': self.request.GET.get('search', ''),
            'is_active': self.request.GET.get('is_active', ''),
        }
        return context


class CustomerCreateView(AdminRequiredMixin, CreateView):
    """Admin view to create new customers"""
    model = User
    template_name = 'authentication/customer_form.html'
    fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'is_active']
    success_url = reverse_lazy('authentication:customer-management')

    def form_valid(self, form):
        # Set user type to customer
        form.instance.user_type = 'customer'

        # Set a temporary password (customer should change it)
        form.instance.set_password('TempPassword123!')

        response = super().form_valid(form)

        # Log customer creation
        AuditLog.log_action(
            user=self.request.user,
            action_type='user_created',
            description=f'Created customer: {self.object.username}',
            request=self.request,
            created_user_id=self.object.id,
            created_username=self.object.username
        )

        messages.success(
            self.request,
            f'Customer {self.object.username} created successfully. '
            f'Temporary password: TempPassword123! (Please share securely with customer)'
        )
        return response


class CustomerDetailView(AdminRequiredMixin, DetailView):
    """Admin view to see customer details"""
    model = User
    template_name = 'authentication/customer_detail.html'
    context_object_name = 'customer'

    def get_queryset(self):
        return User.objects.filter(user_type='customer')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object

        # Get customer's recent sessions
        context['recent_sessions'] = customer.user_sessions.order_by('-login_time')[:5]

        # Get customer's recent audit logs
        context['recent_audit_logs'] = customer.audit_logs.order_by('-timestamp')[:10]

        # Get customer's order statistics (placeholder)
        context['order_stats'] = {
            'total_orders': 0,
            'total_spent': 0,
            'last_order_date': None,
        }

        return context


class CustomerUpdateView(AdminRequiredMixin, UpdateView):
    """Admin view to update customer details"""
    model = User
    template_name = 'authentication/customer_form.html'
    fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'is_active']

    def get_queryset(self):
        return User.objects.filter(user_type='customer')

    def get_success_url(self):
        return reverse('authentication:customer-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log customer update
        AuditLog.log_action(
            user=self.request.user,
            action_type='user_updated',
            description=f'Updated customer: {self.object.username}',
            request=self.request,
            updated_user_id=self.object.id,
            updated_username=self.object.username,
            updated_fields=list(form.changed_data)
        )

        messages.success(self.request, f'Customer {self.object.username} updated successfully.')
        return response


# New Enhanced Views for User Management UI


class UserManagementDashboardView(AdminRequiredMixin, TemplateView):
    """Enhanced User Management Dashboard"""
    template_name = 'authentication/user_management_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # User statistics
        context['user_stats'] = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'active_sales_reps': User.objects.filter(user_type='sales_rep', is_active_sales_rep=True).count(),
            'total_sales_reps': User.objects.filter(user_type='sales_rep').count(),
            'admin_count': User.objects.filter(user_type='admin').count(),
            'sales_rep_count': User.objects.filter(user_type='sales_rep').count(),
            'customer_count': User.objects.filter(user_type='customer').count(),
            'new_users_this_month': User.objects.filter(created_at__month=timezone.now().month).count(),
            'online_users': UserSession.objects.filter(is_active=True).count(),
        }

        # Calculate percentages
        total = context['user_stats']['total_users']
        if total > 0:
            context['user_stats']['admin_percentage'] = round((context['user_stats']['admin_count'] / total) * 100, 1)
            context['user_stats']['sales_rep_percentage'] = round((context['user_stats']['sales_rep_count'] / total) * 100, 1)
            context['user_stats']['customer_percentage'] = round((context['user_stats']['customer_count'] / total) * 100, 1)
        else:
            context['user_stats']['admin_percentage'] = 0
            context['user_stats']['sales_rep_percentage'] = 0
            context['user_stats']['customer_percentage'] = 0

        # Assignment statistics
        context['assignment_stats'] = {
            'total_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count() +
                               SalesRepClubAssignment.objects.filter(is_active=True).count(),
            'school_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count(),
            'club_assignments': SalesRepClubAssignment.objects.filter(is_active=True).count(),
        }

        # Recent users (last 5)
        context['recent_users'] = User.objects.order_by('-created_at')[:5]

        # Recent activity
        context['recent_activity'] = AuditLog.objects.select_related('user').order_by('-timestamp')[:10]

        # System health metrics (placeholder)
        context['system_health'] = {
            'uptime_percentage': 99.9,
            'avg_response_time': 145,
            'failed_logins_today': AuditLog.objects.filter(
                action_type='login',
                timestamp__date=timezone.now().date()
            ).count(),
            'active_sessions': UserSession.objects.filter(is_active=True).count(),
        }

        return context


class SettingsDashboardView(AdminRequiredMixin, TemplateView):
    """Settings Dashboard with system overview"""
    template_name = 'authentication/settings_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # System status
        context['system_status'] = {
            'last_check': timezone.now(),
            'uptime': '99.9%',
            'avg_response_time': '<200ms',
        }

        # User metrics for settings cards
        context['user_metrics'] = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
        }

        # Configuration metrics
        context['config_metrics'] = {
            'total_settings': 25,  # Placeholder
            'modified_today': 3,   # Placeholder
        }

        # Security metrics
        context['security_metrics'] = {
            'failed_logins': AuditLog.objects.filter(
                action_type='login',
                timestamp__date=timezone.now().date()
            ).count(),
            'active_sessions': UserSession.objects.filter(is_active=True).count(),
        }

        # Sync metrics
        context['sync_metrics'] = {
            'last_sync': '2h ago',  # Placeholder
            'sync_status': 'OK',    # Placeholder
        }

        # Price metrics
        context['price_metrics'] = {
            'last_update': '1d ago',  # Placeholder
            'pending_updates': 0,     # Placeholder
        }

        # Assignment metrics
        context['assignment_metrics'] = {
            'total_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count() +
                               SalesRepClubAssignment.objects.filter(is_active=True).count(),
            'unassigned': 0,  # Placeholder - would need logic to count unassigned schools/clubs
        }

        # Audit metrics
        context['audit_metrics'] = {
            'today_events': AuditLog.objects.filter(timestamp__date=timezone.now().date()).count(),
            'total_size': '2.1MB',  # Placeholder
        }

        # Backup metrics
        context['backup_metrics'] = {
            'last_backup': '12h ago',  # Placeholder
            'backup_size': '150MB',    # Placeholder
        }

        # System alerts (placeholder)
        context['system_alerts'] = []

        return context


# AJAX view for user search
@login_required
def user_search_ajax(request):
    """AJAX endpoint for user search"""
    if not request.user.is_admin:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '')
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query)
    )[:10]

    results = []
    for user in users:
        results.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'email': user.email,
            'user_type': user.get_user_type_display(),
        })

    return JsonResponse({'results': results})


@login_required
def bulk_user_action(request):
    """AJAX endpoint for bulk user actions"""
    if not request.user.is_admin:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    form = BulkUserActionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)

    action = form.cleaned_data['action']
    user_ids = form.cleaned_data['user_ids']
    users = User.objects.filter(id__in=user_ids)

    if not users.exists():
        return JsonResponse({'error': 'No users found'}, status=404)

    try:
        if action == 'activate':
            count = users.update(is_active=True)
            AuditLog.log_action(
                user=request.user,
                action_type='user_updated',
                description=f'Bulk activated {count} users',
                request=request,
                affected_user_count=count
            )
            return JsonResponse({'success': True, 'message': f'{count} users activated'})

        elif action == 'deactivate':
            count = users.update(is_active=False)
            AuditLog.log_action(
                user=request.user,
                action_type='user_updated',
                description=f'Bulk deactivated {count} users',
                request=request,
                affected_user_count=count
            )
            return JsonResponse({'success': True, 'message': f'{count} users deactivated'})

        elif action == 'change_type':
            new_user_type = form.cleaned_data.get('new_user_type')
            count = users.update(user_type=new_user_type)
            AuditLog.log_action(
                user=request.user,
                action_type='user_updated',
                description=f'Bulk changed user type to {new_user_type} for {count} users',
                request=request,
                affected_user_count=count,
                new_user_type=new_user_type
            )
            return JsonResponse({'success': True, 'message': f'{count} users updated'})

        elif action == 'delete':
            # Don't allow deletion of current user or other admins by non-superuser
            if not request.user.is_superuser:
                users = users.exclude(user_type='admin').exclude(id=request.user.id)

            count = users.count()
            users.delete()
            AuditLog.log_action(
                user=request.user,
                action_type='user_deleted',
                description=f'Bulk deleted {count} users',
                request=request,
                affected_user_count=count
            )
            return JsonResponse({'success': True, 'message': f'{count} users deleted'})

        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


class UserPasswordChangeView(AdminRequiredMixin, FormView):
    """View for changing user password"""
    form_class = PasswordChangeForm
    template_name = 'authentication/password_change.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = get_object_or_404(User, pk=self.kwargs['pk'])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['target_user'] = get_object_or_404(User, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.save()
        target_user = get_object_or_404(User, pk=self.kwargs['pk'])

        # Log password change
        AuditLog.log_action(
            user=self.request.user,
            action_type='password_change',
            description=f'Changed password for user: {target_user.username}',
            request=self.request,
            target_user_id=target_user.id
        )

        messages.success(self.request, f'Password changed successfully for {target_user.username}')
        return redirect('authentication:user-detail', pk=target_user.pk)


class UserStatsView(AdminRequiredMixin, TemplateView):
    """Enhanced user statistics view"""
    template_name = 'authentication/user_stats.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Enhanced user statistics
        total_users = User.objects.count()
        context['stats'] = {
            'total_users': total_users,
            'active_users': User.objects.filter(is_active=True).count(),
            'inactive_users': User.objects.filter(is_active=False).count(),
            'admin_users': User.objects.filter(user_type='admin').count(),
            'sales_rep_users': User.objects.filter(user_type='sales_rep').count(),
            'customer_users': User.objects.filter(user_type='customer').count(),
            'staff_users': User.objects.filter(is_staff=True).count(),
            'superusers': User.objects.filter(is_superuser=True).count(),
        }

        # Calculate percentages
        if total_users > 0:
            for key, value in context['stats'].items():
                if key != 'total_users':
                    context['stats'][f'{key}_percentage'] = round((value / total_users) * 100, 1)

        # Monthly user creation stats
        from django.utils import timezone
        from django.db.models import Count
        from django.db.models.functions import TruncMonth

        monthly_stats = User.objects.filter(
            created_at__year=timezone.now().year
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')

        context['monthly_stats'] = monthly_stats

        # Recent login activity
        context['recent_logins'] = User.objects.filter(
            last_login__isnull=False
        ).order_by('-last_login')[:10]

        # Assignment statistics
        context['assignment_stats'] = {
            'total_school_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count(),
            'total_club_assignments': SalesRepClubAssignment.objects.filter(is_active=True).count(),
            'sales_reps_with_assignments': User.objects.filter(
                user_type='sales_rep',
                school_assignments__is_active=True
            ).distinct().count(),
            'unassigned_sales_reps': User.objects.filter(
                user_type='sales_rep',
                is_active=True
            ).exclude(
                school_assignments__is_active=True
            ).exclude(
                club_assignments__is_active=True
            ).count()
        }

        return context
