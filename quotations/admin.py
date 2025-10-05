"""
Django admin configuration for quotations app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from .models import (
    Quotation,
    QuotationItem,
    CustomerInstitutionAssignment,
    QuotationVersion
)


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


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    """Admin configuration for Quotation model"""

    list_display = [
        'quotation_number',
        'institution_display',
        'institution_type_display',
        'created_by',
        'status_badge',
        'total_display',
        'created_at',
        'expires_at',
    ]

    list_filter = [
        'status',
        'created_at',
        'expires_at',
        'approved_at',
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

    inlines = [QuotationItemInline, QuotationVersionInline]

    actions = [
        'mark_as_approved',
        'mark_as_rejected',
        'mark_as_cancelled',
        'recalculate_totals',
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
