"""
Wholesale Schools Models for CIN7 Integration

This module contains models specifically for wholesale schools data from CIN7 API.
These models are completely separate from retail club models and regular school models.
"""

import logging
import uuid
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal

logger = logging.getLogger(__name__)


class WholesaleSchool(models.Model):
    """
    Model for wholesale schools from CIN7 API
    Completely separate from regular School model
    """
    # Primary identification from CIN7
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Product ID")
    name = models.CharField(max_length=255, db_index=True, help_text="School name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")

    # School details
    description = models.TextField(blank=True, help_text="School description from CIN7")
    school_code = models.CharField(max_length=50, blank=True, db_index=True, help_text="Internal school code")

    # Contact information
    contact_person = models.CharField(max_length=100, blank=True, help_text="Primary contact person")
    email = models.EmailField(blank=True, help_text="Contact email")
    phone = models.CharField(max_length=20, blank=True, help_text="Contact phone")
    website = models.URLField(blank=True, help_text="School website")

    # Address information
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=50, default='New Zealand')

    # CIN7 specific fields
    cin7_sku = models.CharField(max_length=100, blank=True, help_text="CIN7 SKU")
    cin7_barcode = models.CharField(max_length=100, blank=True, help_text="CIN7 Barcode")
    cin7_brand = models.CharField(max_length=100, blank=True, help_text="CIN7 Brand")
    cin7_supplier = models.CharField(max_length=100, blank=True, help_text="CIN7 Supplier")
    cin7_category_path = models.TextField(blank=True, help_text="Full category path from CIN7")

    # Status and metadata
    is_active = models.BooleanField(default=True, help_text="Whether school is active")
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text="Last sync from CIN7")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Statistics
    total_products = models.PositiveIntegerField(default=0, help_text="Total products for this school")
    active_categories = models.PositiveIntegerField(default=0, help_text="Number of active categories")

    class Meta:
        db_table = 'wholesale_schools'
        verbose_name = 'Wholesale School'
        verbose_name_plural = 'Wholesale Schools'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['cin7_id']),
            models.Index(fields=['is_active']),
            models.Index(fields=['last_synced_at']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('clubs:wholesale-school-detail', kwargs={'slug': self.slug})

    @property
    def full_address(self):
        """Return formatted full address"""
        address_parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.region,
            self.postal_code
        ]
        return ', '.join([part for part in address_parts if part])

    @property
    def categories(self):
        """Get all categories that have products for this school"""
        return WholesaleCategory.objects.filter(products__school=self).distinct()

    @property
    def total_categories(self):
        """Get count of categories for this school"""
        return self.categories.count()

    @property
    def total_products(self):
        """Get count of total products for this school"""
        return self.products.filter(is_active=True).count()


class WholesaleCategory(models.Model):
    """
    Model for wholesale product categories from CIN7
    Represents the category structure: Wholesale Schools > Sub Category > Product Categories
    """
    # Primary identification
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Category ID")
    name = models.CharField(max_length=255, db_index=True, help_text="Category name")
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    # Hierarchy
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subcategories')
    level = models.PositiveSmallIntegerField(default=0, help_text="Category level (0=root, 1=sub, etc.)")

    # Category details
    description = models.TextField(blank=True, help_text="Category description")
    path = models.TextField(blank=True, help_text="Full category path")

    # Status and metadata
    is_active = models.BooleanField(default=True)
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products in this category")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wholesale_categories'
        verbose_name = 'Wholesale Category'
        verbose_name_plural = 'Wholesale Categories'
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['cin7_id']),
            models.Index(fields=['parent']),
            models.Index(fields=['level']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def products_for_school(self, school):
        """Get products in this category for a specific school"""
        return self.products.filter(school=school)

    def product_count_for_school(self, school):
        """Get count of products in this category for a specific school"""
        return self.products.filter(school=school).count()


class WholesaleProduct(models.Model):
    """
    Model for wholesale products from CIN7 API
    Products belong to wholesale schools and categories
    """
    STOCK_STATUS_CHOICES = [
        ('in_stock', 'In Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('discontinued', 'Discontinued'),
        ('on_order', 'On Order'),
    ]

    # Primary identification from CIN7
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Product ID")
    name = models.CharField(max_length=255, db_index=True, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True)

    # Relationships
    school = models.ForeignKey(WholesaleSchool, on_delete=models.CASCADE, related_name='products')
    categories = models.ManyToManyField(WholesaleCategory, through='WholesaleProductCategoryAssignment', related_name='products')

    # Product details
    description = models.TextField(blank=True, help_text="Product description")
    short_description = models.TextField(blank=True, help_text="Short product description")

    # CIN7 specific fields
    cin7_sku = models.CharField(max_length=100, blank=True, db_index=True, help_text="CIN7 SKU")
    cin7_barcode = models.CharField(max_length=100, blank=True, help_text="CIN7 Barcode")
    cin7_brand = models.CharField(max_length=100, blank=True, help_text="CIN7 Brand")
    cin7_supplier = models.CharField(max_length=100, blank=True, help_text="CIN7 Supplier")
    cin7_unit_of_measure = models.CharField(max_length=50, blank=True, help_text="Unit of measure")

    # Pricing
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Wholesale price")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Retail price")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price")

    # Stock information
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='in_stock')
    quantity_available = models.IntegerField(default=0, help_text="Available quantity")
    quantity_on_hand = models.IntegerField(default=0, help_text="Quantity on hand")
    quantity_committed = models.IntegerField(default=0, help_text="Committed quantity")

    # Product attributes
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, help_text="Weight in kg")
    dimensions = models.JSONField(default=dict, blank=True, help_text="Product dimensions")
    attributes = models.JSONField(default=dict, blank=True, help_text="Additional product attributes")

    # Images and media
    image_url = models.URLField(blank=True, help_text="Primary product image URL")
    additional_images = models.JSONField(default=list, blank=True, help_text="Additional image URLs")

    # Status and metadata
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wholesale_products'
        verbose_name = 'Wholesale Product'
        verbose_name_plural = 'Wholesale Products'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['cin7_id']),
            models.Index(fields=['cin7_sku']),
            models.Index(fields=['school']),
            models.Index(fields=['stock_status']),
            models.Index(fields=['is_active']),
            models.Index(fields=['wholesale_price']),
        ]

    def __str__(self):
        return f"{self.name} - {self.school.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.cin7_sku}")
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        """Check if product is in stock"""
        return self.stock_status == 'in_stock' and self.quantity_available > 0

    @property
    def profit_margin(self):
        """Calculate profit margin if prices are available"""
        if self.wholesale_price and self.cost_price and self.cost_price > 0:
            return ((self.wholesale_price - self.cost_price) / self.cost_price) * 100
        return None

    @property
    def primary_category(self):
        """Get the primary category for this product"""
        assignment = self.category_assignments.filter(is_primary=True).first()
        return assignment.category if assignment else None


