from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView, View
)
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .forms import (
    EmailAuthenticationForm, UserForm, UserSearchForm, UserProfileForm,
    PasswordChangeForm, BulkUserActionForm
)
from django.utils import timezone

from .models import (
    User, UserSession, AuditLog, SalesRepSchoolAssignment, SalesRepClubAssignment
)
from .permissions import (
    AdminRequiredMixin, SalesRepRequiredMixin, CustomerRequiredMixin,
    can_user_create_users, can_customer_access_data
)
# TODO: Update to use LottoClub and SASClub instead of unified Club model
# from clubs.models import Club
from schools.models import School, WholesaleSchool


class LoginView(FormView):
    """Custom login view with audit logging and email-based authentication"""
    template_name = 'authentication/login.html'
    form_class = EmailAuthenticationForm
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
        email = form.data.get('username', 'Unknown')  # 'username' field contains email
        AuditLog.log_action(
            user=None,
            action_type='login',
            description=f'Failed login attempt for email: {email}',
            request=self.request,
            email=email
        )

        messages.error(self.request, 'Invalid email or password.')
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


class SignupView(FormView):
    """Customer signup view"""
    template_name = 'authentication/signup.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('authentication:login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('global-dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Create the user as a customer
        user = form.save(commit=False)
        user.user_type = 'customer'
        user.save()

        # Log the signup
        AuditLog.log_action(
            user=user,
            action_type='user_created',
            description=f'New customer signup: {user.username}',
            request=self.request,
            created_user_id=user.id,
            created_username=user.username
        )

        messages.success(
            self.request,
            'Your account has been created successfully! You can now log in.'
        )
        return super().form_valid(form)


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """Dashboard for admin users"""
    template_name = 'authentication/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Statistics
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['sales_reps'] = User.objects.filter(user_type='sales_rep').count()
        context['account_managers'] = User.objects.filter(user_type='account_manager').count()
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
        ).select_related('club_content_type')

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
        queryset = User.objects.order_by('-date_joined')

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

        # Add user statistics for tiles
        total_users = User.objects.count()
        context['user_stats'] = {
            'total_users': total_users,
            'active_users': User.objects.filter(is_active=True).count(),
            'inactive_users': User.objects.filter(is_active=False).count(),
            'admin_count': User.objects.filter(user_type='admin').count(),
            'sales_rep_count': User.objects.filter(user_type='sales_rep').count(),
            'account_manager_count': User.objects.filter(user_type='account_manager').count(),
            'customer_count': User.objects.filter(user_type='customer').count(),
            'new_users_this_month': User.objects.filter(created_at__month=timezone.now().month).count(),
            'recent_registrations': User.objects.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
        }

        # Calculate percentages
        if total_users > 0:
            context['user_stats']['active_percentage'] = round((context['user_stats']['active_users'] / total_users) * 100, 1)
            context['user_stats']['admin_percentage'] = round((context['user_stats']['admin_count'] / total_users) * 100, 1)
            context['user_stats']['sales_rep_percentage'] = round((context['user_stats']['sales_rep_count'] / total_users) * 100, 1)
            context['user_stats']['account_manager_percentage'] = round((context['user_stats']['account_manager_count'] / total_users) * 100, 1)
            context['user_stats']['customer_percentage'] = round((context['user_stats']['customer_count'] / total_users) * 100, 1)
        else:
            context['user_stats']['active_percentage'] = 0
            context['user_stats']['admin_percentage'] = 0
            context['user_stats']['sales_rep_percentage'] = 0
            context['user_stats']['account_manager_percentage'] = 0
            context['user_stats']['customer_percentage'] = 0

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

        # No success message - redirect to user list
        return response


class UserDetailView(AdminRequiredMixin, DetailView):
    """View user details"""
    model = User
    template_name = 'authentication/user_detail.html'
    context_object_name = 'user_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object

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
    if not request.user.is_admin:
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


class AuditLogListView(AdminRequiredMixin, ListView):
    """List audit logs"""
    model = AuditLog
    template_name = 'authentication/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        return AuditLog.objects.select_related('user').order_by('-timestamp')


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
            'account_manager_users': User.objects.filter(user_type='account_manager').count(),
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


