"""
SAS-specific Django models for managing sports, clubs, and products.

This module provides separate models for the SAS WooCommerce integration,
implementing a Sports → Clubs → Products hierarchy with school filtering
and WooCommerce synchronization capabilities.
"""

from django.db import models
from django.utils.text import slugify
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import re


class SASActiveManager(models.Manager):
    """Manager for active SAS records only."""
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class SASSportManager(models.Manager):
    """Custom manager for SASSport with common queries."""
    
    def active_with_clubs(self):
        """Get active sports that have active clubs."""
        return self.get_queryset().filter(
            is_active=True,
            clubs__is_active=True
        ).distinct().prefetch_related('clubs')
    
    def by_club_count(self):
        """Order sports by number of active clubs."""
        return self.get_queryset().annotate(
            club_count=models.Count('clubs', filter=models.Q(clubs__is_active=True))
        ).order_by('-club_count', 'name')


class SASSport(models.Model):
    """
    Represents a sport category in the SAS system.
    Maps to WooCommerce parent categories for sports.
    
    Examples: Basketball (46), Rugby (60), Athletics (17), etc.
    """
    
    # Core Fields
    name = models.CharField(max_length=100, unique=True, help_text="Sport name (e.g., Basketball)")
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="URL-friendly version")
    
    # WooCommerce Integration
    woo_category_id = models.PositiveIntegerField(
        unique=True, 
        help_text="WooCommerce category ID for this sport"
    )
    
    # Metadata
    description = models.TextField(blank=True, help_text="Sport description")
    image_url = models.URLField(blank=True, validators=[URLValidator()], help_text="Sport category image URL")
    
    # Status and Tracking
    is_active = models.BooleanField(default=True, help_text="Whether this sport is active")
    club_count = models.PositiveIntegerField(default=0, help_text="Number of active clubs in this sport")
    product_count = models.PositiveIntegerField(default=0, help_text="Total products across all clubs")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last WooCommerce sync timestamp")
    
    # Managers
    objects = SASSportManager()
    active = SASActiveManager()
    
    class Meta:
        db_table = 'sas_sports'
        verbose_name = 'SAS Sport'
        verbose_name_plural = 'SAS Sports'
        ordering = ['name']
        indexes = [
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['is_active', 'club_count']),
            models.Index(fields=['name']),
            models.Index(fields=['last_sync_at']),
        ]
    
    def __str__(self):
        return f"{self.name} (ID: {self.woo_category_id})"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def update_counts(self):
        """Update club_count and product_count from related objects."""
        active_clubs = self.clubs.filter(is_active=True)
        self.club_count = active_clubs.count()
        self.product_count = SASProduct.objects.filter(
            club__in=active_clubs,
            stock_status__in=['instock', 'onbackorder']
        ).count()
        self.save(update_fields=['club_count', 'product_count'])
    
    @property
    def active_clubs_count(self):
        """Return count of active clubs."""
        return self.clubs.filter(is_active=True).count()
    
    @property
    def total_products_count(self):
        """Return total products across all active clubs."""
        return SASProduct.objects.filter(
            club__sport=self,
            club__is_active=True,
            stock_status__in=['instock', 'onbackorder']
        ).count()


class SASClubManager(models.Manager):
    """Custom manager for SASClub with filtering and common queries."""
    
    def exclude_schools(self):
        """Exclude schools based on name patterns."""
        school_patterns = [
            r'.*\bschool\b.*',
            r'.*\bhigh\b.*',
            r'.*\bprimary\b.*',
            r'.*\bacademy\b.*',
            r'.*\bcollege\b.*',
            r'.*\buniversity\b.*',
            r'.*\beducation\b.*',
        ]
        
        # Build Q object for exclusion
        exclude_q = models.Q()
        for pattern in school_patterns:
            exclude_q |= models.Q(name__iregex=pattern)
        
        return self.get_queryset().exclude(exclude_q)
    
    def clubs_only(self):
        """Get only clubs (exclude schools and generic categories) that are active."""
        return self.filter(is_active=True, is_school=False, is_generic_category=False)
    
    def by_product_count(self):
        """Order clubs by product count descending."""
        return self.get_queryset().annotate(
            total_products=models.Count('products', filter=models.Q(products__stock_status__in=['instock', 'onbackorder']))
        ).order_by('-total_products', 'name')
    
    def with_products(self):
        """Get clubs that have products."""
        return self.get_queryset().filter(product_count__gt=0)


