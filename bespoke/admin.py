from django.contrib import admin
from .models import (
    BespokeCategory,
    BespokeProduct,
    BespokeProductCategoryAssignment,
    BespokeProductVariation,
    BespokeSyncLog
)


@admin.register(BespokeCategory)
class BespokeCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'level', 'is_active', 'last_synced']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug', 'cin7_id']
    readonly_fields = ['cin7_id', 'slug', 'created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Category Information', {
            'fields': ('cin7_id', 'name', 'slug', 'parent', 'description')
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BespokeProduct)
class BespokeProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'product_type', 'display_price', 'stock_status', 'cin7_brand', 'is_active', 'last_synced']
    list_filter = ['product_type', 'stock_status', 'is_active', 'cin7_brand']
    search_fields = ['name', 'sku', 'cin7_id', 'barcode']
    readonly_fields = ['cin7_id', 'slug', 'margin_75_price', 'date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Product Information', {
            'fields': ('cin7_id', 'name', 'slug', 'product_type', 'sku', 'barcode')
        }),
        ('Description', {
            'fields': ('short_description', 'description'),
            'classes': ('collapse',)
        }),
        ('Pricing', {
            'fields': ('cost_price', 'retail_price', 'price', 'margin_75_price')
        }),
        ('Stock Management', {
            'fields': ('stock_status', 'stock_quantity', 'stock_on_hand', 'stock_available')
        }),
        ('CIN7 Details', {
            'fields': ('cin7_brand', 'cin7_supplier', 'cin7_category_path', 'cin7_option1', 'cin7_option2', 'cin7_option3'),
            'classes': ('collapse',)
        }),
        ('Image', {
            'fields': ('featured_image_url',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
    )


@admin.register(BespokeProductCategoryAssignment)
class BespokeProductCategoryAssignmentAdmin(admin.ModelAdmin):
    list_display = ['product', 'category', 'created_at']
    list_filter = ['category']
    search_fields = ['product__name', 'category__name']
    readonly_fields = ['created_at']


@admin.register(BespokeProductVariation)
class BespokeProductVariationAdmin(admin.ModelAdmin):
    list_display = ['variation_name', 'parent_product', 'sku', 'display_price', 'stock_status', 'is_active']
    list_filter = ['stock_status', 'is_active']
    search_fields = ['sku', 'cin7_id', 'barcode', 'parent_product__name']
    readonly_fields = ['cin7_id', 'margin_75_price', 'date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Variation Information', {
            'fields': ('cin7_id', 'parent_product', 'sku', 'barcode', 'description')
        }),
        ('Variation Attributes', {
            'fields': ('option1_value', 'option2_value', 'option3_value')
        }),
        ('Pricing', {
            'fields': ('cost_price', 'retail_price', 'price', 'margin_75_price')
        }),
        ('Stock Management', {
            'fields': ('stock_status', 'stock_quantity', 'stock_on_hand', 'stock_available')
        }),
        ('Image', {
            'fields': ('image_url',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
    )


@admin.register(BespokeSyncLog)
class BespokeSyncLogAdmin(admin.ModelAdmin):
    list_display = ['sync_type', 'status', 'products_synced', 'categories_synced', 'variations_synced', 'duration_seconds', 'started_at']
    list_filter = ['sync_type', 'status', 'started_at']
    search_fields = ['error_message']
    readonly_fields = ['sync_type', 'status', 'categories_synced', 'products_synced', 'variations_synced',
                      'errors_count', 'started_at', 'completed_at', 'duration_seconds',
                      'error_message', 'details']

    fieldsets = (
        ('Sync Information', {
            'fields': ('sync_type', 'status')
        }),
        ('Statistics', {
            'fields': ('categories_synced', 'products_synced', 'variations_synced', 'errors_count')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        ('Details', {
            'fields': ('error_message', 'details'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
