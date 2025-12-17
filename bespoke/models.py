from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class BespokeCategory(models.Model):
    """
    Bespoke Product Category Model
    Synced from CIN7 API - "Quotation Base Library" category
    Subcategories: 1. Addon, 2. Base Garment
    """
    # CIN7 fields
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Category ID")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    description = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'bespoke_category'
        ordering = ['name']
        verbose_name = 'Bespoke Category'
        verbose_name_plural = 'Bespoke Categories'

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    @property
    def level(self):
        """Get category level (1 for parent, 2 for child)"""
        return 2 if self.parent else 1

    @property
    def full_path(self):
        """Get full category path"""
        if self.parent:
            return f"{self.parent.name} / {self.name}"
        return self.name


class BespokeProduct(models.Model):
    """
    Bespoke Product Model
    Synced from CIN7 API - "Quotation Base Library" category
    """
    PRODUCT_TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('variable', 'Variable'),
    ]

    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]

    # CIN7 fields
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Product ID")
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500)

    # Product details
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple')
    sku = models.CharField(max_length=100, blank=True, db_index=True, help_text="CIN7 SKU/Code")
    barcode = models.CharField(max_length=100, blank=True, help_text="CIN7 Barcode")
    description = models.TextField(blank=True, help_text="Product description")
    short_description = models.TextField(blank=True, help_text="Short description")

    # Pricing from CIN7
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price from CIN7")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Retail price from CIN7")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Selling price")

    # 75% margin pricing
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated 75% margin price (cost ÷ 0.25)")

    # Stock management
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    stock_quantity = models.IntegerField(null=True, blank=True)
    stock_on_hand = models.IntegerField(null=True, blank=True, help_text="Stock on hand from CIN7")
    stock_available = models.IntegerField(null=True, blank=True, help_text="Available stock from CIN7")

    # CIN7 specific fields
    cin7_brand = models.CharField(max_length=100, blank=True, help_text="CIN7 Brand")
    cin7_supplier = models.CharField(max_length=100, blank=True, help_text="CIN7 Supplier")
    cin7_category_path = models.TextField(blank=True, help_text="Full category path from CIN7")
    cin7_option1 = models.CharField(max_length=100, blank=True, help_text="CIN7 Option1")
    cin7_option2 = models.CharField(max_length=100, blank=True, help_text="CIN7 Option2")
    cin7_option3 = models.CharField(max_length=100, blank=True, help_text="CIN7 Option3")

    # Images
    featured_image_url = models.URLField(max_length=1000, blank=True)

    # Timestamps from CIN7
    date_created = models.DateTimeField(null=True, blank=True)
    date_modified = models.DateTimeField(null=True, blank=True)

    # Local metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'bespoke_product'
        ordering = ['name']
        verbose_name = 'Bespoke Product'
        verbose_name_plural = 'Bespoke Products'
        indexes = [
            models.Index(fields=['product_type']),
            models.Index(fields=['stock_status']),
            models.Index(fields=['cin7_brand']),
            models.Index(fields=['date_modified']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Calculate 75% margin price and set default price on save"""
        if self.cost_price and self.cost_price > 0:
            self.margin_75_price = (self.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))

            # If price is not set or is zero, use margin_75_price or retail_price
            if not self.price or self.price == 0:
                self.price = self.margin_75_price or self.retail_price

        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        """Check if product is in stock"""
        return self.stock_status == 'instock' or (self.stock_available and self.stock_available > 0)

    @property
    def display_price(self):
        """Get display price - prefer 75% margin if higher than retail"""
        if self.margin_75_price and self.price:
            return self.margin_75_price if self.margin_75_price > self.price else self.price
        return self.price or self.retail_price or self.margin_75_price

    @cached_property
    def base_garment_name(self):
        """
        Extract base garment name by removing size suffixes.
        Examples:
            "TOP 0015SW AOT OC23 -2XL" -> "TOP 0015SW AOT OC23"
            "TOP 0015SW AOT OC23 -XL" -> "TOP 0015SW AOT OC23"
            "POLO SHIRT BASIC -M" -> "POLO SHIRT BASIC"
        """
        import re
        # Pattern to match common size suffixes
        # Matches: -XS, -S, -M, -L, -XL, -XXL, -2XL, -3XL, -4XL, etc.
        size_pattern = r'\s*-\s*(\d*X*[SML]|SMALL|MEDIUM|LARGE)$'
        base_name = re.sub(size_pattern, '', self.name, flags=re.IGNORECASE)
        return base_name.strip()

    @property
    def size_suffix(self):
        """
        Extract size from variation option1_value or fallback to SKU parsing.
        Returns empty string if no size found.
        """
        # First check if we have variations with option1_value (direct from CIN7)
        if self.product_type == 'variable':
            first_variation = self.variations.filter(is_active=True).first()
            if first_variation and first_variation.option1_value:
                return first_variation.option1_value

        # Fallback to regex parsing for simple products or legacy data
        import re
        size_pattern = r'\s*-\s*(\d*X*[SML]|SMALL|MEDIUM|LARGE)$'

        if self.sku:
            match = re.search(size_pattern, self.sku, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        match = re.search(size_pattern, self.name, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return ""  # Return empty string instead of None

    @property
    def variation_count(self):
        """Return the number of active variations for variable products"""
        if self.product_type == 'variable':
            return self.variations.filter(is_active=True).count()
        return 0

    @property
    def has_discount(self):
        """Check if 75% margin price is higher than current price"""
        return (self.margin_75_price and self.price and
                self.margin_75_price > self.price)

    @property
    def discount_percentage(self):
        """Calculate discount percentage"""
        if self.has_discount:
            discount = ((self.margin_75_price - self.price) / self.margin_75_price) * 100
            return round(discount)
        return 0


class BespokeProductCategoryAssignment(models.Model):
    """
    Through model for product-category many-to-many relationship
    Allows products to belong to multiple categories
    """
    product = models.ForeignKey(
        BespokeProduct,
        on_delete=models.CASCADE,
        related_name='category_assignments'
    )
    category = models.ForeignKey(
        BespokeCategory,
        on_delete=models.CASCADE,
        related_name='product_assignments'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bespoke_product_category_assignment'
        unique_together = [['product', 'category']]
        verbose_name = 'Bespoke Product Category Assignment'
        verbose_name_plural = 'Bespoke Product Category Assignments'

    def __str__(self):
        return f"{self.product.name} -> {self.category.name}"


class BespokeProductVariation(models.Model):
    """
    Bespoke Product Variation Model
    For variable products with multiple options (colors, sizes, etc.)
    """
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]

    # CIN7 fields
    cin7_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="CIN7 Variation ID")
    parent_product = models.ForeignKey(
        BespokeProduct,
        on_delete=models.CASCADE,
        related_name='variations'
    )

    # Variation details
    sku = models.CharField(max_length=100, blank=True, db_index=True, help_text="CIN7 SKU/Code")
    barcode = models.CharField(max_length=100, blank=True, help_text="CIN7 Barcode")
    description = models.TextField(blank=True, null=True)

    # Variation attributes (from CIN7 options)
    option1_value = models.CharField(max_length=100, blank=True, help_text="Option 1 value (e.g., Color)")
    option2_value = models.CharField(max_length=100, blank=True, help_text="Option 2 value (e.g., Size)")
    option3_value = models.CharField(max_length=100, blank=True, help_text="Option 3 value")

    # Pricing from CIN7
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price from CIN7")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Retail price from CIN7")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Selling price")

    # 75% margin pricing
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated 75% margin price (cost ÷ 0.25)")

    # Stock management
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    stock_quantity = models.IntegerField(null=True, blank=True)
    stock_on_hand = models.IntegerField(null=True, blank=True, help_text="Stock on hand from CIN7")
    stock_available = models.IntegerField(null=True, blank=True, help_text="Available stock from CIN7")

    # Image
    image_url = models.URLField(max_length=1000, blank=True)

    # Timestamps from CIN7
    date_created = models.DateTimeField(null=True, blank=True)
    date_modified = models.DateTimeField(null=True, blank=True)

    # Local metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'bespoke_product_variation'
        ordering = ['parent_product', 'cin7_id']
        verbose_name = 'Bespoke Product Variation'
        verbose_name_plural = 'Bespoke Product Variations'
        indexes = [
            models.Index(fields=['parent_product', 'stock_status']),
        ]

    def __str__(self):
        options = []
        if self.option1_value:
            options.append(self.option1_value)
        if self.option2_value:
            options.append(self.option2_value)
        if self.option3_value:
            options.append(self.option3_value)

        if options:
            return f"{self.parent_product.name} ({', '.join(options)})"
        return f"{self.parent_product.name} - {self.sku}"

    def save(self, *args, **kwargs):
        """Calculate 75% margin price and set default price on save"""
        if self.cost_price and self.cost_price > 0:
            self.margin_75_price = (self.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))

            # If price is not set or is zero, use margin_75_price or retail_price
            if not self.price or self.price == 0:
                self.price = self.margin_75_price or self.retail_price

        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.stock_status == 'instock' or (self.stock_available and self.stock_available > 0)

    @property
    def display_price(self):
        """Get display price - prefer 75% margin if higher than retail"""
        if self.margin_75_price and self.price:
            return self.margin_75_price if self.margin_75_price > self.price else self.price
        return self.price or self.retail_price or self.margin_75_price

    @property
    def variation_name(self):
        """Get formatted variation name"""
        options = []
        if self.option1_value:
            options.append(self.option1_value)
        if self.option2_value:
            options.append(self.option2_value)
        if self.option3_value:
            options.append(self.option3_value)

        if options:
            return f"{self.parent_product.name} - {', '.join(options)}"
        return self.parent_product.name


class BespokeSyncLog(models.Model):
    """
    Bespoke Sync Log Model
    Track sync operations from CIN7 API
    """
    SYNC_TYPE_CHOICES = [
        ('full', 'Full Sync'),
        ('incremental', 'Incremental Sync'),
        ('categories', 'Categories Only'),
    ]

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # Sync details
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES, default='full')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')

    # Statistics
    categories_synced = models.IntegerField(default=0)
    products_synced = models.IntegerField(default=0)
    variations_synced = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    # Timing
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    # Details
    error_message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'bespoke_sync_log'
        ordering = ['-started_at']
        verbose_name = 'Bespoke Sync Log'
        verbose_name_plural = 'Bespoke Sync Logs'

    def __str__(self):
        return f"Bespoke {self.sync_type} sync - {self.status} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"

    def mark_completed(self):
        """Mark sync as completed and calculate duration"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save()

    def mark_failed(self, error_message):
        """Mark sync as failed with error message"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.error_message = error_message
        self.save()


# ============================================================================
# ADDON PRICING MODELS
# ============================================================================

class AddonPricingTier(models.Model):
    """
    Defines quantity-based pricing tiers for addon products.
    Examples: 1-9, 10-25, 26-50, 51-199, 200+
    """
    ADDON_TYPE_CHOICES = [
        ('heat_transfer', 'Heat Transfer'),
        ('screen_print', 'Screen Print'),
        ('emb_applique', 'Embroidery/Applique'),
    ]

    addon_type = models.CharField(
        max_length=50,
        choices=ADDON_TYPE_CHOICES,
        db_index=True,
        help_text="Type of addon this tier applies to"
    )

    min_quantity = models.PositiveIntegerField(
        help_text="Minimum quantity for this tier (inclusive)"
    )
    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum quantity for this tier (inclusive). NULL = unlimited"
    )

    # Metadata
    display_label = models.CharField(
        max_length=50,
        help_text="Display label for tier (e.g., '1-9', '200+')"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bespoke_addon_pricing_tier'
        ordering = ['addon_type', 'sort_order', 'min_quantity']
        unique_together = [['addon_type', 'min_quantity', 'max_quantity']]
        verbose_name = 'Addon Pricing Tier'
        verbose_name_plural = 'Addon Pricing Tiers'
        indexes = [
            models.Index(fields=['addon_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.get_addon_type_display()} - {self.display_label}"

    def contains_quantity(self, quantity):
        """Check if given quantity falls within this tier"""
        if quantity < self.min_quantity:
            return False
        if self.max_quantity is None:
            return True
        return quantity <= self.max_quantity


class AddonSizeDefinition(models.Model):
    """
    Defines size categories for addon products.
    Examples: Small (up to 5" x 5"), Medium (up to 8" x 8"), Large (up to 11" x 11")
    """
    ADDON_TYPE_CHOICES = [
        ('heat_transfer', 'Heat Transfer'),
        ('screen_print', 'Screen Print'),
        ('emb_applique', 'Embroidery/Applique'),
    ]

    SIZE_CODE_CHOICES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
    ]

    STITCH_COMPLEXITY_CHOICES = [
        ('low', 'Low Stitch'),
        ('avg', 'Average Stitch'),
        ('lrg', 'Large Stitch'),
    ]

    addon_type = models.CharField(
        max_length=50,
        choices=ADDON_TYPE_CHOICES,
        db_index=True
    )

    size_code = models.CharField(
        max_length=20,
        choices=SIZE_CODE_CHOICES,
        help_text="Size category code"
    )

    # Dimension specifications
    max_width_inches = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum width in inches"
    )
    max_height_inches = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum height in inches"
    )

    # Display formatting
    display_label = models.CharField(
        max_length=100,
        help_text="Display label (e.g., 'Small - up to 5\" x 5\"')"
    )

    # Stitch complexity (EMB/Applique only)
    stitch_complexity = models.CharField(
        max_length=20,
        choices=STITCH_COMPLEXITY_CHOICES,
        null=True,
        blank=True,
        help_text="Stitch complexity for embroidery (EMB only)"
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bespoke_addon_size_definition'
        ordering = ['addon_type', 'sort_order']
        unique_together = [['addon_type', 'size_code', 'stitch_complexity']]
        verbose_name = 'Addon Size Definition'
        verbose_name_plural = 'Addon Size Definitions'

    def __str__(self):
        if self.stitch_complexity:
            return f"{self.get_addon_type_display()} - {self.display_label} ({self.get_stitch_complexity_display()})"
        return f"{self.get_addon_type_display()} - {self.display_label}"

    def fits_dimensions(self, width, height):
        """Check if given dimensions fit within this size definition"""
        return width <= self.max_width_inches and height <= self.max_height_inches


class AddonPrice(models.Model):
    """
    Stores the actual price for a specific combination of:
    - Addon type
    - Quantity tier
    - Size definition
    This is the intersection of quantity tiers and size definitions.
    """
    tier = models.ForeignKey(
        AddonPricingTier,
        on_delete=models.CASCADE,
        related_name='prices'
    )

    size_definition = models.ForeignKey(
        AddonSizeDefinition,
        on_delete=models.CASCADE,
        related_name='prices'
    )

    # Pricing
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Price per size/color at this tier and size"
    )

    # Metadata
    notes = models.TextField(blank=True, help_text="Internal notes about this price")
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(
        default=timezone.now,
        help_text="Date this price becomes effective"
    )
    effective_to = models.DateField(
        null=True,
        blank=True,
        help_text="Date this price expires (NULL = no expiry)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='addon_prices_created'
    )

    class Meta:
        db_table = 'bespoke_addon_price'
        ordering = ['tier__addon_type', 'tier__sort_order', 'size_definition__sort_order']
        unique_together = [['tier', 'size_definition', 'effective_from']]
        verbose_name = 'Addon Price'
        verbose_name_plural = 'Addon Prices'
        indexes = [
            models.Index(fields=['tier', 'size_definition', 'is_active']),
            models.Index(fields=['effective_from', 'effective_to']),
        ]

    def __str__(self):
        return f"{self.tier} - {self.size_definition}: R{self.price_per_unit}"

    def clean(self):
        """Validate addon type consistency"""
        if self.tier_id and self.size_definition_id:
            if self.tier.addon_type != self.size_definition.addon_type:
                raise ValidationError({
                    'size_definition': f'Size definition must match tier addon type ({self.tier.addon_type})'
                })

        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({
                'effective_to': 'End date must be after start date'
            })

    def is_currently_effective(self):
        """Check if price is currently effective"""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if today < self.effective_from:
            return False
        if self.effective_to and today > self.effective_to:
            return False
        return True

    @classmethod
    def get_price(cls, addon_type, quantity, width_inches, height_inches, stitch_complexity=None):
        """
        Calculate price for given parameters.

        Args:
            addon_type: 'heat_transfer', 'screen_print', or 'emb_applique'
            quantity: Number of items ordered
            width_inches: Width dimension in inches
            height_inches: Height dimension in inches
            stitch_complexity: For EMB - 'low', 'avg', or 'lrg'

        Returns:
            Decimal: Price per unit, or None if not found
        """
        from django.db.models import Q
        today = timezone.now().date()

        # Find matching tier
        tier = AddonPricingTier.objects.filter(
            addon_type=addon_type,
            is_active=True,
            min_quantity__lte=quantity
        ).filter(
            Q(max_quantity__gte=quantity) | Q(max_quantity__isnull=True)
        ).first()

        if not tier:
            return None

        # Find matching size definition
        size_filters = {
            'addon_type': addon_type,
            'is_active': True,
            'max_width_inches__gte': width_inches,
            'max_height_inches__gte': height_inches,
        }

        if stitch_complexity:
            size_filters['stitch_complexity'] = stitch_complexity

        size_def = AddonSizeDefinition.objects.filter(
            **size_filters
        ).order_by('sort_order').first()

        if not size_def:
            return None

        # Find active price
        price = cls.objects.filter(
            tier=tier,
            size_definition=size_def,
            is_active=True,
            effective_from__lte=today
        ).filter(
            Q(effective_to__gte=today) | Q(effective_to__isnull=True)
        ).first()

        return price.price_per_unit if price else None


class AddonPriceHistory(models.Model):
    """
    Audit trail for addon price changes.
    Records all modifications to pricing for compliance and analysis.
    """
    addon_price = models.ForeignKey(
        AddonPrice,
        on_delete=models.CASCADE,
        related_name='history'
    )

    # Changed fields
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    change_reason = models.TextField(help_text="Reason for price change")

    # Audit metadata
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='addon_price_changes'
    )

    class Meta:
        db_table = 'bespoke_addon_price_history'
        ordering = ['-changed_at']
        verbose_name = 'Addon Price History'
        verbose_name_plural = 'Addon Price Histories'

    def __str__(self):
        return f"{self.addon_price} - R{self.old_price} → R{self.new_price}"
