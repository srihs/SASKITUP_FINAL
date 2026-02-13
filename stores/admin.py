from django.contrib import admin
from django.utils.html import format_html
from .models import Store, StoreOpeningHours, StorePeriod


class StorePeriodInline(admin.TabularInline):
    """Inline admin for store periods."""
    model = StorePeriod.stores.through
    extra = 0
    verbose_name = 'Period'
    verbose_name_plural = 'Periods'


class StoreOpeningHoursInline(admin.TabularInline):
    """Inline admin for store opening hours."""
    model = StoreOpeningHours
    extra = 7  # Show 7 rows by default (one for each day)
    fields = ['period', 'day_of_week', 'opening_time', 'closing_time', 'is_closed', 'notes']
    ordering = ['period', 'day_of_week']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """Admin interface for Store model."""

    list_display = [
        'name',
        'city',
        'suburb',
        'phone',
        'email',
        'is_active',
        'display_order',
        'school_count'
    ]

    list_filter = ['is_active', 'city', 'suburb']

    search_fields = ['name', 'city', 'suburb', 'address_line1', 'phone', 'email']

    filter_horizontal = ['schools']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active', 'display_order')
        }),
        ('Contact Information', {
            'fields': ('phone', 'email')
        }),
        ('Address', {
            'fields': (
                'address_line1',
                'address_line2',
                'suburb',
                'city',
                'postal_code'
            )
        }),
        ('Location Coordinates', {
            'fields': ('latitude', 'longitude'),
            'description': 'GPS coordinates for mapping (optional)'
        }),
        ('Schools Serviced', {
            'fields': ('schools',),
            'description': 'Select which schools this store services'
        }),
    )

    inlines = [StorePeriodInline, StoreOpeningHoursInline]

    readonly_fields = []

    def school_count(self, obj):
        """Display the number of schools serviced by this store."""
        return obj.schools.count()
    school_count.short_description = 'Schools Serviced'

    def has_add_permission(self, request):
        """Only admins can add stores."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Only admins can edit stores."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only admins can delete stores."""
        return request.user.is_superuser

    class Meta:
        verbose_name = 'Store'
        verbose_name_plural = 'Stores'


@admin.register(StorePeriod)
class StorePeriodAdmin(admin.ModelAdmin):
    """Admin interface for StorePeriod model."""

    list_display = [
        'name',
        'store_list',
        'period_type',
        'start_date',
        'end_date',
        'priority',
        'status_badge',
        'is_active'
    ]

    list_filter = ['period_type', 'is_active', 'start_date']

    search_fields = ['name', 'stores__name', 'description']

    ordering = ['-start_date', '-priority']

    filter_horizontal = ['stores']

    fieldsets = (
        ('Period Information', {
            'fields': ('name', 'period_type', 'description')
        }),
        ('Stores', {
            'fields': ('stores',),
            'description': 'Select which stores this period applies to'
        }),
        ('Date Range', {
            'fields': ('start_date', 'end_date')
        }),
        ('Settings', {
            'fields': ('priority', 'is_active')
        }),
    )

    def store_list(self, obj):
        """Display list of stores this period applies to."""
        stores = list(obj.stores.all()[:3])
        store_names = ", ".join([s.name for s in stores])
        if obj.stores.count() > 3:
            store_names += f" (+{obj.stores.count() - 3} more)"
        return store_names if store_names else "No stores"
    store_list.short_description = 'Stores'

    def status_badge(self, obj):
        """Show current status of the period."""
        if obj.is_currently_active():
            return format_html('<span style="color: green;">● Active Now</span>')
        elif obj.is_past:
            return format_html('<span style="color: gray;">● Ended</span>')
        elif obj.is_future:
            return format_html('<span style="color: blue;">● Upcoming</span>')
        else:
            return format_html('<span style="color: red;">● Inactive</span>')
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        """Only admins can add periods."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Only admins can edit periods."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only admins can delete periods."""
        return request.user.is_superuser


@admin.register(StoreOpeningHours)
class StoreOpeningHoursAdmin(admin.ModelAdmin):
    """Admin interface for StoreOpeningHours model."""

    list_display = [
        'store',
        'period_name',
        'get_day_name',
        'opening_time',
        'closing_time',
        'is_closed',
        'notes'
    ]

    list_filter = ['store', 'period', 'day_of_week', 'is_closed']

    search_fields = ['store__name', 'period__name']

    ordering = ['store', 'period', 'day_of_week']

    def get_day_name(self, obj):
        """Get the day name for display."""
        return dict(StoreOpeningHours.DAYS_OF_WEEK)[obj.day_of_week]
    get_day_name.short_description = 'Day'

    def period_name(self, obj):
        """Get the period name."""
        return obj.period.name if obj.period else 'Default Hours'
    period_name.short_description = 'Period'

    def has_add_permission(self, request):
        """Only admins can add opening hours."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Only admins can edit opening hours."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only admins can delete opening hours."""
        return request.user.is_superuser
