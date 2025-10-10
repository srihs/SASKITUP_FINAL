from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
import uuid
import logging

# Import TUS models
from .models_tus import (
    TUSLocation, TUSSchool, TUSGeneralCategory, TUSSchoolCategory,
    TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
)

logger = logging.getLogger(__name__)


class School(models.Model):
    """Model for New Zealand school data from government API"""

    # Primary identification
    school_id = models.CharField(max_length=10, unique=True, db_index=True)
    org_name = models.CharField(max_length=200, db_index=True)

    # Contact information
    telephone = models.CharField(max_length=20, blank=True)
    fax = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    contact1_name = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)

    # Physical address (Address 1)
    add1_line1 = models.CharField(max_length=200, blank=True)
    add1_suburb = models.CharField(max_length=100, blank=True)
    add1_city = models.CharField(max_length=100, blank=True)

    # Postal address (Address 2)
    add2_line1 = models.CharField(max_length=200, blank=True)
    add2_suburb = models.CharField(max_length=100, blank=True)
    add2_city = models.CharField(max_length=100, blank=True)
    add2_postal_code = models.CharField(max_length=10, blank=True)

    # Classification
    urban_rural_indicator = models.CharField(max_length=100, blank=True)
    org_type = models.CharField(max_length=100, blank=True, db_index=True)
    definition = models.TextField(blank=True)
    authority = models.CharField(max_length=50, blank=True)
    school_donations = models.TextField(blank=True)
    coed_status = models.CharField(max_length=50, blank=True)
    kme_peak_body = models.CharField(max_length=100, blank=True)

    # Geographic/administrative regions
    takiwa = models.CharField(max_length=100, blank=True)
    territorial_authority = models.CharField(max_length=150, blank=True)
    regional_council = models.CharField(max_length=100, blank=True)
    local_office_name = models.CharField(max_length=100, blank=True)
    education_region = models.CharField(max_length=100, blank=True)
    general_electorate = models.CharField(max_length=100, blank=True)
    maori_electorate = models.CharField(max_length=100, blank=True)

    # Statistical area
    statistical_area_2_code = models.CharField(max_length=20, blank=True)
    statistical_area_2_description = models.CharField(max_length=200, blank=True)
    ward = models.CharField(max_length=100, blank=True)

    # Community of Learning
    col_id = models.CharField(max_length=20, blank=True)
    col_name = models.CharField(max_length=200, blank=True)

    # Location
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # School characteristics
    enrolment_scheme = models.CharField(max_length=10, blank=True)
    eqi_index = models.CharField(max_length=10, blank=True)

    # Roll information
    roll_date = models.DateTimeField(null=True, blank=True)
    total = models.IntegerField(default=0)
    european = models.IntegerField(default=0)
    maori = models.IntegerField(default=0)
    pacific = models.IntegerField(default=0)
    asian = models.IntegerField(default=0)
    melaa = models.IntegerField(default=0)
    other = models.IntegerField(default=0)
    international = models.IntegerField(default=0)

    # Other characteristics
    isolation_index = models.CharField(max_length=10, blank=True)
    language_of_instruction = models.CharField(max_length=100, blank=True)
    boarding_facilities = models.CharField(max_length=10, blank=True)
    cohort_entry = models.CharField(max_length=10, blank=True)
    status = models.CharField(max_length=20, blank=True)
    date_school_opened = models.DateTimeField(null=True, blank=True)

    # Images
    logo = models.URLField(max_length=500, blank=True, null=True, help_text="School logo image URL")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['org_name']
        indexes = [
            models.Index(fields=['org_type', 'org_name']),
            models.Index(fields=['regional_council', 'org_name']),
            models.Index(fields=['territorial_authority', 'org_name']),
        ]
        verbose_name = 'School'
        verbose_name_plural = 'Schools'

    def __str__(self):
        return self.org_name

    def get_absolute_url(self):
        return reverse('schools:school_detail', kwargs={'school_id': self.school_id})

    @property
    def full_address(self):
        """Return formatted physical address"""
        parts = []
        if self.add1_line1:
            parts.append(self.add1_line1)
        if self.add1_suburb:
            parts.append(self.add1_suburb)
        if self.add1_city:
            parts.append(self.add1_city)
        return ', '.join(parts)

    @property
    def postal_address(self):
        """Return formatted postal address"""
        parts = []
        if self.add2_line1:
            parts.append(self.add2_line1)
        if self.add2_suburb:
            parts.append(self.add2_suburb)
        if self.add2_city:
            parts.append(self.add2_city)
        if self.add2_postal_code:
            parts.append(self.add2_postal_code)
        return ', '.join(parts)

    @property
    def has_location(self):
        """Check if school has GPS coordinates"""
        return self.latitude is not None and self.longitude is not None


