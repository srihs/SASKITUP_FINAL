import os
import logging
from decimal import Decimal
from django.db import models
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


class LottoClub(models.Model):
    """
    LOTTO-specific club model mapping to WooCommerce categories at club level
    """
    SPORT_TAGS = [
        ('Football', 'Football'),
        ('Rugby', 'Rugby'),
        ('Cricket', 'Cricket'),
        ('Basketball', 'Basketball'),
        ('Tennis', 'Tennis'),
        ('Volleyball', 'Volleyball'),
        ('Hockey', 'Hockey'),
        ('Netball', 'Netball'),
        ('Other', 'Other'),
    ]

    # Core fields
    name = models.CharField(max_length=255, unique=True, help_text="Club name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")
    club_type = models.CharField(max_length=10, default='LOTTO', editable=False, help_text="Always LOTTO for this model")
    sport_tag = models.CharField(max_length=50, choices=SPORT_TAGS, default='Football', help_text="Primary sport")
    
    # Contact information
    contact_person = models.CharField(max_length=100, blank=True, null=True, help_text="Primary contact person")
    email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    website = models.URLField(blank=True, null=True, validators=[URLValidator()], help_text="Club website URL")
    address = models.TextField(blank=True, null=True, help_text="Club physical address")
    
    # WooCommerce integration
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    
    # Images
    logo = models.ImageField(upload_to='lotto/clubs/images/', blank=True, null=True, help_text="Club logo image")
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Whether the club is active")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lotto_clubs'
        ordering = ['name']
        verbose_name = "LOTTO Club"
        verbose_name_plural = "LOTTO Clubs"
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['sport_tag']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        # Ensure club_type is always LOTTO
        self.club_type = 'LOTTO'
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} (LOTTO)"
    
    @property
    def total_products(self):
        """Get total number of products across all categories for this club"""
        return sum(category.products.count() for category in self.categories.all())
    
    @property
    def active_categories_count(self):
        """Get count of categories with products"""
        return self.categories.filter(product_count__gt=0).count()
    
    @property
    def total_categories(self):
        """Get total number of categories"""
        return self.categories.count()


