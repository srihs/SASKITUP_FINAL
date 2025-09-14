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
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly version")
    
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
        ]
    
    def __str__(self):
        return f"{self.name} ({self.sport.name}) - ID: {self.woo_category_id}"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            # Create slug from club name only (matches existing data)
            self.slug = slugify(self.name)
        
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
    def discount_percentage(self):
        """Calculate discount percentage if on sale."""
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
    def sport(self):
        """Get the sport through the club relationship."""
        return self.club.sport if self.club else None


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