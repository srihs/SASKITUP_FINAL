"""
Quotation models for SASKITUP project.

This module provides comprehensive quotation management for all user types:
- Sales Representatives
- Account Managers
- Customers

Supports quotations for:
- Schools (regular and wholesale)
- Clubs (LOTTO and SAS)

Products from all 4 types:
- WholesaleProduct (CIN7)
- LottoProduct (WooCommerce)
- SASProduct (WooCommerce)
- TUSProduct (WooCommerce)
"""

import uuid
from decimal import Decimal
from datetime import timedelta

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.urls import reverse


class SiteSettingsManager(models.Manager):
    """Custom manager for singleton SiteSettings model"""

    def get_settings(self):
        """Get or create the singleton settings instance"""
        settings, created = self.get_or_create(pk=1)
        return settings


class SiteSettings(models.Model):
    """
    Singleton model for site-wide settings.
    Only one instance should exist (pk=1).
    """

    gst_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('15.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="GST/VAT percentage applied to quotations"
    )

    quotation_validity_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Default number of days a quotation remains valid"
    )

    # Metadata
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_updates',
        help_text="User who last updated the settings"
    )

    objects = SiteSettingsManager()

    class Meta:
        db_table = 'site_settings'
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return f"Site Settings (GST: {self.gst_percentage}%, Validity: {self.quotation_validity_days} days)"

    def save(self, *args, **kwargs):
        # Enforce singleton pattern
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion of singleton instance
        pass

    @classmethod
    def load(cls):
        """Convenience method to load settings"""
        return cls.objects.get_settings()


class QuotationManager(models.Manager):
    """Custom manager for Quotation model with common query methods"""

    def active(self):
        """Get all non-expired, non-rejected quotations"""
        return self.filter(
            models.Q(expires_at__gt=timezone.now()) | models.Q(expires_at__isnull=True),
            status__in=['draft', 'pending', 'approved']
        )

    def by_user(self, user):
        """Get quotations created by a specific user"""
        return self.filter(created_by=user)

    def for_institution(self, institution):
        """Get quotations for a specific institution (school or club)"""
        content_type = ContentType.objects.get_for_model(institution)
        return self.filter(
            institution_content_type=content_type,
            institution_object_id=institution.id
        )

    def pending_approval(self):
        """Get quotations pending approval"""
        return self.filter(status='pending')

    def expired(self):
        """Get expired quotations"""
        return self.filter(
            expires_at__lte=timezone.now(),
            status__in=['draft', 'pending']
        )


