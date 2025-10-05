import os
import logging
from decimal import Decimal
from django.db import models
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


class TUSLocation(models.Model):
    """
    TUS-specific location model representing geographic locations
    (e.g., cities, regions) that contain schools
    """
    name = models.CharField(max_length=255, unique=True, help_text="Location name (e.g., Pakuranga, Auckland)")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID for this location")
    parent_location = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_locations',
        help_text="Parent location for hierarchical structure"
    )

    # Metadata
    description = models.TextField(blank=True, null=True, help_text="Location description")
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Location image URL")

    # Status
    is_active = models.BooleanField(default=True, help_text="Whether the location is active")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_locations'
        ordering = ['name']
        verbose_name = "TUS Location"
        verbose_name_plural = "TUS Locations"
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['parent_location']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.parent_location:
            return f"{self.parent_location.name} > {self.name}"
        return self.name

    @property
    def total_schools(self):
        """Get total number of schools in this location"""
        return self.schools.count()

    @property
    def active_schools_count(self):
        """Get count of active schools"""
        return self.schools.filter(is_active=True).count()

    @property
    def full_path(self):
        """Get full hierarchical path for this location"""
        path_parts = [self.name]
        parent = self.parent_location
        while parent:
            path_parts.insert(0, parent.name)
            parent = parent.parent_location
        return ' > '.join(path_parts)

    @property
    def total_products(self):
        """Get total number of products across all schools in this location"""
        # Use lazy import to avoid circular imports
        from django.apps import apps
        TUSProduct = apps.get_model('clubs', 'TUSProduct')
        return TUSProduct.objects.filter(
            category_assignments__school_category__school__location=self,
            stock_status__in=['instock', 'onbackorder']
        ).distinct().count()


