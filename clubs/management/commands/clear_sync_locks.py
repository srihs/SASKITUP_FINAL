import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from clubs.models import SyncJob

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clear stuck sync jobs that are running for too long'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=2,
            help='Maximum age in hours for a running job before considering it stale (default: 2)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleared without actually doing it'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force clear ALL running jobs regardless of age'
        )

    def handle(self, *args, **options):
        max_age_hours = options['max_age_hours']
        dry_run = options['dry_run']
        force = options['force']

        self.stdout.write(self.style.SUCCESS('\n=== SYNC LOCK CLEANER ==='))
        
        # Get all running jobs
        running_jobs = SyncJob.objects.filter(status='running')
        self.stdout.write(f'Found {running_jobs.count()} running sync jobs')
        
        if not running_jobs.exists():
            self.stdout.write(self.style.SUCCESS('No running jobs found. All locks are clear!'))
            return
        
        # Show details of running jobs
        jobs_to_clear = []
        for job in running_jobs:
            age_hours = (timezone.now() - job.created_at).total_seconds() / 3600
            is_stale = age_hours > max_age_hours or force
            
            status_style = self.style.ERROR if is_stale else self.style.WARNING
            self.stdout.write(status_style(
                f'  - Job {job.id}: {job.sync_type.upper()}, '
                f'Age: {age_hours:.1f}h, Progress: {job.progress_percentage}%'
            ))
            self.stdout.write(f'    Step: {job.current_step or "N/A"}')
            self.stdout.write(f'    Created: {job.created_at}')
            
            if is_stale:
                jobs_to_clear.append((job, age_hours))
                if force:
                    self.stdout.write(self.style.ERROR('    -> WILL BE FORCE CLEARED'))
                else:
                    self.stdout.write(self.style.ERROR(f'    -> STALE (>{max_age_hours}h) - WILL BE CLEARED'))
            else:
                self.stdout.write(self.style.SUCCESS(f'    -> Active (not stale)'))
        
        if not jobs_to_clear:
            self.stdout.write(self.style.SUCCESS(f'No stale jobs found (using {max_age_hours}h threshold)'))
            if not force:
                self.stdout.write('Use --force to clear all running jobs regardless of age')
            return
        
        # Clear jobs
        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN: Would clear {len(jobs_to_clear)} jobs'))
        else:
            self.stdout.write(f'\nClearing {len(jobs_to_clear)} stale jobs...')
            
            cleared_count = 0
            for job, age_hours in jobs_to_clear:
                try:
                    reason = 'Force cleared by admin' if force else f'Stale job (running for {age_hours:.1f} hours)'
                    error_code = 'ADMIN_FORCE_CLEARED' if force else 'STALE_CLEARED'
                    
                    job.status = 'failed'
                    job.completed_at = timezone.now()
                    job.error_message = reason
                    job.error_code = error_code
                    job.save()
                    
                    cleared_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Cleared job {job.id}'))
                    
                    # Log the action
                    logger.warning(f'Sync job {job.id} cleared: {reason}')
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed to clear job {job.id}: {e}'))
            
            self.stdout.write(self.style.SUCCESS(f'\nCleared {cleared_count} jobs'))
        
        # Final status
        remaining = SyncJob.objects.filter(status='running').count()
        if remaining == 0:
            self.stdout.write(self.style.SUCCESS('All sync locks are now clear! ✓'))
        else:
            self.stdout.write(self.style.WARNING(f'Warning: {remaining} jobs still running'))
        
        self.stdout.write(self.style.SUCCESS('\n=== COMPLETE ==='))