from django.db import models
from django.utils import timezone


class BallStoreCategory(models.Model):
    """
    BallStore Product Category Model
    Synced from WooCommerce API
    """
    # WooCommerce fields
    wc_id = models.IntegerField(unique=True, help_text="WooCommerce Category ID")
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
    display_type = models.CharField(max_length=50, default='default')
    product_count = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ballstore_category'
        ordering = ['name']
        verbose_name = 'BallStore Category'
        verbose_name_plural = 'BallStore Categories'

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


class BallStoreProduct(models.Model):
    """
    BallStore Product Model
    Synced from WooCommerce API
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

    # WooCommerce fields
    wc_id = models.IntegerField(unique=True, help_text="WooCommerce Product ID")
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500)
    permalink = models.URLField(max_length=1000, blank=True)

    # Product details
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple')
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.TextField(blank=True, help_text="Full HTML description")
    short_description = models.TextField(blank=True, help_text="Short HTML description")

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    on_sale = models.BooleanField(default=False)

    # CIN7 price fields
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price from CIN7 API")
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated 75% margin price (cost ÷ 0.25)")

    # Stock management
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    stock_quantity = models.IntegerField(null=True, blank=True)
    manage_stock = models.BooleanField(default=False)

    # Categories (many-to-many - products can belong to multiple categories)
    categories = models.ManyToManyField(BallStoreCategory, related_name='products', blank=True)

    # Images
    featured_image_url = models.URLField(max_length=1000, blank=True)

    # Timestamps from WooCommerce
    date_created = models.DateTimeField(null=True, blank=True)
    date_modified = models.DateTimeField(null=True, blank=True)

    # Local metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ballstore_product'
        ordering = ['name']
        verbose_name = 'BallStore Product'
        verbose_name_plural = 'BallStore Products'
        indexes = [
            models.Index(fields=['product_type']),
            models.Index(fields=['stock_status']),
            models.Index(fields=['date_modified']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_in_stock(self):
        """Check if product is in stock"""
        return self.stock_status == 'instock'

    @property
    def has_sale(self):
        """Check if product has sale price"""
        return self.on_sale and self.sale_price is not None

    @property
    def display_price(self):
        """Get display price (sale price if on sale, otherwise regular price)"""
        if self.has_sale:
            return self.sale_price
        return self.price or self.regular_price

    @property
    def category_names(self):
        """Get list of category names"""
        return [cat.name for cat in self.categories.all()]


class BallStoreProductVariation(models.Model):
    """
    BallStore Product Variation Model
    For variable products with multiple options (colors, sizes, etc.)
    """
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]

    # WooCommerce fields
    wc_id = models.IntegerField(unique=True, help_text="WooCommerce Variation ID")
    parent_product = models.ForeignKey(
        BallStoreProduct,
        on_delete=models.CASCADE,
        related_name='variations'
    )

    # Variation details
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.TextField(blank=True)

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    on_sale = models.BooleanField(default=False)

    # CIN7 price fields
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price from CIN7 API")
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated 75% margin price (cost ÷ 0.25)")

    # Stock management
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    stock_quantity = models.IntegerField(null=True, blank=True)
    manage_stock = models.BooleanField(default=False)

    # Attributes (stored as JSON)
    # Example: [{"name": "Color", "option": "Red"}, {"name": "Size", "option": "Large"}]
    attributes = models.JSONField(default=list, blank=True)

    # Image
    image_url = models.URLField(max_length=1000, blank=True)

    # Timestamps from WooCommerce
    date_created = models.DateTimeField(null=True, blank=True)
    date_modified = models.DateTimeField(null=True, blank=True)

    # Local metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ballstore_product_variation'
        ordering = ['parent_product', 'wc_id']
        verbose_name = 'BallStore Product Variation'
        verbose_name_plural = 'BallStore Product Variations'
        indexes = [
            models.Index(fields=['parent_product', 'stock_status']),
        ]

    def __str__(self):
        attr_str = ", ".join([f"{a['name']}: {a['option']}" for a in self.attributes])
        return f"{self.parent_product.name} ({attr_str})"

    @property
    def is_in_stock(self):
        """Check if variation is in stock"""
        return self.stock_status == 'instock'

    @property
    def has_sale(self):
        """Check if variation has sale price"""
        return self.on_sale and self.sale_price is not None

    @property
    def display_price(self):
        """Get display price (sale price if on sale, otherwise regular price)"""
        if self.has_sale:
            return self.sale_price
        return self.price or self.regular_price

    @property
    def variation_name(self):
        """Get formatted variation name"""
        if not self.attributes:
            return self.parent_product.name
        attr_str = ", ".join([a['option'] for a in self.attributes])
        return f"{self.parent_product.name} - {attr_str}"


class BallStoreProductImage(models.Model):
    """
    BallStore Product Image Model
    Multiple images per product
    """
    # WooCommerce fields
    wc_id = models.IntegerField(help_text="WooCommerce Image ID")
    product = models.ForeignKey(
        BallStoreProduct,
        on_delete=models.CASCADE,
        related_name='images'
    )

    # Image details
    src = models.URLField(max_length=1000)
    name = models.CharField(max_length=255, blank=True)
    alt = models.CharField(max_length=255, blank=True)
    position = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ballstore_product_image'
        ordering = ['product', 'position']
        verbose_name = 'BallStore Product Image'
        verbose_name_plural = 'BallStore Product Images'
        unique_together = [['product', 'wc_id']]

    def __str__(self):
        return f"{self.product.name} - Image {self.position}"


class BallStoreSyncLog(models.Model):
    """
    BallStore Sync Log Model
    Track sync operations
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
    images_synced = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    # Timing
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    # Details
    error_message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'ballstore_sync_log'
        ordering = ['-started_at']
        verbose_name = 'BallStore Sync Log'
        verbose_name_plural = 'BallStore Sync Logs'

    def __str__(self):
        return f"BallStore {self.sync_type} sync - {self.status} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"

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