# Assignment Management Views

class AssignmentManagementView(AdminRequiredMixin, TemplateView):
    """Assignment management dashboard"""
    template_name = 'authentication/assignment_management.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all sales reps and account managers
        context['sales_reps'] = User.objects.filter(
            user_type__in=['sales_rep', 'account_manager'],
            is_active=True
        ).order_by('first_name', 'last_name')

        # Assignment statistics
        context['stats'] = {
            'total_school_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count(),
            'total_club_assignments': SalesRepClubAssignment.objects.filter(is_active=True).count(),
            'total_sales_reps': User.objects.filter(user_type__in=['sales_rep', 'account_manager'], is_active=True).count(),
            'assigned_sales_reps': User.objects.filter(
                user_type__in=['sales_rep', 'account_manager'],
                is_active=True
            ).filter(
                Q(school_assignments__is_active=True) |
                Q(club_assignments__is_active=True)
            ).distinct().count()
        }

        return context


class BulkAssignmentView(AdminRequiredMixin, TemplateView):
    """Bulk assignment interface for customers"""
    template_name = 'authentication/bulk_assignment.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all active sales reps and account managers with assignment counts
        sales_reps = User.objects.filter(
            user_type__in=['sales_rep', 'account_manager'],
            is_active=True
        ).order_by('first_name', 'last_name')

        # Annotate sales reps and account managers with total assignment counts
        for sales_rep in sales_reps:
            school_assignments = SalesRepSchoolAssignment.objects.filter(
                sales_rep=sales_rep,
                is_active=True
            ).count()
            club_assignments = SalesRepClubAssignment.objects.filter(
                sales_rep=sales_rep,
                is_active=True
            ).count()
            sales_rep.total_assignments_count = school_assignments + club_assignments

        context['sales_reps'] = sales_reps

        # Get business entities data
        customers_data = []

        # Import club models
        from clubs.models_lotto import LottoClub
        from clubs.models_sas import SASClub
        from clubs.models_tus import TUSSchool
        from django.contrib.contenttypes.models import ContentType

        # Add LOTTO Clubs
        lotto_clubs = LottoClub.objects.filter(is_active=True).order_by('name')
        lotto_content_type = ContentType.objects.get_for_model(LottoClub)

        for club in lotto_clubs:
            # Check if club is assigned using GenericForeignKey
            current_assignment = SalesRepClubAssignment.objects.filter(
                club_content_type=lotto_content_type,
                club_object_id=club.id,
                is_active=True
            ).select_related('sales_rep').first()

            customers_data.append({
                'id': club.id,
                'name': club.name,
                'type': 'lotto_club',
                'type_display': 'LOTTO Club',
                'customer_id': getattr(club, 'customer_id', None),
                'address': club.address or 'No address',
                'region': 'Not specified',
                'contact_person': club.contact_person or 'Not specified',
                'phone': 'Not specified',
                'email': club.email or 'Not specified',
                'is_assigned': current_assignment is not None,
                'current_assignment': current_assignment.sales_rep.get_full_name() if current_assignment else None,
                'assignment_status': 'Assigned' if current_assignment else 'Unassigned'
            })

        # Add SAS Clubs
        sas_clubs = SASClub.objects.filter(is_active=True).order_by('name')
        sas_content_type = ContentType.objects.get_for_model(SASClub)

        for club in sas_clubs:
            # Check if club is assigned using GenericForeignKey
            current_assignment = SalesRepClubAssignment.objects.filter(
                club_content_type=sas_content_type,
                club_object_id=club.id,
                is_active=True
            ).select_related('sales_rep').first()

            customers_data.append({
                'id': club.id,
                'name': club.name,
                'type': 'sas_club',
                'type_display': 'SAS Club',
                'customer_id': getattr(club, 'customer_id', None),
                'address': club.address or 'No address',
                'region': club.province or 'Not specified',
                'contact_person': club.contact_person or 'Not specified',
                'phone': club.phone or 'Not specified',
                'email': club.email or 'Not specified',
                'is_assigned': current_assignment is not None,
                'current_assignment': current_assignment.sales_rep.get_full_name() if current_assignment else None,
                'assignment_status': 'Assigned' if current_assignment else 'Unassigned'
            })

        # Add Wholesale Schools
        from schools.models import WholesaleSchool
        from authentication.utils.school_matcher import SchoolMatcher

        wholesale_schools = WholesaleSchool.objects.filter(is_active=True).order_by('name')

        # Batch match schools for better performance
        school_contact_details = SchoolMatcher.batch_match_schools(list(wholesale_schools))

        for school in wholesale_schools:
            # Check if school is assigned
            current_assignment = SalesRepSchoolAssignment.objects.filter(
                wholesale_school=school,
                is_active=True
            ).select_related('sales_rep').first()

            # Get contact details from matcher (uses NZ school data if available)
            contact_details = school_contact_details.get(school.id, {})

            customers_data.append({
                'id': school.id,
                'name': school.name,
                'type': 'wholesale_school',
                'type_display': 'Wholesale School',
                'customer_id': getattr(school, 'customer_id', None),
                'address': contact_details.get('address', 'No address available'),
                'region': contact_details.get('region', 'No region'),
                'contact_person': contact_details.get('contact_person', 'Not specified'),
                'phone': contact_details.get('phone', 'Not specified'),
                'email': contact_details.get('email', 'Not specified'),
                'is_assigned': current_assignment is not None,
                'current_assignment': current_assignment.sales_rep.get_full_name() if current_assignment else None,
                'assignment_status': 'Assigned' if current_assignment else 'Unassigned'
            })

        # Add TUS retail schools
        retail_schools = TUSSchool.objects.filter(is_active=True).select_related('location').order_by('name')

        for school in retail_schools:
            # Check if school is assigned
            current_assignment = SalesRepSchoolAssignment.objects.filter(
                school_id=school.id,
                is_active=True
            ).select_related('sales_rep').first()

            customers_data.append({
                'id': school.id,
                'name': school.name,
                'type': 'tus_school',
                'type_display': 'TUS School',
                'customer_id': getattr(school, 'customer_id', None),
                'address': school.address or 'No address available',
                'region': school.location.name if school.location else 'No region',
                'contact_person': school.contact_person or 'Not specified',
                'phone': school.phone or 'Not specified',
                'email': school.email or 'Not specified',
                'is_assigned': current_assignment is not None,
                'current_assignment': current_assignment.sales_rep.get_full_name() if current_assignment else None,
                'assignment_status': 'Assigned' if current_assignment else 'Unassigned'
            })

        context['customers_data'] = customers_data

        # Calculate statistics
        total_customers = len(customers_data)
        assigned_customers = sum(1 for customer in customers_data if customer['is_assigned'])
        unassigned_customers = total_customers - assigned_customers

        context['total_schools'] = total_customers  # Template uses 'total_schools' for customers
        context['assigned_schools'] = assigned_customers
        context['unassigned_schools'] = unassigned_customers

        # Legacy context for backward compatibility
        context['lotto_clubs'] = lotto_clubs
        context['sas_clubs'] = sas_clubs
        context['wholesale_schools'] = wholesale_schools
        context['retail_schools'] = retail_schools
        context['total_entities'] = total_customers

        return context


