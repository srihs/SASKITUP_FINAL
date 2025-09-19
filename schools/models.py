from django.db import models
from django.urls import reverse
from django.utils import timezone


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
