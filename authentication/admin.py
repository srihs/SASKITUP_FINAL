from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    User, SalesRepSchoolAssignment, SalesRepClubAssignment,
    UserSession, AuditLog
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Enhanced User admin with custom fields and functionality
    """
    # Fields to display in the list view
    list_display = [
        'username', 'email', 'get_full_name', 'user_type',
        'employee_id', 'is_active', 'is_staff', 'total_assignments',
        'last_login', 'date_joined'
    ]

    list_filter = [
        'user_type', 'is_active', 'is_staff', 'is_superuser',
        'is_active_sales_rep', 'date_joined', 'last_login'
    ]

    search_fields = [
        'username', 'first_name', 'last_name', 'email',
        'employee_id', 'phone', 'department'
    ]

    ordering = ['-date_joined']

    # Fieldsets for the user edit form
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile Information', {
            'fields': (
                'user_type', 'employee_id', 'phone', 'department',
                'hire_date', 'is_active_sales_rep'
            ),
        }),
        ('System Information', {
            'fields': ('last_login_ip', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # Fields for adding a new user
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Profile Information', {
            'fields': (
                'user_type', 'employee_id', 'phone', 'department',
                'hire_date', 'first_name', 'last_name', 'email'
            ),
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'last_login_ip']

    def get_full_name(self, obj):
        """Display full name or username if no name available"""
        return obj.get_full_name() or obj.username
    get_full_name.short_description = 'Full Name'

    def total_assignments(self, obj):
        """Display total assignments with links"""
        if obj.is_sales_rep:
            schools = obj.assigned_schools_count
            clubs = obj.assigned_clubs_count
            total = schools + clubs

            if total > 0:
                return format_html(
                    '<span title="Schools: {}, Clubs: {}">{} assignments</span>',
                    schools, clubs, total
                )
            return '0 assignments'
        return 'N/A'
    total_assignments.short_description = 'Assignments'

    def get_queryset(self, request):
        """Optimize queryset with prefetch related"""
        queryset = super().get_queryset(request)
        return queryset.prefetch_related(
            'school_assignments', 'club_assignments'
        )


@admin.register(SalesRepSchoolAssignment)
class SalesRepSchoolAssignmentAdmin(admin.ModelAdmin):
    """
    Admin for managing sales rep school assignments
    """
    list_display = [
        'sales_rep', 'assigned_school_name', 'school_type',
        'is_active', 'assigned_date', 'priority_level', 'territory_name'
    ]

    list_filter = [
        'is_active', 'priority_level', 'assigned_date', 'territory_name'
    ]

    search_fields = [
        'sales_rep__username', 'sales_rep__first_name', 'sales_rep__last_name',
        'school__org_name', 'wholesale_school__name', 'territory_name'
    ]

    date_hierarchy = 'assigned_date'
    ordering = ['-assigned_date']

    fieldsets = [
        ('Assignment Details', {
            'fields': (
                'sales_rep', 'school', 'wholesale_school', 'is_active'
            )
        }),
        ('Territory Information', {
            'fields': (
                'territory_name', 'priority_level', 'assigned_date'
            )
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('wide',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]

    readonly_fields = ['created_at', 'updated_at']

    def assigned_school_name(self, obj):
        """Display school name"""
        if obj.school:
            return obj.school.org_name
        elif obj.wholesale_school:
            return obj.wholesale_school.name
        return "No school assigned"
    assigned_school_name.short_description = 'School'

    def school_type(self, obj):
        """Display school type"""
        return obj.school_type
    school_type.short_description = 'Type'

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'sales_rep', 'school', 'wholesale_school', 'created_by'
        )


@admin.register(SalesRepClubAssignment)
class SalesRepClubAssignmentAdmin(admin.ModelAdmin):
    """
    Admin for managing sales rep club assignments
    TODO: Update to work properly with GenericForeignKey for club field
    """
    list_display = [
        'sales_rep', 'club_name', 'is_active',
        'assigned_date', 'priority_level', 'territory_name'
    ]

    list_filter = [
        'is_active', 'priority_level',
        'assigned_date', 'territory_name'
    ]

    search_fields = [
        'sales_rep__username', 'sales_rep__first_name', 'sales_rep__last_name',
        'territory_name'
    ]

    date_hierarchy = 'assigned_date'
    ordering = ['-assigned_date']

    fieldsets = [
        ('Assignment Details', {
            'fields': (
                'sales_rep', 'club_content_type', 'club_object_id', 'is_active'
            )
        }),
        ('Territory Information', {
            'fields': (
                'territory_name', 'priority_level', 'assigned_date'
            )
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('wide',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]

    readonly_fields = ['created_at', 'updated_at']

    def club_name(self, obj):
        """Display club name"""
        if obj.club:
            return getattr(obj.club, 'name', str(obj.club))
        return '-'
    club_name.short_description = 'Club'

    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related(
            'sales_rep', 'created_by', 'club_content_type'
        )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """
    Admin for viewing user sessions
    """
    list_display = [
        'user', 'ip_address', 'login_time', 'last_activity',
        'is_active', 'session_duration'
    ]

    list_filter = [
        'is_active', 'login_time', 'last_activity'
    ]

    search_fields = [
        'user__username', 'user__first_name', 'user__last_name',
        'ip_address', 'session_key'
    ]

    date_hierarchy = 'login_time'
    ordering = ['-login_time']

    readonly_fields = [
        'user', 'session_key', 'ip_address', 'user_agent',
        'login_time', 'last_activity', 'session_duration'
    ]

    def session_duration(self, obj):
        """Calculate session duration"""
        if obj.login_time and obj.last_activity:
            duration = obj.last_activity - obj.login_time
            return str(duration).split('.')[0]  # Remove microseconds
        return 'N/A'
    session_duration.short_description = 'Duration'

    def has_add_permission(self, request):
        """Prevent manual session creation"""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent session editing"""
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin for viewing audit logs
    """
    list_display = [
        'timestamp', 'user', 'action_type', 'description_short',
        'ip_address', 'affected_model', 'affected_object_id'
    ]

    list_filter = [
        'action_type', 'timestamp', 'affected_model'
    ]

    search_fields = [
        'user__username', 'description', 'affected_model',
        'affected_object_id', 'ip_address'
    ]

    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    readonly_fields = [
        'id', 'user', 'action_type', 'description', 'ip_address',
        'user_agent', 'session_key', 'metadata', 'affected_model',
        'affected_object_id', 'timestamp'
    ]

    fieldsets = [
        ('Action Details', {
            'fields': (
                'timestamp', 'user', 'action_type', 'description'
            )
        }),
        ('Context Information', {
            'fields': (
                'ip_address', 'user_agent', 'session_key'
            )
        }),
        ('Affected Object', {
            'fields': (
                'affected_model', 'affected_object_id'
            )
        }),
        ('Additional Data', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    ]

    def description_short(self, obj):
        """Show truncated description"""
        if len(obj.description) > 50:
            return f"{obj.description[:50]}..."
        return obj.description
    description_short.short_description = 'Description'

    def has_add_permission(self, request):
        """Prevent manual audit log creation"""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent audit log editing"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent audit log deletion"""
        return False
