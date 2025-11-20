from django.contrib import admin
from .models import School, CIN7Contact


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['school_id', 'org_name', 'org_type', 'add1_city', 'regional_council', 'total', 'status']
    list_filter = ['org_type', 'regional_council', 'authority', 'status', 'coed_status']
    search_fields = ['school_id', 'org_name', 'add1_city', 'email']
    ordering = ['org_name']
    readonly_fields = ['created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Basic Information', {
            'fields': ('school_id', 'org_name', 'org_type', 'authority', 'status')
        }),
        ('Contact Information', {
            'fields': ('contact1_name', 'telephone', 'fax', 'email', 'url'),
            'classes': ('collapse',)
        }),
        ('Address Information', {
            'fields': (
                ('add1_line1', 'add1_suburb', 'add1_city'),
                ('add2_line1', 'add2_suburb', 'add2_city', 'add2_postal_code')
            ),
            'classes': ('collapse',)
        }),
        ('Location & Administrative', {
            'fields': (
                'latitude', 'longitude', 'regional_council', 'territorial_authority',
                'education_region', 'general_electorate', 'maori_electorate'
            ),
            'classes': ('collapse',)
        }),
        ('School Characteristics', {
            'fields': (
                'coed_status', 'enrolment_scheme', 'language_of_instruction',
                'boarding_facilities', 'date_school_opened'
            ),
            'classes': ('collapse',)
        }),
        ('Enrollment Data', {
            'fields': (
                'roll_date', 'total', 'european', 'maori', 'pacific',
                'asian', 'melaa', 'other', 'international'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CIN7Contact)
class CIN7ContactAdmin(admin.ModelAdmin):
    list_display = ['cin7_id', 'company', 'email', 'phone', 'delivery_city', 'delivery_state', 'last_synced_at']
    list_filter = ['last_synced_at', 'delivery_state', 'billing_state']
    search_fields = ['cin7_id', 'company', 'email', 'first_name', 'last_name', 'phone', 'delivery_city', 'billing_city']
    ordering = ['company']
    readonly_fields = ['created_at', 'updated_at', 'last_synced_at']

    fieldsets = (
        ('Contact Information', {
            'fields': ('cin7_id', 'company', 'email', 'first_name', 'last_name', 'phone')
        }),
        ('Delivery Address', {
            'fields': ('delivery_address1', 'delivery_address2', 'delivery_city', 'delivery_state', 'delivery_postcode')
        }),
        ('Billing Address', {
            'fields': ('billing_address1', 'billing_address2', 'billing_city', 'billing_state', 'billing_postcode')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_synced_at'),
            'classes': ('collapse',)
        }),
    )