class LottoClubCategory(models.Model):
    """
    LOTTO-specific category model mapping to subcategories within clubs
    """
    # Relationships
    club = models.ForeignKey(LottoClub, on_delete=models.CASCADE, related_name='categories')
    
    # Core fields
    name = models.CharField(max_length=255, help_text="Category name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    description = models.TextField(blank=True, null=True, help_text="Category description")
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products in this category")
    
    # Images
    image = models.ImageField(upload_to='lotto/categories/images/', blank=True, null=True, help_text="Category image")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lotto_club_categories'
        ordering = ['club', 'name']
        verbose_name = "LOTTO Club Category"
        verbose_name_plural = "LOTTO Club Categories"
        unique_together = ['club', 'name']
        indexes = [
            models.Index(fields=['club', 'product_count']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.club.name}-{self.name}")
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.club.name} - {self.name}"
    
    def update_product_count(self):
        """Update the product count for this category"""
        self.product_count = self.products.filter(stock_status__in=['instock', 'onbackorder']).count()
        self.save(update_fields=['product_count', 'updated_at'])


class LottoProduct(models.Model):
    """
    LOTTO-specific product model with comprehensive WooCommerce field mapping
    """
    # WooCommerce status choices
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]
    
    PRODUCT_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('private', 'Private'),
        ('publish', 'Published'),
        ('future', 'Future'),
        ('trash', 'Trash'),
    ]
    
    PRODUCT_TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('grouped', 'Grouped'),
        ('external', 'External/Affiliate'),
        ('variable', 'Variable'),
    ]
    
    CATALOG_VISIBILITY_CHOICES = [
        ('visible', 'Visible'),
        ('catalog', 'Catalog'),
        ('search', 'Search'),
        ('hidden', 'Hidden'),
    ]
    
    TAX_STATUS_CHOICES = [
        ('taxable', 'Taxable'),
        ('shipping', 'Shipping Only'),
        ('none', 'None'),
    ]
    
    BACKORDERS_CHOICES = [
        ('no', 'No'),
        ('notify', 'Notify'),
        ('yes', 'Yes'),
    ]
    
    # Relationships
    category = models.ForeignKey(LottoClubCategory, on_delete=models.CASCADE, related_name='products')
    
    # Core WooCommerce fields
    name = models.CharField(max_length=255, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_product_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce product ID")
    
    # WooCommerce metadata
    permalink = models.URLField(blank=True, null=True, help_text="WooCommerce product permalink")
    date_created = models.DateTimeField(blank=True, null=True, help_text="WooCommerce creation date")
    date_modified = models.DateTimeField(blank=True, null=True, help_text="WooCommerce modification date")
    type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple', help_text="Product type")
    status = models.CharField(max_length=20, choices=PRODUCT_STATUS_CHOICES, default='publish', help_text="Product status")
    featured = models.BooleanField(default=False, help_text="Is featured product")
    catalog_visibility = models.CharField(max_length=20, choices=CATALOG_VISIBILITY_CHOICES, default='visible', help_text="Catalog visibility")
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current product price")
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Regular price")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Sale price")
    price_html = models.TextField(blank=True, null=True, help_text="Formatted price HTML")
    on_sale = models.BooleanField(default=False, help_text="Is product on sale")
    purchasable = models.BooleanField(default=True, help_text="Is product purchasable")
    total_sales = models.PositiveIntegerField(default=0, help_text="Total sales count")
    date_on_sale_from = models.DateTimeField(blank=True, null=True, help_text="Sale start date")
    date_on_sale_to = models.DateTimeField(blank=True, null=True, help_text="Sale end date")
    
    # Content
    description = models.TextField(blank=True, null=True, help_text="Product description")
    short_description = models.TextField(blank=True, null=True, help_text="Short product description")
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Stock Keeping Unit")
    
    # Product characteristics
    virtual = models.BooleanField(default=False, help_text="Is virtual product")
    downloadable = models.BooleanField(default=False, help_text="Is downloadable product")
    downloads = models.JSONField(blank=True, null=True, help_text="Download files")
    download_limit = models.IntegerField(default=-1, help_text="Download limit (-1 for unlimited)")
    download_expiry = models.IntegerField(default=-1, help_text="Download expiry in days (-1 for unlimited)")
    
    # External product
    external_url = models.URLField(blank=True, null=True, help_text="External product URL")
    button_text = models.CharField(max_length=255, blank=True, null=True, help_text="External product button text")
    
    # Inventory
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock', help_text="Stock status")
    manage_stock = models.BooleanField(default=False, help_text="Manage stock at product level")
    stock_quantity = models.IntegerField(blank=True, null=True, help_text="Stock quantity")
    backorders = models.CharField(max_length=10, choices=BACKORDERS_CHOICES, default='no', help_text="Backorder status")
    sold_individually = models.BooleanField(default=False, help_text="Sold individually")
    
    # Tax
    tax_status = models.CharField(max_length=20, choices=TAX_STATUS_CHOICES, default='taxable', help_text="Tax status")
    tax_class = models.CharField(max_length=50, blank=True, null=True, help_text="Tax class")
    
    # Shipping
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Product weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Product dimensions")
    shipping_required = models.BooleanField(default=True, help_text="Shipping required")
    shipping_taxable = models.BooleanField(default=True, help_text="Shipping taxable")
    shipping_class = models.CharField(max_length=100, blank=True, null=True, help_text="Shipping class")
    shipping_class_id = models.PositiveIntegerField(blank=True, null=True, help_text="Shipping class ID")
    
    # Reviews
    reviews_allowed = models.BooleanField(default=True, help_text="Reviews allowed")
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, help_text="Average rating")
    rating_count = models.PositiveIntegerField(default=0, help_text="Number of ratings")
    
    # Related products
    related_ids = models.JSONField(blank=True, null=True, help_text="Related product IDs")
    upsell_ids = models.JSONField(blank=True, null=True, help_text="Upsell product IDs")
    cross_sell_ids = models.JSONField(blank=True, null=True, help_text="Cross-sell product IDs")
    
    # Variable/Grouped products
    parent_id = models.PositiveIntegerField(blank=True, null=True, help_text="Parent product ID for variations")
    grouped_products = models.JSONField(blank=True, null=True, help_text="Grouped product IDs")
    woo_variations = models.JSONField(blank=True, null=True, help_text="WooCommerce variation data")
    default_attributes = models.JSONField(blank=True, null=True, help_text="Default attributes for variable products")
    
    # Additional
    purchase_note = models.TextField(blank=True, null=True, help_text="Purchase note")
    menu_order = models.PositiveIntegerField(default=0, help_text="Menu order")
    meta_data = models.JSONField(blank=True, null=True, help_text="Additional meta data")
    
    # Enhanced fields
    woo_categories = models.JSONField(blank=True, null=True, help_text="WooCommerce categories")
    images = models.JSONField(blank=True, null=True, help_text="All product images")
    tags = models.JSONField(blank=True, null=True, help_text="Product tags")
    attributes = models.JSONField(blank=True, null=True, help_text="Product attributes")
    
    # Local image
    image = models.ImageField(upload_to='lotto/products/images/', blank=True, null=True, help_text="Primary product image")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lotto_products'
        ordering = ['category', 'name']
        verbose_name = "LOTTO Product"
        verbose_name_plural = "LOTTO Products"
        unique_together = ['category', 'name']
        indexes = [
            models.Index(fields=['category', 'stock_status']),
            models.Index(fields=['woo_product_id']),
            models.Index(fields=['sku']),
            models.Index(fields=['price']),
            models.Index(fields=['status', 'featured']),
            models.Index(fields=['on_sale']),
            models.Index(fields=['created_at']),
            models.Index(fields=['parent_id']),
        ]
    
    def clean(self):
        """Validate model fields"""
        super().clean()
        
        # Validate pricing
        if self.regular_price is not None and self.regular_price < 0:
            raise ValidationError({'regular_price': 'Regular price cannot be negative'})
        
        if self.sale_price is not None and self.sale_price < 0:
            raise ValidationError({'sale_price': 'Sale price cannot be negative'})
        
        if (self.regular_price is not None and self.sale_price is not None and 
            self.sale_price >= self.regular_price):
            raise ValidationError({'sale_price': 'Sale price must be less than regular price'})
        
        # Validate stock quantity
        if self.manage_stock and self.stock_quantity is None:
            raise ValidationError({'stock_quantity': 'Stock quantity is required when managing stock'})
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.category.club.name}-{self.category.name}-{self.name}")
        
        # Ensure price is set correctly - prioritize sale_price, then regular_price
        if self.sale_price and self.sale_price > 0:
            # If there's a sale price, use it as the main price and set on_sale flag
            if not self.price or self.price == 0:
                self.price = self.sale_price
            self.on_sale = True
        elif self.regular_price and self.regular_price > 0:
            # Use regular price if no sale price
            if not self.price or self.price == 0:
                self.price = self.regular_price
            self.on_sale = False
        
        # Set purchasable based on status and stock
        if self.status != 'publish':
            self.purchasable = False
        elif self.stock_status == 'outofstock':
            self.purchasable = False
        else:
            self.purchasable = True
        
        super().save(*args, **kwargs)
        
        # Update parent category product count
        if hasattr(self, 'category'):
            self.category.update_product_count()
    
    def delete(self, *args, **kwargs):
        category = self.category
        super().delete(*args, **kwargs)
        # Update parent category product count after deletion
        if category:
            category.update_product_count()
    
    def __str__(self):
        return f"{self.category.club.name} - {self.name}"
    
    @property
    def is_on_sale(self):
        """Check if product is on sale"""
        return self.on_sale and self.sale_price and self.regular_price and self.sale_price < self.regular_price
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage if on sale"""
        if self.is_on_sale and self.regular_price:
            return round(((self.regular_price - self.sale_price) / self.regular_price) * 100, 2)
        return 0
    
    @property
    def has_variations(self):
        """Check if product has variations"""
        return self.variations.exists()
    
    @property
    def is_variable_product(self):
        """Check if this is a variable product"""
        return self.type == 'variable' or self.has_variations
    
    @property
    def is_in_stock(self):
        """Check if product is in stock"""
        if self.is_variable_product:
            # For variable products, check if any variation is in stock
            return self.variations.filter(is_active=True, stock_quantity__gt=0).exists()
        elif self.manage_stock:
            return self.stock_quantity and self.stock_quantity > 0
        return self.stock_status == 'instock'
    
    @property
    def calculated_stock_status(self):
        """Calculate stock status dynamically, especially for variable products"""
        if self.is_variable_product:
            # For variable products, base status on variations
            has_stock = self.variations.filter(is_active=True, stock_quantity__gt=0).exists()
            if has_stock:
                return 'instock'
            else:
                # Check if any variations allow backorders
                has_backorder = self.variations.filter(is_active=True).exists()
                return 'onbackorder' if has_backorder else 'outofstock'
        else:
            # For simple products, use the stored stock_status
            return self.stock_status
    
    def update_stock_status_from_variations(self):
        """Update the product's stock_status field based on variations availability"""
        if self.is_variable_product:
            calculated_status = self.calculated_stock_status
            if self.stock_status != calculated_status:
                self.stock_status = calculated_status
                self.save(update_fields=['stock_status', 'updated_at'])
                logger.info(f"Updated stock status for product {self.id} to {calculated_status}")
                return True
        return False
    
    @property
    def effective_price(self):
        """Get the effective selling price"""
        if self.is_on_sale:
            return self.sale_price
        return self.regular_price or self.price
    
    @property
    def price_display(self):
        """Get formatted price for display"""
        if self.is_on_sale and self.regular_price and self.sale_price:
            return f"${self.sale_price:.2f} (was ${self.regular_price:.2f})"
        elif self.price:
            return f"${self.price:.2f}"
        return "Price not set"
    
    @property
    def total_stock(self):
        """Get total stock across all variations"""
        if not self.has_variations:
            return self.stock_quantity if self.manage_stock else None
        
        return self.variations.filter(is_active=True).aggregate(
            total=models.Sum('stock_quantity')
        )['total'] or 0
    
    @property
    def can_backorder(self):
        """Check if product can be backordered"""
        return self.backorders in ['yes', 'notify']
    
    @property
    def is_external(self):
        """Check if product is external/affiliate"""
        return self.type == 'external' and bool(self.external_url)
    
    def _parse_variation_attributes(self):
        """
        Parse composite variation_value fields to extract individual attributes.
        Handles both single and multi-dimensional variations.
        
        Returns dict with attribute type as key and set of values as value.
        """
        # Attribute priority order matching sync logic
        attribute_priority = ['size', 'color', 'material', 'style', 'gender', 'age_group']
        
        # Dictionary to store parsed attributes
        parsed_attributes = {attr: set() for attr in attribute_priority}
        
        # Get all active variations
        variations = self.variations.filter(is_active=True, stock_quantity__gt=0)
        
        for variation in variations:
            if not variation.variation_value:
                continue
            
            # Split composite variation_value (e.g., "3XL - Turquoise" -> ["3XL", "Turquoise"])
            components = [comp.strip() for comp in variation.variation_value.split(' - ')]
            
            # If it's a single component variation, use the variation_type
            if len(components) == 1:
                if variation.variation_type in attribute_priority:
                    parsed_attributes[variation.variation_type].add(components[0])
            else:
                # Multi-dimensional variation - map components to attribute types
                # Based on the sync logic priority order
                for i, component in enumerate(components):
                    if i < len(attribute_priority):
                        attr_type = attribute_priority[i]
                        parsed_attributes[attr_type].add(component)
        
        # Convert sets to sorted lists and filter out empty ones
        result = {}
        for attr_type, values in parsed_attributes.items():
            if values:
                result[attr_type] = sorted(list(values))
        
        return result
    
    @property
    def available_sizes(self):
        """Get available sizes for this product"""
        parsed = self._parse_variation_attributes()
        return parsed.get('size', [])
    
    @property
    def available_colors(self):
        """Get available colors for this product"""
        parsed = self._parse_variation_attributes()
        return parsed.get('color', [])
    
    @property
    def available_materials(self):
        """Get available materials for this product"""
        parsed = self._parse_variation_attributes()
        return parsed.get('material', [])
    
    @property
    def available_styles(self):
        """Get available styles for this product"""
        parsed = self._parse_variation_attributes()
        return parsed.get('style', [])
    
    @property
    def parsed_variation_attributes(self):
        """Get all parsed variation attributes as a dictionary"""
        return self._parse_variation_attributes()
    
    def get_available_variations_for_selection(self, **selection):
        """
        Get available variation options based on current selection.
        Returns dict with available options for each variation type.
        
        Args:
            **selection: Current user selection (e.g., size='Large', color='Red')
        
        Returns:
            dict: Available options for each variation type with stock info
        """
        from django.db.models import Q, Sum
        
        # Get all active variations with stock
        base_variations = self.variations.filter(is_active=True, stock_quantity__gt=0)
        
        # Apply current selection filters
        for attr_type, attr_value in selection.items():
            if attr_value:  # Only filter if value is provided
                base_variations = base_variations.filter(
                    variation_type=attr_type,
                    variation_value=attr_value
                )
        
        # Get available options for each variation type
        result = {}
        variation_types = ['size', 'color', 'material', 'style', 'gender', 'age_group']
        
        for var_type in variation_types:
            # Skip if this type is already selected
            if var_type in selection and selection[var_type]:
                continue
                
            # Get available options for this type
            options = []
            type_variations = base_variations.filter(variation_type=var_type).distinct()
            
            for variation in type_variations:
                # Check stock for this option combined with current selection
                test_selection = selection.copy()
                test_selection[var_type] = variation.variation_value
                
                # Find variations that match all criteria
                matching_variations = self.variations.filter(is_active=True)
                for test_attr, test_value in test_selection.items():
                    if test_value:
                        matching_variations = matching_variations.filter(
                            variation_type=test_attr,
                            variation_value=test_value
                        )
                
                total_stock = matching_variations.aggregate(
                    total=Sum('stock_quantity')
                )['total'] or 0
                
                if total_stock > 0:
                    options.append({
                        'value': variation.variation_value,
                        'stock': total_stock,
                        'available': True,
                        'variation_id': variation.id,
                        'price_modifier': float(variation.price_modifier),
                        'image': variation.image.url if variation.image else None
                    })
            
            if options:
                # Sort options by value
                options.sort(key=lambda x: x['value'])
                result[var_type] = options
        
        return result
    
    def get_variation_combination_stock(self, **combination):
        """
        Get stock quantity for a specific variation combination.
        
        Args:
            **combination: Variation attributes (e.g., size='Large', color='Red')
        
        Returns:
            int: Total stock quantity for the combination
        """
        from django.db.models import Sum
        
        variations = self.variations.filter(is_active=True)
        
        for attr_type, attr_value in combination.items():
            if attr_value:
                variations = variations.filter(
                    variation_type=attr_type,
                    variation_value=attr_value
                )
        
        total_stock = variations.aggregate(
            total=Sum('stock_quantity')
        )['total'] or 0
        
        return total_stock
    
    def is_variation_combination_available(self, **combination):
        """
        Check if a specific variation combination is available.
        
        Args:
            **combination: Variation attributes (e.g., size='Large', color='Red')
        
        Returns:
            bool: True if combination has stock, False otherwise
        """
        return self.get_variation_combination_stock(**combination) > 0
    
    def get_variation_data_for_frontend(self):
        """
        Get structured variation data for frontend JavaScript.
        
        Returns:
            dict: Structured data for frontend variation handling
        """
        if not self.has_variations:
            return {}
        
        variations_data = {
            'product_id': self.id,
            'has_variations': True,
            'variation_types': list(self.variations.filter(is_active=True).values_list('variation_type', flat=True).distinct()),
            'variations': [],
            'parsed_attributes': self.parsed_variation_attributes,
            'total_stock': self.total_stock
        }
        
        # Add individual variation data
        for variation in self.variations.filter(is_active=True):
            var_data = {
                'id': variation.id,
                'type': variation.variation_type,
                'value': variation.variation_value,
                'stock': variation.stock_quantity,
                'price_modifier': float(variation.price_modifier),
                'final_price': float(variation.final_price),
                'sku_suffix': variation.sku_suffix,
                'is_in_stock': variation.is_in_stock,
                'image': variation.effective_image_url,
                'attributes': variation.attributes or {}
            }
            variations_data['variations'].append(var_data)
        
        return variations_data
    
    @property
    def is_downloadable_product(self):
        """Check if product is downloadable"""
        return self.downloadable and self.downloads
    
    @property
    def has_unlimited_downloads(self):
        """Check if downloads are unlimited"""
        return self.download_limit == -1
    
    @property
    def has_unlimited_download_expiry(self):
        """Check if download expiry is unlimited"""
        return self.download_expiry == -1
    
    @property
    def primary_image_url(self):
        """Get primary image URL"""
        if self.image:
            return self.image  # image is now a URLField that stores URL directly
        elif self.images and isinstance(self.images, list) and len(self.images) > 0:
            return self.images[0].get('src', '')
        return None
    
    def get_attribute_value(self, attribute_name):
        """Get value for a specific attribute"""
        if not self.attributes or not isinstance(self.attributes, list):
            return None
        
        for attr in self.attributes:
            if isinstance(attr, dict) and attr.get('name') == attribute_name:
                return attr.get('options', [])
        
        return None
    
    def has_attribute(self, attribute_name):
        """Check if product has a specific attribute"""
        return self.get_attribute_value(attribute_name) is not None
    
    def get_tag_names(self):
        """Get list of tag names"""
        if not self.tags or not isinstance(self.tags, list):
            return []
        
        return [tag.get('name', '') for tag in self.tags if isinstance(tag, dict)]
    
    def has_tag(self, tag_name):
        """Check if product has a specific tag"""
        tag_names = self.get_tag_names()
        return tag_name.lower() in [name.lower() for name in tag_names]
    
    def get_category_names(self):
        """Get list of WooCommerce category names"""
        if not self.woo_categories or not isinstance(self.woo_categories, list):
            return []
        
        return [cat.get('name', '') for cat in self.woo_categories if isinstance(cat, dict)]
    
    def detect_changes(self, other_product_data):
        """
        Intelligent change detection for sync operations
        Returns dict of changes with field names as keys
        """
        changes = {}
        
        # Define fields to compare
        comparable_fields = [
            'name', 'status', 'featured', 'catalog_visibility', 'price', 'regular_price', 
            'sale_price', 'on_sale', 'description', 'short_description', 'sku', 
            'stock_status', 'stock_quantity', 'weight', 'average_rating', 'rating_count'
        ]
        
        for field in comparable_fields:
            if hasattr(self, field):
                current_value = getattr(self, field)
                new_value = other_product_data.get(field)
                
                # Handle different types of comparisons
                if field in ['price', 'regular_price', 'sale_price'] and new_value:
                    try:
                        new_value = Decimal(str(new_value))
                    except:
                        new_value = None
                
                if current_value != new_value:
                    changes[field] = {
                        'old': current_value,
                        'new': new_value
                    }
        
        # Check JSON fields
        json_fields = ['dimensions', 'tags', 'attributes', 'images']
        for field in json_fields:
            if hasattr(self, field):
                current_value = getattr(self, field)
                new_value = other_product_data.get(field)
                
                # Simple comparison for JSON fields (could be enhanced)
                if str(current_value) != str(new_value):
                    changes[field] = {
                        'old': current_value,
                        'new': new_value
                    }
        
        return changes


