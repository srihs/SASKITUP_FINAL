import os
import logging
import uuid
from django.db import models
from django.core.validators import URLValidator
from django.utils.text import slugify
from django.utils import timezone

# Import LOTTO-specific models
from .models_lotto import LottoClub, LottoClubCategory, LottoProduct, LottoProductVariation

# Import SAS-specific models
from .models_sas import SASSport, SASClub, SASProduct, SASProductVariation

# TUS models moved to schools app
# Wholesale models moved to schools app

logger = logging.getLogger(__name__)


class SyncJob(models.Model):
    """
    Model to track sync job status and progress for async operations
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    SYNC_TYPE_CHOICES = [
        ('lotto', 'LOTTO Clubs'),
        ('sas', 'SAS Clubs'),
        ('tus', 'TUS Schools'),
        ('wholesale', 'Wholesale Schools'),
        ('nz', 'NZ Government Schools'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sync_type = models.CharField(max_length=10, choices=SYNC_TYPE_CHOICES, help_text="Type of sync operation")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress_percentage = models.PositiveSmallIntegerField(default=0, help_text="Progress from 0 to 100")
    current_step = models.CharField(max_length=255, blank=True, help_text="Current operation being performed")
    
    # Statistics
    clubs_created = models.PositiveIntegerField(default=0)
    clubs_updated = models.PositiveIntegerField(default=0)
    categories_created = models.PositiveIntegerField(default=0)
    categories_updated = models.PositiveIntegerField(default=0)
    products_created = models.PositiveIntegerField(default=0)
    products_updated = models.PositiveIntegerField(default=0)
    
    # Logs and errors
    log_messages = models.JSONField(default=list, help_text="Array of log messages")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if failed")
    error_code = models.CharField(max_length=50, blank=True, null=True, help_text="Error code for programmatic handling")
    
    # Metadata
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Sync Job"
        verbose_name_plural = "Sync Jobs"
        indexes = [
            models.Index(fields=['status', 'sync_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_sync_type_display()} - {self.get_status_display()}"
    
    def add_log_message(self, message, level='info'):
        """Add a log message to the job"""
        if not isinstance(self.log_messages, list):
            self.log_messages = []
        
        self.log_messages.append({
            'timestamp': timezone.now().isoformat(),
            'level': level,
            'message': message
        })
        self.save(update_fields=['log_messages', 'updated_at'])
    
    def update_progress(self, percentage, step=None):
        """Update progress and current step"""
        self.progress_percentage = min(100, max(0, percentage))
        if step:
            self.current_step = step
        self.save(update_fields=['progress_percentage', 'current_step', 'updated_at'])
    
    def start(self):
        """Mark job as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.progress_percentage = 0
        self.save(update_fields=['status', 'started_at', 'progress_percentage', 'updated_at'])
    
    def is_stale(self, max_age_hours=2):
        """Check if a running job is stale (running for too long)"""
        if self.status != 'running':
            return False
        
        start_time = self.started_at or self.created_at
        if not start_time:
            return True  # No start time is suspicious
        
        age = timezone.now() - start_time
        return age.total_seconds() > (max_age_hours * 3600)
    
    def get_age_hours(self):
        """Get the age of the job in hours"""
        start_time = self.started_at or self.created_at
        if not start_time:
            return None
        
        age = timezone.now() - start_time
        return age.total_seconds() / 3600
    
    @classmethod
    def cleanup_stale_jobs(cls, max_age_hours=2):
        """Clean up stale running jobs"""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        
        # Find stale running jobs
        stale_jobs = cls.objects.filter(
            status='running'
        ).filter(
            models.Q(started_at__lt=cutoff_time) |
            models.Q(started_at__isnull=True, created_at__lt=cutoff_time)
        )
        
        cleaned_count = 0
        for job in stale_jobs:
            age_hours = job.get_age_hours()
            job.fail(
                f'Job automatically cleaned up - was stuck in running state for {age_hours:.2f} hours',
                'AUTO_CLEANUP'
            )
            job.add_log_message('Job was automatically cleaned up due to being stuck in running state', 'warning')
            cleaned_count += 1
        
        return cleaned_count
    
    def complete(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress_percentage = 100
        self.save(update_fields=['status', 'completed_at', 'progress_percentage', 'updated_at'])
    
    def fail(self, error_message, error_code=None):
        """Mark job as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.error_code = error_code
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'error_code', 'completed_at', 'updated_at'])
    
    @property
    def duration(self):
        """Get job duration if completed"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def is_finished(self):
        """Check if job is finished (completed, failed, or cancelled)"""
        return self.status in ['completed', 'failed', 'cancelled']
    
    @property
    def total_items_created(self):
        """Get total items created across all types"""
        return self.clubs_created + self.categories_created + self.products_created
    
    @property
    def total_items_updated(self):
        """Get total items updated across all types"""
        return self.clubs_updated + self.categories_updated + self.products_updated