class TUSSchool(models.Model):
    """
    TUS-specific school model mapping to WooCommerce categories at school level
    Schools are organized under locations (e.g., /location/pakuranga/pakuranga-college/)
    """
    SCHOOL_TYPES = [
        ('Primary', 'Primary School'),
        ('Intermediate', 'Intermediate School'),
        ('Secondary', 'Secondary School'),
        ('Combined', 'Combined School'),
        ('Special', 'Special School'),
        ('Early Childhood', 'Early Childhood'),
        ('Tertiary', 'Tertiary Institution'),
        ('Other', 'Other'),
    ]

    # Core fields
    name = models.CharField(max_length=255, help_text="School name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")
    location = models.ForeignKey(
        TUSLocation,
        on_delete=models.CASCADE,
        related_name='schools',
        help_text="Location this school belongs to"
    )
    school_type = models.CharField(max_length=20, choices=SCHOOL_TYPES, default='Secondary', help_text="Type of school")

    # Contact information
    contact_person = models.CharField(max_length=100, blank=True, null=True, help_text="Primary contact person")
    email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    website = models.URLField(blank=True, null=True, validators=[URLValidator()], help_text="School website URL")
    address = models.TextField(blank=True, null=True, help_text="School physical address")

    # WooCommerce integration
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")

    # Images
    logo_url = models.URLField(max_length=500, blank=True, null=True, help_text="School logo URL")
    banner_url = models.URLField(max_length=500, blank=True, null=True, help_text="School banner image URL")

    # Additional metadata
    enrollment_number = models.PositiveIntegerField(blank=True, null=True, help_text="Number of enrolled students")
    decile_rating = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="School decile rating (1-10)"
    )

    # Status
    is_active = models.BooleanField(default=True, help_text="Whether the school is active")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_schools'
        ordering = ['location', 'name']
        verbose_name = "TUS School"
        verbose_name_plural = "TUS Schools"
        unique_together = ['location', 'name']
        indexes = [
            models.Index(fields=['location', 'is_active']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['school_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['slug']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            # Create unique slug
            base_slug = slugify(f"{self.location.name}-{self.name}")
            slug = base_slug
            counter = 1

            # Ensure uniqueness by appending numbers if needed
            while TUSSchool.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.location.name} - {self.name}"

    @property
    def total_products(self):
        """Get total number of products across all categories for this school"""
        # Use lazy import to avoid circular imports
        from django.apps import apps
        TUSProduct = apps.get_model('clubs', 'TUSProduct')
        return TUSProduct.objects.filter(
            category_assignments__school_category__school=self,
            stock_status__in=['instock', 'onbackorder']
        ).distinct().count()

    @property
    def active_categories_count(self):
        """Get count of categories with products"""
        return self.categories.filter(product_count__gt=0).count()

    @property
    def total_categories(self):
        """Get total number of categories"""
        return self.categories.count()

    @property
    def full_path(self):
        """Get full hierarchical path including location"""
        return f"{self.location.full_path} > {self.name}"


class TUSGeneralCategory(models.Model):
    """
    TUS general categories that are not location/school specific
    (e.g., general uniform items, accessories)
    """
    name = models.CharField(max_length=255, unique=True, help_text="Category name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly name")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    parent_category = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_categories',
        help_text="Parent category for hierarchical structure"
    )

    # Metadata
    description = models.TextField(blank=True, null=True, help_text="Category description")
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Category image URL")
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products in this category")

    # Display settings
    display_order = models.PositiveIntegerField(default=0, help_text="Display order for sorting")
    is_featured = models.BooleanField(default=False, help_text="Is this a featured category")

    # Status
    is_active = models.BooleanField(default=True, help_text="Whether the category is active")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_general_categories'
        ordering = ['display_order', 'name']
        verbose_name = "TUS General Category"
        verbose_name_plural = "TUS General Categories"
        indexes = [
            models.Index(fields=['is_active', 'is_featured']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['parent_category']),
            models.Index(fields=['display_order']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.parent_category:
            return f"{self.parent_category.name} > {self.name}"
        return self.name

    def update_product_count(self):
        """Update the product count for this category"""
        # Count products through the product assignments
        # Use lazy import to avoid circular imports
        from django.apps import apps
        TUSProduct = apps.get_model('clubs', 'TUSProduct')
        self.product_count = TUSProduct.objects.filter(
            category_assignments__general_category=self,
            stock_status__in=['instock', 'onbackorder']
        ).count()
        self.save(update_fields=['product_count', 'updated_at'])


class TUSSchoolCategory(models.Model):
    """
    TUS-specific category model mapping to subcategories within schools
    (e.g., uniforms, sportswear, accessories for a specific school)
    """
    # Relationships
    school = models.ForeignKey(TUSSchool, on_delete=models.CASCADE, related_name='categories')

    # Core fields
    name = models.CharField(max_length=255, help_text="Category name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_category_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce category ID")
    description = models.TextField(blank=True, null=True, help_text="Category description")
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products in this category")

    # Images
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Category image URL")

    # Display settings
    display_order = models.PositiveIntegerField(default=0, help_text="Display order within school")
    is_featured = models.BooleanField(default=False, help_text="Is this a featured category for the school")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_school_categories'
        ordering = ['school', 'display_order', 'name']
        verbose_name = "TUS School Category"
        verbose_name_plural = "TUS School Categories"
        unique_together = ['school', 'name']
        indexes = [
            models.Index(fields=['school', 'product_count']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['display_order']),
            models.Index(fields=['created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.school.name}-{self.name}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school.name} - {self.name}"

    @property
    def products(self):
        """Get products assigned to this school category"""
        # Use lazy import to avoid circular imports
        from django.apps import apps
        TUSProduct = apps.get_model('clubs', 'TUSProduct')
        return TUSProduct.objects.filter(
            category_assignments__school_category=self
        ).distinct()

    def update_product_count(self):
        """Update the product count for this category"""
        # Count products through the product assignments
        # Use lazy import to avoid circular imports
        from django.apps import apps
        TUSProduct = apps.get_model('clubs', 'TUSProduct')
        self.product_count = TUSProduct.objects.filter(
            category_assignments__school_category=self,
            stock_status__in=['instock', 'onbackorder']
        ).count()
        self.save(update_fields=['product_count', 'updated_at'])


class TUSProductCategoryAssignment(models.Model):
    """
    Through model for Product-Category Many-to-Many relationship.
    Handles products belonging to both school categories and general categories.
    """
    product = models.ForeignKey('TUSProduct', on_delete=models.CASCADE, related_name='category_assignments')

    # A product can belong to either a school category OR a general category
    school_category = models.ForeignKey(
        TUSSchoolCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='product_assignments'
    )
    general_category = models.ForeignKey(
        TUSGeneralCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='product_assignments'
    )

    # Assignment metadata
    is_primary = models.BooleanField(default=False, help_text="Is this the primary category for the product")
    sort_order = models.PositiveIntegerField(default=0, help_text="Sort order within the category")

    # WooCommerce metadata
    woo_category_id = models.PositiveIntegerField(help_text="WooCommerce category ID from API")
    date_assigned = models.DateTimeField(auto_now_add=True, help_text="When product was assigned to category")
    last_synced = models.DateTimeField(auto_now=True, help_text="Last sync with WooCommerce")

    class Meta:
        db_table = 'tus_product_category_assignments'
        unique_together = ['product', 'school_category', 'general_category']
        verbose_name = "TUS Product Category Assignment"
        verbose_name_plural = "TUS Product Category Assignments"
        ordering = ['sort_order', 'product__name']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
            models.Index(fields=['school_category', 'sort_order']),
            models.Index(fields=['general_category', 'sort_order']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['date_assigned']),
        ]

    def clean(self):
        """Ensure a product is assigned to either a school category OR a general category, not both"""
        if self.school_category and self.general_category:
            raise ValidationError("A product can only be assigned to either a school category or a general category, not both.")
        if not self.school_category and not self.general_category:
            raise ValidationError("A product must be assigned to either a school category or a general category.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        # Update the category's product count after assignment changes
        if self.school_category:
            self.school_category.update_product_count()
        if self.general_category:
            self.general_category.update_product_count()

    def delete(self, *args, **kwargs):
        school_category = self.school_category
        general_category = self.general_category
        super().delete(*args, **kwargs)
        # Update the category's product count after assignment removal
        if school_category:
            school_category.update_product_count()
        if general_category:
            general_category.update_product_count()

    def __str__(self):
        primary_indicator = " (Primary)" if self.is_primary else ""
        if self.school_category:
            return f"{self.product.name} → {self.school_category.name}{primary_indicator}"
        elif self.general_category:
            return f"{self.product.name} → {self.general_category.name}{primary_indicator}"
        return f"{self.product.name} → [No Category]{primary_indicator}"

    @property
    def category_name(self):
        """Get the category name regardless of type"""
        if self.school_category:
            return self.school_category.name
        elif self.general_category:
            return self.general_category.name
        return None

    @property
    def category_type(self):
        """Get the category type"""
        if self.school_category:
            return 'school'
        elif self.general_category:
            return 'general'
        return None


class TUSProduct(models.Model):
    """
    TUS-specific product model with comprehensive WooCommerce field mapping.
    Products can belong to multiple categories (school-specific or general).
    """
    # WooCommerce status choices
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]

    PRODUCT_TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('grouped', 'Grouped'),
        ('external', 'External/Affiliate'),
        ('variable', 'Variable'),
    ]

    # Core WooCommerce fields
    name = models.CharField(max_length=255, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    woo_product_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce product ID")

    # Product type and status
    type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple', help_text="Product type")
    featured = models.BooleanField(default=False, help_text="Is featured product")

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current product price")
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Regular price")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Sale price")
    on_sale = models.BooleanField(default=False, help_text="Is product on sale")

    # Content
    description = models.TextField(blank=True, null=True, help_text="Product description")
    short_description = models.TextField(blank=True, null=True, help_text="Short product description")
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Stock Keeping Unit")

    # Inventory
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock', help_text="Stock status")
    manage_stock = models.BooleanField(default=False, help_text="Manage stock at product level")
    stock_quantity = models.IntegerField(blank=True, null=True, help_text="Stock quantity")

    # Images and media
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Primary product image URL")
    gallery_urls = models.JSONField(blank=True, null=True, help_text="Gallery image URLs")

    # Product characteristics
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Product weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Product dimensions")

    # Additional WooCommerce data
    tags = models.JSONField(blank=True, null=True, help_text="Product tags")
    attributes = models.JSONField(blank=True, null=True, help_text="Product attributes")
    woo_categories = models.JSONField(blank=True, null=True, help_text="WooCommerce categories from API")
    meta_data = models.JSONField(blank=True, null=True, help_text="Additional meta data")

    # Related products
    related_ids = models.JSONField(blank=True, null=True, help_text="Related product IDs")
    upsell_ids = models.JSONField(blank=True, null=True, help_text="Upsell product IDs")
    cross_sell_ids = models.JSONField(blank=True, null=True, help_text="Cross-sell product IDs")

    # Variable/Grouped products
    parent_id = models.PositiveIntegerField(blank=True, null=True, help_text="Parent product ID for variations")
    grouped_products = models.JSONField(blank=True, null=True, help_text="Grouped product IDs")
    default_attributes = models.JSONField(blank=True, null=True, help_text="Default attributes for variable products")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_products'
        ordering = ['name']
        verbose_name = "TUS Product"
        verbose_name_plural = "TUS Products"
        indexes = [
            models.Index(fields=['stock_status']),
            models.Index(fields=['woo_product_id']),
            models.Index(fields=['sku']),
            models.Index(fields=['price']),
            models.Index(fields=['featured']),
            models.Index(fields=['on_sale']),
            models.Index(fields=['created_at']),
            models.Index(fields=['parent_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.woo_product_id}")

        # Ensure price is set correctly - prioritize sale_price, then regular_price
        if self.sale_price and self.sale_price > 0:
            if not self.price or self.price == 0:
                self.price = self.sale_price
            self.on_sale = True
        elif self.regular_price and self.regular_price > 0:
            if not self.price or self.price == 0:
                self.price = self.regular_price
            self.on_sale = False

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

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
    def primary_category(self):
        """Get the primary category assignment for this product"""
        assignment = self.category_assignments.filter(is_primary=True).first()
        if assignment:
            return assignment.school_category or assignment.general_category
        # Fallback to first category if no primary
        assignment = self.category_assignments.first()
        if assignment:
            return assignment.school_category or assignment.general_category
        return None

    @property
    def school_categories(self):
        """Get all school categories this product belongs to"""
        from django.db.models import Q
        return TUSSchoolCategory.objects.filter(
            product_assignments__product=self
        ).distinct()

    @property
    def general_categories(self):
        """Get all general categories this product belongs to"""
        return TUSGeneralCategory.objects.filter(
            product_assignments__product=self
        ).distinct()

    @property
    def all_categories(self):
        """Get all categories (both school and general) this product belongs to"""
        categories = []
        for assignment in self.category_assignments.all():
            if assignment.school_category:
                categories.append(assignment.school_category)
            elif assignment.general_category:
                categories.append(assignment.general_category)
        return categories

    def belongs_to_school(self, school):
        """Check if product belongs to a specific school through any category"""
        return self.category_assignments.filter(school_category__school=school).exists()

    def get_categories_by_school(self, school):
        """Get all categories for this product within a specific school"""
        return TUSSchoolCategory.objects.filter(
            product_assignments__product=self,
            school=school
        ).distinct()


class TUSProductVariation(models.Model):
    """
    TUS-specific product variation model mapping to WooCommerce product variations
    """
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('gender', 'Gender'),
        ('style', 'Style'),
        ('length', 'Length'),
        ('fit', 'Fit'),
        ('other', 'Other'),
    ]

    # Relationships
    product = models.ForeignKey(TUSProduct, on_delete=models.CASCADE, related_name='variations')

    # Core fields
    variation_type = models.CharField(max_length=50, choices=VARIATION_TYPE_CHOICES, help_text="Type of variation")
    variation_value = models.CharField(max_length=255, help_text="Variation value (e.g., 'Size 10', 'Navy', 'Boys')")
    woo_variation_id = models.PositiveIntegerField(unique=True, help_text="WooCommerce variation ID")

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Variation price")
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Regular price")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Sale price")

    # Stock
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Stock quantity for this variation")
    stock_status = models.CharField(
        max_length=20,
        choices=TUSProduct.STOCK_STATUS_CHOICES,
        default='instock',
        help_text="Stock status"
    )
    sku = models.CharField(max_length=100, blank=True, null=True, help_text="Variation SKU")

    # Status
    is_active = models.BooleanField(default=True, help_text="Whether this variation is active")

    # Additional variation data from WooCommerce
    attributes = models.JSONField(blank=True, null=True, help_text="WooCommerce variation attributes")
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Variation-specific image URL")
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Variation weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Variation dimensions")

    # Metadata
    menu_order = models.PositiveIntegerField(default=0, help_text="Sort order for variations")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tus_product_variations'
        ordering = ['product', 'menu_order', 'variation_type', 'variation_value']
        verbose_name = "TUS Product Variation"
        verbose_name_plural = "TUS Product Variations"
        unique_together = ['product', 'variation_type', 'variation_value']
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['woo_variation_id']),
            models.Index(fields=['variation_type', 'variation_value']),
            models.Index(fields=['stock_quantity']),
            models.Index(fields=['menu_order']),
            models.Index(fields=['created_at']),
        ]

    def save(self, *args, **kwargs):
        # Ensure price is set correctly
        if self.sale_price and self.sale_price > 0:
            if not self.price or self.price == 0:
                self.price = self.sale_price
        elif self.regular_price and self.regular_price > 0:
            if not self.price or self.price == 0:
                self.price = self.regular_price

        super().save(*args, **kwargs)

    def __str__(self):
        # Check if this is a multi-dimensional variation with attributes
        if self.attributes and len(self.attributes) > 1:
            # Show all attributes for multi-dimensional variations
            attr_parts = []
            for attr_name, attr_value in self.attributes.items():
                if attr_value:
                    attr_parts.append(f"{attr_name}:{attr_value}")
            if attr_parts:
                return f"{self.product.name} - {', '.join(attr_parts)}"

        # Fallback to standard display
        return f"{self.product.name} - {self.variation_type}: {self.variation_value}"

    @property
    def is_on_sale(self):
        """Check if variation is on sale"""
        return self.sale_price and self.regular_price and self.sale_price < self.regular_price

    @property
    def discount_percentage(self):
        """Calculate discount percentage if on sale"""
        if self.is_on_sale and self.regular_price:
            return round(((self.regular_price - self.sale_price) / self.regular_price) * 100, 2)
        return 0

    @property
    def full_sku(self):
        """Generate full SKU"""
        if self.sku:
            return self.sku
        base_sku = self.product.sku or f"TUS-{self.product.woo_product_id}"
        return f"{base_sku}-{self.variation_type[:3].upper()}-{self.variation_value[:5].upper()}"

    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.is_active and self.stock_quantity > 0

    @property
    def effective_image_url(self):
        """Get effective image URL for this variation"""
        # If variation has its own image, use it
        if self.image_url:
            return self.image_url
        # Fallback to parent product image
        if self.product and self.product.image_url:
            return self.product.image_url
        return None