class BulkAssignmentCustomersAPIView(AdminRequiredMixin, View):
    """API endpoint to get customers for bulk assignment"""

    def get(self, request, *args, **kwargs):
        """Return all schools and clubs as JSON"""
        from schools.models import WholesaleSchool
        from clubs.models_lotto import LottoClub
        from clubs.models_sas import SASClub
        from clubs.models_tus import TUSSchool
        from django.contrib.contenttypes.models import ContentType

        sales_rep_id = request.GET.get('sales_rep')

        # Get all customers
        schools_data = []

        # Regular schools (from TUSSchool for retail)
        retail_schools = TUSSchool.objects.all()
        for school in retail_schools:
            # Check if assigned to this or any sales rep
            assignment = SalesRepSchoolAssignment.objects.filter(
                content_type=ContentType.objects.get_for_model(TUSSchool),
                object_id=school.id
            ).first()

            schools_data.append({
                'id': school.id,
                'name': school.name,
                'type': 'regular',
                'org_type': 'TUS School',
                'location': f"{school.city}, {school.country}" if hasattr(school, 'city') else 'Unknown',
                'is_assigned': assignment is not None,
                'current_assignment': assignment.sales_rep.get_full_name() if assignment else None,
                'customer_type': 'tusschool'
            })

        # Wholesale schools
        wholesale_schools = WholesaleSchool.objects.all()
        for school in wholesale_schools:
            assignment = SalesRepSchoolAssignment.objects.filter(
                content_type=ContentType.objects.get_for_model(WholesaleSchool),
                object_id=school.id
            ).first()

            schools_data.append({
                'id': school.id,
                'name': school.name,
                'type': 'wholesale',
                'org_type': 'Wholesale School',
                'location': f"{school.city}, {school.country}" if hasattr(school, 'city') else 'Unknown',
                'is_assigned': assignment is not None,
                'current_assignment': assignment.sales_rep.get_full_name() if assignment else None,
                'customer_type': 'wholesaleschool'
            })

        # Lotto Clubs
        lotto_clubs = LottoClub.objects.all()
        for club in lotto_clubs:
            assignment = SalesRepClubAssignment.objects.filter(
                content_type=ContentType.objects.get_for_model(LottoClub),
                object_id=club.id
            ).first()

            schools_data.append({
                'id': club.id,
                'name': club.name,
                'type': 'club',
                'org_type': 'Lotto Club',
                'location': f"{club.city}, {club.country}" if hasattr(club, 'city') else 'Unknown',
                'is_assigned': assignment is not None,
                'current_assignment': assignment.sales_rep.get_full_name() if assignment else None,
                'customer_type': 'lottoclub'
            })

        # SAS Clubs
        sas_clubs = SASClub.objects.all()
        for club in sas_clubs:
            assignment = SalesRepClubAssignment.objects.filter(
                content_type=ContentType.objects.get_for_model(SASClub),
                object_id=club.id
            ).first()

            schools_data.append({
                'id': club.id,
                'name': club.name,
                'type': 'club',
                'org_type': 'SAS Club',
                'location': f"{club.city}, {club.country}" if hasattr(club, 'city') else 'Unknown',
                'is_assigned': assignment is not None,
                'current_assignment': assignment.sales_rep.get_full_name() if assignment else None,
                'customer_type': 'sasclub'
            })

        return JsonResponse({
            'success': True,
            'schools': schools_data  # Template expects 'schools' key
        })