# =====================================
# WHOLESALE SCHOOLS MODELS
# =====================================
# Wholesale Schools Models for CIN7 Integration
#
# This section contains models specifically for wholesale schools data from CIN7 API.
# These models are completely separate from retail club models and regular school models.


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

    # Images
    logo = models.URLField(max_length=500, blank=True, null=True, help_text="School logo image URL")

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
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # Create unique slug
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            # Ensure uniqueness by appending numbers if needed
            while WholesaleSchool.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('schools:wholesale-school-detail', kwargs={'slug': self.slug})

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

    # Calculated pricing fields for price update feature
    margin_75_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="75% margin price (Cost ÷ 0.25)"
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Discount percentage from 75% margin price"
    )
    last_price_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When prices were last updated"
    )

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
            models.Index(fields=['margin_75_price']),
            models.Index(fields=['discount_percentage']),
            models.Index(fields=['last_price_update']),
        ]

    def __str__(self):
        return f"{self.name} - {self.school.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.cin7_sku}")

        # Calculate margin_75_price if cost_price is available
        if self.cost_price and self.cost_price > 0:
            self.margin_75_price = self.cost_price / Decimal('0.25')

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

    def calculate_margin_75_price(self):
        """Calculate the 75% margin price (Cost ÷ 0.25)"""
        if self.cost_price and self.cost_price > 0:
            return self.cost_price / Decimal('0.25')
        return None

    def calculate_discount_percentage(self):
        """Calculate discount percentage from 75% margin price"""
        if self.margin_75_price and self.wholesale_price and self.margin_75_price > 0:
            discount = ((self.margin_75_price - self.wholesale_price) / self.margin_75_price) * 100
            return max(Decimal('0'), discount)  # Don't allow negative discounts
        return None

    def update_calculated_pricing(self):
        """Update all calculated pricing fields"""
        from django.utils import timezone

        self.margin_75_price = self.calculate_margin_75_price()
        self.discount_percentage = self.calculate_discount_percentage()
        self.last_price_update = timezone.now()
        self.save(update_fields=['margin_75_price', 'discount_percentage', 'last_price_update'])

    @property
    def has_variations(self):
        """Check if product has variations"""
        return self.variations.filter(is_active=True).exists()

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

    # Pricing management fields (for wholesale price update system)
    margin_75_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Price with 75% margin (cost ÷ 0.25)"
    )
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Discount percentage from 75% margin price"
    )
    last_price_update = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp of last price update"
    )

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


class Cin7Product(models.Model):
    """
    Temporary storage for Cin7 API product data

    This model stores raw data from Cin7 API before matching and price updates.
    Allows for two-stage processing: fetch → match/update

    Fields map directly to Cin7 API response fields.
    """

    # Cin7 identifiers
    cin7_id = models.IntegerField(db_index=True, help_text="Cin7 product ID")
    code = models.CharField(max_length=100, db_index=True, help_text="Product SKU/Code")
    style_code = models.CharField(max_length=100, blank=True, db_index=True, help_text="Product style code")
    barcode = models.CharField(max_length=100, blank=True, db_index=True, help_text="Product barcode")

    # Product details
    name = models.CharField(max_length=500, help_text="Product name")
    category = models.CharField(max_length=200, blank=True, help_text="Cin7 category")
    brand = models.CharField(max_length=200, blank=True, help_text="Product brand")

    # Pricing data
    cost_nzd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price in NZD")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Retail price (RRP)")

    # Calculated pricing (on save)
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="75% margin price (Cost ÷ 0.25)")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Discount from 75% margin")

    # Stock data
    stock_available = models.IntegerField(null=True, blank=True, help_text="Available stock quantity")

    # Matching status
    matched = models.BooleanField(default=False, db_index=True, help_text="Whether matched to local product")
    matched_product_id = models.IntegerField(null=True, blank=True, help_text="Local product ID if matched")
    matched_variation_id = models.IntegerField(null=True, blank=True, help_text="Local variation ID if matched")
    match_method = models.CharField(max_length=100, blank=True, help_text="How product was matched")
    price_type = models.CharField(max_length=50, db_index=True, help_text="Price type: TUS, LOTTO, SAS, Wholesale")

    # Processing status
    processed = models.BooleanField(default=False, db_index=True, help_text="Whether prices have been applied")
    processed_at = models.DateTimeField(null=True, blank=True, help_text="When prices were applied")

    # Metadata
    fetch_session_id = models.CharField(max_length=100, db_index=True, help_text="Session ID from fetch operation")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Raw JSON data (for debugging/future use)
    raw_data = models.JSONField(null=True, blank=True, help_text="Raw Cin7 API response")

    class Meta:
        db_table = 'cin7_products'
        verbose_name = 'Cin7 Product'
        verbose_name_plural = 'Cin7 Products'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['fetch_session_id', 'matched']),
            models.Index(fields=['price_type', 'processed']),
            models.Index(fields=['created_at', 'fetch_session_id']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        """Calculate derived fields on save"""
        # Calculate 75% margin price
        if self.cost_nzd and self.cost_nzd > 0:
            self.margin_75_price = self.cost_nzd / Decimal('0.25')

        # Calculate discount percentage
        if self.margin_75_price and self.retail_price and self.margin_75_price > 0:
            discount = ((self.margin_75_price - self.retail_price) / self.margin_75_price) * 100
            self.discount_percentage = max(Decimal('0'), discount)

        super().save(*args, **kwargs)

    @property
    def has_pricing_data(self):
        """Check if product has valid pricing data"""
        return self.cost_nzd is not None and self.cost_nzd > 0

    @property
    def is_ready_for_update(self):
        """Check if product is ready for price update"""
        return self.matched and self.has_pricing_data and not self.processed
