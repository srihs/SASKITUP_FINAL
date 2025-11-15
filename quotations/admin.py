"""
Django admin configuration for quotations app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import (
    SiteSettings,
    Quotation,
    QuotationItem,
    CustomerInstitutionAssignment,
    QuotationVersion,
    CIN7OrderMapping
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """
    Admin configuration for SiteSettings singleton model.
    Simplified interface for managing site-wide quotation settings.
    """

    fieldsets = (
        ('Quotation Settings', {
            'fields': (
                'gst_percentage',
                'quotation_validity_days',
            ),
            'description': 'Configure default values for quotations. These settings affect all new quotations created.'
        }),
        ('Last Update', {
            'fields': ('updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('updated_at', 'updated_by')

    def has_add_permission(self, request):
        """Prevent adding new instances (singleton pattern)"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of the singleton instance"""
        return False

    def save_model(self, request, obj, form, change):
        """Save with current user"""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        """Redirect to the single instance edit page"""
        from django.shortcuts import redirect
        settings_obj = SiteSettings.objects.get_settings()
        return redirect('admin:quotations_sitesettings_change', object_id=settings_obj.pk)


class QuotationItemInline(admin.TabularInline):
    """Inline admin for quotation items"""
    model = QuotationItem
    extra = 0
    fields = [
        'product_name',
        'product_sku',
        'quantity',
        'unit_price',
        'line_total',
        'sort_order'
    ]
    readonly_fields = ['line_total']
    ordering = ['sort_order']


class QuotationVersionInline(admin.TabularInline):
    """Inline admin for quotation versions"""
    model = QuotationVersion
    extra = 0
    fields = ['version_number', 'change_description', 'created_at', 'created_by']
    readonly_fields = ['version_number', 'change_description', 'created_at', 'created_by']
    can_delete = False
    ordering = ['-version_number']