class ProcessBulkAssignmentView(AdminRequiredMixin, View):
    """Process bulk assignment requests"""

    def post(self, request, *args, **kwargs):
        """Handle bulk assignment processing"""
        try:
            import json
            import sys
            data = json.loads(request.body)

            sales_rep_id = data.get('sales_rep_id')
            customers = data.get('customers', [])
            notes = data.get('notes', '')

            # Force flush to see logs immediately
            print(f"\n========== BULK ASSIGNMENT REQUEST ==========", flush=True)
            print(f"Sales rep ID: {sales_rep_id}", flush=True)
            print(f"Number of customers: {len(customers)}", flush=True)
            print(f"Customers data: {customers}", flush=True)
            print(f"Customer types: {[c.get('type') for c in customers]}", flush=True)
            print(f"Customer IDs: {[c.get('id') for c in customers]}", flush=True)
            print(f"Customer priorities: {[c.get('priority', 'medium') for c in customers]}", flush=True)
            sys.stdout.flush()

            if not sales_rep_id or not customers:
                print("ERROR: Missing sales rep or customers")
                return JsonResponse({
                    'success': False,
                    'error': 'Sales rep and customers are required'
                }, status=400)

            # Get the sales rep or account manager
            try:
                sales_rep = User.objects.get(
                    id=sales_rep_id,
                    user_type__in=['sales_rep', 'account_manager']
                )
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Sales rep or account manager not found'
                }, status=404)

            assignments_created = 0

            # Import models
            from schools.models import WholesaleSchool
            from clubs.models_lotto import LottoClub
            from clubs.models_sas import SASClub
            from clubs.models_tus import TUSSchool  # Add TUSSchool import for TUS retail schools
            from django.contrib.contenttypes.models import ContentType

            # Process assignments for each customer
            for customer in customers:
                customer_id = customer.get('id')
                customer_type = customer.get('type')
                customer_priority = customer.get('priority', 'medium')  # Get individual priority

                print(f"\n--- Processing customer: ID={customer_id}, Type={customer_type}, Priority={customer_priority} ---", flush=True)

                try:
                    # Process based on customer type
                    if customer_type == 'wholesale_school':
                        # Get wholesale school
                        try:
                            print(f"Querying WholesaleSchool with ID={customer_id} (type: {type(customer_id).__name__})", flush=True)
                            wholesale_school = WholesaleSchool.objects.get(id=customer_id, is_active=True)
                            print(f"✓ Found wholesale school: {wholesale_school.name}", flush=True)
                        except WholesaleSchool.DoesNotExist:
                            print(f"✗ ERROR: Wholesale school {customer_id} not found or not active", flush=True)
                            continue
                        except Exception as e:
                            print(f"✗ ERROR querying wholesale school: {type(e).__name__}: {e}", flush=True)
                            continue

                        # Create wholesale school assignment with individual priority
                        print(f"Creating/getting assignment for sales_rep={sales_rep.id}, wholesale_school={wholesale_school.id}, priority={customer_priority}", flush=True)
                        assignment, created = SalesRepSchoolAssignment.objects.get_or_create(
                            sales_rep=sales_rep,
                            wholesale_school=wholesale_school,
                            defaults={
                                'priority_level': customer_priority,
                                'notes': notes,
                                'is_active': True,
                                'assigned_date': timezone.now()
                            }
                        )
                        if created:
                            print(f"✓ Created new assignment for {wholesale_school.name} with priority {customer_priority}", flush=True)
                            assignments_created += 1
                        elif not assignment.is_active:
                            # Reactivate if it was previously deactivated
                            print(f"✓ Reactivated assignment for {wholesale_school.name} with priority {customer_priority}", flush=True)
                            assignment.is_active = True
                            assignment.assigned_date = timezone.now()
                            assignment.priority_level = customer_priority
                            assignment.notes = notes
                            assignment.save()
                            assignments_created += 1
                        else:
                            print(f"⚠ Assignment already exists and is active for {wholesale_school.name}", flush=True)

                    elif customer_type == 'tus_school':
                        # Get TUS retail school
                        try:
                            tus_school = TUSSchool.objects.get(id=customer_id, is_active=True)
                            print(f"✓ Found TUS school: {tus_school.name}")
                        except TUSSchool.DoesNotExist:
                            print(f"TUS school {customer_id} not found")
                            continue

                        # Create TUS school assignment with individual priority
                        print(f"Creating/getting assignment for sales_rep={sales_rep.id}, tus_school={tus_school.id}, priority={customer_priority}")
                        assignment, created = SalesRepSchoolAssignment.objects.get_or_create(
                            sales_rep=sales_rep,
                            school_id=tus_school.id,
                            defaults={
                                'priority_level': customer_priority,
                                'notes': notes,
                                'is_active': True,
                                'assigned_date': timezone.now()
                            }
                        )
                        if created:
                            assignments_created += 1
                            print(f"✓ Created new assignment for {tus_school.name} with priority {customer_priority}")
                        elif not assignment.is_active:
                            # Reactivate if it was previously deactivated
                            assignment.is_active = True
                            assignment.assigned_date = timezone.now()
                            assignment.priority_level = customer_priority
                            assignment.notes = notes
                            assignment.save()
                            assignments_created += 1
                            print(f"✓ Reactivated assignment for {tus_school.name}")

                    elif customer_type == 'lotto_club':
                        # Get LOTTO club
                        try:
                            lotto_club = LottoClub.objects.get(id=customer_id, is_active=True)
                            print(f"✓ Found LOTTO club: {lotto_club.name}", flush=True)
                        except LottoClub.DoesNotExist:
                            print(f"✗ ERROR: LOTTO club {customer_id} not found or not active", flush=True)
                            continue
                        except Exception as e:
                            print(f"✗ ERROR querying LOTTO club: {type(e).__name__}: {e}", flush=True)
                            continue

                        # Get content type for GenericForeignKey
                        lotto_content_type = ContentType.objects.get_for_model(LottoClub)

                        # Create LOTTO club assignment with individual priority
                        print(f"Creating/getting assignment for sales_rep={sales_rep.id}, lotto_club={lotto_club.id}, priority={customer_priority}", flush=True)
                        assignment, created = SalesRepClubAssignment.objects.get_or_create(
                            sales_rep=sales_rep,
                            club_content_type=lotto_content_type,
                            club_object_id=lotto_club.id,
                            defaults={
                                'priority_level': customer_priority,
                                'notes': notes,
                                'is_active': True,
                                'assigned_date': timezone.now()
                            }
                        )
                        if created:
                            print(f"✓ Created new assignment for {lotto_club.name} with priority {customer_priority}", flush=True)
                            assignments_created += 1
                        elif not assignment.is_active:
                            # Reactivate if it was previously deactivated
                            print(f"✓ Reactivated assignment for {lotto_club.name} with priority {customer_priority}", flush=True)
                            assignment.is_active = True
                            assignment.assigned_date = timezone.now()
                            assignment.priority_level = customer_priority
                            assignment.notes = notes
                            assignment.save()
                            assignments_created += 1
                        else:
                            print(f"⚠ Assignment already exists and is active for {lotto_club.name}", flush=True)

                    elif customer_type == 'sas_club':
                        # Get SAS club
                        try:
                            sas_club = SASClub.objects.get(id=customer_id, is_active=True)
                            print(f"✓ Found SAS club: {sas_club.name}", flush=True)
                        except SASClub.DoesNotExist:
                            print(f"✗ ERROR: SAS club {customer_id} not found or not active", flush=True)
                            continue
                        except Exception as e:
                            print(f"✗ ERROR querying SAS club: {type(e).__name__}: {e}", flush=True)
                            continue

                        # Get content type for GenericForeignKey
                        sas_content_type = ContentType.objects.get_for_model(SASClub)

                        # Create SAS club assignment with individual priority
                        print(f"Creating/getting assignment for sales_rep={sales_rep.id}, sas_club={sas_club.id}, priority={customer_priority}", flush=True)
                        assignment, created = SalesRepClubAssignment.objects.get_or_create(
                            sales_rep=sales_rep,
                            club_content_type=sas_content_type,
                            club_object_id=sas_club.id,
                            defaults={
                                'priority_level': customer_priority,
                                'notes': notes,
                                'is_active': True,
                                'assigned_date': timezone.now()
                            }
                        )
                        if created:
                            print(f"✓ Created new assignment for {sas_club.name} with priority {customer_priority}", flush=True)
                            assignments_created += 1
                        elif not assignment.is_active:
                            # Reactivate if it was previously deactivated
                            print(f"✓ Reactivated assignment for {sas_club.name} with priority {customer_priority}", flush=True)
                            assignment.is_active = True
                            assignment.assigned_date = timezone.now()
                            assignment.priority_level = customer_priority
                            assignment.notes = notes
                            assignment.save()
                            assignments_created += 1
                        else:
                            print(f"⚠ Assignment already exists and is active for {sas_club.name}", flush=True)

                    else:
                        print(f"Unknown customer type: {customer_type}")
                        continue

                except Exception as e:
                    # Log the error but continue processing other customers
                    print(f"Error processing customer {customer_id}: {str(e)}")
                    continue

            # Log the bulk assignment action
            AuditLog.log_action(
                user=request.user,
                action_type='bulk_assignment_created',
                description=f'Bulk assigned {assignments_created} entities to {sales_rep.get_full_name()}',
                request=request,
                sales_rep_id=sales_rep.id
            )

            print(f"\n========== BULK ASSIGNMENT COMPLETE ==========", flush=True)
            print(f"Total assignments created/reactivated: {assignments_created}", flush=True)
            print(f"Returning success response", flush=True)
            sys.stdout.flush()

            return JsonResponse({
                'success': True,
                'message': f'Successfully assigned {assignments_created} entities to {sales_rep.get_full_name()}',
                'assignments_created': assignments_created,
                'assigned_count': assignments_created
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=500)


@login_required
def assignment_ajax_handler(request):
    """AJAX handler for assignment operations"""
    if not request.user.is_admin:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    action = request.POST.get('action')

    if action == 'get_current_assignments':
        sales_rep_id = request.POST.get('sales_rep_id')
        try:
            sales_rep = User.objects.get(id=sales_rep_id, user_type='sales_rep')

            # Get current assignments
            school_assignments = SalesRepSchoolAssignment.objects.filter(
                sales_rep=sales_rep,
                is_active=True
            ).select_related('school', 'wholesale_school')

            club_assignments = SalesRepClubAssignment.objects.filter(
                sales_rep=sales_rep,
                is_active=True
            ).select_related('club_content_type')

            # Format response
            school_data = []
            for assignment in school_assignments:
                entity_name = assignment.wholesale_school.name if assignment.wholesale_school else assignment.school.name
                school_data.append({
                    'id': assignment.id,
                    'name': entity_name,
                    'type': 'wholesale' if assignment.wholesale_school else 'retail',
                    'assigned_date': assignment.assigned_date.strftime('%Y-%m-%d')
                })

            club_data = []
            for assignment in club_assignments:
                club_data.append({
                    'id': assignment.id,
                    'name': assignment.club.name,
                    'type': 'club',
                    'assigned_date': assignment.assigned_date.strftime('%Y-%m-%d')
                })

            return JsonResponse({
                'success': True,
                'school_assignments': school_data,
                'club_assignments': club_data,
                'total_assignments': len(school_data) + len(club_data)
            })

        except User.DoesNotExist:
            return JsonResponse({'error': 'Sales rep not found'}, status=404)

    elif action == 'bulk_assign':
        sales_rep_id = request.POST.get('sales_rep_id')
        entity_ids = request.POST.getlist('entity_ids[]')
        entity_type = request.POST.get('entity_type')

        try:
            sales_rep = User.objects.get(id=sales_rep_id, user_type='sales_rep')
            created_count = 0

            if entity_type == 'wholesale':
                from schools.models import WholesaleSchool
                for entity_id in entity_ids:
                    try:
                        wholesale_school = WholesaleSchool.objects.get(id=entity_id)
                        # Check if assignment already exists
                        existing = SalesRepSchoolAssignment.objects.filter(
                            sales_rep=sales_rep,
                            wholesale_school=wholesale_school,
                            is_active=True
                        ).exists()

                        if not existing:
                            SalesRepSchoolAssignment.objects.create(
                                sales_rep=sales_rep,
                                wholesale_school=wholesale_school,
                                assigned_by=request.user,
                                assigned_date=timezone.now(),
                                is_active=True
                            )
                            created_count += 1
                    except WholesaleSchool.DoesNotExist:
                        continue

            elif entity_type == 'retail':
                # TODO: Update to use LottoClub and SASClub from clubs app
                # Disabled - unified Club model removed
                # for entity_id in entity_ids:
                #     try:
                #         club = Club.objects.get(id=entity_id)
                #         # Check if assignment already exists
                #         existing = SalesRepClubAssignment.objects.filter(
                #             sales_rep=sales_rep,
                #             club=club,
                #             is_active=True
                #         ).exists()
                #
                #         if not existing:
                #             SalesRepClubAssignment.objects.create(
                #                 sales_rep=sales_rep,
                #                 club=club,
                #                 assigned_by=request.user,
                #                 assigned_date=timezone.now(),
                #                 is_active=True
                #             )
                #             created_count += 1
                #     except Club.DoesNotExist:
                #         continue
                pass  # Skip retail club assignments for now

            # Log the bulk assignment action
            AuditLog.log_action(
                user=request.user,
                action_type='assignment_created',
                description=f'Bulk assigned {created_count} {entity_type} customers to {sales_rep.get_full_name()}',
                request=request,
                sales_rep_id=sales_rep.id
            )

            return JsonResponse({
                'success': True,
                'message': f'Successfully assigned {created_count} customers to {sales_rep.get_full_name()}',
                'assignments_created': created_count
            })

        except User.DoesNotExist:
            return JsonResponse({'error': 'Sales rep not found'}, status=404)

    elif action == 'remove_assignment':
        assignment_id = request.POST.get('assignment_id')
        assignment_type = request.POST.get('assignment_type')

        try:
            if assignment_type == 'school':
                assignment = SalesRepSchoolAssignment.objects.get(id=assignment_id)
                entity_name = assignment.wholesale_school.name if assignment.wholesale_school else assignment.school.name
            else:
                assignment = SalesRepClubAssignment.objects.get(id=assignment_id)
                entity_name = assignment.club.name

            # Deactivate instead of delete
            assignment.is_active = False
            assignment.save()

            # Log the removal
            AuditLog.log_action(
                user=request.user,
                action_type='assignment_deleted',
                description=f'Removed assignment: {entity_name} from {assignment.sales_rep.get_full_name()}',
                request=request,
                sales_rep_id=assignment.sales_rep.id
            )

            return JsonResponse({
                'success': True,
                'message': f'Assignment removed successfully'
            })

        except (SalesRepSchoolAssignment.DoesNotExist, SalesRepClubAssignment.DoesNotExist):
            return JsonResponse({'error': 'Assignment not found'}, status=404)

    return JsonResponse({'error': 'Invalid action'}, status=400)


@login_required
def get_current_assignments(request):
    """Get current assignments for a sales rep"""
    if not request.user.is_admin:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    sales_rep_id = request.GET.get('sales_rep')
    if not sales_rep_id:
        return JsonResponse({'error': 'Sales rep ID is required'}, status=400)

    try:
        sales_rep = User.objects.get(id=sales_rep_id, user_type__in=['sales_rep', 'account_manager'])

        # Get current assignments
        school_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=sales_rep,
            is_active=True
        ).select_related('school', 'wholesale_school')

        club_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=sales_rep,
            is_active=True
        ).select_related('club_content_type')

        # Import TUSSchool for retail school handling
        from clubs.models_tus import TUSSchool

        # Format school assignments response
        school_data = []
        for assignment in school_assignments:
            if assignment.wholesale_school:
                entity_name = assignment.wholesale_school.name
                entity_type = 'Wholesale School'
            elif assignment.school:
                entity_name = assignment.school.org_name
                entity_type = 'Retail School'
            elif assignment.school_id:
                # Try to get TUS school using school_id
                try:
                    tus_school = TUSSchool.objects.get(id=assignment.school_id, is_active=True)
                    entity_name = tus_school.name
                    entity_type = 'TUS School'
                except TUSSchool.DoesNotExist:
                    continue  # Skip if TUS school not found
            else:
                continue  # Skip invalid assignments

            school_data.append({
                'school_name': entity_name,
                'school_type': entity_type,
                'territory': assignment.territory_name or 'Not specified',
                'priority': assignment.priority_level or 'medium',
                'assigned_date': assignment.assigned_date.strftime('%Y-%m-%d')
            })

        # Format club assignments response
        club_data = []
        for assignment in club_assignments:
            # Get the actual club object via GenericForeignKey
            club = assignment.club_content_type.get_object_for_this_type(pk=assignment.club_object_id)
            club_type_name = assignment.club_content_type.model

            club_data.append({
                'club_name': club.name,
                'club_type': 'LOTTO Club' if club_type_name == 'lottoclub' else 'SAS Club',
                'territory': assignment.territory_name or 'Not specified',
                'priority': assignment.priority_level or 'medium',
                'assigned_date': assignment.assigned_date.strftime('%Y-%m-%d')
            })

        return JsonResponse({
            'success': True,
            'school_assignments': school_data,
            'club_assignments': club_data,
            'total_assignments': len(school_data) + len(club_data)
        })

    except User.DoesNotExist:
        return JsonResponse({'error': 'Sales rep not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