class Quotation(models.Model):
    """
    Main quotation model supporting all institution types and user roles.
    Uses GenericForeignKey to reference either School or Club institutions.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quotation_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        help_text="Auto-generated quotation number (Q-YYYYMMDD-XXXX)"
    )

    # User who created the quotation
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.PROTECT,
        related_name='quotations_created',
        help_text="User who created this quotation (sales rep/account manager/customer)"
    )

    # Institution reference using GenericForeignKey (OPTIONAL)
    # Supports: School, WholesaleSchool, LottoClub, SASClub
    # Institution helps with organization but is not mandatory
    institution_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={
            'model__in': ['school', 'wholesaleschool', 'lottoclub', 'sasclub']
        },
        help_text="Type of institution (school or club) - optional"
    )
    institution_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the institution - optional"
    )
    institution = GenericForeignKey('institution_content_type', 'institution_object_id')

    # Status and workflow
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
        help_text="Current quotation status"
    )

    # Dates
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Quotation expiry date"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    # Approval/rejection tracking
    approved_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_approved',
        help_text="User who approved this quotation"
    )
    rejected_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_rejected',
        help_text="User who rejected this quotation"
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection"
    )

    # Pricing fields (calculated from items)
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Subtotal before tax and discount"
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Discount percentage applied to subtotal"
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Fixed discount amount"
    )
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('15.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Tax percentage (VAT)"
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Calculated tax amount"
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Final total amount"
    )

    # Notes and comments
    notes = models.TextField(
        blank=True,
        help_text="Internal notes about this quotation"
    )
    customer_notes = models.TextField(
        blank=True,
        help_text="Notes visible to the customer"
    )
    terms_and_conditions = models.TextField(
        blank=True,
        help_text="Terms and conditions for this quotation"
    )

    # Recipient information (optional)
    recipient_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the quotation recipient"
    )
    recipient_address = models.TextField(
        blank=True,
        help_text="Address of the quotation recipient"
    )

    # Version tracking
    version = models.PositiveIntegerField(
        default=1,
        help_text="Quotation version number"
    )

    # Reference fields
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="External reference number (PO, etc.)"
    )

    # Metadata
    is_locked = models.BooleanField(
        default=False,
        help_text="Whether quotation is locked from editing"
    )

    objects = QuotationManager()

    class Meta:
        db_table = 'quotations'
        verbose_name = 'Quotation'
        verbose_name_plural = 'Quotations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['quotation_number']),
            models.Index(fields=['created_by', 'status']),
            models.Index(fields=['institution_content_type', 'institution_object_id']),
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['approved_at']),
        ]
        permissions = [
            ('can_approve_quotation', 'Can approve quotations'),
            ('can_reject_quotation', 'Can reject quotations'),
            ('can_view_all_quotations', 'Can view all quotations'),
        ]

    def __str__(self):
        if self.institution:
            institution_name = getattr(self.institution, 'name', None) or getattr(self.institution, 'org_name', 'Unknown')
            return f"{self.quotation_number} - {institution_name} ({self.get_status_display()})"
        else:
            return f"{self.quotation_number} - No Institution ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Check if this is a new quotation by looking for absence of created_at
        # (created_at is set by auto_now_add only after first save)
        is_new = self._state.adding

        # Auto-generate quotation number if not set
        if not self.quotation_number:
            self.quotation_number = self._generate_quotation_number()

        # For new quotations, capture settings from SiteSettings
        if is_new:
            settings = SiteSettings.objects.get_settings()

            # Set default expiry date from settings
            if not self.expires_at:
                self.expires_at = timezone.now() + timedelta(days=settings.quotation_validity_days)

            # Capture GST percentage from settings (snapshot at creation time)
            # Only set if tax_percentage is still at default value
            if self.tax_percentage == Decimal('15.00'):
                self.tax_percentage = settings.gst_percentage

        # Auto-update status if expired
        if self.expires_at and self.expires_at <= timezone.now() and self.status in ['draft', 'pending']:
            self.status = 'expired'

        super().save(*args, **kwargs)

    def clean(self):
        """Validate quotation data"""
        super().clean()

        # Ensure user has permission to create quotations for this institution
        if self.created_by and self.institution:
            if self.created_by.is_customer:
                # Customers can only create quotations for their assigned institutions
                # This would need to be implemented with CustomerInstitutionAssignment
                pass
            elif self.created_by.is_sales_rep:
                # Sales reps can only create for assigned institutions
                if not self._user_can_access_institution():
                    raise ValidationError({
                        'institution': 'You do not have permission to create quotations for this institution.'
                    })

        # Validate pricing
        if self.discount_percentage and self.discount_amount:
            raise ValidationError({
                'discount_amount': 'Cannot have both percentage and fixed discount. Choose one.'
            })

        # Validate approved/rejected users and dates
        if self.status == 'approved' and not self.approved_by:
            raise ValidationError({
                'approved_by': 'Approved quotations must have an approver.'
            })

        if self.status == 'rejected' and not self.rejected_by:
            raise ValidationError({
                'rejected_by': 'Rejected quotations must have a rejector.'
            })

    def _generate_quotation_number(self):
        """Generate unique quotation number: Q-YYYYMMDD-XXXX"""
        today = timezone.now().date()
        date_str = today.strftime('%Y%m%d')

        # Get count of quotations created today
        today_count = Quotation.objects.filter(
            quotation_number__startswith=f'Q-{date_str}'
        ).count()

        sequence = today_count + 1
        return f'Q-{date_str}-{sequence:04d}'

    def _user_can_access_institution(self):
        """Check if user can access the institution"""
        if not self.created_by or not self.institution:
            return False

        # Account managers have access to all institutions
        if self.created_by.is_account_manager or self.created_by.is_admin:
            return True

        # Check for school access
        from schools.models import School, WholesaleSchool
        if isinstance(self.institution, (School, WholesaleSchool)):
            return self.created_by.can_access_school(self.institution)

        # Check for club access (both LOTTO and SAS)
        from clubs.models_lotto import LottoClub
        from clubs.models_sas import SASClub
        if isinstance(self.institution, (LottoClub, SASClub)):
            return self.created_by.can_access_club(self.institution)

        return False

    @property
    def institution_name(self):
        """Get the institution name"""
        if not self.institution:
            return 'No Institution'
        return getattr(self.institution, 'name', None) or getattr(self.institution, 'org_name', 'Unknown')

    @property
    def institution_type(self):
        """Get the institution type as a readable string"""
        if not self.institution_content_type:
            return 'No Institution'

        model_name = self.institution_content_type.model
        type_map = {
            'school': 'School',
            'wholesaleschool': 'Wholesale School',
            'lottoclub': 'LOTTO Club',
            'sasclub': 'SAS Club',
        }
        return type_map.get(model_name, model_name.title())

    @property
    def is_expired(self):
        """Check if quotation has expired"""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at and self.status in ['draft', 'pending']

    @property
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if not self.expires_at:
            return None
        delta = self.expires_at - timezone.now()
        return delta.days if delta.days >= 0 else 0

    def calculate_totals(self):
        """
        Calculate and update all totals based on quotation items.
        Should be called after adding/removing/updating items.
        """
        # Calculate subtotal from all items
        self.subtotal = sum(
            item.line_total for item in self.items.all()
        )

        # Calculate discount
        if self.discount_percentage:
            discount = (self.subtotal * self.discount_percentage / Decimal('100'))
        else:
            discount = self.discount_amount

        # Calculate tax
        taxable_amount = self.subtotal - discount
        self.tax_amount = (taxable_amount * self.tax_percentage / Decimal('100')).quantize(Decimal('0.01'))

        # Calculate total
        self.total = (taxable_amount + self.tax_amount).quantize(Decimal('0.01'))

        self.save(update_fields=['subtotal', 'tax_amount', 'total', 'updated_at'])

    def approve(self, approved_by, notes=''):
        """Approve the quotation and set status to confirmed"""
        if self.status == 'confirmed':
            raise ValidationError('Quotation is already confirmed')

        self.status = 'confirmed'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        if notes:
            self.notes = f"{self.notes}\n\nApproved: {notes}" if self.notes else f"Approved: {notes}"
        self.save()

        # Create version snapshot
        self.create_version_snapshot(f'Approved by {approved_by.get_full_name()}')

    def reject(self, rejected_by, reason=''):
        """Reject the quotation"""
        if self.status == 'rejected':
            raise ValidationError('Quotation is already rejected')

        self.status = 'rejected'
        self.rejected_by = rejected_by
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save()

        # Create version snapshot
        self.create_version_snapshot(f'Rejected by {rejected_by.get_full_name()}: {reason}')

    def create_version_snapshot(self, description=''):
        """Create a version snapshot of the current quotation state"""
        snapshot_data = {
            'quotation_number': self.quotation_number,
            'status': self.status,
            'subtotal': str(self.subtotal),
            'discount_percentage': str(self.discount_percentage),
            'discount_amount': str(self.discount_amount),
            'tax_percentage': str(self.tax_percentage),
            'tax_amount': str(self.tax_amount),
            'total': str(self.total),
            'items': [
                {
                    'product_name': item.product_name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'line_total': str(item.line_total),
                }
                for item in self.items.all()
            ]
        }

        QuotationVersion.objects.create(
            quotation=self,
            version_number=self.version,
            snapshot_data=snapshot_data,
            created_by=self.created_by,
            change_description=description
        )

        # Increment version
        self.version += 1
        self.save(update_fields=['version', 'updated_at'])

    def get_absolute_url(self):
        """Get absolute URL for quotation detail"""
        return reverse('quotations:quotation-detail', kwargs={'pk': self.pk})


class QuotationItem(models.Model):
    """
    Individual line items in a quotation.
    Uses GenericForeignKey to reference any product type.
    """

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Quotation relationship
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Parent quotation"
    )

    # Product reference using GenericForeignKey
    # Supports: WholesaleProduct, LottoProduct, SASProduct, TUSProduct
    product_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        limit_choices_to={
            'model__in': ['wholesaleproduct', 'lottoproduct', 'sasproduct', 'tusproduct']
        },
        help_text="Type of product"
    )
    product_object_id = models.PositiveIntegerField(
        help_text="ID of the product"
    )
    product = GenericForeignKey('product_content_type', 'product_object_id')

    # Product snapshot (stores product details at time of quotation)
    product_snapshot = models.JSONField(
        default=dict,
        help_text="Snapshot of product data at time of quotation creation"
    )

    # Item details (cached from product for performance)
    product_name = models.CharField(max_length=255, help_text="Product name at time of quote")
    product_sku = models.CharField(max_length=100, blank=True, help_text="Product SKU")
    product_image_url = models.URLField(max_length=500, blank=True, help_text="Product image URL")

    # Quantity and pricing
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantity of this item"
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Unit price at time of quotation"
    )

    # Variations (size, color, etc.) stored as JSON
    variations = models.JSONField(
        default=dict,
        blank=True,
        help_text="Product variations (size, color, etc.)"
    )

    # Calculated fields
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Line total (quantity × unit_price)"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Notes about this item"
    )

    # Ordering
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in quotation"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'quotation_items'
        verbose_name = 'Quotation Item'
        verbose_name_plural = 'Quotation Items'
        ordering = ['sort_order', 'created_at']
        indexes = [
            models.Index(fields=['quotation', 'sort_order']),
            models.Index(fields=['product_content_type', 'product_object_id']),
        ]

    def __str__(self):
        return f"{self.quotation.quotation_number} - {self.product_name} (×{self.quantity})"

    def save(self, *args, **kwargs):
        # Calculate line total
        self.line_total = (Decimal(str(self.quantity)) * self.unit_price).quantize(Decimal('0.01'))

        # Create product snapshot if not exists
        if not self.product_snapshot and self.product:
            self.product_snapshot = self._create_product_snapshot()

        # Cache product details
        if self.product and not self.product_name:
            self.product_name = getattr(self.product, 'name', 'Unknown Product')
            self.product_sku = getattr(self.product, 'cin7_sku', None) or getattr(self.product, 'sku', '')

            # Get image URL
            image_url = getattr(self.product, 'image_url', None) or getattr(self.product, 'image', '')
            self.product_image_url = image_url if isinstance(image_url, str) else ''

        super().save(*args, **kwargs)

        # Update quotation totals
        self.quotation.calculate_totals()

    def delete(self, *args, **kwargs):
        quotation = self.quotation
        super().delete(*args, **kwargs)
        # Update quotation totals after deletion
        quotation.calculate_totals()

    def clean(self):
        """Validate item data"""
        super().clean()

        # Validate unit price is positive
        if self.unit_price and self.unit_price < 0:
            raise ValidationError({
                'unit_price': 'Unit price must be positive'
            })

        # Validate quantity
        if self.quantity and self.quantity < 1:
            raise ValidationError({
                'quantity': 'Quantity must be at least 1'
            })

    def _create_product_snapshot(self):
        """Create a snapshot of the product data at time of quotation"""
        if not self.product:
            return {}

        snapshot = {
            'name': getattr(self.product, 'name', ''),
            'sku': getattr(self.product, 'cin7_sku', None) or getattr(self.product, 'sku', ''),
            'description': getattr(self.product, 'description', ''),
            'price': str(getattr(self.product, 'wholesale_price', None) or getattr(self.product, 'price', 0)),
            'stock_status': getattr(self.product, 'stock_status', ''),
        }

        # Add product-type specific fields
        if hasattr(self.product, 'cin7_brand'):
            snapshot['brand'] = self.product.cin7_brand

        if hasattr(self.product, 'weight'):
            snapshot['weight'] = str(self.product.weight) if self.product.weight else ''

        return snapshot

    @property
    def product_type(self):
        """Get the product type as a readable string"""
        if not self.product_content_type:
            return 'Unknown'

        model_name = self.product_content_type.model
        type_map = {
            'wholesaleproduct': 'Wholesale',
            'lottoproduct': 'LOTTO',
            'sasproduct': 'SAS',
            'tusproduct': 'TUS Retail',
        }
        return type_map.get(model_name, model_name.title())


class CustomerInstitutionAssignment(models.Model):
    """
    Assignment of customers to institutions (schools or clubs).
    Allows customers to create quotations for their assigned institutions.
    """

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Customer relationship
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='institution_assignments',
        limit_choices_to={'user_type': 'customer'},
        help_text="Customer user"
    )

    # Institution reference using GenericForeignKey
    institution_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={
            'model__in': ['tusschool', 'wholesaleschool', 'lottoclub', 'sasclub']
        },
        help_text="Type of institution"
    )
    institution_object_id = models.PositiveIntegerField(
        help_text="ID of the institution"
    )
    institution = GenericForeignKey('institution_content_type', 'institution_object_id')

    # Assignment details
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this assignment is active"
    )
    assigned_date = models.DateTimeField(
        default=timezone.now,
        help_text="When assignment was made"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this assignment"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_assignments_created',
        help_text="User who created this assignment"
    )

    class Meta:
        db_table = 'customer_institution_assignments'
        verbose_name = 'Customer Institution Assignment'
        verbose_name_plural = 'Customer Institution Assignments'
        ordering = ['-assigned_date']
        indexes = [
            models.Index(fields=['customer', 'is_active']),
            models.Index(fields=['institution_content_type', 'institution_object_id']),
            models.Index(fields=['assigned_date']),
        ]
        constraints = [
            # Ensure each institution-customer combination is unique
            models.UniqueConstraint(
                fields=['customer', 'institution_content_type', 'institution_object_id'],
                condition=models.Q(is_active=True),
                name='unique_active_customer_institution'
            ),
        ]

    def __str__(self):
        institution_name = getattr(self.institution, 'name', None) or getattr(self.institution, 'org_name', 'Unknown')
        status = "Active" if self.is_active else "Inactive"
        return f"{self.customer.get_full_name()} → {institution_name} ({status})"

    def clean(self):
        """Validate assignment data"""
        super().clean()

        # Ensure customer is actually a customer user type
        if self.customer and not self.customer.is_customer:
            raise ValidationError({
                'customer': 'Only customer users can be assigned to institutions'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def deactivate(self, deactivated_by=None):
        """Deactivate this assignment"""
        self.is_active = False
        if deactivated_by:
            self.notes = f"{self.notes}\nDeactivated by {deactivated_by.get_full_name()} on {timezone.now()}"
        self.save(update_fields=['is_active', 'notes', 'updated_at'])


class QuotationVersion(models.Model):
    """
    Version history tracking for quotations.
    Stores snapshots of quotation state at key moments.
    """

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Quotation relationship
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text="Parent quotation"
    )

    # Version details
    version_number = models.PositiveIntegerField(
        help_text="Version number"
    )
    snapshot_data = models.JSONField(
        help_text="Complete snapshot of quotation data"
    )
    change_description = models.TextField(
        blank=True,
        help_text="Description of what changed in this version"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotation_versions_created',
        help_text="User who created this version"
    )

    class Meta:
        db_table = 'quotation_versions'
        verbose_name = 'Quotation Version'
        verbose_name_plural = 'Quotation Versions'
        ordering = ['-version_number']
        indexes = [
            models.Index(fields=['quotation', 'version_number']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['quotation', 'version_number'],
                name='unique_quotation_version'
            ),
        ]

    def __str__(self):
        return f"{self.quotation.quotation_number} - Version {self.version_number}"
