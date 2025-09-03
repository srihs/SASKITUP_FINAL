import os
import logging
import uuid
from django.db import models
from django.core.validators import URLValidator
from django.utils.text import slugify
from django.utils import timezone


logger = logging.getLogger(__name__)


class SyncJob(models.Model):
    """
    Model to track sync job status and progress for async operations
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    SYNC_TYPE_CHOICES = [
        ('lotto', 'LOTTO Clubs'),
        ('sas', 'SAS Clubs'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sync_type = models.CharField(max_length=10, choices=SYNC_TYPE_CHOICES, help_text="Type of sync operation")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress_percentage = models.PositiveSmallIntegerField(default=0, help_text="Progress from 0 to 100")
    current_step = models.CharField(max_length=255, blank=True, help_text="Current operation being performed")
    
    # Statistics
    clubs_created = models.PositiveIntegerField(default=0)
    clubs_updated = models.PositiveIntegerField(default=0)
    categories_created = models.PositiveIntegerField(default=0)
    categories_updated = models.PositiveIntegerField(default=0)
    products_created = models.PositiveIntegerField(default=0)
    products_updated = models.PositiveIntegerField(default=0)
    
    # Logs and errors
    log_messages = models.JSONField(default=list, help_text="Array of log messages")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if failed")
    error_code = models.CharField(max_length=50, blank=True, null=True, help_text="Error code for programmatic handling")
    
    # Metadata
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Sync Job"
        verbose_name_plural = "Sync Jobs"
        indexes = [
            models.Index(fields=['status', 'sync_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_sync_type_display()} - {self.get_status_display()}"
    
    def add_log_message(self, message, level='info'):
        """Add a log message to the job"""
        if not isinstance(self.log_messages, list):
            self.log_messages = []
        
        self.log_messages.append({
            'timestamp': timezone.now().isoformat(),
            'level': level,
            'message': message
        })
        self.save(update_fields=['log_messages', 'updated_at'])
    
    def update_progress(self, percentage, step=None):
        """Update progress and current step"""
        self.progress_percentage = min(100, max(0, percentage))
        if step:
            self.current_step = step
        self.save(update_fields=['progress_percentage', 'current_step', 'updated_at'])
    
    def start(self):
        """Mark job as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.progress_percentage = 0
        self.save(update_fields=['status', 'started_at', 'progress_percentage', 'updated_at'])
    
    def complete(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress_percentage = 100
        self.save(update_fields=['status', 'completed_at', 'progress_percentage', 'updated_at'])
    
    def fail(self, error_message, error_code=None):
        """Mark job as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.error_code = error_code
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'error_code', 'completed_at', 'updated_at'])
    
    @property
    def duration(self):
        """Get job duration if completed"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def is_finished(self):
        """Check if job is finished (completed, failed, or cancelled)"""
        return self.status in ['completed', 'failed', 'cancelled']
    
    @property
    def total_items_created(self):
        """Get total items created across all types"""
        return self.clubs_created + self.categories_created + self.products_created
    
    @property
    def total_items_updated(self):
        """Get total items updated across all types"""
        return self.clubs_updated + self.categories_updated + self.products_updated


class Club(models.Model):
    """
    Model representing a sports club (LOTTO or SAS)
    """
    CLUB_TYPES = [
        ('LOTTO', 'LOTTO'),
        ('SAS', 'SAS'),
    ]
    
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

    name = models.CharField(max_length=255, unique=True, help_text="Club name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")
    contact_person = models.CharField(max_length=100, blank=True, null=True, help_text="Primary contact person")
    email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    website = models.URLField(blank=True, null=True, validators=[URLValidator()], help_text="Club website URL")
    address = models.TextField(blank=True, null=True, help_text="Club physical address")
    club_type = models.CharField(max_length=10, choices=CLUB_TYPES, default='LOTTO', help_text="Type of club")
    sport_tag = models.CharField(max_length=50, choices=SPORT_TAGS, default='Football', help_text="Primary sport")
    logo = models.ImageField(upload_to='clubs/images/', blank=True, null=True, help_text="Club logo image")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    is_active = models.BooleanField(default=True, help_text="Whether the club is active")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Club"
        verbose_name_plural = "Clubs"
        indexes = [
            models.Index(fields=['club_type', 'is_active']),
            models.Index(fields=['woo_category_id']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.club_type})"
    
    @property
    def total_products(self):
        """Get total number of products across all categories for this club"""
        return sum(category.products.count() for category in self.categories.all())
    
    @property
    def active_categories_count(self):
        """Get count of categories with products"""
        return self.categories.filter(product_count__gt=0).count()


class ClubCategory(models.Model):
    """
    Model representing product categories within a club
    """
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=255, help_text="Category name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    description = models.TextField(blank=True, null=True, help_text="Category description")
    image = models.ImageField(upload_to='categories/images/', blank=True, null=True, help_text="Category image")
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products in this category")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['club', 'name']
        verbose_name = "Club Category"
        verbose_name_plural = "Club Categories"
        unique_together = ['club', 'name']
        indexes = [
            models.Index(fields=['club', 'product_count']),
            models.Index(fields=['woo_category_id']),
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
        self.save(update_fields=['product_count'])


class Product(models.Model):
    """
    Model representing products within club categories
    """
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]
    
    category = models.ForeignKey(ClubCategory, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_product_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce product ID")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Product price")
    description = models.TextField(blank=True, null=True, help_text="Product description")
    short_description = models.TextField(blank=True, null=True, help_text="Short product description")
    image = models.ImageField(upload_to='products/images/', blank=True, null=True, help_text="Product image")
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Stock Keeping Unit")
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Additional WooCommerce fields
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Product weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Product dimensions")
    tags = models.JSONField(blank=True, null=True, help_text="Product tags")
    attributes = models.JSONField(blank=True, null=True, help_text="Product attributes")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name = "Product"
        verbose_name_plural = "Products"
        unique_together = ['category', 'name']
        indexes = [
            models.Index(fields=['category', 'stock_status']),
            models.Index(fields=['woo_product_id']),
            models.Index(fields=['sku']),
            models.Index(fields=['price']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.category.club.name}-{self.category.name}-{self.name}")
        
        # Ensure price is set correctly - prioritize sale_price, then price, then regular_price
        if self.sale_price and self.sale_price > 0:
            # If there's a sale price, use it as the main price
            if not self.price or self.price == 0:
                self.price = self.sale_price
        elif not self.price and self.regular_price:
            # Fallback to regular_price if no main price is set
            self.price = self.regular_price
        
        super().save(*args, **kwargs)
        
        # Update parent category product count
        self.category.update_product_count()
    
    def delete(self, *args, **kwargs):
        category = self.category
        super().delete(*args, **kwargs)
        # Update parent category product count after deletion
        category.update_product_count()
    
    def __str__(self):
        return f"{self.category.club.name} - {self.name}"
    
    @property
    def is_on_sale(self):
        """Check if product is on sale"""
        return self.sale_price and self.sale_price < self.regular_price
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage if on sale"""
        if self.is_on_sale and self.regular_price:
            return round(((self.regular_price - self.sale_price) / self.regular_price) * 100, 2)
        return 0
    
    @property
    def has_variations(self):
        """Check if product has variations"""
        return self.variations.filter(is_active=True).exists()
    
    @property
    def is_variable_product(self):
        """Check if this is a variable product (same as has_variations)"""
        return self.has_variations
    
    @property
    def available_sizes(self):
        """Get available sizes for this product"""
        return self.variations.filter(
            variation_type='size', 
            is_active=True, 
            stock_quantity__gt=0
        ).values_list('variation_value', flat=True).distinct()
    
    @property
    def available_colors(self):
        """Get available colors for this product"""
        return self.variations.filter(
            variation_type='color', 
            is_active=True, 
            stock_quantity__gt=0
        ).values_list('variation_value', flat=True).distinct()
    
    @property
    def variation_types(self):
        """Get all variation types available for this product"""
        return self.variations.filter(is_active=True).values_list(
            'variation_type', flat=True
        ).distinct()
    
    @property 
    def price_range(self):
        """Get price range for variable products"""
        if not self.has_variations:
            return None
        
        variations = self.variations.filter(is_active=True)
        if not variations.exists():
            return None
        
        prices = [variation.final_price for variation in variations]
        min_price = min(prices)
        max_price = max(prices)
        
        if min_price == max_price:
            return f"${min_price:.2f}"
        else:
            return f"${min_price:.2f} - ${max_price:.2f}"
    
    @property
    def total_stock(self):
        """Get total stock across all variations"""
        if not self.has_variations:
            return None
        
        return self.variations.filter(is_active=True).aggregate(
            total=models.Sum('stock_quantity')
        )['total'] or 0
    
    def get_variations_by_type(self, variation_type):
        """Get variations filtered by type"""
        return self.variations.filter(
            variation_type=variation_type, 
            is_active=True
        ).order_by('variation_value')
    
    def get_variation_by_attributes(self, **attributes):
        """Get specific variation by attributes (e.g., size='Large', color='Red')"""
        variations = self.variations.filter(is_active=True)
        
        for attr_type, attr_value in attributes.items():
            variations = variations.filter(
                variation_type=attr_type,
                variation_value=attr_value
            )
        
        return variations.first()
    
    def get_variation_images_by_type(self, variation_type):
        """Get all unique images for variations of a specific type"""
        variations = self.variations.filter(
            variation_type=variation_type,
            is_active=True
        ).exclude(image__isnull=True).exclude(image='')
        
        # Return list of (variation_value, image) tuples
        return [(var.variation_value, var.image) for var in variations]
    
    def get_primary_variation_image(self):
        """Get primary variation image (preferring color variations)"""
        # Try color variations first
        color_variations = self.variations.filter(
            variation_type='color',
            is_active=True
        ).exclude(image__isnull=True).exclude(image='').first()
        
        if color_variations:
            return color_variations.image
        
        # Then try style variations
        style_variations = self.variations.filter(
            variation_type='style',
            is_active=True
        ).exclude(image__isnull=True).exclude(image='').first()
        
        if style_variations:
            return style_variations.image
        
        # Finally, any variation with image
        any_variation = self.variations.filter(
            is_active=True
        ).exclude(image__isnull=True).exclude(image='').first()
        
        if any_variation:
            return any_variation.image
        
        # Fallback to product image
        return self.image


class ProductVariation(models.Model):
    """
    Model representing product variations (size, color, etc.) for variable products
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
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')
    variation_type = models.CharField(max_length=50, choices=VARIATION_TYPE_CHOICES, help_text="Type of variation")
    variation_value = models.CharField(max_length=255, help_text="Variation value (e.g., 'Large', 'Red', 'Cotton')")
    price_modifier = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        help_text="Price adjustment (+/-) from base product price"
    )
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Stock quantity for this variation")
    sku_suffix = models.CharField(max_length=50, blank=True, null=True, help_text="SKU suffix for this variation")
    woo_variation_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce variation ID")
    is_active = models.BooleanField(default=True, help_text="Whether this variation is active")
    
    # Additional variation data from WooCommerce
    attributes = models.JSONField(blank=True, null=True, help_text="WooCommerce variation attributes")
    image = models.ImageField(
        upload_to='variations/images/', 
        blank=True, 
        null=True, 
        help_text="Variation-specific image"
    )
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Variation weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Variation dimensions")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['product', 'variation_type', 'variation_value']
        verbose_name = "Product Variation"
        verbose_name_plural = "Product Variations"
        unique_together = ['product', 'variation_type', 'variation_value']
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['woo_variation_id']),
            models.Index(fields=['variation_type', 'variation_value']),
            models.Index(fields=['stock_quantity']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-generate SKU suffix if not provided
        if not self.sku_suffix and self.variation_value:
            # Create a simple suffix from variation type and value
            type_short = self.variation_type[:3].upper()
            value_short = ''.join(c for c in self.variation_value if c.isalnum())[:5].upper()
            self.sku_suffix = f"{type_short}-{value_short}"
        
        super().save(*args, **kwargs)
    
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
        base_sku = self.product.sku or f"PROD-{self.product.woo_product_id}"
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
            return effective_image.url
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
