from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    # Authentication URLs
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.SignupView.as_view(), name='signup'),

    # Password Reset URLs
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/<uidb64>/<token>/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset-complete/', views.PasswordResetCompleteView.as_view(), name='password-reset-complete'),

    # Unified Profile URL (role-based routing)
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # Dashboard URLs
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('sales-rep-dashboard/', views.SalesRepDashboardView.as_view(), name='sales-rep-dashboard'),
    path('customer-dashboard/', views.CustomerDashboardView.as_view(), name='customer-dashboard'),

    # User Management URLs
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/create/', views.UserCreateView.as_view(), name='user-create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user-update'),

    # Settings URLs
    path('settings/', views.SettingsDashboardView.as_view(), name='settings-dashboard'),

    # Audit Log URLs
    path('audit-logs/', views.AuditLogListView.as_view(), name='audit-log-list'),

    # Access Control URLs
    path('access-denied/', views.AccessDeniedView.as_view(), name='access-denied'),

    # Customer URLs
    path('customer/profile/', views.CustomerProfileView.as_view(), name='customer-profile'),
    path('customer/orders/', views.CustomerOrdersView.as_view(), name='customer-orders'),
    path('customer/support/', views.CustomerSupportView.as_view(), name='customer-support'),
    path('customer/notifications/', views.CustomerNotificationsView.as_view(), name='customer-notifications'),
    path('customer/activity/', views.CustomerActivityView.as_view(), name='customer-activity'),
    path('customer/faq/', views.CustomerFAQView.as_view(), name='customer-faq'),

    # Customer Management URLs (Admin Only)
    path('customers/', views.CustomerManagementView.as_view(), name='customer-management'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer-update'),

    # Enhanced User Management URLs
    path('users/stats/', views.UserStatsView.as_view(), name='user-stats'),
    path('users/<int:pk>/password/', views.UserPasswordChangeView.as_view(), name='user-password-change'),

    # Assignment Management URLs
    path('assignments/', views.BulkAssignmentView.as_view(), name='bulk-assignment'),
    path('assignments/customers/', views.BulkAssignmentCustomersAPIView.as_view(), name='bulk-assignment-customers'),
    path('assignments/process/', views.ProcessBulkAssignmentView.as_view(), name='process-bulk-assignment'),
    path('assignments/current/', views.get_current_assignments, name='get-current-assignments'),

    # AJAX URLs
    path('ajax/users/search/', views.user_search_ajax, name='user-search-ajax'),
    path('ajax/users/bulk-action/', views.bulk_user_action, name='bulk-user-action'),
    path('ajax/assignments/', views.assignment_ajax_handler, name='assignment-ajax'),

    # Password Change
    path('change-password/', views.change_password_view, name='change-password'),
]