import uuid
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Supports Admin, Sales Rep, Account Manager, and Customer user types
    Uses email as the primary login identifier
    """
    USER_TYPE_CHOICES = [
        ('admin', 'Admin'),
        ('sales_rep', 'Sales Representative'),
        ('account_manager', 'Account Manager'),
        ('customer', 'Customer'),
    ]

    # Override email field to make it unique and required
    email = models.EmailField(
        unique=True,
        help_text="Email address - used for login"
    )

    # Custom fields
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='sales_rep',
        help_text="User type determines access level and permissions"
    )

    # Profile information
    phone = models.CharField(max_length=20, blank=True, help_text="Contact phone number")
    department = models.CharField(max_length=100, blank=True, help_text="Department or team")
    hire_date = models.DateField(null=True, blank=True, help_text="Date hired")
    employee_id = models.CharField(max_length=50, blank=True, unique=True, null=True, help_text="Employee ID")

    # Status fields
    is_active_sales_rep = models.BooleanField(
        default=True,
        help_text="Whether this sales rep is actively working assignments"
    )
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'authentication_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['user_type', 'is_active']),
            models.Index(fields=['employee_id']),
            models.Index(fields=['is_active_sales_rep']),
        ]

    def __str__(self):
        if self.get_full_name():
            return f"{self.get_full_name()} ({self.get_user_type_display()})"
        return f"{self.username} ({self.get_user_type_display()})"

    def clean(self):
        """Validate user data"""
        super().clean()

        # Ensure email is provided
        if not self.email:
            raise ValidationError({
                'email': 'Email address is required'
            })

        # Normalize email to lowercase for case-insensitive matching
        if self.email:
            self.email = self.email.lower()

        # Check for duplicate emails (case-insensitive)
        if self.email:
            existing_user = User.objects.filter(
                email__iexact=self.email
            ).exclude(pk=self.pk).first()

            if existing_user:
                raise ValidationError({
                    'email': 'A user with this email address already exists'
                })

    def save(self, *args, **kwargs):
        # Only run full_clean if not creating a new user or if password is already set
        # This allows set_password() to work properly after user creation
        if self.pk or self.password:
            self.full_clean()
        else:
            # For new users without password, only validate custom fields
            self.clean()
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        """Check if user is admin"""
        return self.user_type == 'admin'

    @property
    def is_sales_rep(self):
        """Check if user is sales representative"""
        return self.user_type == 'sales_rep'

    @property
    def is_customer(self):
        """Check if user is customer"""
        return self.user_type == 'customer'

    @property
    def is_account_manager(self):
        """Check if user is account manager"""
        return self.user_type == 'account_manager'

    @property
    def can_access_admin_panel(self):
        """Check if user can access admin panel"""
        return self.is_admin and self.is_superuser

    @property
    def assigned_schools_count(self):
        """Get count of assigned schools"""
        if self.is_sales_rep or self.is_account_manager:
            return self.school_assignments.filter(is_active=True).count()
        return 0

    @property
    def assigned_clubs_count(self):
        """Get count of assigned clubs"""
        if self.is_sales_rep or self.is_account_manager:
            return self.club_assignments.filter(is_active=True).count()
        return 0

    @property
    def total_assignments(self):
        """Get total count of all assignments"""
        return self.assigned_schools_count + self.assigned_clubs_count

    def get_assigned_schools(self):
        """
        Get all assigned schools for this sales rep or account manager
        Account managers have access to ALL schools
        """
        from schools.models import School, WholesaleSchool

        # Account managers have access to all schools
        if self.is_account_manager:
            regular_schools = School.objects.filter(is_active=True)
            wholesale_schools = WholesaleSchool.objects.filter(is_active=True)
            return {
                'regular': regular_schools,
                'wholesale': wholesale_schools,
                'total_count': regular_schools.count() + wholesale_schools.count()
            }

        # Sales reps only get their assigned schools
        if self.is_sales_rep:
            school_assignments = self.school_assignments.filter(is_active=True)

            # Get both regular and wholesale schools
            regular_school_ids = school_assignments.filter(
                school__isnull=False
            ).values_list('school_id', flat=True)

            wholesale_school_ids = school_assignments.filter(
                wholesale_school__isnull=False
            ).values_list('wholesale_school_id', flat=True)

            regular_schools = School.objects.filter(id__in=regular_school_ids)
            wholesale_schools = WholesaleSchool.objects.filter(id__in=wholesale_school_ids)

            return {
                'regular': regular_schools,
                'wholesale': wholesale_schools,
                'total_count': len(regular_school_ids) + len(wholesale_school_ids)
            }
        return {'regular': [], 'wholesale': [], 'total_count': 0}

    def get_assigned_clubs(self):
        """
        Get all assigned clubs for this sales rep or account manager
        Account managers have access to ALL clubs

        TODO: Update to use GenericForeignKey or return separate LottoClub/SASClub querysets
        The unified Club model has been removed. This method needs to be updated
        to handle LottoClub (from clubs.models_lotto) and SASClub (from clubs.models_sas).
        Consider returning a dict with separate querysets for each club type.
        """
        # Account managers have access to all clubs
        if self.is_account_manager:
            # TODO: Uncomment and update when club models are properly integrated
            # from clubs.models_lotto import LottoClub
            # from clubs.models_sas import SASClub
            # return {
            #     'lotto': LottoClub.objects.filter(is_active=True),
            #     'sas': SASClub.objects.filter(is_active=True),
            #     'total_count': LottoClub.objects.filter(is_active=True).count() +
            #                    SASClub.objects.filter(is_active=True).count()
            # }
            return None  # Return None until club models are properly integrated

        if self.is_sales_rep:
            # DISABLED - unified Club model removed
            # from clubs.models import Club
            # club_assignments = self.club_assignments.filter(is_active=True)
            # club_ids = club_assignments.values_list('club_id', flat=True)
            # return Club.objects.filter(id__in=club_ids)

            # For now, return empty querysets until updated
            # from clubs.models_lotto import LottoClub
            # from clubs.models_sas import SASClub
            # return {
            #     'lotto': LottoClub.objects.none(),
            #     'sas': SASClub.objects.none(),
            #     'total_count': 0
            # }
            return None  # Return None to indicate this method needs updating
        return None

    def can_access_school(self, school):
        """
        Check if user can access a specific school
        Account managers have access to ALL schools
        """
        if self.is_admin:
            return True

        # Account managers have access to all schools
        if self.is_account_manager:
            return True

        if self.is_sales_rep:
            return self.school_assignments.filter(
                models.Q(school=school) | models.Q(wholesale_school=school),
                is_active=True
            ).exists()

        return False

    def can_access_club(self, club):
        """
        Check if user can access a specific club
        Account managers have access to ALL clubs
        """
        if self.is_admin:
            return True

        # Account managers have access to all clubs
        if self.is_account_manager:
            return True

        if self.is_sales_rep:
            return self.club_assignments.filter(club=club, is_active=True).exists()

        return False

    def get_absolute_url(self):
        """Get absolute URL for user profile"""
        return reverse('authentication:user-detail', kwargs={'pk': self.pk})


class SalesRepSchoolAssignment(models.Model):
    """
    Model for assigning sales representatives and account managers to schools
    Supports both regular schools and wholesale schools
    Each school can only have one active sales rep/account manager

    Note: Despite the name, this model also supports account_manager assignments
    """
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships - supports both sales_rep and account_manager user types
    sales_rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='school_assignments',
        limit_choices_to={'user_type__in': ['sales_rep', 'account_manager']},
        help_text="Sales representative or account manager assigned to this school"
    )

    # School relationships (one of these should be set, not both)
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        related_name='sales_rep_assignments',
        null=True,
        blank=True,
        help_text="Regular school assignment"
    )

    wholesale_school = models.ForeignKey(
        'schools.WholesaleSchool',
        on_delete=models.CASCADE,
        related_name='sales_rep_assignments',
        null=True,
        blank=True,
        help_text="Wholesale school assignment"
    )

    # Assignment details
    is_active = models.BooleanField(default=True, help_text="Whether this assignment is currently active")
    assigned_date = models.DateTimeField(default=timezone.now, help_text="When assignment was made")
    notes = models.TextField(blank=True, help_text="Notes about this assignment")

    # Territory information
    territory_name = models.CharField(max_length=100, blank=True, help_text="Territory or region name")
    priority_level = models.CharField(
        max_length=20,
        choices=[
            ('high', 'High Priority'),
            ('medium', 'Medium Priority'),
            ('low', 'Low Priority'),
        ],
        default='medium',
        help_text="Priority level for this assignment"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_school_assignments',
        help_text="User who created this assignment"
    )

    class Meta:
        db_table = 'sales_rep_school_assignments'
        verbose_name = 'Sales Rep School Assignment'
        verbose_name_plural = 'Sales Rep School Assignments'
        ordering = ['-assigned_date']
        indexes = [
            models.Index(fields=['sales_rep', 'is_active']),
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['wholesale_school', 'is_active']),
            models.Index(fields=['assigned_date']),
            models.Index(fields=['territory_name']),
        ]
        constraints = [
            # Ensure each regular school has only one active assignment
            models.UniqueConstraint(
                fields=['school'],
                condition=models.Q(is_active=True, school__isnull=False),
                name='unique_active_school_assignment'
            ),
            # Ensure each wholesale school has only one active assignment
            models.UniqueConstraint(
                fields=['wholesale_school'],
                condition=models.Q(is_active=True, wholesale_school__isnull=False),
                name='unique_active_wholesale_school_assignment'
            ),
        ]

    def clean(self):
        """Validate assignment data"""
        super().clean()

        # Ensure exactly one school type is assigned
        if self.school and self.wholesale_school:
            raise ValidationError(
                "Assignment cannot have both regular school and wholesale school. Choose one."
            )

        if not self.school and not self.wholesale_school:
            raise ValidationError(
                "Assignment must have either a regular school or wholesale school."
            )

        # Ensure sales rep is actually a sales rep or account manager
        if self.sales_rep and not (self.sales_rep.is_sales_rep or self.sales_rep.is_account_manager):
            raise ValidationError({
                'sales_rep': 'Only sales representatives or account managers can be assigned to schools'
            })

        # Check for existing active assignments
        if self.is_active:
            existing_assignments = SalesRepSchoolAssignment.objects.filter(
                is_active=True
            ).exclude(pk=self.pk)

            if self.school:
                if existing_assignments.filter(school=self.school).exists():
                    raise ValidationError({
                        'school': 'This school already has an active sales representative assigned'
                    })

            if self.wholesale_school:
                if existing_assignments.filter(wholesale_school=self.wholesale_school).exists():
                    raise ValidationError({
                        'wholesale_school': 'This wholesale school already has an active sales representative assigned'
                    })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        school_name = self.school.org_name if self.school else self.wholesale_school.name
        status = "Active" if self.is_active else "Inactive"
        return f"{self.sales_rep.get_full_name()} → {school_name} ({status})"

    @property
    def assigned_school(self):
        """Get the assigned school (regular or wholesale)"""
        return self.school or self.wholesale_school

    @property
    def school_type(self):
        """Get the type of school assigned"""
        if self.school:
            return 'regular'
        elif self.wholesale_school:
            return 'wholesale'
        return None

    @property
    def school_name(self):
        """Get the name of the assigned school"""
        if self.school:
            return self.school.org_name
        elif self.wholesale_school:
            return self.wholesale_school.name
        return "No school assigned"

    def deactivate(self, deactivated_by=None):
        """Deactivate this assignment"""
        self.is_active = False
        if deactivated_by:
            self.notes = f"{self.notes}\nDeactivated by {deactivated_by.get_full_name()} on {timezone.now()}"
        self.save(update_fields=['is_active', 'notes', 'updated_at'])

    def get_absolute_url(self):
        """Get absolute URL for assignment detail"""
        return reverse('authentication:school-assignment-detail', kwargs={'pk': self.pk})


class SalesRepClubAssignment(models.Model):
    """
    Model for assigning sales representatives and account managers to clubs
    Each club can only have one active sales rep/account manager

    Note: Despite the name, this model also supports account_manager assignments
    """
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships - supports both sales_rep and account_manager user types
    sales_rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='club_assignments',
        limit_choices_to={'user_type__in': ['sales_rep', 'account_manager']},
        help_text="Sales representative or account manager assigned to this club"
    )

    # Generic relationship to support both LottoClub and SASClub
    club_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={'model__in': ['lottoclub', 'sasclub']},
        null=True,
        blank=True
    )
    club_object_id = models.PositiveIntegerField(null=True, blank=True)
    club = GenericForeignKey('club_content_type', 'club_object_id')

    # Assignment details
    is_active = models.BooleanField(default=True, help_text="Whether this assignment is currently active")
    assigned_date = models.DateTimeField(default=timezone.now, help_text="When assignment was made")
    notes = models.TextField(blank=True, help_text="Notes about this assignment")

    # Territory information
    territory_name = models.CharField(max_length=100, blank=True, help_text="Territory or region name")
    priority_level = models.CharField(
        max_length=20,
        choices=[
            ('high', 'High Priority'),
            ('medium', 'Medium Priority'),
            ('low', 'Low Priority'),
        ],
        default='medium',
        help_text="Priority level for this assignment"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_club_assignments',
        help_text="User who created this assignment"
    )

    class Meta:
        db_table = 'sales_rep_club_assignments'
        verbose_name = 'Sales Rep Club Assignment'
        verbose_name_plural = 'Sales Rep Club Assignments'
        ordering = ['-assigned_date']
        indexes = [
            # Temporarily commented out to fix server startup
            # models.Index(fields=['sales_rep', 'is_active']),
            # models.Index(fields=['club_content_type', 'club_object_id']),
            # models.Index(fields=['assigned_date']),
            # models.Index(fields=['territory_name']),
        ]
        constraints = [
            # Temporarily commented out to fix server startup
            # Ensure each club has only one active assignment
            # models.UniqueConstraint(
            #     fields=['club_content_type', 'club_object_id'],
            #     condition=models.Q(is_active=True),
            #     name='unique_active_club_assignment'
            # ),
        ]

    def clean(self):
        """Validate assignment data"""
        super().clean()

        # Ensure sales rep is actually a sales rep or account manager
        if self.sales_rep and not (self.sales_rep.is_sales_rep or self.sales_rep.is_account_manager):
            raise ValidationError({
                'sales_rep': 'Only sales representatives or account managers can be assigned to clubs'
            })

        # Check for existing active assignments
        if self.is_active and self.club_content_type and self.club_object_id:
            existing_assignment = SalesRepClubAssignment.objects.filter(
                club_content_type=self.club_content_type,
                club_object_id=self.club_object_id,
                is_active=True
            ).exclude(pk=self.pk).first()

            if existing_assignment:
                raise ValidationError({
                    'club': 'This club already has an active sales representative assigned'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.sales_rep.get_full_name()} → {self.club.name} ({status})"

    def deactivate(self, deactivated_by=None):
        """Deactivate this assignment"""
        self.is_active = False
        if deactivated_by:
            self.notes = f"{self.notes}\nDeactivated by {deactivated_by.get_full_name()} on {timezone.now()}"
        self.save(update_fields=['is_active', 'notes', 'updated_at'])

    def get_absolute_url(self):
        """Get absolute URL for assignment detail"""
        return reverse('authentication:club-assignment-detail', kwargs={'pk': self.pk})


class UserSession(models.Model):
    """
    Model to track user sessions for security and audit purposes
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_sessions'
        verbose_name = 'User Session'
        verbose_name_plural = 'User Sessions'
        ordering = ['-login_time']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_key']),
            models.Index(fields=['last_activity']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.ip_address} ({self.login_time})"


