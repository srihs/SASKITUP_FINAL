import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Supports Admin, Sales Rep, and Customer user types
    """
    USER_TYPE_CHOICES = [
        ('admin', 'Admin'),
        ('sales_rep', 'Sales Representative'),
        ('customer', 'Customer'),
    ]

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

        # Sales reps should have employee_id
        if self.user_type == 'sales_rep' and not self.employee_id:
            raise ValidationError({
                'employee_id': 'Sales representatives must have an employee ID'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
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
    def can_access_admin_panel(self):
        """Check if user can access admin panel"""
        return self.is_admin and self.is_superuser

    @property
    def assigned_schools_count(self):
        """Get count of assigned schools"""
        if self.is_sales_rep:
            return self.school_assignments.filter(is_active=True).count()
        return 0

    @property
    def assigned_clubs_count(self):
        """Get count of assigned clubs"""
        if self.is_sales_rep:
            return self.club_assignments.filter(is_active=True).count()
        return 0

    @property
    def total_assignments(self):
        """Get total count of all assignments"""
        return self.assigned_schools_count + self.assigned_clubs_count

    def get_assigned_schools(self):
        """Get all assigned schools for this sales rep"""
        if self.is_sales_rep:
            from schools.models import School, WholesaleSchool
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
        """Get all assigned clubs for this sales rep"""
        if self.is_sales_rep:
            from clubs.models import Club
            club_assignments = self.club_assignments.filter(is_active=True)
            club_ids = club_assignments.values_list('club_id', flat=True)
            return Club.objects.filter(id__in=club_ids)
        return Club.objects.none()

    def can_access_school(self, school):
        """Check if sales rep can access a specific school"""
        if self.is_admin:
            return True

        if self.is_sales_rep:
            return self.school_assignments.filter(
                models.Q(school=school) | models.Q(wholesale_school=school),
                is_active=True
            ).exists()

        return False

    def can_access_club(self, club):
        """Check if sales rep can access a specific club"""
        if self.is_admin:
            return True

        if self.is_sales_rep:
            return self.club_assignments.filter(club=club, is_active=True).exists()

        return False

    def get_absolute_url(self):
        """Get absolute URL for user profile"""
        return reverse('authentication:user-detail', kwargs={'pk': self.pk})


class SalesRepSchoolAssignment(models.Model):
    """
    Model for assigning sales representatives to schools
    Supports both regular schools and wholesale schools
    Each school can only have one active sales rep
    """
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    sales_rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='school_assignments',
        limit_choices_to={'user_type': 'sales_rep'}
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

        # Ensure sales rep is actually a sales rep
        if self.sales_rep and not self.sales_rep.is_sales_rep:
            raise ValidationError({
                'sales_rep': 'Only sales representatives can be assigned to schools'
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
    Model for assigning sales representatives to clubs
    Each club can only have one active sales rep
    """
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    sales_rep = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='club_assignments',
        limit_choices_to={'user_type': 'sales_rep'}
    )

    club = models.ForeignKey(
        'clubs.Club',
        on_delete=models.CASCADE,
        related_name='sales_rep_assignments'
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
        related_name='created_club_assignments',
        help_text="User who created this assignment"
    )

    class Meta:
        db_table = 'sales_rep_club_assignments'
        verbose_name = 'Sales Rep Club Assignment'
        verbose_name_plural = 'Sales Rep Club Assignments'
        ordering = ['-assigned_date']
        indexes = [
            models.Index(fields=['sales_rep', 'is_active']),
            models.Index(fields=['club', 'is_active']),
            models.Index(fields=['assigned_date']),
            models.Index(fields=['territory_name']),
        ]
        constraints = [
            # Ensure each club has only one active assignment
            models.UniqueConstraint(
                fields=['club'],
                condition=models.Q(is_active=True),
                name='unique_active_club_assignment'
            ),
        ]

    def clean(self):
        """Validate assignment data"""
        super().clean()

        # Ensure sales rep is actually a sales rep
        if self.sales_rep and not self.sales_rep.is_sales_rep:
            raise ValidationError({
                'sales_rep': 'Only sales representatives can be assigned to clubs'
            })

        # Check for existing active assignments
        if self.is_active:
            existing_assignment = SalesRepClubAssignment.objects.filter(
                club=self.club,
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
            audit_data.update({
                'ip_address': cls._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'session_key': request.session.session_key if hasattr(request, 'session') else '',
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
