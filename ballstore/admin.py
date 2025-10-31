from django.contrib import admin
from .models import (
    BallStoreCategory,
    BallStoreProduct,
    BallStoreProductVariation,
    BallStoreProductImage,
    BallStoreSyncLog
)


@admin.register(BallStoreCategory)
class BallStoreCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'product_count', 'level', 'is_active', 'last_synced']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug']
    readonly_fields = ['wc_id', 'slug', 'created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Category Information', {
            'fields': ('wc_id', 'name', 'slug', 'parent', 'description', 'product_count')
        }),
        ('Settings', {
            'fields': ('display_type', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BallStoreProduct)
class BallStoreProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'product_type', 'display_price', 'stock_status', 'is_active', 'last_synced']
    list_filter = ['product_type', 'stock_status', 'on_sale', 'is_active', 'categories']
    search_fields = ['name', 'sku', 'wc_id']
    readonly_fields = ['wc_id', 'slug', 'permalink', 'date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced']
    filter_horizontal = ['categories']

    fieldsets = (
        ('Product Information', {
            'fields': ('wc_id', 'name', 'slug', 'permalink', 'product_type', 'sku')
        }),
        ('Description', {
            'fields': ('short_description', 'description'),
            'classes': ('collapse',)
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price', 'on_sale')
        }),
        ('Stock Management', {
            'fields': ('stock_status', 'stock_quantity', 'manage_stock')
        }),
        ('Categories & Images', {
            'fields': ('categories', 'featured_image_url')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
    )


@admin.register(BallStoreProductVariation)
class BallStoreProductVariationAdmin(admin.ModelAdmin):
    list_display = ['variation_name', 'parent_product', 'sku', 'display_price', 'stock_status', 'is_active']
    list_filter = ['stock_status', 'on_sale', 'is_active']
    search_fields = ['sku', 'wc_id', 'parent_product__name']
    readonly_fields = ['wc_id', 'date_created', 'date_modified', 'created_at', 'updated_at', 'last_synced']

    fieldsets = (
        ('Variation Information', {
            'fields': ('wc_id', 'parent_product', 'sku', 'description', 'attributes')
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price', 'on_sale')
        }),
        ('Stock Management', {
            'fields': ('stock_status', 'stock_quantity', 'manage_stock')
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


@admin.register(BallStoreProductImage)
class BallStoreProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'position', 'name', 'alt']
    list_filter = ['product']
    search_fields = ['product__name', 'name', 'alt']
    readonly_fields = ['wc_id', 'created_at', 'updated_at']

    fieldsets = (
        ('Image Information', {
            'fields': ('wc_id', 'product', 'src', 'name', 'alt', 'position')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BallStoreSyncLog)
class BallStoreSyncLogAdmin(admin.ModelAdmin):
    list_display = ['sync_type', 'status', 'products_synced', 'categories_synced', 'variations_synced', 'duration_seconds', 'started_at']
    list_filter = ['sync_type', 'status', 'started_at']
    search_fields = ['error_message']
    readonly_fields = ['sync_type', 'status', 'categories_synced', 'products_synced', 'variations_synced',
                      'images_synced', 'errors_count', 'started_at', 'completed_at', 'duration_seconds',
                      'error_message', 'details']

    fieldsets = (
        ('Sync Information', {
            'fields': ('sync_type', 'status')
        }),
        ('Statistics', {
            'fields': ('categories_synced', 'products_synced', 'variations_synced', 'images_synced', 'errors_count')
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