class CIN7OrderMappingInline(admin.StackedInline):
    """Inline admin for CIN7 order mapping"""
    model = CIN7OrderMapping
    extra = 0
    fields = [
        'cin7_order_id',
        'cin7_reference',
        'cin7_stage',
        'sync_status',
        'sync_attempts',
        'last_sync_attempt',
        'error_message',
        'created_at',
    ]
    readonly_fields = [
        'cin7_order_id',
        'cin7_reference',
        'cin7_stage',
        'sync_status',
        'sync_attempts',
        'last_sync_attempt',
        'error_message',
        'created_at',
        'updated_at',
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """Don't allow manual creation"""
        return False


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    """Admin configuration for Quotation model"""

    list_display = [
        'quotation_number',
        'institution_display',
        'institution_type_display',
        'created_by',
        'status_badge',
        'cin7_sync_status_badge',
        'total_display',
        'created_at',
        'expires_at',
    ]

    list_filter = [
        'status',
        'cin7_sync_status',
        'created_at',
        'expires_at',
        'approved_at',
        'submitted_for_approval_at',
        'account_manager_approved_at',
    ]

    search_fields = [
        'quotation_number',
        'created_by__email',
        'created_by__first_name',
        'created_by__last_name',
        'reference_number',
        'notes',
    ]

    readonly_fields = [
        'id',
        'quotation_number',
        'created_at',
        'updated_at',
        'approved_at',
        'rejected_at',
        'version',
        'subtotal',
        'tax_amount',
        'total',
    ]

    fieldsets = (
        ('Quotation Information', {
            'fields': (
                'id',
                'quotation_number',
                'reference_number',
                'version',
                'status',
                'is_locked',
            )
        }),
        ('User and Institution', {
            'fields': (
                'created_by',
                'institution_content_type',
                'institution_object_id',
            )
        }),
        ('Pricing', {
            'fields': (
                'subtotal',
                'discount_percentage',
                'discount_amount',
                'tax_percentage',
                'tax_amount',
                'total',
            )
        }),
        ('Dates', {
            'fields': (
                'created_at',
                'updated_at',
                'expires_at',
                'approved_at',
                'rejected_at',
            )
        }),
        ('Approval/Rejection', {
            'fields': (
                'approved_by',
                'rejected_by',
                'rejection_reason',
            )
        }),
        ('Notes', {
            'fields': (
                'notes',
                'customer_notes',
                'terms_and_conditions',
            ),
            'classes': ('collapse',)
        }),
    )

    inlines = [QuotationItemInline, QuotationVersionInline, CIN7OrderMappingInline]

    actions = [
        'mark_as_approved',
        'mark_as_rejected',
        'mark_as_cancelled',
        'recalculate_totals',
        'sync_to_cin7',
        'retry_failed_sync',
    ]

    def institution_display(self, obj):
        """Display institution name"""
        return obj.institution_name
    institution_display.short_description = 'Institution'

    def institution_type_display(self, obj):
        """Display institution type"""
        return obj.institution_type
    institution_type_display.short_description = 'Type'

    def status_badge(self, obj):
        """Display status as colored badge"""
        colors = {
            'draft': '#6c757d',      # Gray
            'pending': '#ffc107',    # Amber
            'approved': '#28a745',   # Green
            'rejected': '#dc3545',   # Red
            'expired': '#6c757d',    # Gray
            'cancelled': '#dc3545',  # Red
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="padding: 3px 8px; border-radius: 3px; background-color: {}; color: white; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def total_display(self, obj):
        """Display total with currency"""
        return format_html('<strong>R {:,.2f}</strong>', obj.total)
    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'

    def mark_as_approved(self, request, queryset):
        """Mark selected quotations as approved"""
        count = 0
        for quotation in queryset:
            if quotation.status not in ['approved', 'rejected']:
                try:
                    quotation.approve(request.user, 'Bulk approved from admin')
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error approving {quotation.quotation_number}: {str(e)}', level='error')

        if count > 0:
            self.message_user(request, f'{count} quotation(s) approved successfully.')
    mark_as_approved.short_description = 'Mark selected as approved'

    def mark_as_rejected(self, request, queryset):
        """Mark selected quotations as rejected"""
        count = 0
        for quotation in queryset:
            if quotation.status not in ['approved', 'rejected']:
                try:
                    quotation.reject(request.user, 'Bulk rejected from admin')
                    count += 1
                except Exception as e:
                    self.message_user(request, f'Error rejecting {quotation.quotation_number}: {str(e)}', level='error')

        if count > 0:
            self.message_user(request, f'{count} quotation(s) rejected successfully.')
    mark_as_rejected.short_description = 'Mark selected as rejected'

    def mark_as_cancelled(self, request, queryset):
        """Mark selected quotations as cancelled"""
        count = queryset.update(status='cancelled')
        self.message_user(request, f'{count} quotation(s) marked as cancelled.')
    mark_as_cancelled.short_description = 'Mark selected as cancelled'

    def recalculate_totals(self, request, queryset):
        """Recalculate totals for selected quotations"""
        count = 0
        for quotation in queryset:
            try:
                quotation.calculate_totals()
                count += 1
            except Exception as e:
                self.message_user(request, f'Error recalculating {quotation.quotation_number}: {str(e)}', level='error')

        if count > 0:
            self.message_user(request, f'Totals recalculated for {count} quotation(s).')
    recalculate_totals.short_description = 'Recalculate totals'

    def cin7_sync_status_badge(self, obj):
        """Display CIN7 sync status as colored badge"""
        colors = {
            'not_required': '#6c757d',  # Gray
            'pending': '#ffc107',       # Amber
            'syncing': '#17a2b8',       # Cyan
            'synced': '#28a745',        # Green
            'failed': '#dc3545',        # Red
        }
        color = colors.get(obj.cin7_sync_status, '#6c757d')
        return format_html(
            '<span style="padding: 3px 8px; border-radius: 3px; background-color: {}; color: white; font-weight: bold;">{}</span>',
            color,
            obj.get_cin7_sync_status_display()
        )
    cin7_sync_status_badge.short_description = 'CIN7 Status'

    def sync_to_cin7(self, request, queryset):
        """Manually trigger CIN7 sync for selected quotations"""
        if not request.user.is_admin:
            self.message_user(request, 'Only administrators can sync quotations to CIN7.', level='error')
            return

        from quotations.services.cin7_service import CIN7Service

        success_count = 0
        error_count = 0

        for quotation in queryset:
            if not quotation.can_be_synced_to_cin7():
                self.message_user(
                    request,
                    f'{quotation.quotation_number}: Not eligible for CIN7 sync (must be approved by account manager)',
                    level='warning'
                )
                error_count += 1
                continue

            try:
                cin7_service = CIN7Service()
                cin7_service.sync_quotation_to_cin7(quotation)
                success_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'{quotation.quotation_number}: Sync failed - {str(e)}',
                    level='error'
                )
                error_count += 1

        if success_count > 0:
            self.message_user(request, f'{success_count} quotation(s) synced to CIN7 successfully.')
        if error_count > 0:
            self.message_user(request, f'{error_count} quotation(s) failed to sync.', level='warning')

    sync_to_cin7.short_description = 'Sync to CIN7'

    def retry_failed_sync(self, request, queryset):
        """Retry CIN7 sync for quotations with failed sync status"""
        if not request.user.is_admin:
            self.message_user(request, 'Only administrators can retry CIN7 sync.', level='error')
            return

        from quotations.services.cin7_service import CIN7Service

        failed_quotations = queryset.filter(cin7_sync_status='failed')
        if not failed_quotations.exists():
            self.message_user(request, 'No quotations with failed sync status in selection.', level='warning')
            return

        success_count = 0
        error_count = 0

        for quotation in failed_quotations:
            try:
                cin7_service = CIN7Service()
                cin7_service.sync_quotation_to_cin7(quotation)
                success_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'{quotation.quotation_number}: Retry failed - {str(e)}',
                    level='error'
                )
                error_count += 1

        if success_count > 0:
            self.message_user(request, f'{success_count} quotation(s) retried successfully.')
        if error_count > 0:
            self.message_user(request, f'{error_count} quotation(s) still failed.', level='warning')

    retry_failed_sync.short_description = 'Retry failed CIN7 sync'