class LottoProductVariation(models.Model):
    """
    LOTTO-specific product variation model mapping to WooCommerce product variations
    """
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('material', 'Material'),
        ('style', 'Style'),
        ('gender', 'Gender'),
        ('age_group', 'Age Group'),
        ('other', 'Other'),
    ]
    
    # Relationships
    product = models.ForeignKey(LottoProduct, on_delete=models.CASCADE, related_name='variations')
    
    # Core fields
    variation_type = models.CharField(max_length=50, choices=VARIATION_TYPE_CHOICES, help_text="Type of variation")
    variation_value = models.CharField(max_length=255, help_text="Variation value (e.g., 'Large', 'Red', 'Cotton')")
    woo_variation_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce variation ID")
    
    # Pricing
    price_modifier = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        help_text="Price adjustment (+/-) from base product price"
    )
    
    # Stock
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Stock quantity for this variation")
    sku_suffix = models.CharField(max_length=50, blank=True, null=True, help_text="SKU suffix for this variation")
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Whether this variation is active")
    
    # Additional variation data from WooCommerce
    attributes = models.JSONField(blank=True, null=True, help_text="WooCommerce variation attributes")
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Variation weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Variation dimensions")
    
    # Image
    image = models.ImageField(
        upload_to='lotto/variations/images/', 
        blank=True, 
        null=True, 
        help_text="Variation-specific image"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lotto_product_variations'
        ordering = ['product', 'variation_type', 'variation_value']
        verbose_name = "LOTTO Product Variation"
        verbose_name_plural = "LOTTO Product Variations"
        unique_together = ['product', 'variation_type', 'variation_value']
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['woo_variation_id']),
            models.Index(fields=['variation_type', 'variation_value']),
            models.Index(fields=['stock_quantity']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-generate SKU suffix if not provided
        if not self.sku_suffix and self.variation_value:
            # Create a simple suffix from variation type and value
            type_short = self.variation_type[:3].upper()
            value_short = ''.join(c for c in self.variation_value if c.isalnum())[:5].upper()
            self.sku_suffix = f"{type_short}-{value_short}"
        
        super().save(*args, **kwargs)
        
        # Update parent product's stock status after variation changes
        if self.product and self.product.is_variable_product:
            self.product.update_stock_status_from_variations()
    
    def __str__(self):
        return f"{self.product.name} - {self.variation_type}: {self.variation_value}"
    
    @property
    def final_price(self):
        """Calculate the final price including price modifier"""
        base_price = self.product.price or 0
        return base_price + self.price_modifier
    
    @property
    def full_sku(self):
        """Generate full SKU including suffix"""
        base_sku = self.product.sku or f"LOTTO-{self.product.woo_product_id}"
        if self.sku_suffix:
            return f"{base_sku}-{self.sku_suffix}"
        return base_sku
    
    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.is_active and self.stock_quantity > 0
    
    @property
    def stock_status(self):
        """Get stock status based on quantity"""
        if not self.is_active:
            return 'discontinued'
        elif self.stock_quantity > 0:
            return 'instock'
        else:
            return 'outofstock'
    
    @property
    def effective_image(self):
        """Get effective image for this variation with fallback logic"""
        # If variation has its own image, use it
        if self.image:
            return self.image
        
        # Fallback to parent product image
        if self.product and self.product.image:
            return self.product.image
        
        return None
    
    @property
    def effective_image_url(self):
        """Get effective image URL for this variation"""
        effective_image = self.effective_image
        if effective_image:
            return effective_image  # effective_image now returns URL directly
        return None
    
    @property
    def has_unique_image(self):
        """Check if variation has its own unique image"""
        return bool(self.image)
    
    @property
    def should_show_variation_image(self):
        """Determine if variation image should be displayed based on variation type"""
        # Variation types that typically benefit from showing unique images
        image_priority_types = ['color', 'style', 'material']
        return self.variation_type in image_priority_types and self.has_unique_image
    
    def get_image_for_display(self):
        """Get appropriate image for display purposes"""
        # For color/style/material variations, prefer variation-specific image
        if self.should_show_variation_image:
            return self.image
        
        # For size/gender/other variations, use effective image with fallback
        return self.effective_image
    
    def detect_changes(self, other_variation_data):
        """
        Intelligent change detection for sync operations
        Returns dict of changes with field names as keys
        """
        changes = {}
        
        # Define fields to compare
        comparable_fields = [
            'variation_value', 'price_modifier', 'stock_quantity', 'is_active', 'weight'
        ]
        
        for field in comparable_fields:
            if hasattr(self, field):
                current_value = getattr(self, field)
                new_value = other_variation_data.get(field)
                
                # Handle different types of comparisons
                if field == 'price_modifier' and new_value:
                    try:
                        new_value = Decimal(str(new_value))
                    except:
                        new_value = Decimal('0.00')
                
                if current_value != new_value:
                    changes[field] = {
                        'old': current_value,
                        'new': new_value
                    }
        
        # Check JSON fields
        json_fields = ['attributes', 'dimensions']
        for field in json_fields:
            if hasattr(self, field):
                current_value = getattr(self, field)
                new_value = other_variation_data.get(field)
                
                if str(current_value) != str(new_value):
                    changes[field] = {
                        'old': current_value,
                        'new': new_value
                    }
        
        return changes