from django.urls import path
from . import views
from . import assignment_views

app_name = 'authentication'

urlpatterns = [
    # Authentication URLs
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard URLs
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('sales-rep-dashboard/', views.SalesRepDashboardView.as_view(), name='sales-rep-dashboard'),
    path('customer-dashboard/', views.CustomerDashboardView.as_view(), name='customer-dashboard'),

    # User Management URLs
    path('user-management/', views.UserManagementDashboardView.as_view(), name='user-management-dashboard'),
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/create/', views.UserCreateView.as_view(), name='user-create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user-update'),

    # Settings URLs
    path('settings/', views.SettingsDashboardView.as_view(), name='settings-dashboard'),

    # Assignment Management URLs
    path('assignments/', assignment_views.AssignmentManagementView.as_view(), name='assignment-management'),

    # School Assignment URLs
    path('assignments/schools/', assignment_views.SchoolAssignmentListView.as_view(), name='school-assignment-list'),
    path('assignments/schools/create/', assignment_views.SchoolAssignmentCreateView.as_view(), name='school-assignment-create'),
    path('assignments/schools/<uuid:pk>/', assignment_views.SchoolAssignmentDetailView.as_view(), name='school-assignment-detail'),
    path('assignments/schools/<uuid:pk>/edit/', assignment_views.SchoolAssignmentUpdateView.as_view(), name='school-assignment-update'),

    # Club Assignment URLs
    path('assignments/clubs/', assignment_views.ClubAssignmentListView.as_view(), name='club-assignment-list'),
    path('assignments/clubs/create/', assignment_views.ClubAssignmentCreateView.as_view(), name='club-assignment-create'),
    path('assignments/clubs/<uuid:pk>/', assignment_views.ClubAssignmentDetailView.as_view(), name='club-assignment-detail'),
    path('assignments/clubs/<uuid:pk>/edit/', assignment_views.ClubAssignmentUpdateView.as_view(), name='club-assignment-update'),

    # Audit Log URLs
    path('audit-logs/', assignment_views.AuditLogListView.as_view(), name='audit-log-list'),

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

    # AJAX URLs
    path('ajax/users/search/', views.user_search_ajax, name='user-search-ajax'),
    path('ajax/users/bulk-action/', views.bulk_user_action, name='bulk-user-action'),
    path('ajax/schools/search/', assignment_views.school_search_ajax, name='school-search-ajax'),
    path('ajax/clubs/search/', assignment_views.club_search_ajax, name='club-search-ajax'),
    path('ajax/assignments/stats/', assignment_views.assignment_stats_ajax, name='assignment-stats-ajax'),
]