class AuditLog(models.Model):
    """
    Model to log important user actions for security and compliance
    """
    ACTION_TYPES = [
        # Authentication & User Management
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('password_change', 'Password Change'),
        ('assignment_created', 'Assignment Created'),
        ('assignment_updated', 'Assignment Updated'),
        ('assignment_deleted', 'Assignment Deleted'),
        ('user_created', 'User Created'),
        ('user_updated', 'User Updated'),
        ('user_deactivated', 'User Deactivated'),
        ('permission_granted', 'Permission Granted'),
        ('permission_revoked', 'Permission Revoked'),
        ('data_access', 'Data Access'),
        ('admin_action', 'Admin Action'),

        # Schools Operations
        ('school_viewed', 'School Viewed'),
        ('school_searched', 'School Search'),
        ('school_list_viewed', 'School List Viewed'),
        ('school_detail_viewed', 'School Detail Viewed'),
        ('school_data_accessed', 'School Data Access'),

        # Wholesale Schools Operations
        ('wholesale_school_viewed', 'Wholesale School Viewed'),
        ('wholesale_school_searched', 'Wholesale School Search'),
        ('wholesale_school_created', 'Wholesale School Created'),
        ('wholesale_school_updated', 'Wholesale School Updated'),
        ('wholesale_school_deleted', 'Wholesale School Deleted'),
        ('wholesale_category_viewed', 'Wholesale Category Viewed'),
        ('wholesale_category_created', 'Wholesale Category Created'),
        ('wholesale_category_updated', 'Wholesale Category Updated'),
        ('wholesale_product_viewed', 'Wholesale Product Viewed'),
        ('wholesale_product_created', 'Wholesale Product Created'),
        ('wholesale_product_updated', 'Wholesale Product Updated'),
        ('wholesale_product_deleted', 'Wholesale Product Deleted'),
        ('wholesale_variation_created', 'Wholesale Variation Created'),
        ('wholesale_variation_updated', 'Wholesale Variation Updated'),

        # Wholesale Price Operations
        ('wholesale_price_preview', 'Wholesale Price Preview'),
        ('wholesale_price_update', 'Wholesale Price Update'),
        ('wholesale_price_bulk_update', 'Wholesale Price Bulk Update'),
        ('wholesale_price_settings_accessed', 'Wholesale Price Settings Accessed'),

        # Sync Operations
        ('wholesale_sync_started', 'Wholesale Sync Started'),
        ('wholesale_sync_completed', 'Wholesale Sync Completed'),
        ('wholesale_sync_failed', 'Wholesale Sync Failed'),
        ('tus_sync_started', 'TUS Sync Started'),
        ('tus_sync_completed', 'TUS Sync Completed'),
        ('tus_sync_failed', 'TUS Sync Failed'),
        ('sync_job_created', 'Sync Job Created'),
        ('sync_job_updated', 'Sync Job Updated'),
        ('sync_job_cancelled', 'Sync Job Cancelled'),

        # CSV Import/Export Operations
        ('csv_upload_started', 'CSV Upload Started'),
        ('csv_upload_completed', 'CSV Upload Completed'),
        ('csv_upload_failed', 'CSV Upload Failed'),
        ('csv_import_started', 'CSV Import Started'),
        ('csv_import_completed', 'CSV Import Completed'),
        ('csv_import_failed', 'CSV Import Failed'),
        ('data_export_requested', 'Data Export Requested'),
        ('data_export_completed', 'Data Export Completed'),

        # TUS Retail Operations
        ('tus_location_viewed', 'TUS Location Viewed'),
        ('tus_school_viewed', 'TUS School Viewed'),
        ('tus_category_viewed', 'TUS Category Viewed'),
        ('tus_product_viewed', 'TUS Product Viewed'),
        ('tus_search_performed', 'TUS Search Performed'),
        ('tus_variation_checked', 'TUS Variation Checked'),

        # Clubs Operations
        ('club_viewed', 'Club Viewed'),
        ('club_searched', 'Club Search'),
        ('club_list_viewed', 'Club List Viewed'),
        ('club_detail_viewed', 'Club Detail Viewed'),
        ('club_data_accessed', 'Club Data Access'),
        ('club_created', 'Club Created'),
        ('club_updated', 'Club Updated'),
        ('club_deleted', 'Club Deleted'),

        # Club Category Operations
        ('club_category_viewed', 'Club Category Viewed'),
        ('club_category_created', 'Club Category Created'),
        ('club_category_updated', 'Club Category Updated'),
        ('club_category_deleted', 'Club Category Deleted'),
        ('club_category_list_viewed', 'Club Category List Viewed'),

        # Club Product Operations
        ('club_product_viewed', 'Club Product Viewed'),
        ('club_product_created', 'Club Product Created'),
        ('club_product_updated', 'Club Product Updated'),
        ('club_product_deleted', 'Club Product Deleted'),
        ('club_product_searched', 'Club Product Search'),
        ('club_product_variation_viewed', 'Club Product Variation Viewed'),
        ('club_product_variation_created', 'Club Product Variation Created'),
        ('club_product_variation_updated', 'Club Product Variation Updated'),
        ('club_product_variation_deleted', 'Club Product Variation Deleted'),

        # Club Category Assignment Operations
        ('club_product_category_assigned', 'Club Product Category Assigned'),
        ('club_product_category_unassigned', 'Club Product Category Unassigned'),
        ('club_product_category_primary_changed', 'Club Product Category Primary Changed'),

        # LOTTO Club Operations
        ('lotto_club_viewed', 'LOTTO Club Viewed'),
        ('lotto_club_searched', 'LOTTO Club Search'),
        ('lotto_product_viewed', 'LOTTO Product Viewed'),
        ('lotto_category_viewed', 'LOTTO Category Viewed'),
        ('lotto_variation_checked', 'LOTTO Variation Checked'),

        # SAS Club Operations
        ('sas_club_viewed', 'SAS Club Viewed'),
        ('sas_club_searched', 'SAS Club Search'),
        ('sas_sport_viewed', 'SAS Sport Viewed'),
        ('sas_product_viewed', 'SAS Product Viewed'),
        ('sas_variation_checked', 'SAS Variation Checked'),

        # Club Sync Operations
        ('club_sync_started', 'Club Sync Started'),
        ('club_sync_completed', 'Club Sync Completed'),
        ('club_sync_failed', 'Club Sync Failed'),
        ('lotto_sync_started', 'LOTTO Sync Started'),
        ('lotto_sync_completed', 'LOTTO Sync Completed'),
        ('lotto_sync_failed', 'LOTTO Sync Failed'),
        ('sas_sync_started', 'SAS Sync Started'),
        ('sas_sync_completed', 'SAS Sync Completed'),
        ('sas_sync_failed', 'SAS Sync Failed'),
        ('club_sync_job_created', 'Club Sync Job Created'),
        ('club_sync_job_updated', 'Club Sync Job Updated'),
        ('club_sync_job_cancelled', 'Club Sync Job Cancelled'),

        # Club Bulk Operations
        ('club_bulk_update', 'Club Bulk Update'),
        ('club_product_bulk_update', 'Club Product Bulk Update'),
        ('club_category_bulk_update', 'Club Category Bulk Update'),
        ('club_bulk_delete', 'Club Bulk Delete'),
        ('club_product_bulk_delete', 'Club Product Bulk Delete'),

        # Club Stock Operations
        ('club_stock_updated', 'Club Stock Updated'),
        ('club_stock_status_changed', 'Club Stock Status Changed'),
        ('club_variation_stock_updated', 'Club Variation Stock Updated'),

        # Club Image Operations
        ('club_image_uploaded', 'Club Image Uploaded'),
        ('club_product_image_uploaded', 'Club Product Image Uploaded'),
        ('club_variation_image_uploaded', 'Club Variation Image Uploaded'),
        ('club_image_proxy_accessed', 'Club Image Proxy Accessed'),
    ]

    # Primary identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # User and action details
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField(help_text="Detailed description of the action")

    # Context information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)

    # Additional data
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional action metadata")
    affected_model = models.CharField(max_length=100, blank=True, help_text="Model that was affected")
    affected_object_id = models.CharField(max_length=100, blank=True, help_text="ID of affected object")

    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['affected_model', 'affected_object_id']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else "System"
        return f"{user_name} - {self.get_action_type_display()} ({self.timestamp})"

    @classmethod
    def log_action(cls, user, action_type, description, request=None, **metadata):
        """
        Helper method to create audit log entries

        Args:
            user: User instance or None for system actions
            action_type: Action type from ACTION_TYPES
            description: Human-readable description
            request: Django request object (optional)
            **metadata: Additional metadata to store
        """
        audit_data = {
            'user': user,
            'action_type': action_type,
            'description': description,
            'metadata': metadata,
        }

        if request:
            session_key = ''
            if hasattr(request, 'session') and request.session:
                try:
                    session_key = request.session.session_key or ''
                except:
                    session_key = ''

            audit_data.update({
                'ip_address': cls._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'session_key': session_key,
            })

        return cls.objects.create(**audit_data)

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
