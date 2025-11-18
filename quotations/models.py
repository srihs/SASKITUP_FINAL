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

    # Assigned staff for notifications
    assigned_sales_rep = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_quotations_sales',
        limit_choices_to={'user_type': 'sales_rep'},
        help_text="Sales representative assigned to this quotation"
    )
    account_manager = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_quotations_manager',
        limit_choices_to={'user_type': 'account_manager'},
        help_text="Account manager assigned to this quotation"
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

    # Shipping fields
    shipping_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Calculated shipping cost based on boxes and region"
    )
    shipping_boxes = models.PositiveIntegerField(
        default=0,
        help_text="Number of boxes required for shipping"
    )
    shipping_region = models.CharField(
        max_length=100,
        blank=True,
        help_text="NZ region for shipping rate calculation"
    )
    is_rural_delivery = models.BooleanField(
        default=False,
        help_text="Rural Delivery (RD) surcharge applies"
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
    additional_emails = models.TextField(
        blank=True,
        help_text="Additional email addresses to send quotation copies to (separated by semicolons)"
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

    # CIN7 Integration Fields
    cin7_so_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="CIN7 SO Number",
        help_text="CIN7 Sales Order Number"
    )
    cin7_so_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="CIN7 SO ID",
        help_text="CIN7 Sales Order ID"
    )
    cin7_sync_status = models.CharField(
        max_length=20,
        choices=[
            ('not_required', 'Not Required'),
            ('pending', 'Pending Sync'),
            ('syncing', 'Syncing'),
            ('synced', 'Synced to CIN7'),
            ('failed', 'Sync Failed'),
        ],
        default='not_required',
        blank=True,
        verbose_name="CIN7 Sync Status",
        help_text="Status of synchronization with CIN7"
    )
    cin7_sync_error = models.TextField(
        blank=True,
        null=True,
        verbose_name="CIN7 Sync Error",
        help_text="Error message if CIN7 sync failed"
    )
    cin7_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="CIN7 Synced At",
        help_text="Timestamp when quotation was synced to CIN7"
    )

    # Account Manager Approval Fields
    submitted_for_approval_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Submitted for Approval At",
        help_text="Timestamp when quotation was submitted for account manager approval"
    )
    submitted_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_submitted',
        verbose_name="Submitted By",
        help_text="User who submitted the quotation for approval"
    )
    account_manager_approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Account Manager Approved At",
        help_text="Timestamp when account manager approved the quotation"
    )

    # Customer Approval Fields (First Level Approval)
    customer_approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Customer Approved At",
        help_text="Timestamp when customer approved the quotation"
    )
    customer_approved_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_customer_approved',
        verbose_name="Customer Approved By",
        help_text="User who gave customer approval (customer or sales rep on their behalf)"
    )

    # Account Manager Approval Override Fields
    approval_override_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_approval_override',
        verbose_name="Approval Override By",
        help_text="Account manager who overrode customer approval requirement"
    )
    approval_override_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Approval Override At",
        help_text="Timestamp when account manager overrode customer approval requirement"
    )

    # Account Manager Edit Tracking
    last_edited_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations_last_edited',
        verbose_name="Last Edited By",
        help_text="User who last edited this quotation (Account Manager or Sales Rep)"
    )
    last_edited_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last Edited At",
        help_text="Timestamp when quotation was last edited"
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

    def calculate_shipping_cost(self):
        """
        Calculate shipping cost based on cart items, box capacity, and customer region.

        Returns:
            Decimal: Total shipping cost (including RD surcharge if applicable)
        """
        import logging
        import math
        from .models_shipping import ShippingSettings
        from .utils_shipping import get_region_from_address, get_capacity_key_for_product

        logger = logging.getLogger(__name__)

        # Get customer address
        customer = self.created_by
        if not customer:
            logger.warning(f"Quotation {self.id} has no customer, cannot calculate shipping")
            self.shipping_cost = Decimal('0.00')
            self.shipping_boxes = 0
            self.shipping_region = ''
            self.is_rural_delivery = False
            return Decimal('0.00')

        # Get region from address
        region = get_region_from_address(
            street_address=customer.street_address,
            suburb=customer.suburb,
            city=customer.city,
            postcode=customer.postcode
        )

        if not region:
            logger.warning(f"Could not determine region for customer {customer.id} ({customer.city}), defaulting to Wellington")
            region = 'Wellington'  # Default fallback

        self.shipping_region = region

        # Get shipping settings
        try:
            shipping_settings = ShippingSettings.get_solo()
        except Exception as e:
            logger.error(f"Could not load ShippingSettings: {e}")
            self.shipping_cost = Decimal('0.00')
            self.shipping_boxes = 0
            self.is_rural_delivery = False
            return Decimal('0.00')

        # Calculate boxes needed for each product type
        total_boxes = 0
        items = self.items.select_related('product_content_type').all()

        for item in items:
            if not item.product:
                logger.warning(f"QuotationItem {item.id} has no product, skipping")
                continue

            # Get capacity key for this product
            capacity_key = get_capacity_key_for_product(item.product)

            # Calculate boxes needed for this item
            boxes = shipping_settings.calculate_boxes_needed(capacity_key, item.quantity)

            if boxes is None:
                logger.warning(f"Could not calculate boxes for item {item.id} (capacity_key: {capacity_key}), using 1 box per 8 items as fallback")
                boxes = math.ceil(item.quantity / 8)  # Fallback

            total_boxes += boxes
            logger.debug(f"Item {item.id} ({item.product_name}): {item.quantity} units = {boxes} boxes (capacity_key: {capacity_key})")

        self.shipping_boxes = total_boxes

        if total_boxes == 0:
            logger.info(f"Quotation {self.id} has no boxes to ship")
            self.shipping_cost = Decimal('0.00')
            self.is_rural_delivery = False
            return Decimal('0.00')

        # Get shipping rate for region
        rate = shipping_settings.get_rate_for_region(region)

        if not rate:
            logger.warning(f"Could not find shipping rate for region '{region}', using Auckland rate as fallback")
            rate = '7.15'  # Auckland rate as fallback

        rate_decimal = Decimal(rate)

        # Calculate base shipping cost
        shipping_cost = rate_decimal * total_boxes

        # Check for rural delivery surcharge
        # RD applies to: Waikato, Tairāwhiti, Hawke's Bay, Taranaki, Manawatū-Whanganui, Otago, Southland, West Coast
        rural_regions = [
            'Waikato', 'Tairāwhiti', "Hawke's Bay", 'Taranaki',
            'Manawatū-Whanganui', 'Otago', 'Southland', 'West Coast'
        ]

        if region in rural_regions:
            self.is_rural_delivery = True
            rd_surcharge = shipping_settings.rural_delivery_surcharge * total_boxes
            shipping_cost += rd_surcharge
            logger.info(f"Rural Delivery surcharge applied: ${rd_surcharge} ({total_boxes} boxes × ${shipping_settings.rural_delivery_surcharge})")
        else:
            self.is_rural_delivery = False

        self.shipping_cost = shipping_cost.quantize(Decimal('0.01'))

        logger.info(
            f"Quotation {self.id}: {total_boxes} boxes to {region} "
            f"= ${self.shipping_cost} (RD: {self.is_rural_delivery})"
        )

        return self.shipping_cost

    def calculate_totals(self):
        """
        Calculate and update all totals based on quotation items.
        Should be called after adding/removing/updating items.

        Calculation order:
        1. Subtotal (sum of line totals)
        2. Shipping (based on boxes and region)
        3. Discount (applied to subtotal only, not shipping)
        4. Tax (applied to subtotal + shipping - discount)
        5. Total (subtotal + shipping - discount + tax)
        """
        # 1. Calculate subtotal from all items
        self.subtotal = sum(
            item.line_total for item in self.items.all()
        )

        # 2. Calculate shipping cost
        shipping_cost = self.calculate_shipping_cost()

        # 3. Calculate discount (applied to subtotal only, not shipping)
        if self.discount_percentage:
            discount = (self.subtotal * self.discount_percentage / Decimal('100'))
        else:
            discount = self.discount_amount

        # 4. Calculate tax (on subtotal + shipping - discount)
        taxable_amount = self.subtotal + shipping_cost - discount
        self.tax_amount = (taxable_amount * self.tax_percentage / Decimal('100')).quantize(Decimal('0.01'))

        # 5. Calculate total
        self.total = (taxable_amount + self.tax_amount).quantize(Decimal('0.01'))

        self.save(update_fields=[
            'subtotal', 'shipping_cost', 'shipping_boxes', 'shipping_region',
            'is_rural_delivery', 'tax_amount', 'total', 'updated_at'
        ])

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

    def create_version_snapshot(self, description='', user=None, change_note=''):
        """
        Create a version snapshot of the current quotation state

        Args:
            description: Auto-generated description of the change
            user: User who made the change (defaults to created_by)
            change_note: User-provided note explaining the changes
        """
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

        # Calculate detailed changes if there's a previous version
        changes_detail = None
        previous_version = self.versions.order_by('-version_number').first()
        if previous_version and previous_version.snapshot_data:
            changes_detail = calculate_detailed_changes(
                previous_version.snapshot_data,
                snapshot_data
            )

        QuotationVersion.objects.create(
            quotation=self,
            version_number=self.version,
            snapshot_data=snapshot_data,
            changes_detail=changes_detail,
            created_by=user or self.created_by,
            change_description=description,
            change_note=change_note
        )

        # Increment version
        self.version += 1
        self.save(update_fields=['version', 'updated_at'])

    def get_version_history(self):
        """
        Get all version history for this quotation

        Returns:
            QuerySet: All QuotationVersion objects for this quotation, ordered by version_number descending
        """
        return self.versions.all().select_related('created_by')

    def create_edit_snapshot(self, user, change_note, description=''):
        """
        Create a version snapshot when editing a quotation with user-provided change note

        Args:
            user: User who made the edit
            change_note: User-provided note explaining the changes (required for edits)
            description: Auto-generated description of the change (optional)

        Raises:
            ValueError: If change_note is empty
        """
        if not change_note or not change_note.strip():
            raise ValueError('Change note is required when editing a quotation')

        # Auto-generate description if not provided
        if not description:
            description = f'Edited by {user.get_full_name()}'

        # Create the snapshot
        self.create_version_snapshot(
            description=description,
            user=user,
            change_note=change_note.strip()
        )

    def get_absolute_url(self):
        """Get absolute URL for quotation detail"""
        return reverse('quotations:quotation-detail', kwargs={'pk': self.pk})

    def get_all_email_recipients(self):
        """
        Get all email recipients for this quotation.

        Returns:
            list: List of email addresses including primary recipient and additional emails
        """
        recipients = []

        # Add primary recipient email (created_by user)
        if self.created_by and self.created_by.email:
            recipients.append(self.created_by.email)

        # Add additional emails if provided
        if self.additional_emails:
            additional = [email.strip() for email in self.additional_emails.split(';') if email.strip()]
            recipients.extend(additional)

        # Remove duplicates while preserving order
        seen = set()
        unique_recipients = []
        for email in recipients:
            if email.lower() not in seen:
                seen.add(email.lower())
                unique_recipients.append(email)

        return unique_recipients

    def submit_for_approval(self, submitted_by):
        """
        Submit quotation for account manager approval.

        Args:
            submitted_by: User instance who is submitting the quotation

        Raises:
            ValidationError: If quotation cannot be submitted
        """
        if self.status not in ['draft', 'pending']:
            raise ValidationError('Only draft or pending quotations can be submitted for approval')

        if self.submitted_for_approval_at:
            raise ValidationError('Quotation has already been submitted for approval')

        self.submitted_for_approval_at = timezone.now()
        self.submitted_by = submitted_by
        self.status = 'pending'
        self.save(update_fields=['submitted_for_approval_at', 'submitted_by', 'status', 'updated_at'])

    def customer_approve(self, approved_by):
        """
        Customer approval - First level of two-level approval system.

        Args:
            approved_by: User instance who is approving (customer or sales rep)

        Raises:
            ValidationError: If quotation cannot be approved by customer
        """
        if self.status not in ['draft', 'pending']:
            raise ValidationError('Only draft or pending quotations can be approved by customer')

        if self.customer_approved_at:
            raise ValidationError('Quotation has already been approved by customer')

        # Set customer approval fields
        self.customer_approved_at = timezone.now()
        self.customer_approved_by = approved_by
        self.status = 'pending'  # Status remains pending, awaiting account manager approval
        self.save(update_fields=['customer_approved_at', 'customer_approved_by', 'status', 'updated_at'])

        # Create version snapshot
        self.create_version_snapshot(
            description=f'Customer approved by {approved_by.get_full_name()}',
            user=approved_by,
            change_note='Customer approval granted'
        )

    def can_be_approved_by_customer(self, user):
        """
        Check if quotation can be approved by customer.

        Args:
            user: User instance to check permissions for

        Returns:
            bool: True if user can approve as customer
        """
        return (
            self.status in ['draft', 'pending'] and
            not self.customer_approved_at and
            (user.is_customer or user.is_sales_rep)
        )

    def needs_customer_approval(self):
        """
        Check if quotation is pending customer approval.

        Returns:
            bool: True if quotation needs customer approval
        """
        return (
            self.status in ['draft', 'pending'] and
            not self.customer_approved_at and
            not self.account_manager_approved_at
        )

    def needs_account_manager_approval(self):
        """
        Check if quotation is pending account manager approval.

        Returns:
            bool: True if quotation needs account manager approval
        """
        return (
            self.status == 'pending' and
            self.customer_approved_at and
            not self.account_manager_approved_at
        )

    def can_be_synced_to_cin7(self, during_approval=False):
        """
        Check if quotation is eligible for CIN7 sync.

        Business Rules:
        - All non-Bespoke items → Sync to CIN7
        - Mixed (Bespoke + non-Bespoke) → Sync non-Bespoke items to CIN7
        - All Bespoke items → Don't sync (goes to eWand)

        Args:
            during_approval: If True, skip checks for fields that will be set during approval.
                           This is used when validating sync eligibility before the approval transaction.

        Returns:
            bool: True if quotation has syncable items for CIN7, False otherwise
        """
        # Must not already be synced
        if self.cin7_sync_status == 'synced':
            return False

        if during_approval:
            # During approval flow: quotation is still 'pending' and account_manager_approved_at is not set yet
            # Only check if quotation has syncable items
            if self.status != 'pending':
                return False
        else:
            # Normal check: quotation must be approved and have account manager approval timestamp
            if not self.account_manager_approved_at:
                return False

            # Status must be approved or confirmed
            if self.status not in ['approved', 'confirmed']:
                return False

        # Check if quotation has any non-Bespoke items
        # This handles all three scenarios:
        # 1. All non-Bespoke → has_non_bespoke_items() = True → Sync
        # 2. Mixed → has_non_bespoke_items() = True → Sync non-Bespoke only
        # 3. All Bespoke → has_non_bespoke_items() = False → Don't sync
        return self.has_non_bespoke_items()

    def has_bespoke_items(self):
        """
        Check if quotation contains any Bespoke products.

        Returns:
            bool: True if quotation has Bespoke items, False otherwise
        """
        from django.contrib.contenttypes.models import ContentType

        # Get ContentType for BespokeProduct
        try:
            bespoke_ct = ContentType.objects.get(app_label='bespoke', model='bespokeproduct')
        except ContentType.DoesNotExist:
            return False

        # Check if any items reference BespokeProduct
        return self.items.filter(product_content_type=bespoke_ct).exists()

    def has_non_bespoke_items(self):
        """
        Check if quotation contains any non-Bespoke products.

        Non-Bespoke products include: Wholesale, Lotto, SAS, TUS, BallStore.
        These products are eligible for CIN7 sync.

        Returns:
            bool: True if quotation has at least one non-Bespoke item, False otherwise
        """
        from django.contrib.contenttypes.models import ContentType

        # Get ContentType for BespokeProduct
        try:
            bespoke_ct = ContentType.objects.get(app_label='bespoke', model='bespokeproduct')
        except ContentType.DoesNotExist:
            # If BespokeProduct model doesn't exist, all items are non-Bespoke
            return self.items.exists()

        # Check if any items are NOT BespokeProduct
        # Returns True if at least one non-Bespoke item exists
        return self.items.exclude(product_content_type=bespoke_ct).exists()

    def can_be_edited_by_account_manager(self, user):
        """
        Check if quotation can be edited by account manager.

        Args:
            user: User instance to check permissions for

        Returns:
            bool: True if user can edit this quotation as an account manager
        """
        return (
            self.status == 'pending' and
            (user.is_account_manager or user.is_admin)
        )


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
    # Supports: WholesaleProduct, LottoProduct, SASProduct, TUSProduct, BallStoreProduct
    product_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        limit_choices_to={
            'model__in': ['wholesaleproduct', 'lottoproduct', 'sasproduct', 'tusproduct', 'ballstoreproduct']
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

    # CIN7 Integration Fields
    cin7_product_option_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="CIN7 Product Option ID",
        help_text="CIN7 product option ID (variant ID) from API lookup"
    )
    cin7_match_method = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('barcode', 'Barcode Match'),
            ('sku', 'SKU Match'),
            ('database', 'Database Match'),
        ],
        verbose_name="CIN7 Match Method",
        help_text="Method used to match this item to CIN7 product option"
    )
    cin7_matched_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="CIN7 Matched At",
        help_text="Timestamp when CIN7 product option was matched"
    )

    # Addon-specific fields
    is_addon = models.BooleanField(
        default=False,
        help_text="Whether this item is an addon (customization) for a base garment"
    )
    parent_item = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='addons',
        help_text="Parent base garment item (if this is an addon)"
    )
    addon_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ('heat_transfer', 'Heat Transfer'),
            ('screen_print', 'Screen Print'),
            ('emb_applique', 'EMB/Applique'),
        ],
        help_text="Type of addon customization"
    )
    addon_details = models.JSONField(
        null=True,
        blank=True,
        help_text="Addon configuration details (size, colors, stitch complexity, etc.)"
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

        # Lookup CIN7 product option ID if not already set
        if not self.cin7_product_option_id and self.product:
            self._lookup_cin7_product_option()

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

    def get_addon_type_display_name(self):
        """Get display name for addon type"""
        if not self.is_addon or not self.addon_type:
            return None
        addon_map = {
            'heat_transfer': 'Heat Transfer',
            'screen_print': 'Screen Print',
            'emb_applique': 'EMB/Applique',
        }
        return addon_map.get(self.addon_type, self.addon_type.replace('_', ' ').title())

    def can_have_addons(self):
        """Check if this item type supports addons (only Bespoke products)"""
        if not self.product_content_type:
            return False
        model_name = self.product_content_type.model
        return model_name.lower() == 'bespokeproduct'

    def get_addons(self):
        """Get addon items for this base item (only for Bespoke products)"""
        if self.can_have_addons():
            return self.addons.filter(is_addon=True)
        return QuotationItem.objects.none()

    def _lookup_cin7_product_option(self):
        """
        Lookup and set CIN7 product option ID from API using product-type specific strategy.

        Product Type Mapping Strategy:
        - TUS Products: SKU → CIN7 Barcode
        - Bespoke Products: SKU → CIN7 Code
        - LOTTO Products: SKU → CIN7 Code
        - SAS Products: SKU → CIN7 Barcode
        - Unknown/Other: Try barcode first, then code

        Sets cin7_product_option_id, cin7_match_method, and cin7_matched_at if found.
        """
        from schools.services.cin7_api_service import Cin7ApiService
        import logging

        logger = logging.getLogger(__name__)

        try:
            api = Cin7ApiService()

            # Get product type
            product_type = self.product_content_type.model.lower() if self.product_content_type else None

            # Get SKU and barcode values
            sku = self._get_sku()
            barcode = self._get_barcode()

            logger.info(f"CIN7 lookup for '{self.product_name}' (type: {product_type}, SKU: {sku}, barcode: {barcode})")

            # Product-type specific lookup strategies
            if product_type == 'tusproduct':
                # TUS Products: SKU → CIN7 Barcode
                if sku:
                    logger.info(f"[TUS] Attempting barcode lookup with SKU value: {sku}")
                    option = api.lookup_product_option_by_barcode(sku)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode_from_sku'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[TUS] ✓ Matched to CIN7 option {option['id']} via barcode (from SKU)")
                        return

                # Fallback: Try actual barcode field
                if barcode:
                    logger.info(f"[TUS] Fallback: Attempting barcode lookup: {barcode}")
                    option = api.lookup_product_option_by_barcode(barcode)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[TUS] ✓ Matched to CIN7 option {option['id']} via barcode field")
                        return

            elif product_type in ['bespokeproduct', 'lottoproduct']:
                # Bespoke/LOTTO Products: SKU → CIN7 Code
                if sku:
                    logger.info(f"[{product_type.upper()}] Attempting code lookup with SKU: {sku}")
                    option = api.lookup_product_option_by_code(sku)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'code'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[{product_type.upper()}] ✓ Matched to CIN7 option {option['id']} via code")
                        return

                # Fallback: Try barcode if SKU lookup failed
                if barcode:
                    logger.info(f"[{product_type.upper()}] Fallback: Attempting barcode lookup: {barcode}")
                    option = api.lookup_product_option_by_barcode(barcode)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[{product_type.upper()}] ✓ Matched to CIN7 option {option['id']} via barcode")
                        return

            elif product_type == 'sasproduct':
                # SAS Products: SKU → CIN7 Barcode
                if sku:
                    logger.info(f"[SAS] Attempting barcode lookup with SKU value: {sku}")
                    option = api.lookup_product_option_by_barcode(sku)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode_from_sku'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[SAS] ✓ Matched to CIN7 option {option['id']} via barcode (from SKU)")
                        return

                # Fallback: Try actual barcode field
                if barcode:
                    logger.info(f"[SAS] Fallback: Attempting barcode lookup: {barcode}")
                    option = api.lookup_product_option_by_barcode(barcode)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[SAS] ✓ Matched to CIN7 option {option['id']} via barcode field")
                        return

            else:
                # Unknown product type: Try generic strategy
                logger.info(f"[UNKNOWN:{product_type}] Using generic lookup strategy")

                # Try barcode first
                if barcode:
                    logger.info(f"[UNKNOWN] Attempting barcode lookup: {barcode}")
                    option = api.lookup_product_option_by_barcode(barcode)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[UNKNOWN] ✓ Matched to CIN7 option {option['id']} via barcode")
                        return

                # Fallback to code lookup
                if sku:
                    logger.info(f"[UNKNOWN] Attempting code lookup with SKU: {sku}")
                    option = api.lookup_product_option_by_code(sku)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'code'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[UNKNOWN] ✓ Matched to CIN7 option {option['id']} via code")
                        return

                # Final fallback: Try SKU as barcode if numeric
                if sku and sku.replace('-', '').replace(' ', '').isdigit():
                    logger.info(f"[UNKNOWN] Final fallback: Attempting barcode with SKU: {sku}")
                    option = api.lookup_product_option_by_barcode(sku)
                    if option and 'id' in option:
                        self.cin7_product_option_id = option['id']
                        self.cin7_match_method = 'barcode_from_sku'
                        self.cin7_matched_at = timezone.now()
                        logger.info(f"[UNKNOWN] ✓ Matched to CIN7 option {option['id']} via barcode (from SKU)")
                        return

            logger.warning(f"✗ Could not find CIN7 product option for '{self.product_name}' (type: {product_type}, barcode: {barcode}, SKU: {sku})")

        except Exception as e:
            # Don't block quotation item creation if CIN7 lookup fails
            logger.error(f"✗ Error during CIN7 product option lookup for '{self.product_name}': {e}", exc_info=True)

    def _get_barcode(self):
        """Extract barcode from product"""
        if not self.product:
            return None

        # Try various barcode field names
        for field in ['barcode', 'cin7_barcode', 'product_barcode']:
            if hasattr(self.product, field):
                value = getattr(self.product, field)
                if value and str(value).strip():
                    return str(value).strip()

        return None

    def _get_sku(self):
        """Extract SKU from product or quotation item"""
        # First check quotation item's product_sku field
        if self.product_sku and self.product_sku.strip():
            return self.product_sku.strip()

        if not self.product:
            return None

        # Try various SKU field names
        for field in ['sku', 'cin7_sku', 'product_code', 'code']:
            if hasattr(self.product, field):
                value = getattr(self.product, field)
                if value and str(value).strip():
                    return str(value).strip()

        return None


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


def calculate_detailed_changes(old_snapshot, new_snapshot):
    """
    Calculate detailed changes between two quotation snapshots.

    Args:
        old_snapshot (dict): Previous version snapshot data
        new_snapshot (dict): Current version snapshot data

    Returns:
        dict: Detailed changes with items added/removed/modified and totals
    """
    changes = {
        'before_total': old_snapshot.get('total', '0.00'),
        'after_total': new_snapshot.get('total', '0.00'),
        'items_added': [],
        'items_removed': [],
        'items_modified': []
    }

    # Get item lists
    old_items = old_snapshot.get('items', [])
    new_items = new_snapshot.get('items', [])

    # Create dictionaries for easier comparison (using product_name as key)
    # Note: In a production system, you'd want a more robust identifier
    old_items_dict = {item['product_name']: item for item in old_items}
    new_items_dict = {item['product_name']: item for item in new_items}

    # Find added items (in new but not in old)
    for product_name, item in new_items_dict.items():
        if product_name not in old_items_dict:
            changes['items_added'].append({
                'product_name': item['product_name'],
                'quantity': item['quantity'],
                'price': item['unit_price'],
                'total': item['line_total']
            })

    # Find removed items (in old but not in new)
    for product_name, item in old_items_dict.items():
        if product_name not in new_items_dict:
            changes['items_removed'].append({
                'product_name': item['product_name'],
                'quantity': item['quantity'],
                'price': item['unit_price'],
                'total': item['line_total']
            })

    # Find modified items (in both but with different quantity or price)
    for product_name in old_items_dict.keys():
        if product_name in new_items_dict:
            old_item = old_items_dict[product_name]
            new_item = new_items_dict[product_name]

            # Check if quantity or price changed
            quantity_changed = old_item['quantity'] != new_item['quantity']
            price_changed = old_item['unit_price'] != new_item['unit_price']

            if quantity_changed or price_changed:
                changes['items_modified'].append({
                    'product_name': product_name,
                    'old_quantity': old_item['quantity'],
                    'new_quantity': new_item['quantity'],
                    'old_price': old_item['unit_price'],
                    'new_price': new_item['unit_price'],
                    'old_total': old_item['line_total'],
                    'new_total': new_item['line_total']
                })

    return changes


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
    changes_detail = models.JSONField(
        null=True,
        blank=True,
        help_text="Detailed changes including items added/removed/modified and pricing changes"
    )
    change_description = models.TextField(
        blank=True,
        help_text="Description of what changed in this version"
    )
    change_note = models.TextField(
        blank=True,
        help_text="User-provided note explaining the changes made in this version"
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


class CIN7OrderMapping(models.Model):
    """
    Track CIN7 sales orders created from quotations.
    Maps SASKITUP quotations to CIN7 sales orders for synchronization.
    """

    SYNC_STATUS_CHOICES = [
        ('pending', 'Pending Sync'),
        ('syncing', 'Syncing'),
        ('synced', 'Synced'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Quotation relationship (one-to-one)
    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.PROTECT,
        related_name='cin7_order',
        verbose_name="Quotation",
        help_text="Quotation that was synced to CIN7"
    )

    # CIN7 order details
    cin7_order_id = models.IntegerField(
        unique=True,
        verbose_name="CIN7 Order ID",
        help_text="CIN7 internal order ID"
    )
    cin7_reference = models.CharField(
        max_length=30,
        db_index=True,
        verbose_name="CIN7 Reference",
        help_text="CIN7 order reference number"
    )
    cin7_stage = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="CIN7 Stage",
        help_text="Current stage of the order in CIN7 (e.g., Draft, Confirmed, Dispatched)"
    )

    # Sync status tracking
    sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default='pending',
        db_index=True,
        verbose_name="Sync Status",
        help_text="Current synchronization status"
    )
    sync_attempts = models.PositiveIntegerField(
        default=0,
        verbose_name="Sync Attempts",
        help_text="Number of synchronization attempts"
    )
    last_sync_attempt = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Sync Attempt",
        help_text="Timestamp of last synchronization attempt"
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="Error Message",
        help_text="Error message if sync failed"
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At"
    )

    class Meta:
        db_table = 'cin7_order_mappings'
        verbose_name = 'CIN7 Order Mapping'
        verbose_name_plural = 'CIN7 Order Mappings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cin7_order_id']),
            models.Index(fields=['cin7_reference']),
            models.Index(fields=['sync_status', 'last_sync_attempt']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"CIN7 Order {self.cin7_reference} → {self.quotation.quotation_number} ({self.get_sync_status_display()})"

    def clean(self):
        """Validate mapping data"""
        super().clean()

        # Ensure quotation is eligible for CIN7 sync
        if self.quotation and not self.quotation.can_be_synced_to_cin7():
            raise ValidationError({
                'quotation': 'This quotation is not eligible for CIN7 synchronization'
            })

    def mark_sync_failed(self, error_message):
        """
        Mark sync as failed and increment attempt counter.

        Args:
            error_message (str): Error message describing the failure
        """
        self.sync_status = 'failed'
        self.error_message = error_message
        self.sync_attempts += 1
        self.save(update_fields=['sync_status', 'error_message', 'sync_attempts', 'updated_at'])

    def mark_sync_success(self, cin7_stage=None):
        """
        Mark sync as successful.

        Args:
            cin7_stage (str, optional): Current stage in CIN7
        """
        self.sync_status = 'synced'
        self.error_message = ''
        if cin7_stage:
            self.cin7_stage = cin7_stage
        self.save(update_fields=['sync_status', 'error_message', 'cin7_stage', 'updated_at'])

    def can_retry_sync(self, max_attempts=5):
        """
        Check if sync can be retried.

        Args:
            max_attempts (int): Maximum number of sync attempts allowed

        Returns:
            bool: True if sync can be retried, False otherwise
        """
        return self.sync_status == 'failed' and self.sync_attempts < max_attempts


# Import shipping settings model
from .models_shipping import ShippingSettings