class SASClub(models.Model):
    """
    Represents a sports club in the SAS system.
    Maps to WooCommerce subcategories under sports.
    
    Excludes schools using pattern matching.
    """
    
    # Relationships
    sport = models.ForeignKey(
        SASSport, 
        on_delete=models.CASCADE, 
        related_name='clubs',
        help_text="Sport this club belongs to"
    )
    
    # Core Fields
    name = models.CharField(max_length=255, help_text="Club name")
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="URL-friendly version")
    
    # WooCommerce Integration
    woo_category_id = models.PositiveIntegerField(
        unique=True, 
        help_text="WooCommerce category ID for this club"
    )
    
    # Club Details
    description = models.TextField(blank=True, help_text="Club description")
    image_url = models.URLField(blank=True, validators=[URLValidator()], help_text="Club logo/image URL")
    
    # Contact Information
    contact_person = models.CharField(max_length=100, blank=True, help_text="Primary contact person")
    email = models.EmailField(blank=True, help_text="Contact email")
    website = models.URLField(blank=True, validators=[URLValidator()], help_text="Club website")
    phone = models.CharField(max_length=20, blank=True, help_text="Contact phone number")
    
    # Location
    city = models.CharField(max_length=100, blank=True, help_text="City/Location")
    province = models.CharField(max_length=50, blank=True, help_text="Province")
    address = models.TextField(blank=True, help_text="Full address")
    
    # Status and Metrics
    is_active = models.BooleanField(default=True, help_text="Whether this club is active")
    is_school = models.BooleanField(default=False, help_text="Whether this is identified as a school")
    is_generic_category = models.BooleanField(default=False, help_text="Whether this is a generic product category")
    product_count = models.PositiveIntegerField(default=0, help_text="Number of products for this club")

    # CIN7 Contact mapping fields
    cin7_id = models.CharField(max_length=50, blank=True, db_index=True, help_text="CIN7 Contact ID for sales orders")
    cin7_company_name = models.CharField(max_length=255, blank=True, help_text="CIN7 Contact company name")
    cin7_email = models.EmailField(blank=True, help_text="CIN7 Contact email address")
    cin7_first_name = models.CharField(max_length=100, blank=True, help_text="CIN7 Contact first name")
    cin7_last_name = models.CharField(max_length=100, blank=True, help_text="CIN7 Contact last name")
    cin7_phone = models.CharField(max_length=50, blank=True, help_text="CIN7 Contact phone number")

    # CIN7 Delivery address
    cin7_delivery_address1 = models.CharField(max_length=255, blank=True, help_text="CIN7 Delivery address line 1")
    cin7_delivery_address2 = models.CharField(max_length=255, blank=True, help_text="CIN7 Delivery address line 2")
    cin7_delivery_city = models.CharField(max_length=100, blank=True, help_text="CIN7 Delivery city")
    cin7_delivery_state = models.CharField(max_length=100, blank=True, help_text="CIN7 Delivery state")
    cin7_delivery_postcode = models.CharField(max_length=20, blank=True, help_text="CIN7 Delivery postcode")

    # CIN7 Billing address
    cin7_billing_address1 = models.CharField(max_length=255, blank=True, help_text="CIN7 Billing address line 1")
    cin7_billing_address2 = models.CharField(max_length=255, blank=True, help_text="CIN7 Billing address line 2")
    cin7_billing_city = models.CharField(max_length=100, blank=True, help_text="CIN7 Billing city")
    cin7_billing_state = models.CharField(max_length=100, blank=True, help_text="CIN7 Billing state")
    cin7_billing_postcode = models.CharField(max_length=20, blank=True, help_text="CIN7 Billing postcode")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last WooCommerce sync timestamp")
    
    # Managers
    objects = SASClubManager()
    active = SASActiveManager()
    
    class Meta:
        db_table = 'sas_clubs'
        verbose_name = 'SAS Club'
        verbose_name_plural = 'SAS Clubs'
        ordering = ['sport__name', 'name']
        unique_together = [['sport', 'name']]  # Prevent duplicate names within same sport
        indexes = [
            models.Index(fields=['sport', 'is_active']),
            models.Index(fields=['woo_category_id']),
            models.Index(fields=['name']),
            models.Index(fields=['is_school', 'is_active']),
            models.Index(fields=['is_generic_category', 'is_active']),
            models.Index(fields=['is_school', 'is_generic_category', 'is_active']),
            models.Index(fields=['product_count']),
            models.Index(fields=['last_sync_at']),
            models.Index(fields=['sport', 'product_count']),
            models.Index(fields=['slug']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.sport.name}) - ID: {self.woo_category_id}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            # Create slug from club name only (matches existing data)
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            # Ensure uniqueness by appending numbers if needed
            while SASClub.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        # Auto-detect if this is a school
        if not hasattr(self, '_skip_school_detection'):
            self.is_school = self._detect_school()

        # Auto-detect if this is a generic category
        if not hasattr(self, '_skip_generic_detection'):
            self.is_generic_category = self._detect_generic_category()

        super().save(*args, **kwargs)

        # Update parent sport counts
        if hasattr(self, '_update_parent_counts') and self._update_parent_counts:
            self.sport.update_counts()
    
    def _detect_school(self):
        """Detect if this club is actually a school based on name patterns."""
        if not self.name:
            return False
        
        school_indicators = [
            'school', 'high', 'primary', 'academy', 'college', 
            'university', 'education', 'learners', 'students'
        ]
        
        name_lower = self.name.lower()
        return any(indicator in name_lower for indicator in school_indicators)
    
    def _detect_generic_category(self):
        """Detect if this club is actually a generic product category."""
        if not self.name:
            return False
        
        # Generic category patterns - these are product categories, not clubs
        generic_patterns = [
            # Accessories/Equipment categories (case insensitive, word boundaries)
            r'^bags?$', r'^balls?$', r'^bottles?$', r'^caps?$', r'^clothing$',
            r'^equipment$', r'^accessories?$', r'^beanie$', r'^bucket\s*hats?$',
            r'^face\s*masks?$', r'^clearance$', r'^sport\s*accessories?$',
            r'^tag\s*sets?$', r'^socks?$', r'^shorts?$', r'^shirts?$',
            
            # Generic product types
            r'^bibs?$', r'^numbers?$', r'^tags?$', r'^uniforms?$',
            r'^offers?$', r'^specials?$', r'^sale$', r'^new$',
            r'^corporate$', r'^custom$', r'^general$',
            
            # Size/Option categories
            r'^sizes?$', r'^options?$', r'^extras?$', r'^add.ons?$',
            r'^number\s*option$', r'^nickname\s*option$', r'^new\s*number\s*option$',
            
            # Team pack categories
            r'^team\s*packs?$', r'^pack\s*deals?$', r'^bulk\s*orders?$',
            
            # NEW: Single word sports (generic product categories, not actual clubs)
            r'^sports?$', r'^basketball$', r'^cricket$', r'^rugby$', r'^football$',
            r'^athletics$', r'^touch$', r'^netball$', r'^hockey$',
            
            # NEW: Multi-sport generic categories (pipe separated sports indicate product categories)
            r'^rugby\s*\|\s*league$', r'^football\s*\|\s*hockey$', r'^touch\s*\|\s*tag\s*rugby$',
            r'^.*\s*\|\s*.*$',  # Any category with pipe separator (typically generic product groupings)
            
            # NEW: Deals and promotional categories
            r'^deals?\s*\(.*\)$', r'^sale\s*\(.*\)$', r'^specials?\s*\(.*\)$',
            r'^offers?\s*\(.*\)$', r'^discounts?\s*\(.*\)$',
            r'^\d+%.*off.*$', r'^.*\(\d+%.*off\).*$',
            
            # NEW: Generic clothing/merchandise categories (more specific patterns)
            r'.*\bclothing\b.*', r'.*\bmerchandise\b.*', r'.*\bapparel\b.*',
            r'.*\bgarments?\b.*', r'.*\btextiles?\b.*', r'.*\bwear$',
            
            # NEW: Corporate/organizational categories
            r'.*\bcorps?\b.*', r'.*\bmilitary\b.*', r'.*\borganisation\b.*',
            r'.*\borganization\b.*', r'.*\bdepartment\b.*',
            
            # NEW: Size/Gender/Age categories
            r'^kids?$', r'^mens?$', r'^womens?$', r'^unisex$', r'^adults?$',
            r'^junior$', r'^senior$', r'^youth$', r'^childrens?$',
            
            # NEW: Product pack categories
            r'.*\bpacks?$', r'.*\bsets?$', r'.*\bbundles?$',
            
            # NEW: Single word sport names that are generic product categories
            r'^volleyball$', r'^swimming$', r'^cycling$', r'^running$', r'^fitness$',
        ]
        
        name_lower = self.name.lower()
        return any(re.match(pattern, name_lower) for pattern in generic_patterns)
    
    def update_product_count(self):
        """Update the product count from related products."""
        self.product_count = self.products.filter(
            stock_status__in=['instock', 'onbackorder']
        ).count()
        self.save(update_fields=['product_count'])
    
    @property
    def total_products(self):
        """Return count of active products."""
        return self.products.filter(stock_status__in=['instock', 'onbackorder']).count()
    
    @property
    def in_stock_products(self):
        """Return count of in-stock products."""
        return self.products.filter(stock_status='instock').count()
    
    @property
    def is_club_only(self):
        """Return True if this is a real club (not a school or generic category)."""
        return not self.is_school and not self.is_generic_category and self.is_active