@admin.register(QuotationItem)
class QuotationItemAdmin(admin.ModelAdmin):
    """Admin configuration for QuotationItem model"""

    list_display = [
        'quotation_number_display',
        'product_name',
        'product_type',
        'quantity',
        'unit_price_display',
        'line_total_display',
    ]

    list_filter = [
        'product_content_type',
        'created_at',
    ]

    search_fields = [
        'quotation__quotation_number',
        'product_name',
        'product_sku',
    ]

    readonly_fields = [
        'id',
        'line_total',
        'created_at',
        'updated_at',
        'product_snapshot',
    ]

    fieldsets = (
        ('Quotation', {
            'fields': ('quotation',)
        }),
        ('Product Reference', {
            'fields': (
                'product_content_type',
                'product_object_id',
            )
        }),
        ('Item Details', {
            'fields': (
                'product_name',
                'product_sku',
                'product_image_url',
                'quantity',
                'unit_price',
                'line_total',
                'variations',
                'notes',
            )
        }),
        ('Product Snapshot', {
            'fields': ('product_snapshot',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'id',
                'sort_order',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    def quotation_number_display(self, obj):
        """Display quotation number with link"""
        url = reverse('admin:quotations_quotation_change', args=[obj.quotation.pk])
        return format_html('<a href="{}">{}</a>', url, obj.quotation.quotation_number)
    quotation_number_display.short_description = 'Quotation'

    def unit_price_display(self, obj):
        """Display unit price with currency"""
        return f'R {obj.unit_price:,.2f}'
    unit_price_display.short_description = 'Unit Price'
    unit_price_display.admin_order_field = 'unit_price'

    def line_total_display(self, obj):
        """Display line total with currency"""
        return format_html('<strong>R {:,.2f}</strong>', obj.line_total)
    line_total_display.short_description = 'Line Total'
    line_total_display.admin_order_field = 'line_total'


@admin.register(CustomerInstitutionAssignment)
class CustomerInstitutionAssignmentAdmin(admin.ModelAdmin):
    """Admin configuration for CustomerInstitutionAssignment model"""

    list_display = [
        'customer_display',
        'institution_display',
        'institution_type_display',
        'is_active',
        'assigned_date',
        'created_by',
    ]

    list_filter = [
        'is_active',
        'assigned_date',
        'institution_content_type',
    ]

    search_fields = [
        'customer__email',
        'customer__first_name',
        'customer__last_name',
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Assignment', {
            'fields': (
                'customer',
                'institution_content_type',
                'institution_object_id',
                'is_active',
            )
        }),
        ('Details', {
            'fields': (
                'assigned_date',
                'notes',
            )
        }),
        ('Metadata', {
            'fields': (
                'id',
                'created_by',
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate_assignments', 'deactivate_assignments']

    def customer_display(self, obj):
        """Display customer name with link"""
        url = reverse('admin:authentication_user_change', args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.get_full_name())
    customer_display.short_description = 'Customer'

    def institution_display(self, obj):
        """Display institution name"""
        institution_name = getattr(obj.institution, 'name', None) or getattr(obj.institution, 'org_name', 'Unknown')
        return institution_name
    institution_display.short_description = 'Institution'

    def institution_type_display(self, obj):
        """Display institution type"""
        if not obj.institution_content_type:
            return 'Unknown'
        model_name = obj.institution_content_type.model
        type_map = {
            'school': 'School',
            'wholesaleschool': 'Wholesale School',
            'lottoclub': 'LOTTO Club',
            'sasclub': 'SAS Club',
        }
        return type_map.get(model_name, model_name.title())
    institution_type_display.short_description = 'Type'

    def activate_assignments(self, request, queryset):
        """Activate selected assignments"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} assignment(s) activated.')
    activate_assignments.short_description = 'Activate selected assignments'

    def deactivate_assignments(self, request, queryset):
        """Deactivate selected assignments"""
        for assignment in queryset:
            assignment.deactivate(request.user)
        self.message_user(request, f'{queryset.count()} assignment(s) deactivated.')
    deactivate_assignments.short_description = 'Deactivate selected assignments'


@admin.register(QuotationVersion)
class QuotationVersionAdmin(admin.ModelAdmin):
    """Admin configuration for QuotationVersion model"""

    list_display = [
        'quotation_number_display',
        'version_number',
        'created_at',
        'created_by',
    ]

    list_filter = [
        'created_at',
    ]

    search_fields = [
        'quotation__quotation_number',
        'change_description',
    ]

    readonly_fields = [
        'id',
        'quotation',
        'version_number',
        'snapshot_data',
        'change_description',
        'created_at',
        'created_by',
    ]

    fieldsets = (
        ('Version Information', {
            'fields': (
                'id',
                'quotation',
                'version_number',
                'change_description',
            )
        }),
        ('Snapshot Data', {
            'fields': ('snapshot_data',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'created_by',
            )
        }),
    )

    def quotation_number_display(self, obj):
        """Display quotation number with link"""
        url = reverse('admin:quotations_quotation_change', args=[obj.quotation.pk])
        return format_html('<a href="{}">{}</a>', url, obj.quotation.quotation_number)
    quotation_number_display.short_description = 'Quotation'

    def has_add_permission(self, request):
        """Disable manual creation of versions"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deletion of versions"""
        return False


@admin.register(CIN7OrderMapping)
class CIN7OrderMappingAdmin(admin.ModelAdmin):
    """Admin configuration for CIN7OrderMapping model"""

    list_display = [
        'quotation_number_display',
        'cin7_reference',
        'cin7_order_id',
        'sync_status_badge',
        'sync_attempts',
        'created_at',
    ]

    list_filter = [
        'sync_status',
        'created_at',
        'last_sync_attempt',
    ]

    search_fields = [
        'quotation__quotation_number',
        'cin7_order_id',
        'cin7_reference',
    ]

    readonly_fields = [
        'id',
        'quotation',
        'cin7_order_id',
        'cin7_reference',
        'cin7_stage',
        'sync_status',
        'sync_attempts',
        'last_sync_attempt',
        'error_message',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Quotation Reference', {
            'fields': (
                'id',
                'quotation',
            )
        }),
        ('CIN7 Order Details', {
            'fields': (
                'cin7_order_id',
                'cin7_reference',
                'cin7_stage',
            )
        }),
        ('Sync Status', {
            'fields': (
                'sync_status',
                'sync_attempts',
                'last_sync_attempt',
                'error_message',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )

    def quotation_number_display(self, obj):
        """Display quotation number with link"""
        url = reverse('admin:quotations_quotation_change', args=[obj.quotation.pk])
        return format_html('<a href="{}">{}</a>', url, obj.quotation.quotation_number)
    quotation_number_display.short_description = 'Quotation'

    def sync_status_badge(self, obj):
        """Display sync status as colored badge"""
        colors = {
            'pending': '#ffc107',    # Amber
            'syncing': '#17a2b8',    # Cyan
            'synced': '#28a745',     # Green
            'failed': '#dc3545',     # Red
            'cancelled': '#6c757d',  # Gray
        }
        color = colors.get(obj.sync_status, '#6c757d')
        return format_html(
            '<span style="padding: 3px 8px; border-radius: 3px; background-color: {}; color: white; font-weight: bold;">{}</span>',
            color,
            obj.get_sync_status_display()
        )
    sync_status_badge.short_description = 'Sync Status'

    def has_add_permission(self, request):
        """Disable manual creation"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup"""
        return request.user.is_admin