class WholesaleProductCategoryAssignment(models.Model):
    """
    Through model for product-category relationships
    Allows products to belong to multiple categories with metadata
    """
    product = models.ForeignKey(WholesaleProduct, on_delete=models.CASCADE, related_name='category_assignments')
    category = models.ForeignKey(WholesaleCategory, on_delete=models.CASCADE, related_name='product_assignments')

    # Assignment metadata
    is_primary = models.BooleanField(default=False, help_text="Is this the primary category for the product?")
    sort_order = models.PositiveIntegerField(default=0, help_text="Sort order within category")
    cin7_category_id = models.CharField(max_length=50, blank=True, help_text="Original CIN7 category ID")

    # Timestamps
    assigned_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'wholesale_product_category_assignments'
        verbose_name = 'Product Category Assignment'
        verbose_name_plural = 'Product Category Assignments'
        unique_together = ['product', 'category']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
            models.Index(fields=['category', 'sort_order']),
            models.Index(fields=['cin7_category_id']),
        ]

    def __str__(self):
        return f"{self.product.name} -> {self.category.name}"


class WholesaleProductVariation(models.Model):
    """
    Model for product variations (sizes, colors, etc.)
    """
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('style', 'Style'),
        ('material', 'Material'),
        ('other', 'Other'),
    ]

    # Primary identification
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Variation ID")
    product = models.ForeignKey(WholesaleProduct, on_delete=models.CASCADE, related_name='variations')

    # Variation details
    variation_type = models.CharField(max_length=20, choices=VARIATION_TYPE_CHOICES, help_text="Type of variation")
    variation_value = models.CharField(max_length=100, help_text="Variation value (e.g., 'Large', 'Red')")
    variation_description = models.TextField(blank=True, help_text="Detailed variation description")

    # CIN7 specific fields
    cin7_sku = models.CharField(max_length=100, blank=True, help_text="CIN7 SKU for this variation")
    cin7_barcode = models.CharField(max_length=100, blank=True, help_text="CIN7 Barcode for this variation")

    # Pricing (can override product pricing)
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Stock for this specific variation
    quantity_available = models.IntegerField(default=0)
    quantity_on_hand = models.IntegerField(default=0)
    quantity_committed = models.IntegerField(default=0)

    # Variation-specific attributes
    weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    dimensions = models.JSONField(default=dict, blank=True)
    image_url = models.URLField(blank=True, help_text="Variation-specific image URL")

    # Status and metadata
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wholesale_product_variations'
        verbose_name = 'Wholesale Product Variation'
        verbose_name_plural = 'Wholesale Product Variations'
        unique_together = ['product', 'variation_type', 'variation_value']
        ordering = ['variation_type', 'variation_value']
        indexes = [
            models.Index(fields=['cin7_id']),
            models.Index(fields=['product', 'variation_type']),
            models.Index(fields=['cin7_sku']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.variation_type}: {self.variation_value}"

    @property
    def is_in_stock(self):
        """Check if this variation is in stock"""
        return self.quantity_available > 0


class WholesaleSyncJob(models.Model):
    """
    Model to track wholesale sync job status and progress
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    # Job identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Progress tracking
    progress_percentage = models.PositiveSmallIntegerField(default=0, help_text="Progress from 0 to 100")
    current_step = models.CharField(max_length=255, blank=True, help_text="Current operation being performed")

    # Statistics
    schools_created = models.PositiveIntegerField(default=0)
    schools_updated = models.PositiveIntegerField(default=0)
    products_created = models.PositiveIntegerField(default=0)
    products_updated = models.PositiveIntegerField(default=0)
    categories_created = models.PositiveIntegerField(default=0)
    categories_updated = models.PositiveIntegerField(default=0)
    variations_created = models.PositiveIntegerField(default=0)
    variations_updated = models.PositiveIntegerField(default=0)

    # Error tracking
    errors_count = models.PositiveIntegerField(default=0)
    error_messages = models.JSONField(default=list, blank=True)

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wholesale_sync_jobs'
        verbose_name = 'Wholesale Sync Job'
        verbose_name_plural = 'Wholesale Sync Jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Wholesale Sync Job {self.id} - {self.status}"

    @property
    def duration(self):
        """Calculate job duration if completed"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def total_items_processed(self):
        """Total number of items processed"""
        return (self.schools_created + self.schools_updated +
                self.products_created + self.products_updated +
                self.categories_created + self.categories_updated +
                self.variations_created + self.variations_updated)