class SASProductManager(models.Manager):
    """Custom manager for SASProduct with common queries."""
    
    def available(self):
        """Get products that are in stock or on backorder."""
        return self.get_queryset().filter(stock_status__in=['instock', 'onbackorder'])
    
    def in_stock(self):
        """Get products that are in stock."""
        return self.get_queryset().filter(stock_status='instock')
    
    def on_sale(self):
        """Get products that are on sale."""
        return self.get_queryset().filter(
            sale_price__isnull=False,
            sale_price__gt=0,
            sale_price__lt=models.F('regular_price')
        )
    
    def by_sport(self, sport):
        """Get products for a specific sport."""
        return self.get_queryset().filter(club__sport=sport)
    
    def recent(self, days=30):
        """Get products created in the last N days."""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.get_queryset().filter(created_at__gte=cutoff_date)


class SASProduct(models.Model):
    """
    Represents a product in the SAS system.
    Maps to WooCommerce products belonging to club categories.
    """
    
    STOCK_STATUS_CHOICES = [
        ('instock', 'In Stock'),
        ('outofstock', 'Out of Stock'),
        ('onbackorder', 'On Backorder'),
    ]
    
    TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('grouped', 'Grouped'),
        ('external', 'External'),
        ('variable', 'Variable'),
    ]
    
    # Relationships
    club = models.ForeignKey(
        SASClub, 
        on_delete=models.CASCADE, 
        related_name='products',
        help_text="Club this product belongs to"
    )
    
    # Core Fields
    name = models.CharField(max_length=255, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly version")
    
    # WooCommerce Integration
    woo_product_id = models.PositiveIntegerField(
        unique=True, 
        help_text="WooCommerce product ID"
    )
    
    # Product Type and Status
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='simple')
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='instock')
    sku = models.CharField(max_length=100, blank=True, help_text="Stock Keeping Unit")
    style_code = models.CharField(max_length=100, blank=True, null=True, help_text="Product style code")

    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Current selling price"
    )
    regular_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Regular price"
    )
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Sale price (if on sale)"
    )

    # Pricing management fields (for price update system)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cost price from supplier")
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Price with 75% margin")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Discount percentage applied")
    last_price_update = models.DateTimeField(null=True, blank=True, help_text="Last price update timestamp")
    barcode = models.CharField(max_length=100, blank=True, db_index=True, help_text="Product barcode")
    
    # Product Details
    description = models.TextField(blank=True, help_text="Full product description")
    short_description = models.TextField(blank=True, help_text="Short product description")
    
    # Product Attributes
    weight = models.CharField(max_length=50, blank=True, help_text="Product weight")
    dimensions = models.JSONField(default=dict, blank=True, help_text="Product dimensions")
    
    # Media
    image_url = models.URLField(blank=True, validators=[URLValidator()], help_text="Main product image URL")
    gallery_urls = models.JSONField(default=list, blank=True, help_text="Additional product images")
    
    # WooCommerce Metadata
    tags = models.JSONField(default=list, blank=True, help_text="Product tags")
    attributes = models.JSONField(default=list, blank=True, help_text="Product attributes")
    categories = models.JSONField(default=list, blank=True, help_text="Additional WooCommerce categories")
    
    # SEO and Marketing
    featured = models.BooleanField(default=False, help_text="Whether product is featured")
    catalog_visibility = models.CharField(max_length=20, default='visible', help_text="Catalog visibility")
    
    # Stock Management
    manage_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(null=True, blank=True)
    backorders = models.CharField(max_length=10, default='no')
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Whether this product is active")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last WooCommerce sync timestamp")
    
    # Managers
    objects = SASProductManager()
    active = SASActiveManager()
    
    class Meta:
        db_table = 'sas_products'
        verbose_name = 'SAS Product'
        verbose_name_plural = 'SAS Products'
        ordering = ['club__sport__name', 'club__name', 'name']
        indexes = [
            models.Index(fields=['club', 'stock_status']),
            models.Index(fields=['woo_product_id']),
            models.Index(fields=['sku']),
            models.Index(fields=['style_code']),
            models.Index(fields=['price']),
            models.Index(fields=['stock_status']),
            models.Index(fields=['featured', 'stock_status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['last_sync_at']),
            models.Index(fields=['club', 'featured']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.club.name} ({self.club.sport.name})"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            # Create slug from product name only (matches existing data)
            self.slug = slugify(self.name)
        
        # Set effective price
        if self.sale_price and self.sale_price > 0:
            self.price = self.sale_price
        elif self.regular_price:
            self.price = self.regular_price
        
        super().save(*args, **kwargs)
        
        # Update parent club product count
        if hasattr(self, '_update_parent_counts') and self._update_parent_counts:
            self.club.update_product_count()
    
    def delete(self, *args, **kwargs):
        club = self.club
        super().delete(*args, **kwargs)
        # Update parent counts after deletion
        club.update_product_count()
        club.sport.update_counts()
    
    @property
    def is_on_sale(self):
        """Check if product is currently on sale."""
        return (
            self.sale_price is not None and 
            self.sale_price > 0 and 
            self.regular_price is not None and
            self.sale_price < self.regular_price
        )
    
    @property
    def sale_discount_percentage(self):
        """Calculate sale discount percentage if on sale (WooCommerce sale price)."""
        if not self.is_on_sale:
            return 0

        discount = self.regular_price - self.sale_price
        percentage = (discount / self.regular_price) * 100
        return round(percentage, 1)
    
    @property
    def effective_price(self):
        """Return the effective selling price."""
        return self.sale_price if self.is_on_sale else self.regular_price or Decimal('0.00')
    
    @property
    def is_available(self):
        """Check if product is available for purchase."""
        return self.stock_status in ['instock', 'onbackorder'] and self.is_active

    @property
    def normalized_image_url(self):
        """
        Get product image URL (for template compatibility with LOTTO products).
        SAS products don't need URL normalization like LOTTO products do.
        """
        return self.image_url

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
        import logging
        logger = logging.getLogger(__name__)

        if self.is_variable_product:
            calculated_status = self.calculated_stock_status
            if self.stock_status != calculated_status:
                self.stock_status = calculated_status
                self.save(update_fields=['stock_status', 'updated_at'])
                logger.info(f"Updated stock status for SAS product {self.id} to {calculated_status}")
                return True
        return False

    @property
    def sport(self):
        """Get the sport through the club relationship."""
        return self.club.sport if self.club else None
    
    @property
    def has_variations(self):
        """Check if product has variations based on attributes or related variations"""
        # Check if there are related SAS variations
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
            return True
        
        # Check if attributes contain variation data
        if self.attributes:
            for attr in self.attributes:
                if isinstance(attr, dict) and attr.get('variation', False):
                    options = attr.get('options', [])
                    if len(options) > 1:  # More than one option means it's a variation
                        return True
        return False
    
    def _parse_variation_attributes(self):
        """
        Parse variation attributes from the attributes field.
        Returns dict with attribute type as key and list of values as value.
        """
        # Standard attribute priority order
        attribute_priority = ['size', 'color', 'material', 'style', 'gender', 'age_group']
        
        # Dictionary to store parsed attributes
        parsed_attributes = {}
        
        # Check actual SAS variations first
        if hasattr(self, 'variations'):
            variations = self.variations.filter(is_active=True, stock_quantity__gt=0)
            for variation in variations:
                if variation.variation_type not in parsed_attributes:
                    parsed_attributes[variation.variation_type] = set()
                parsed_attributes[variation.variation_type].add(variation.variation_value)
        
        # Parse from attributes field
        if self.attributes:
            for attr in self.attributes:
                if isinstance(attr, dict) and attr.get('variation', False):
                    attr_name = attr.get('name', '').lower()
                    # Map common attribute names to standard types
                    attr_type = attr_name
                    if 'colour' in attr_name:
                        attr_type = 'color'
                    elif 'size' in attr_name:
                        attr_type = 'size'
                    elif 'material' in attr_name:
                        attr_type = 'material'
                    elif 'style' in attr_name:
                        attr_type = 'style'
                    
                    options = attr.get('options', [])
                    if options and len(options) > 1:
                        if attr_type not in parsed_attributes:
                            parsed_attributes[attr_type] = set()
                        for option in options:
                            parsed_attributes[attr_type].add(str(option))
        
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
    
    @property
    def is_variable_product(self):
        """Check if this is a variable product"""
        return self.product_type == 'variable' or self.has_variations
    
    @property
    def total_stock(self):
        """Get total stock across all variations"""
        if not self.has_variations:
            return self.stock_quantity if self.manage_stock else None
        
        # If has actual variations, sum their stock
        if hasattr(self, 'variations'):
            from django.db.models import Sum
            return self.variations.filter(is_active=True).aggregate(
                total=Sum('stock_quantity')
            )['total'] or 0
        
        # For attribute-based variations, return product stock
        return self.stock_quantity if self.manage_stock else None
    
    def get_available_variations_for_selection(self, **selection):
        """
        Get available variation options based on current selection.
        Returns dict with available options for each variation type.
        """
        result = {}
        
        # If product has actual SAS variations, use them
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
            # Use similar logic to LOTTO products
            base_variations = self.variations.filter(is_active=True, stock_quantity__gt=0)
            
            # Apply current selection filters
            for attr_type, attr_value in selection.items():
                if attr_value:
                    base_variations = base_variations.filter(
                        variation_type=attr_type,
                        variation_value=attr_value
                    )
            
            # Get available options for each variation type
            variation_types = ['size', 'color', 'material', 'style', 'gender', 'age_group']
            
            for var_type in variation_types:
                if var_type in selection and selection[var_type]:
                    continue
                    
                options = []
                type_variations = base_variations.filter(variation_type=var_type).distinct()
                
                for variation in type_variations:
                    options.append({
                        'value': variation.variation_value,
                        'stock': variation.stock_quantity,
                        'available': variation.stock_quantity > 0,
                        'variation_id': variation.id,
                        'price_modifier': 0.0,  # SAS typically doesn't have price modifiers
                        'image': variation.image_url if hasattr(variation, 'image_url') else None
                    })
                
                if options:
                    options.sort(key=lambda x: x['value'])
                    result[var_type] = options
        
        else:
            # Use attribute-based variations
            parsed_attrs = self.parsed_variation_attributes
            for attr_type, values in parsed_attrs.items():
                if attr_type in selection and selection[attr_type]:
                    continue
                
                options = []
                for value in values:
                    # For SAS products, use stock_quantity if available, otherwise None for status-only
                    stock_value = None
                    if self.manage_stock and self.stock_quantity is not None:
                        stock_value = self.stock_quantity
                    
                    options.append({
                        'value': value,
                        'stock': stock_value,
                        'available': self.stock_status in ['instock', 'onbackorder'],
                        'variation_id': f"{self.id}_{attr_type}_{value}",
                        'price_modifier': 0.0,
                        'image': self.image_url
                    })
                
                if options:
                    result[attr_type] = options
        
        return result
    
    def get_variation_combination_stock(self, **combination):
        """
        Get stock quantity for a specific variation combination.
        """
        # If product has actual variations, use them
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
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
        else:
            # For attribute-based variations, return product stock
            # Check if the combination is valid first
            parsed_attrs = self.parsed_variation_attributes
            for attr_type, attr_value in combination.items():
                if attr_value:
                    if attr_type not in parsed_attrs or attr_value not in parsed_attrs[attr_type]:
                        return 0  # Invalid combination
            
            # For SAS products, check if stock is managed and return appropriate value
            if self.manage_stock and self.stock_quantity is not None:
                return self.stock_quantity
            else:
                # For products without explicit stock management, check if product has stock_quantity data
                # This handles cases where WooCommerce has stock data but manage_stock might be False
                if hasattr(self, 'stock_quantity') and self.stock_quantity is not None and self.stock_quantity > 0:
                    return self.stock_quantity
                elif self.stock_status == 'instock':
                    # Return a default positive value to indicate availability when no specific quantity
                    return 1
                elif self.stock_status == 'onbackorder':
                    return 1  # Available for backorder
                else:
                    return 0  # Out of stock
    
    def is_variation_combination_available(self, **combination):
        """
        Check if a specific variation combination is available.
        """
        stock = self.get_variation_combination_stock(**combination)
        if stock is None:
            # For products without stock management, check stock status
            return self.stock_status in ['instock', 'onbackorder']
        return stock > 0
    
    def get_stock_by_color_for_all_sizes(self, color_value):
        """
        Get stock information for all sizes in a specific color.
        
        Args:
            color_value: The color variation value (e.g., 'Black', 'Red')
        
        Returns:
            dict: Stock information by size for the selected color
        """
        if not self.has_variations:
            return {'color': color_value, 'sizes': []}
        
        # Get all available sizes for this product
        all_sizes = self.available_sizes
        size_stock_map = {}
        
        # Initialize all sizes with zero stock
        for size in all_sizes:
            size_stock_map[size] = {
                'size': size,
                'stock_quantity': 0,
                'stock_status': 'outofstock',
                'is_available': False
            }
        
        # If product has actual variations, use them
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
            for variation in self.variations.filter(is_active=True):
                # Check if this variation matches our color
                attributes = getattr(variation, 'attributes', {}) or {}
                variation_color = attributes.get('color') or attributes.get('colour')
                
                if variation_color and variation_color.lower() == color_value.lower():
                    # Get the size for this variation
                    variation_size = attributes.get('size')
                    if variation_size and variation_size in size_stock_map:
                        current_stock = size_stock_map[variation_size]['stock_quantity']
                        new_stock = current_stock + getattr(variation, 'stock_quantity', 0)
                        
                        size_stock_map[variation_size] = {
                            'size': variation_size,
                            'stock_quantity': new_stock,
                            'stock_status': 'instock' if new_stock > 0 else 'outofstock',
                            'is_available': new_stock > 0
                        }
        else:
            # Use attribute-based variations from WooCommerce data
            parsed_attrs = self.parsed_variation_attributes
            if 'color' in parsed_attrs and color_value in parsed_attrs['color']:
                # For products without individual stock tracking, assume all sizes are available
                # if the product stock status indicates availability
                is_available = self.stock_status in ['instock', 'onbackorder']
                stock_quantity = 1 if is_available else 0
                
                for size in all_sizes:
                    size_stock_map[size] = {
                        'size': size,
                        'stock_quantity': stock_quantity,
                        'stock_status': self.stock_status,
                        'is_available': is_available
                    }
        
        # Convert to list and sort by size
        sizes_list = list(size_stock_map.values())
        sizes_list.sort(key=lambda x: self._get_size_sort_order(x['size']))
        
        return {
            'color': color_value,
            'sizes': sizes_list
        }
    
    def _get_size_sort_order(self, size):
        """Helper method to get sort order for sizes"""
        # SAS-specific size order including kids sizes
        size_order = ['4k', '6k', '8k', '10k', '12k', '14k', '16k', 'xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl']
        try:
            return size_order.index(size.lower())
        except ValueError:
            return 999  # Put unknown sizes at the end
    
    def get_all_color_size_combinations(self):
        """
        Get stock information for all color-size combinations.
        
        Returns:
            dict: Complete stock matrix organized by color, then by size
        """
        if not self.has_variations:
            return {}
        
        colors = self.available_colors
        result = {}
        
        for color in colors:
            result[color] = self.get_stock_by_color_for_all_sizes(color)
        
        return result
    
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
            'variation_types': [],
            'variations': [],
            'parsed_attributes': self.parsed_variation_attributes,
            'total_stock': self.total_stock,
            'color_size_stock_matrix': self.get_all_color_size_combinations()  # Add stock matrix
        }
        
        # If product has actual SAS variations
        if hasattr(self, 'variations') and self.variations.filter(is_active=True).exists():
            variations_data['variation_types'] = list(
                self.variations.filter(is_active=True).values_list('variation_type', flat=True).distinct()
            )
            
            for variation in self.variations.filter(is_active=True):
                is_in_stock = getattr(variation, 'is_in_stock', variation.stock_quantity > 0)
                # Calculate stock_status like LOTTO does
                if not variation.is_active:
                    stock_status = 'discontinued'
                elif variation.stock_quantity > 0:
                    stock_status = 'instock'
                else:
                    stock_status = 'outofstock'

                var_data = {
                    'id': variation.id,
                    'type': variation.variation_type,
                    'value': variation.variation_value,
                    'stock': variation.stock_quantity,
                    'stock_status': stock_status,  # Add stock_status field like LOTTO
                    'price_modifier': 0.0,  # SAS typically doesn't have price modifiers
                    'final_price': float(self.effective_price),
                    'sku_suffix': getattr(variation, 'sku_suffix', ''),
                    'is_in_stock': is_in_stock,
                    'image': getattr(variation, 'image_url', self.image_url),
                    'attributes': getattr(variation, 'attributes', {}) or {}
                }
                variations_data['variations'].append(var_data)
        else:
            # Use attribute-based variations
            parsed_attrs = self.parsed_variation_attributes
            variations_data['variation_types'] = list(parsed_attrs.keys())
            
            for attr_type, values in parsed_attrs.items():
                for value in values:
                    # For SAS products, use stock_quantity if available, otherwise None for status-only
                    stock_value = None
                    stock_value = 0  # Initialize stock_value with default
                    if self.manage_stock and self.stock_quantity is not None:
                        stock_value = self.stock_quantity

                    # Fixed logic: is_in_stock should be based on actual stock, not just status
                    is_in_stock = (stock_value > 0) or (self.stock_status == 'onbackorder')

                    # Calculate stock_status like LOTTO does for attribute-based variations
                    if not self.is_active:
                        stock_status = 'discontinued'
                    elif stock_value and stock_value > 0:
                        stock_status = 'instock'
                        is_in_stock = True
                    elif self.stock_status == 'onbackorder':
                        stock_status = 'onbackorder'
                        is_in_stock = True  # Can order on backorder
                    else:
                        stock_status = 'outofstock'
                        is_in_stock = False  # Not in stock

                    var_data = {
                        'id': f"{self.id}_{attr_type}_{value}",
                        'type': attr_type,
                        'value': value,
                        'stock': stock_value,
                        'stock_status': stock_status,  # Add stock_status field like LOTTO
                        'price_modifier': 0.0,
                        'final_price': float(self.effective_price),
                        'sku_suffix': f"{attr_type}-{value}",
                        'is_in_stock': is_in_stock,
                        'image': self.image_url,
                        'attributes': {attr_type: value}
                    }
                    variations_data['variations'].append(var_data)
        
        return variations_data


class SASProductVariation(models.Model):
    """
    SAS-specific product variation model for variable products
    """
    VARIATION_TYPE_CHOICES = [
        ('size', 'Size'),
        ('color', 'Color'),
        ('colour', 'Colour'),  # British spelling
        ('material', 'Material'),
        ('style', 'Style'),
        ('gender', 'Gender'),
        ('age_group', 'Age Group'),
        ('other', 'Other'),
    ]
    
    # Relationships
    product = models.ForeignKey(SASProduct, on_delete=models.CASCADE, related_name='variations')
    
    # Core fields
    variation_type = models.CharField(max_length=50, choices=VARIATION_TYPE_CHOICES, help_text="Type of variation")
    variation_value = models.CharField(max_length=255, help_text="Variation value (e.g., 'Large', 'Red', 'Cotton')")
    woo_variation_id = models.PositiveIntegerField(unique=True, null=True, blank=True, help_text="WooCommerce variation ID")
    
    # Pricing (SAS products typically don't have variation pricing, but keeping for consistency)
    price_modifier = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Price adjustment (+/-) from base product price"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Variation price"
    )
    regular_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Regular price"
    )
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sale price"
    )

    # Pricing management fields (for wholesale price update system)
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cost price from supplier"
    )
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

    # Stock
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Stock quantity for this variation")
    sku_suffix = models.CharField(max_length=50, blank=True, null=True, help_text="SKU suffix for this variation")
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Whether this variation is active")
    
    # Additional variation data
    attributes = models.JSONField(blank=True, null=True, help_text="Additional variation attributes")
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Variation weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Variation dimensions")
    
    # Image
    image_url = models.URLField(blank=True, help_text="Variation-specific image URL")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Managers
    objects = models.Manager()
    active = SASActiveManager()
    
    class Meta:
        db_table = 'sas_product_variations'
        verbose_name = 'SAS Product Variation'
        verbose_name_plural = 'SAS Product Variations'
        ordering = ['product', 'variation_type', 'variation_value']
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
            type_short = self.variation_type[:3].upper()
            value_short = ''.join(c for c in self.variation_value if c.isalnum())[:5].upper()
            self.sku_suffix = f"{type_short}-{value_short}"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.product.name} - {self.variation_type}: {self.variation_value}"
    
    @property
    def final_price(self):
        """Calculate the final price including price modifier"""
        base_price = self.product.effective_price or 0
        return base_price + self.price_modifier
    
    @property
    def full_sku(self):
        """Generate full SKU including suffix"""
        base_sku = self.product.sku or f"SAS-{self.product.id}"
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
        if self.image_url:
            return self.image_url
        
        # Fallback to parent product image
        if self.product and self.product.image_url:
            return self.product.image_url
        
        return None
    
    @property
    def effective_image_url(self):
        """Get effective image URL for this variation"""
        return self.effective_image
    
    @property
    def has_unique_image(self):
        """Check if variation has its own unique image"""
        return bool(self.image_url)
    
    @property
    def should_show_variation_image(self):
        """Determine if variation image should be displayed based on variation type"""
        # Variation types that typically benefit from showing unique images
        image_priority_types = ['color', 'colour', 'style', 'material']
        return self.variation_type in image_priority_types and self.has_unique_image
    
    def get_image_for_display(self):
        """Get appropriate image for display purposes"""
        # For color/style/material variations, prefer variation-specific image
        if self.should_show_variation_image:
            return self.image_url
        
        # For size/gender/other variations, use effective image with fallback
        return self.effective_image


# Custom indexes for cross-table queries
class Meta:
    """Global model metadata for the SAS models."""
    
    # Add database-level constraints and indexes
    pass


# Signal handlers for maintaining data integrity
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver([post_save, post_delete], sender=SASClub)
def update_sport_counts_on_club_change(sender, instance, **kwargs):
    """Update sport counts when clubs are created, updated, or deleted."""
    if hasattr(instance, 'sport'):
        instance.sport.update_counts()

@receiver([post_save, post_delete], sender=SASProduct)
def update_club_counts_on_product_change(sender, instance, **kwargs):
    """Update club and sport counts when products are created, updated, or deleted."""
    if hasattr(instance, 'club') and instance.club:
        instance.club.update_product_count()
        if instance.club.sport:
            instance.club.sport.update_counts()