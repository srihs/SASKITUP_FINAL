from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import date
from schools.models import School


class Store(models.Model):
    """Model representing a physical store location for The Uniform Shoppe."""

    name = models.CharField(
        max_length=200,
        help_text="Store name (e.g., 'Botany Store', 'Chartwell Store')"
    )

    # Contact Information
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        help_text="Contact phone number"
    )
    email = models.EmailField(
        blank=True,
        help_text="Store email address"
    )

    # Address Information
    address_line1 = models.CharField(
        max_length=255,
        help_text="Street address"
    )
    address_line2 = models.CharField(
        max_length=255,
        blank=True,
        help_text="Additional address information (optional)"
    )
    suburb = models.CharField(
        max_length=100,
        help_text="Suburb"
    )
    city = models.CharField(
        max_length=100,
        help_text="City"
    )
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Postal code"
    )

    # Location coordinates for mapping
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude coordinate"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude coordinate"
    )

    # Schools served by this store
    schools = models.ManyToManyField(
        School,
        related_name='stores',
        blank=True,
        help_text="Schools serviced by this store"
    )

    # Additional information
    description = models.TextField(
        blank=True,
        help_text="Additional store information or notes"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Is this store currently active?"
    )

    # Display order
    display_order = models.IntegerField(
        default=0,
        help_text="Order in which stores should be displayed (lower numbers first)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'Store'
        verbose_name_plural = 'Stores'

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        """Return the complete formatted address."""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.suburb}, {self.city}")
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)

    @property
    def has_location(self):
        """Check if the store has GPS coordinates."""
        return self.latitude is not None and self.longitude is not None

    def get_current_period(self):
        """Get the currently active period for this store, if any."""
        today = date.today()
        # Get periods that include this store
        return self.periods.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today
        ).order_by('-priority').first()

    def get_current_opening_hours(self):
        """Get all opening hours for the current week based on active period, or default hours."""
        current_period = self.get_current_period()

        if current_period:
            # Get hours for the current period
            period_hours = self.opening_hours.filter(period=current_period).order_by('day_of_week')
            if period_hours.exists():
                return period_hours

        # Fall back to default hours (period is null)
        return self.opening_hours.filter(period__isnull=True).order_by('day_of_week')

    def get_opening_hours_for_period(self, period=None):
        """Get all opening hours for a specific period or default hours."""
        if period:
            return self.opening_hours.filter(period=period).order_by('day_of_week')
        else:
            return self.opening_hours.filter(period__isnull=True).order_by('day_of_week')


class StorePeriod(models.Model):
    """Model representing a period with specific opening hours (e.g., term time, holidays)."""

    PERIOD_TYPES = [
        ('term', 'Term Time'),
        ('holiday', 'School Holidays'),
        ('christmas', 'Christmas Period'),
        ('easter', 'Easter Period'),
        ('special', 'Special Event'),
        ('other', 'Other'),
    ]

    stores = models.ManyToManyField(
        Store,
        related_name='periods',
        help_text="Stores this period applies to"
    )

    name = models.CharField(
        max_length=200,
        help_text="Period name (e.g., 'Term 1 2024', 'Christmas 2024')"
    )

    period_type = models.CharField(
        max_length=20,
        choices=PERIOD_TYPES,
        default='other',
        help_text="Type of period"
    )

    start_date = models.DateField(
        help_text="Period start date"
    )

    end_date = models.DateField(
        help_text="Period end date"
    )

    priority = models.IntegerField(
        default=0,
        help_text="Priority for overlapping periods (higher number = higher priority)"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Is this period active? (can be disabled without deleting)"
    )

    description = models.TextField(
        blank=True,
        help_text="Description or notes about this period"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'start_date']
        verbose_name = 'Store Period'
        verbose_name_plural = 'Store Periods'
        indexes = [
            models.Index(fields=['start_date', 'end_date', 'is_active']),
        ]

    def __str__(self):
        store_names = ", ".join([store.name for store in self.stores.all()[:3]])
        if self.stores.count() > 3:
            store_names += f" (+{self.stores.count() - 3} more)"
        return f"{self.name} ({self.start_date} to {self.end_date})" + (f" - {store_names}" if store_names else "")

    def is_currently_active(self):
        """Check if this period is currently active (today falls within the date range)."""
        if not self.is_active:
            return False
        today = date.today()
        return self.start_date <= today <= self.end_date

    def clean(self):
        """Validate that end_date is after start_date."""
        from django.core.exceptions import ValidationError
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})

    @property
    def duration_days(self):
        """Calculate the number of days in this period."""
        return (self.end_date - self.start_date).days + 1

    @property
    def is_past(self):
        """Check if this period has ended."""
        return date.today() > self.end_date

    @property
    def is_future(self):
        """Check if this period hasn't started yet."""
        return date.today() < self.start_date


class StoreOpeningHours(models.Model):
    """Model representing opening hours for a store."""

    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='opening_hours',
        help_text="Store these hours apply to"
    )

    period = models.ForeignKey(
        StorePeriod,
        on_delete=models.CASCADE,
        related_name='opening_hours',
        null=True,
        blank=True,
        help_text="Period these hours apply to (null = default/regular hours)"
    )

    day_of_week = models.IntegerField(
        choices=DAYS_OF_WEEK,
        help_text="Day of the week"
    )

    opening_time = models.TimeField(
        help_text="Opening time (e.g., 09:00)"
    )

    closing_time = models.TimeField(
        help_text="Closing time (e.g., 17:00)"
    )

    is_closed = models.BooleanField(
        default=False,
        help_text="Is the store closed on this day?"
    )

    # Special notes for this day (e.g., "Appointment only")
    notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Special notes for this day (optional)"
    )

    class Meta:
        ordering = ['store', 'period', 'day_of_week']
        verbose_name = 'Store Opening Hours'
        verbose_name_plural = 'Store Opening Hours'
        unique_together = ['store', 'period', 'day_of_week']
        indexes = [
            models.Index(fields=['store', 'period', 'day_of_week']),
        ]

    def __str__(self):
        day_name = dict(self.DAYS_OF_WEEK)[self.day_of_week]
        period_name = f" ({self.period.name})" if self.period else " (Default)"
        if self.is_closed:
            return f"{self.store.name}{period_name} - {day_name}: Closed"
        return f"{self.store.name}{period_name} - {day_name}: {self.opening_time.strftime('%H:%M')} - {self.closing_time.strftime('%H:%M')}"

    @property
    def formatted_hours(self):
        """Return formatted opening hours string."""
        if self.is_closed:
            return "Closed"
        return f"{self.opening_time.strftime('%I:%M %p')} - {self.closing_time.strftime('%I:%M %p')}"
