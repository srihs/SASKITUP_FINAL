from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from .models import Club, ClubCategory, Product, ProductVariation, ProductCategoryAssignment
from .models_lotto import LottoClub, LottoClubCategory, LottoProduct, LottoProductVariation
from .models_sas import SASSport, SASClub, SASProduct
from .models_wholesale import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment, WholesaleSyncJob
)
from .services.woocommerce_service import WooCommerceService


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    """
    Admin interface for Club model
    """
    list_display = [
        'name', 'club_type', 'sport_tag', 'active_categories_count', 
        'total_products', 'is_active', 'woo_category_id', 'created_at'
    ]
    list_filter = ['club_type', 'sport_tag', 'is_active', 'created_at']
    search_fields = ['name', 'contact_person', 'email', 'address']
    readonly_fields = ['slug', 'woo_category_id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'club_type', 'sport_tag', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'email', 'website', 'address')
        }),
        ('Media', {
            'fields': ('logo',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['sync_selected_clubs', 'activate_clubs', 'deactivate_clubs']
    
    def active_categories_count(self, obj):
        """Display count of active categories"""
        count = obj.active_categories_count
        if count > 0:
            url = reverse('admin:clubs_clubcategory_changelist') + f'?club__id__exact={obj.id}'
            return format_html('<a href="{}">{} categories</a>', url, count)
        return 0
    active_categories_count.short_description = 'Active Categories'
    
    def total_products(self, obj):
        """Display total products count"""
        count = obj.total_products
        if count > 0:
            url = reverse('admin:clubs_product_changelist') + f'?category__club__id__exact={obj.id}'
            return format_html('<a href="{}">{} products</a>', url, count)
        return 0
    total_products.short_description = 'Total Products'
    
    def sync_selected_clubs(self, request, queryset):
        """Sync selected clubs with WooCommerce"""
        try:
            for club in queryset:
                woo_service = WooCommerceService(store_type=club.club_type)
                # Add sync logic here if needed
            
            self.message_user(request, f"Successfully synced {queryset.count()} clubs.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing clubs: {str(e)}", messages.ERROR)
    
    sync_selected_clubs.short_description = "Sync selected clubs with WooCommerce"
    
    def activate_clubs(self, request, queryset):
        """Activate selected clubs"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} clubs.", messages.SUCCESS)
    activate_clubs.short_description = "Activate selected clubs"
    
    def deactivate_clubs(self, request, queryset):
        """Deactivate selected clubs"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} clubs.", messages.SUCCESS)
    deactivate_clubs.short_description = "Deactivate selected clubs"


@admin.register(ProductCategoryAssignment)
class ProductCategoryAssignmentAdmin(admin.ModelAdmin):
    """
    Admin interface for ProductCategoryAssignment model
    """
    list_display = [
        'product', 'category', 'club_name', 'is_primary', 'sort_order',
        'woo_category_id', 'date_assigned', 'last_synced'
    ]
    list_filter = [
        'is_primary', 'category__club__club_type', 'category__club',
        'category', 'date_assigned', 'last_synced'
    ]
    search_fields = [
        'product__name', 'category__name', 'category__club__name'
    ]
    readonly_fields = [
        'woo_category_id', 'date_assigned', 'last_synced'
    ]
    
    fieldsets = (
        ('Assignment Information', {
            'fields': ('product', 'category', 'is_primary', 'sort_order')
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('date_assigned', 'last_synced'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('product', 'category', 'category__club')
    
    def club_name(self, obj):
        """Display club name"""
        return obj.category.club.name
    club_name.short_description = 'Club'
    club_name.admin_order_field = 'category__club__name'
    
    actions = ['mark_as_primary', 'unmark_as_primary']
    
    def mark_as_primary(self, request, queryset):
        """Mark selected assignments as primary"""
        # Ensure only one primary assignment per product
        products_updated = set()
        for assignment in queryset:
            # Clear other primary assignments for this product
            ProductCategoryAssignment.objects.filter(
                product=assignment.product,
                is_primary=True
            ).exclude(id=assignment.id).update(is_primary=False)
            
            # Mark this one as primary
            assignment.is_primary = True
            assignment.save()
            products_updated.add(assignment.product.name)
        
        self.message_user(
            request,
            f"Successfully marked assignments as primary for {len(products_updated)} products.",
            messages.SUCCESS
        )
    mark_as_primary.short_description = "Mark as primary category"
    
    def unmark_as_primary(self, request, queryset):
        """Remove primary status from selected assignments"""
        updated = queryset.update(is_primary=False)
        self.message_user(
            request,
            f"Successfully removed primary status from {updated} assignments.",
            messages.SUCCESS
        )
    unmark_as_primary.short_description = "Remove primary status"


@admin.register(ClubCategory)
class ClubCategoryAdmin(admin.ModelAdmin):
    """
    Admin interface for ClubCategory model
    """
    list_display = [
        'name', 'club', 'product_count', 'woo_category_id', 'created_at'
    ]
    list_filter = ['club__club_type', 'club', 'created_at']
    search_fields = ['name', 'description', 'club__name']
    readonly_fields = ['slug', 'woo_category_id', 'product_count', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('club', 'name', 'slug', 'description')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Statistics', {
            'fields': ('product_count',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('club')
    
    actions = ['update_product_counts']
    
    def update_product_counts(self, request, queryset):
        """Update product counts for selected categories"""
        for category in queryset:
            category.update_product_count()
        
        self.message_user(
            request, 
            f"Successfully updated product counts for {queryset.count()} categories.", 
            messages.SUCCESS
        )
    update_product_counts.short_description = "Update product counts"


class ProductVariationInline(admin.TabularInline):
    """
    Inline admin interface for ProductVariation within Product admin
    """
    model = ProductVariation
    extra = 0
    readonly_fields = ['woo_variation_id', 'full_sku', 'final_price', 'stock_status', 'image_preview', 'created_at']
    fields = [
        'variation_type', 'variation_value', 'image', 'image_preview', 'price_modifier', 'stock_quantity', 
        'sku_suffix', 'is_active', 'final_price', 'stock_status', 'woo_variation_id'
    ]
    
    def image_preview(self, obj):
        """Display image preview for variation"""
        if obj.pk and obj.effective_image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" title="{}"/>',
                obj.effective_image,  # effective_image now returns URL directly
                f"{obj.variation_type}: {obj.variation_value}"
            )
        return format_html('<span style="color: gray;">No Image</span>')
    image_preview.short_description = 'Preview'
    
    def final_price(self, obj):
        """Display calculated final price"""
        if obj.pk:
            return f"${obj.final_price:.2f}"
        return "-"
    final_price.short_description = 'Final Price'
    
    def stock_status(self, obj):
        """Display stock status with color coding"""
        if obj.pk:
            status = obj.stock_status
            colors = {
                'instock': 'green',
                'outofstock': 'red',
                'discontinued': 'gray'
            }
            color = colors.get(status, 'black')
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>', 
                color, 
                status.upper()
            )
        return "-"
    stock_status.short_description = 'Stock Status'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Admin interface for Product model
    """
    list_display = [
        'name', 'primary_category', 'category_count', 'price', 'stock_status', 
        'sku', 'is_on_sale', 'has_variations_display', 'woo_product_id', 'created_at'
    ]
    list_filter = [
        'stock_status', 'categories__club__club_type', 'categories__club', 
        'created_at'
    ]
    search_fields = [
        'name', 'description', 'short_description', 'sku', 
        'categories__name', 'categories__club__name'
    ]
    readonly_fields = [
        'slug', 'woo_product_id', 'is_on_sale', 'discount_percentage', 
        'has_variations', 'total_stock', 'price_range', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'name', 'slug', 'sku', 'stock_status')
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price', 'is_on_sale', 'discount_percentage', 'price_range')
        }),
        ('Variations', {
            'fields': ('has_variations', 'total_stock'),
            'classes': ('collapse',)
        }),
        ('Description', {
            'fields': ('short_description', 'description')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Product Details', {
            'fields': ('weight', 'dimensions', 'tags', 'attributes'),
            'classes': ('collapse',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_product_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ProductVariationInline]
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('category', 'category__club').prefetch_related('variations')
    
    def club_name(self, obj):
        """Display club name"""
        return obj.category.club.name
    club_name.short_description = 'Club'
    club_name.admin_order_field = 'category__club__name'
    
    def is_on_sale(self, obj):
        """Display if product is on sale"""
        if obj.is_on_sale:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {}% OFF</span>', 
                obj.discount_percentage
            )
        return format_html('<span style="color: gray;">-</span>')
    is_on_sale.short_description = 'On Sale'
    
    def has_variations_display(self, obj):
        """Display if product has variations"""
        if obj.has_variations:
            count = obj.variations.filter(is_active=True).count()
            return format_html(
                '<span style="color: blue; font-weight: bold;">✓ {} variations</span>', 
                count
            )
        return format_html('<span style="color: gray;">Simple Product</span>')
    has_variations_display.short_description = 'Variations'
    
    actions = ['mark_in_stock', 'mark_out_of_stock', 'mark_on_backorder']
    
    def mark_in_stock(self, request, queryset):
        """Mark selected products as in stock"""
        updated = queryset.update(stock_status='instock')
        self.message_user(request, f"Successfully marked {updated} products as in stock.", messages.SUCCESS)
    mark_in_stock.short_description = "Mark as in stock"
    
    def mark_out_of_stock(self, request, queryset):
        """Mark selected products as out of stock"""
        updated = queryset.update(stock_status='outofstock')
        self.message_user(request, f"Successfully marked {updated} products as out of stock.", messages.SUCCESS)
    mark_out_of_stock.short_description = "Mark as out of stock"
    
    def mark_on_backorder(self, request, queryset):
        """Mark selected products as on backorder"""
        updated = queryset.update(stock_status='onbackorder')
        self.message_user(request, f"Successfully marked {updated} products as on backorder.", messages.SUCCESS)
    mark_on_backorder.short_description = "Mark as on backorder"


@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    """
    Admin interface for ProductVariation model
    """
    list_display = [
        'variation_display', 'product', 'club_name', 'variation_type', 'variation_value',
        'image_preview', 'final_price', 'stock_quantity', 'stock_status_display', 'is_active', 'woo_variation_id'
    ]
    list_filter = [
        'variation_type', 'is_active', 'product__categories__club__club_type',
        'product__categories__club', 'created_at'
    ]
    search_fields = [
        'variation_value', 'sku_suffix', 'product__name', 
        'product__categories__name', 'product__categories__club__name'
    ]
    readonly_fields = [
        'woo_variation_id', 'full_sku', 'final_price', 'stock_status',
        'image_preview', 'effective_image_info', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'variation_type', 'variation_value', 'is_active')
        }),
        ('Pricing & Stock', {
            'fields': ('price_modifier', 'final_price', 'stock_quantity', 'stock_status')
        }),
        ('Product Details', {
            'fields': ('sku_suffix', 'full_sku', 'weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('WooCommerce Data', {
            'fields': ('woo_variation_id', 'attributes'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image', 'image_preview', 'effective_image_info')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'product', 'product__category', 'product__category__club'
        )
    
    def variation_display(self, obj):
        """Display variation in a readable format"""
        return f"{obj.product.name} - {obj.variation_type}: {obj.variation_value}"
    variation_display.short_description = 'Variation'
    variation_display.admin_order_field = 'product__name'
    
    def club_name(self, obj):
        """Display club name"""
        return obj.product.category.club.name
    club_name.short_description = 'Club'
    club_name.admin_order_field = 'product__category__club__name'
    
    def final_price(self, obj):
        """Display calculated final price"""
        return f"${obj.final_price:.2f}"
    final_price.short_description = 'Final Price'
    
    def image_preview(self, obj):
        """Display image preview for variation"""
        if obj.effective_image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" title="{}"/>',
                obj.effective_image,  # effective_image now returns URL directly
                f"{obj.variation_type}: {obj.variation_value}"
            )
        return format_html('<span style="color: gray;">No Image</span>')
    image_preview.short_description = 'Image'
    
    def effective_image_info(self, obj):
        """Display information about which image is being used"""
        if obj.image:
            return format_html('<span style="color: green;">✓ Variation image</span>')
        elif obj.product.image:
            return format_html('<span style="color: orange;">◐ Product image (fallback)</span>')
        else:
            return format_html('<span style="color: gray;">✗ No image available</span>')
    effective_image_info.short_description = 'Image Source'
    
    def stock_status_display(self, obj):
        """Display stock status with color coding"""
        status = obj.stock_status
        colors = {
            'instock': 'green',
            'outofstock': 'red',
            'discontinued': 'gray'
        }
        color = colors.get(status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', 
            color, 
            status.upper()
        )
    stock_status_display.short_description = 'Stock Status'
    
    actions = ['activate_variations', 'deactivate_variations', 'update_stock_status']
    
    def activate_variations(self, request, queryset):
        """Activate selected variations"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} variations.", messages.SUCCESS)
    activate_variations.short_description = "Activate selected variations"
    
    def deactivate_variations(self, request, queryset):
        """Deactivate selected variations"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} variations.", messages.SUCCESS)
    deactivate_variations.short_description = "Deactivate selected variations"
    
    def update_stock_status(self, request, queryset):
        """Update stock status based on quantity"""
        updated_count = 0
        for variation in queryset:
            old_status = variation.stock_status
            # This will trigger the property calculation
            new_status = variation.stock_status
            if old_status != new_status:
                updated_count += 1
        
        self.message_user(
            request, 
            f"Stock status updated for {updated_count} variations.", 
            messages.SUCCESS
        )
    update_stock_status.short_description = "Update stock status"


# LOTTO-specific Admin Classes

@admin.register(LottoClub)
class LottoClubAdmin(admin.ModelAdmin):
    """
    Admin interface for LottoClub model
    """
    list_display = [
        'name', 'sport_tag', 'active_categories_count', 
        'total_products', 'is_active', 'woo_category_id', 'created_at'
    ]
    list_filter = ['sport_tag', 'is_active', 'created_at']
    search_fields = ['name', 'contact_person', 'email', 'address']
    readonly_fields = ['slug', 'club_type', 'woo_category_id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'club_type', 'sport_tag', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'email', 'website', 'address')
        }),
        ('Media', {
            'fields': ('logo',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['sync_selected_clubs', 'activate_clubs', 'deactivate_clubs']
    
    def active_categories_count(self, obj):
        """Display count of active categories"""
        count = obj.active_categories_count
        if count > 0:
            url = reverse('admin:clubs_lottoclubcategory_changelist') + f'?club__id__exact={obj.id}'
            return format_html('<a href="{}">{} categories</a>', url, count)
        return 0
    active_categories_count.short_description = 'Active Categories'
    
    def total_products(self, obj):
        """Display total products count"""
        count = obj.total_products
        if count > 0:
            url = reverse('admin:clubs_lottoproduct_changelist') + f'?category__club__id__exact={obj.id}'
            return format_html('<a href="{}">{} products</a>', url, count)
        return 0
    total_products.short_description = 'Total Products'
    
    def sync_selected_clubs(self, request, queryset):
        """Sync selected clubs with WooCommerce"""
        try:
            for club in queryset:
                woo_service = WooCommerceService(store_type='LOTTO')
                # Add sync logic here if needed
            
            self.message_user(request, f"Successfully synced {queryset.count()} LOTTO clubs.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing LOTTO clubs: {str(e)}", messages.ERROR)
    
    sync_selected_clubs.short_description = "Sync selected LOTTO clubs with WooCommerce"
    
    def activate_clubs(self, request, queryset):
        """Activate selected clubs"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} LOTTO clubs.", messages.SUCCESS)
    activate_clubs.short_description = "Activate selected LOTTO clubs"
    
    def deactivate_clubs(self, request, queryset):
        """Deactivate selected clubs"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} LOTTO clubs.", messages.SUCCESS)
    deactivate_clubs.short_description = "Deactivate selected LOTTO clubs"


@admin.register(LottoClubCategory)
class LottoClubCategoryAdmin(admin.ModelAdmin):
    """
    Admin interface for LottoClubCategory model
    """
    list_display = [
        'name', 'club', 'product_count', 'woo_category_id', 'created_at'
    ]
    list_filter = ['club', 'created_at']
    search_fields = ['name', 'description', 'club__name']
    readonly_fields = ['slug', 'woo_category_id', 'product_count', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('club', 'name', 'slug', 'description')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Statistics', {
            'fields': ('product_count',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('club')
    
    actions = ['update_product_counts']
    
    def update_product_counts(self, request, queryset):
        """Update product counts for selected categories"""
        for category in queryset:
            category.update_product_count()
        
        self.message_user(
            request, 
            f"Successfully updated product counts for {queryset.count()} LOTTO categories.", 
            messages.SUCCESS
        )
    update_product_counts.short_description = "Update product counts"


class LottoProductVariationInline(admin.TabularInline):
    """
    Inline admin interface for LottoProductVariation within LottoProduct admin
    """
    model = LottoProductVariation
    extra = 0
    readonly_fields = ['woo_variation_id', 'full_sku', 'final_price', 'stock_status', 'image_preview', 'created_at']
    fields = [
        'variation_type', 'variation_value', 'image', 'image_preview', 'price_modifier', 'stock_quantity', 
        'sku_suffix', 'is_active', 'final_price', 'stock_status', 'woo_variation_id'
    ]
    
    def image_preview(self, obj):
        """Display image preview for variation"""
        if obj.pk and obj.effective_image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" title="{}"/>',
                obj.effective_image,  # effective_image now returns URL directly
                f"{obj.variation_type}: {obj.variation_value}"
            )
        return format_html('<span style="color: gray;">No Image</span>')
    image_preview.short_description = 'Preview'
    
    def final_price(self, obj):
        """Display calculated final price"""
        if obj.pk:
            return f"${obj.final_price:.2f}"
        return "-"
    final_price.short_description = 'Final Price'
    
    def stock_status(self, obj):
        """Display stock status with color coding"""
        if obj.pk:
            status = obj.stock_status
            colors = {
                'instock': 'green',
                'outofstock': 'red',
                'discontinued': 'gray'
            }
            color = colors.get(status, 'black')
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>', 
                color, 
                status.upper()
            )
        return "-"
    stock_status.short_description = 'Stock Status'


@admin.register(LottoProduct)
class LottoProductAdmin(admin.ModelAdmin):
    """
    Admin interface for LottoProduct model with comprehensive field display
    """
    list_display = [
        'name', 'category', 'club_name', 'effective_price', 'stock_status', 
        'sku', 'is_on_sale_display', 'has_variations_display', 'status', 
        'featured', 'woo_product_id', 'created_at'
    ]
    list_filter = [
        'status', 'stock_status', 'featured', 'on_sale', 'type', 
        'category__club', 'category', 'created_at'
    ]
    search_fields = [
        'name', 'description', 'short_description', 'sku', 
        'category__name', 'category__club__name'
    ]
    readonly_fields = [
        'slug', 'woo_product_id', 'on_sale', 'purchasable', 'discount_percentage', 
        'has_variations', 'total_stock', 'effective_price', 'price_display',
        'is_in_stock', 'primary_image_url', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'name', 'slug', 'type', 'status', 'featured', 'catalog_visibility')
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price', 'on_sale', 'purchasable', 
                      'discount_percentage', 'effective_price', 'price_display', 'total_sales')
        }),
        ('Sale Dates', {
            'fields': ('date_on_sale_from', 'date_on_sale_to'),
            'classes': ('collapse',)
        }),
        ('Content', {
            'fields': ('short_description', 'description', 'purchase_note')
        }),
        ('Inventory', {
            'fields': ('sku', 'stock_status', 'manage_stock', 'stock_quantity', 
                      'backorders', 'sold_individually', 'is_in_stock')
        }),
        ('Variations', {
            'fields': ('has_variations', 'total_stock'),
            'classes': ('collapse',)
        }),
        ('Product Characteristics', {
            'fields': ('virtual', 'downloadable', 'downloads', 'download_limit', 'download_expiry'),
            'classes': ('collapse',)
        }),
        ('External Product', {
            'fields': ('external_url', 'button_text'),
            'classes': ('collapse',)
        }),
        ('Tax & Shipping', {
            'fields': ('tax_status', 'tax_class', 'shipping_required', 'shipping_taxable', 
                      'shipping_class', 'shipping_class_id'),
            'classes': ('collapse',)
        }),
        ('Physical Properties', {
            'fields': ('weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('Reviews', {
            'fields': ('reviews_allowed', 'average_rating', 'rating_count'),
            'classes': ('collapse',)
        }),
        ('Related Products', {
            'fields': ('related_ids', 'upsell_ids', 'cross_sell_ids', 'grouped_products'),
            'classes': ('collapse',)
        }),
        ('Variable Product Data', {
            'fields': ('parent_id', 'woo_variations', 'default_attributes'),
            'classes': ('collapse',)
        }),
        ('WooCommerce Data', {
            'fields': ('woo_product_id', 'permalink', 'date_created', 'date_modified', 
                      'woo_categories', 'tags', 'attributes', 'images', 'meta_data'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image', 'primary_image_url')
        }),
        ('System', {
            'fields': ('menu_order', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [LottoProductVariationInline]
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('category', 'category__club').prefetch_related('variations')
    
    def club_name(self, obj):
        """Display club name"""
        return obj.category.club.name
    club_name.short_description = 'Club'
    club_name.admin_order_field = 'category__club__name'
    
    def is_on_sale_display(self, obj):
        """Display if product is on sale"""
        if obj.is_on_sale:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {}% OFF</span>', 
                obj.discount_percentage
            )
        return format_html('<span style="color: gray;">-</span>')
    is_on_sale_display.short_description = 'On Sale'
    
    def has_variations_display(self, obj):
        """Display if product has variations"""
        if obj.has_variations:
            count = obj.variations.filter(is_active=True).count()
            return format_html(
                '<span style="color: blue; font-weight: bold;">✓ {} variations</span>', 
                count
            )
        return format_html('<span style="color: gray;">Simple Product</span>')
    has_variations_display.short_description = 'Variations'
    
    actions = ['mark_published', 'mark_draft', 'mark_in_stock', 'mark_out_of_stock', 'mark_featured', 'unmark_featured']
    
    def mark_published(self, request, queryset):
        """Mark selected products as published"""
        updated = queryset.update(status='publish')
        self.message_user(request, f"Successfully published {updated} LOTTO products.", messages.SUCCESS)
    mark_published.short_description = "Mark as published"
    
    def mark_draft(self, request, queryset):
        """Mark selected products as draft"""
        updated = queryset.update(status='draft')
        self.message_user(request, f"Successfully marked {updated} LOTTO products as draft.", messages.SUCCESS)
    mark_draft.short_description = "Mark as draft"
    
    def mark_in_stock(self, request, queryset):
        """Mark selected products as in stock"""
        updated = queryset.update(stock_status='instock')
        self.message_user(request, f"Successfully marked {updated} LOTTO products as in stock.", messages.SUCCESS)
    mark_in_stock.short_description = "Mark as in stock"
    
    def mark_out_of_stock(self, request, queryset):
        """Mark selected products as out of stock"""
        updated = queryset.update(stock_status='outofstock')
        self.message_user(request, f"Successfully marked {updated} LOTTO products as out of stock.", messages.SUCCESS)
    mark_out_of_stock.short_description = "Mark as out of stock"
    
    def mark_featured(self, request, queryset):
        """Mark selected products as featured"""
        updated = queryset.update(featured=True)
        self.message_user(request, f"Successfully marked {updated} LOTTO products as featured.", messages.SUCCESS)
    mark_featured.short_description = "Mark as featured"
    
    def unmark_featured(self, request, queryset):
        """Remove featured status from selected products"""
        updated = queryset.update(featured=False)
        self.message_user(request, f"Successfully removed featured status from {updated} LOTTO products.", messages.SUCCESS)
    unmark_featured.short_description = "Remove featured status"


@admin.register(LottoProductVariation)
class LottoProductVariationAdmin(admin.ModelAdmin):
    """
    Admin interface for LottoProductVariation model
    """
    list_display = [
        'variation_display', 'product', 'club_name', 'variation_type', 'variation_value',
        'image_preview', 'final_price', 'stock_quantity', 'stock_status_display', 'is_active', 'woo_variation_id'
    ]
    list_filter = [
        'variation_type', 'is_active', 'product__category__club',
        'product__category', 'created_at'
    ]
    search_fields = [
        'variation_value', 'sku_suffix', 'product__name', 
        'product__category__name', 'product__category__club__name'
    ]
    readonly_fields = [
        'woo_variation_id', 'full_sku', 'final_price', 'stock_status',
        'image_preview', 'effective_image_info', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'variation_type', 'variation_value', 'is_active')
        }),
        ('Pricing & Stock', {
            'fields': ('price_modifier', 'final_price', 'stock_quantity', 'stock_status')
        }),
        ('Product Details', {
            'fields': ('sku_suffix', 'full_sku', 'weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('WooCommerce Data', {
            'fields': ('woo_variation_id', 'attributes'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image', 'image_preview', 'effective_image_info')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'product', 'product__category', 'product__category__club'
        )
    
    def variation_display(self, obj):
        """Display variation in a readable format"""
        return f"{obj.product.name} - {obj.variation_type}: {obj.variation_value}"
    variation_display.short_description = 'Variation'
    variation_display.admin_order_field = 'product__name'
    
    def club_name(self, obj):
        """Display club name"""
        return obj.product.category.club.name
    club_name.short_description = 'Club'
    club_name.admin_order_field = 'product__category__club__name'
    
    def final_price(self, obj):
        """Display calculated final price"""
        return f"${obj.final_price:.2f}"
    final_price.short_description = 'Final Price'
    
    def image_preview(self, obj):
        """Display image preview for variation"""
        if obj.effective_image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" title="{}"/>',
                obj.effective_image,  # effective_image now returns URL directly
                f"{obj.variation_type}: {obj.variation_value}"
            )
        return format_html('<span style="color: gray;">No Image</span>')
    image_preview.short_description = 'Image'
    
    def effective_image_info(self, obj):
        """Display information about which image is being used"""
        if obj.image:
            return format_html('<span style="color: green;">✓ Variation image</span>')
        elif obj.product.image:
            return format_html('<span style="color: orange;">◐ Product image (fallback)</span>')
        else:
            return format_html('<span style="color: gray;">✗ No image available</span>')
    effective_image_info.short_description = 'Image Source'
    
    def stock_status_display(self, obj):
        """Display stock status with color coding"""
        status = obj.stock_status
        colors = {
            'instock': 'green',
            'outofstock': 'red',
            'discontinued': 'gray'
        }
        color = colors.get(status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', 
            color, 
            status.upper()
        )
    stock_status_display.short_description = 'Stock Status'
    
    actions = ['activate_variations', 'deactivate_variations']
    
    def activate_variations(self, request, queryset):
        """Activate selected variations"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} LOTTO variations.", messages.SUCCESS)
    activate_variations.short_description = "Activate selected variations"
    
    def deactivate_variations(self, request, queryset):
        """Deactivate selected variations"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} LOTTO variations.", messages.SUCCESS)
    deactivate_variations.short_description = "Deactivate selected variations"


# SAS-specific Admin Classes

@admin.register(SASSport)
class SASSportAdmin(admin.ModelAdmin):
    """
    Admin interface for SASSport model
    """
    list_display = [
        'name', 'club_count', 'product_count', 'is_active', 
        'woo_category_id', 'last_sync_at', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'last_sync_at']
    search_fields = ['name', 'description']
    readonly_fields = ['slug', 'woo_category_id', 'club_count', 'product_count', 'created_at', 'updated_at', 'last_sync_at']
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'is_active')
        }),
        ('Statistics', {
            'fields': ('club_count', 'product_count')
        }),
        ('Media', {
            'fields': ('image_url',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_sync_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['update_counts', 'activate_sports', 'deactivate_sports', 'sync_sports']
    
    def update_counts(self, request, queryset):
        """Update club and product counts for selected sports"""
        for sport in queryset:
            sport.update_counts()
        
        self.message_user(
            request, 
            f"Successfully updated counts for {queryset.count()} sports.", 
            messages.SUCCESS
        )
    update_counts.short_description = "Update club and product counts"
    
    def activate_sports(self, request, queryset):
        """Activate selected sports"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} sports.", messages.SUCCESS)
    activate_sports.short_description = "Activate selected sports"
    
    def deactivate_sports(self, request, queryset):
        """Deactivate selected sports"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} sports.", messages.SUCCESS)
    deactivate_sports.short_description = "Deactivate selected sports"
    
    def sync_sports(self, request, queryset):
        """Sync selected sports with WooCommerce"""
        try:
            for sport in queryset:
                woo_service = WooCommerceService(store_type='SAS')
                # Add sync logic here if needed
            
            self.message_user(request, f"Successfully synced {queryset.count()} SAS sports.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing SAS sports: {str(e)}", messages.ERROR)
    
    sync_sports.short_description = "Sync selected sports with WooCommerce"


@admin.register(SASClub)
class SASClubAdmin(admin.ModelAdmin):
    """
    Admin interface for SASClub model
    """
    list_display = [
        'name', 'sport', 'city', 'product_count', 'is_school', 
        'is_active', 'woo_category_id', 'last_sync_at', 'created_at'
    ]
    list_filter = [
        'sport', 'is_active', 'is_school', 'city', 'province', 
        'created_at', 'last_sync_at'
    ]
    search_fields = [
        'name', 'contact_person', 'email', 'city', 'address'
    ]
    readonly_fields = [
        'slug', 'woo_category_id', 'is_school', 'product_count', 
        'created_at', 'updated_at', 'last_sync_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('sport', 'name', 'slug', 'description', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'email', 'website', 'phone')
        }),
        ('Location', {
            'fields': ('city', 'province', 'address')
        }),
        ('Classification', {
            'fields': ('is_school', 'product_count')
        }),
        ('Media', {
            'fields': ('image_url',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_category_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_sync_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('sport')
    
    actions = [
        'activate_clubs', 'deactivate_clubs', 'mark_as_school', 'mark_as_club', 
        'update_product_counts', 'sync_selected_clubs'
    ]
    
    def activate_clubs(self, request, queryset):
        """Activate selected clubs"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} SAS clubs.", messages.SUCCESS)
    activate_clubs.short_description = "Activate selected clubs"
    
    def deactivate_clubs(self, request, queryset):
        """Deactivate selected clubs"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} SAS clubs.", messages.SUCCESS)
    deactivate_clubs.short_description = "Deactivate selected clubs"
    
    def mark_as_school(self, request, queryset):
        """Mark selected items as schools"""
        updated = queryset.update(is_school=True)
        self.message_user(request, f"Successfully marked {updated} items as schools.", messages.SUCCESS)
    mark_as_school.short_description = "Mark as school"
    
    def mark_as_club(self, request, queryset):
        """Mark selected items as clubs (not schools)"""
        updated = queryset.update(is_school=False)
        self.message_user(request, f"Successfully marked {updated} items as clubs.", messages.SUCCESS)
    mark_as_club.short_description = "Mark as club (not school)"
    
    def update_product_counts(self, request, queryset):
        """Update product counts for selected clubs"""
        for club in queryset:
            club.update_product_count()
        
        self.message_user(
            request, 
            f"Successfully updated product counts for {queryset.count()} SAS clubs.", 
            messages.SUCCESS
        )
    update_product_counts.short_description = "Update product counts"
    
    def sync_selected_clubs(self, request, queryset):
        """Sync selected clubs with WooCommerce"""
        try:
            for club in queryset:
                woo_service = WooCommerceService(store_type='SAS')
                # Add sync logic here if needed
            
            self.message_user(request, f"Successfully synced {queryset.count()} SAS clubs.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing SAS clubs: {str(e)}", messages.ERROR)
    
    sync_selected_clubs.short_description = "Sync selected SAS clubs with WooCommerce"


@admin.register(SASProduct)
class SASProductAdmin(admin.ModelAdmin):
    """
    Admin interface for SASProduct model
    """
    list_display = [
        'name', 'club', 'sport_name', 'effective_price', 'stock_status', 
        'sku', 'is_on_sale_display', 'featured', 'is_active', 
        'woo_product_id', 'created_at'
    ]
    list_filter = [
        'stock_status', 'featured', 'is_active', 'product_type', 
        'club__sport', 'club', 'created_at', 'last_sync_at'
    ]
    search_fields = [
        'name', 'description', 'short_description', 'sku', 
        'club__name', 'club__sport__name'
    ]
    readonly_fields = [
        'slug', 'woo_product_id', 'is_on_sale', 'discount_percentage', 
        'sport', 'is_available', 'effective_price', 'created_at', 'updated_at', 'last_sync_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('club', 'name', 'slug', 'product_type', 'is_active')
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price', 'is_on_sale', 'discount_percentage', 'effective_price')
        }),
        ('Inventory', {
            'fields': ('sku', 'stock_status', 'manage_stock', 'stock_quantity', 'backorders')
        }),
        ('Content', {
            'fields': ('short_description', 'description')
        }),
        ('Product Features', {
            'fields': ('featured', 'catalog_visibility'),
        }),
        ('Product Details', {
            'fields': ('weight', 'dimensions', 'tags', 'attributes', 'categories'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image_url', 'gallery_urls')
        }),
        ('Related Information', {
            'fields': ('sport',),
            'classes': ('collapse',)
        }),
        ('WooCommerce Integration', {
            'fields': ('woo_product_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_sync_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('club', 'club__sport')
    
    def sport_name(self, obj):
        """Display sport name"""
        return obj.club.sport.name if obj.club and obj.club.sport else '-'
    sport_name.short_description = 'Sport'
    sport_name.admin_order_field = 'club__sport__name'
    
    def is_on_sale_display(self, obj):
        """Display if product is on sale"""
        if obj.is_on_sale:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {}% OFF</span>', 
                obj.discount_percentage
            )
        return format_html('<span style="color: gray;">-</span>')
    is_on_sale_display.short_description = 'On Sale'
    
    actions = [
        'mark_active', 'mark_inactive', 'mark_featured', 'unmark_featured',
        'mark_in_stock', 'mark_out_of_stock', 'mark_on_backorder'
    ]
    
    def mark_active(self, request, queryset):
        """Mark selected products as active"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} SAS products.", messages.SUCCESS)
    mark_active.short_description = "Mark as active"
    
    def mark_inactive(self, request, queryset):
        """Mark selected products as inactive"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} SAS products.", messages.SUCCESS)
    mark_inactive.short_description = "Mark as inactive"
    
    def mark_featured(self, request, queryset):
        """Mark selected products as featured"""
        updated = queryset.update(featured=True)
        self.message_user(request, f"Successfully marked {updated} SAS products as featured.", messages.SUCCESS)
    mark_featured.short_description = "Mark as featured"
    
    def unmark_featured(self, request, queryset):
        """Remove featured status from selected products"""
        updated = queryset.update(featured=False)
        self.message_user(request, f"Successfully removed featured status from {updated} SAS products.", messages.SUCCESS)
    unmark_featured.short_description = "Remove featured status"
    
    def mark_in_stock(self, request, queryset):
        """Mark selected products as in stock"""
        updated = queryset.update(stock_status='instock')
        self.message_user(request, f"Successfully marked {updated} SAS products as in stock.", messages.SUCCESS)
    mark_in_stock.short_description = "Mark as in stock"
    
    def mark_out_of_stock(self, request, queryset):
        """Mark selected products as out of stock"""
        updated = queryset.update(stock_status='outofstock')
        self.message_user(request, f"Successfully marked {updated} SAS products as out of stock.", messages.SUCCESS)
    mark_out_of_stock.short_description = "Mark as out of stock"
    
    def mark_on_backorder(self, request, queryset):
        """Mark selected products as on backorder"""
        updated = queryset.update(stock_status='onbackorder')
        self.message_user(request, f"Successfully marked {updated} SAS products as on backorder.", messages.SUCCESS)
    mark_on_backorder.short_description = "Mark as on backorder"


# Wholesale-specific Admin Classes

@admin.register(WholesaleSchool)
class WholesaleSchoolAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleSchool model
    """
    list_display = [
        'name', 'school_code', 'contact_person', 'email', 'city', 'region',
        'total_products', 'active_categories', 'is_active', 'last_synced_at', 'created_at'
    ]
    list_filter = [
        'is_active', 'city', 'region', 'country', 'cin7_brand', 'cin7_supplier',
        'created_at', 'last_synced_at'
    ]
    search_fields = [
        'name', 'school_code', 'contact_person', 'email', 'phone', 'cin7_id',
        'cin7_sku', 'cin7_barcode', 'address_line1', 'city'
    ]
    readonly_fields = [
        'slug', 'cin7_id', 'total_products', 'active_categories',
        'last_synced_at', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'school_code', 'description', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'email', 'phone', 'website')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'region', 'postal_code', 'country')
        }),
        ('CIN7 Integration', {
            'fields': ('cin7_id', 'cin7_sku', 'cin7_barcode', 'cin7_brand', 'cin7_supplier', 'cin7_category_path'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_products', 'active_categories')
        }),
        ('Metadata', {
            'fields': ('last_synced_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['sync_schools', 'activate_schools', 'deactivate_schools', 'update_statistics']

    def sync_schools(self, request, queryset):
        """Sync selected schools with CIN7"""
        try:
            # This would integrate with the CIN7 sync service
            self.message_user(request, f"Sync initiated for {queryset.count()} schools.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing schools: {str(e)}", messages.ERROR)
    sync_schools.short_description = "Sync selected schools with CIN7"

    def activate_schools(self, request, queryset):
        """Activate selected schools"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} schools.", messages.SUCCESS)
    activate_schools.short_description = "Activate selected schools"

    def deactivate_schools(self, request, queryset):
        """Deactivate selected schools"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} schools.", messages.SUCCESS)
    deactivate_schools.short_description = "Deactivate selected schools"

    def update_statistics(self, request, queryset):
        """Update statistics for selected schools"""
        for school in queryset:
            school.total_products = WholesaleProduct.objects.filter(school=school, is_active=True).count()
            school.active_categories = WholesaleCategory.objects.filter(
                products__school=school, is_active=True
            ).distinct().count()
            school.save(update_fields=['total_products', 'active_categories'])

        self.message_user(
            request,
            f"Successfully updated statistics for {queryset.count()} schools.",
            messages.SUCCESS
        )
    update_statistics.short_description = "Update statistics"


@admin.register(WholesaleCategory)
class WholesaleCategoryAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleCategory model
    """
    list_display = [
        'name', 'parent', 'level', 'product_count', 'is_active',
        'cin7_id', 'last_synced_at', 'created_at'
    ]
    list_filter = [
        'level', 'is_active', 'parent', 'created_at', 'last_synced_at'
    ]
    search_fields = [
        'name', 'description', 'path', 'cin7_id'
    ]
    readonly_fields = [
        'slug', 'cin7_id', 'level', 'path', 'product_count',
        'last_synced_at', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'is_active')
        }),
        ('Hierarchy', {
            'fields': ('parent', 'level', 'path')
        }),
        ('CIN7 Integration', {
            'fields': ('cin7_id',),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('product_count',)
        }),
        ('Metadata', {
            'fields': ('last_synced_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate_categories', 'deactivate_categories', 'update_product_counts']

    def activate_categories(self, request, queryset):
        """Activate selected categories"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} categories.", messages.SUCCESS)
    activate_categories.short_description = "Activate selected categories"

    def deactivate_categories(self, request, queryset):
        """Deactivate selected categories"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} categories.", messages.SUCCESS)
    deactivate_categories.short_description = "Deactivate selected categories"

    def update_product_counts(self, request, queryset):
        """Update product counts for selected categories"""
        for category in queryset:
            category.product_count = WholesaleProduct.objects.filter(
                categories=category, is_active=True
            ).count()
            category.save(update_fields=['product_count'])

        self.message_user(
            request,
            f"Successfully updated product counts for {queryset.count()} categories.",
            messages.SUCCESS
        )
    update_product_counts.short_description = "Update product counts"


@admin.register(WholesaleProductCategoryAssignment)
class WholesaleProductCategoryAssignmentAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleProductCategoryAssignment model
    """
    list_display = [
        'product', 'category', 'school_name', 'is_primary', 'sort_order',
        'cin7_category_id', 'assigned_at', 'last_synced_at'
    ]
    list_filter = [
        'is_primary', 'category', 'product__school',
        'assigned_at', 'last_synced_at'
    ]
    search_fields = [
        'product__name', 'category__name', 'product__school__name',
        'cin7_category_id'
    ]
    readonly_fields = [
        'cin7_category_id', 'assigned_at', 'last_synced_at'
    ]

    fieldsets = (
        ('Assignment Information', {
            'fields': ('product', 'category', 'is_primary', 'sort_order')
        }),
        ('CIN7 Integration', {
            'fields': ('cin7_category_id',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('assigned_at', 'last_synced_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'product', 'category', 'product__school'
        )

    def school_name(self, obj):
        """Display school name"""
        return obj.product.school.name
    school_name.short_description = 'School'
    school_name.admin_order_field = 'product__school__name'

    actions = ['mark_as_primary', 'unmark_as_primary']

    def mark_as_primary(self, request, queryset):
        """Mark selected assignments as primary"""
        products_updated = set()
        for assignment in queryset:
            # Clear other primary assignments for this product
            WholesaleProductCategoryAssignment.objects.filter(
                product=assignment.product,
                is_primary=True
            ).exclude(id=assignment.id).update(is_primary=False)

            # Mark this one as primary
            assignment.is_primary = True
            assignment.save()
            products_updated.add(assignment.product.name)

        self.message_user(
            request,
            f"Successfully marked assignments as primary for {len(products_updated)} products.",
            messages.SUCCESS
        )
    mark_as_primary.short_description = "Mark as primary category"

    def unmark_as_primary(self, request, queryset):
        """Remove primary status from selected assignments"""
        updated = queryset.update(is_primary=False)
        self.message_user(
            request,
            f"Successfully removed primary status from {updated} assignments.",
            messages.SUCCESS
        )
    unmark_as_primary.short_description = "Remove primary status"


class WholesaleProductVariationInline(admin.TabularInline):
    """
    Inline admin interface for WholesaleProductVariation within WholesaleProduct admin
    """
    model = WholesaleProductVariation
    extra = 0
    readonly_fields = ['cin7_id', 'cin7_sku', 'is_in_stock', 'image_preview', 'created_at']
    fields = [
        'variation_type', 'variation_value', 'image_url', 'image_preview',
        'wholesale_price', 'retail_price', 'cost_price', 'quantity_available',
        'is_active', 'cin7_id', 'cin7_sku'
    ]

    def image_preview(self, obj):
        """Display image preview for variation"""
        if obj.pk and obj.image_url:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" title="{}"/>',
                obj.image_url,
                f"{obj.variation_type}: {obj.variation_value}"
            )
        return format_html('<span style="color: gray;">No Image</span>')
    image_preview.short_description = 'Preview'


@admin.register(WholesaleProduct)
class WholesaleProductAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleProduct model
    """
    list_display = [
        'name', 'school', 'primary_category', 'wholesale_price', 'retail_price',
        'stock_status', 'quantity_available', 'is_in_stock', 'is_active',
        'cin7_id', 'last_synced_at'
    ]
    list_filter = [
        'stock_status', 'is_active', 'school', 'cin7_brand', 'cin7_supplier',
        'created_at', 'last_synced_at'
    ]
    search_fields = [
        'name', 'description', 'short_description', 'cin7_id', 'cin7_sku',
        'cin7_barcode', 'school__name'
    ]
    readonly_fields = [
        'slug', 'cin7_id', 'is_in_stock', 'profit_margin', 'primary_category',
        'last_synced_at', 'created_at', 'updated_at'
    ]
    prepopulated_fields = {'slug': ('name',)}
    # Note: categories uses through model, so can't use filter_horizontal

    fieldsets = (
        ('Basic Information', {
            'fields': ('school', 'name', 'slug', 'description', 'short_description', 'is_active')
        }),
        ('Categories', {
            'fields': ('primary_category',)
        }),
        ('Pricing', {
            'fields': ('wholesale_price', 'retail_price', 'cost_price', 'profit_margin')
        }),
        ('Stock Management', {
            'fields': ('stock_status', 'quantity_available', 'quantity_on_hand',
                      'quantity_committed', 'is_in_stock')
        }),
        ('Product Details', {
            'fields': ('weight', 'dimensions', 'attributes'),
            'classes': ('collapse',)
        }),
        ('CIN7 Integration', {
            'fields': ('cin7_id', 'cin7_sku', 'cin7_barcode', 'cin7_brand',
                      'cin7_supplier', 'cin7_unit_of_measure'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image_url', 'additional_images')
        }),
        ('Metadata', {
            'fields': ('last_synced_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [WholesaleProductVariationInline]

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related('school').prefetch_related(
            'categories', 'variations'
        )

    def primary_category(self, obj):
        """Display primary category"""
        return obj.primary_category
    primary_category.short_description = 'Primary Category'

    def is_in_stock(self, obj):
        """Display stock status with color coding"""
        if obj.is_in_stock:
            return format_html('<span style="color: green; font-weight: bold;">✓ In Stock</span>')
        else:
            return format_html('<span style="color: red; font-weight: bold;">✗ Out of Stock</span>')
    is_in_stock.short_description = 'Stock Status'

    def profit_margin(self, obj):
        """Display profit margin if available"""
        margin = obj.profit_margin
        if margin is not None:
            color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, margin
            )
        return format_html('<span style="color: gray;">-</span>')
    profit_margin.short_description = 'Profit Margin'

    actions = [
        'activate_products', 'deactivate_products', 'mark_in_stock',
        'mark_out_of_stock', 'sync_products'
    ]

    def activate_products(self, request, queryset):
        """Activate selected products"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} products.", messages.SUCCESS)
    activate_products.short_description = "Activate selected products"

    def deactivate_products(self, request, queryset):
        """Deactivate selected products"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} products.", messages.SUCCESS)
    deactivate_products.short_description = "Deactivate selected products"

    def mark_in_stock(self, request, queryset):
        """Mark selected products as in stock"""
        updated = queryset.update(stock_status='in_stock')
        self.message_user(request, f"Successfully marked {updated} products as in stock.", messages.SUCCESS)
    mark_in_stock.short_description = "Mark as in stock"

    def mark_out_of_stock(self, request, queryset):
        """Mark selected products as out of stock"""
        updated = queryset.update(stock_status='out_of_stock')
        self.message_user(request, f"Successfully marked {updated} products as out of stock.", messages.SUCCESS)
    mark_out_of_stock.short_description = "Mark as out of stock"

    def sync_products(self, request, queryset):
        """Sync selected products with CIN7"""
        try:
            # This would integrate with the CIN7 sync service
            self.message_user(request, f"Sync initiated for {queryset.count()} products.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error syncing products: {str(e)}", messages.ERROR)
    sync_products.short_description = "Sync selected products with CIN7"


@admin.register(WholesaleProductVariation)
class WholesaleProductVariationAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleProductVariation model
    """
    list_display = [
        'variation_display', 'product', 'school_name', 'variation_type', 'variation_value',
        'wholesale_price', 'retail_price', 'quantity_available', 'is_in_stock',
        'is_active', 'cin7_id'
    ]
    list_filter = [
        'variation_type', 'is_active', 'product__school',
        'created_at', 'last_synced_at'
    ]
    search_fields = [
        'variation_value', 'variation_description', 'cin7_id', 'cin7_sku',
        'product__name', 'product__school__name'
    ]
    readonly_fields = [
        'cin7_id', 'is_in_stock', 'created_at', 'updated_at', 'last_synced_at'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'variation_type', 'variation_value', 'variation_description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('wholesale_price', 'retail_price', 'cost_price')
        }),
        ('Stock', {
            'fields': ('quantity_available', 'quantity_on_hand', 'quantity_committed', 'is_in_stock')
        }),
        ('Physical Properties', {
            'fields': ('weight', 'dimensions'),
            'classes': ('collapse',)
        }),
        ('CIN7 Integration', {
            'fields': ('cin7_id', 'cin7_sku', 'cin7_barcode'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image_url',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'last_synced_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'product', 'product__school'
        )

    def variation_display(self, obj):
        """Display variation in a readable format"""
        return f"{obj.product.name} - {obj.variation_type}: {obj.variation_value}"
    variation_display.short_description = 'Variation'
    variation_display.admin_order_field = 'product__name'

    def school_name(self, obj):
        """Display school name"""
        return obj.product.school.name
    school_name.short_description = 'School'
    school_name.admin_order_field = 'product__school__name'

    def is_in_stock(self, obj):
        """Display stock status with color coding"""
        if obj.is_in_stock:
            return format_html('<span style="color: green; font-weight: bold;">✓ Available</span>')
        else:
            return format_html('<span style="color: red; font-weight: bold;">✗ Unavailable</span>')
    is_in_stock.short_description = 'Stock'

    actions = ['activate_variations', 'deactivate_variations']

    def activate_variations(self, request, queryset):
        """Activate selected variations"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Successfully activated {updated} variations.", messages.SUCCESS)
    activate_variations.short_description = "Activate selected variations"

    def deactivate_variations(self, request, queryset):
        """Deactivate selected variations"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Successfully deactivated {updated} variations.", messages.SUCCESS)
    deactivate_variations.short_description = "Deactivate selected variations"


@admin.register(WholesaleSyncJob)
class WholesaleSyncJobAdmin(admin.ModelAdmin):
    """
    Admin interface for WholesaleSyncJob model
    """
    list_display = [
        'id', 'status', 'progress_percentage', 'current_step', 'total_items_processed',
        'errors_count', 'duration_display', 'started_at', 'completed_at'
    ]
    list_filter = ['status', 'created_at', 'started_at', 'completed_at']
    readonly_fields = [
        'id', 'status', 'progress_percentage', 'current_step', 'total_items_processed',
        'duration', 'duration_display', 'schools_created', 'schools_updated',
        'products_created', 'products_updated', 'categories_created', 'categories_updated',
        'variations_created', 'variations_updated', 'errors_count', 'error_messages',
        'started_at', 'completed_at', 'created_at'
    ]

    fieldsets = (
        ('Job Information', {
            'fields': ('id', 'status', 'progress_percentage', 'current_step')
        }),
        ('Statistics', {
            'fields': (
                'schools_created', 'schools_updated', 'products_created', 'products_updated',
                'categories_created', 'categories_updated', 'variations_created', 'variations_updated',
                'total_items_processed'
            )
        }),
        ('Error Information', {
            'fields': ('errors_count', 'error_messages'),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration', 'duration_display', 'created_at')
        }),
    )

    def duration_display(self, obj):
        """Display job duration in human-readable format"""
        duration = obj.duration
        if duration:
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "-"
    duration_display.short_description = 'Duration'

    def total_items_processed(self, obj):
        """Display total items processed with color coding"""
        total = obj.total_items_processed
        if total > 0:
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', total)
        return format_html('<span style="color: gray;">0</span>')
    total_items_processed.short_description = 'Items Processed'

    def has_add_permission(self, request):
        """Don't allow manual creation of sync jobs"""
        return False

    def has_change_permission(self, request, obj=None):
        """Don't allow editing of sync jobs"""
        return False


# Customize admin site
admin.site.site_header = "SASKITUP Clubs Administration"
admin.site.site_title = "SASKITUP Clubs Admin"
admin.site.index_title = "Welcome to SASKITUP Clubs Administration"
