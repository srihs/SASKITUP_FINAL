from django.core.management.base import BaseCommand
from clubs.models import SyncJob


class Command(BaseCommand):
    help = 'Automatically clean up stale sync jobs (for cron jobs)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=2,
            help='Max age in hours for a running sync job before considering it stale (default: 2)'
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Only show output if stale jobs are found'
        )
    
    def handle(self, *args, **options):
        max_age_hours = options['max_age_hours']
        quiet = options['quiet']
        
        # Clean up stale jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=max_age_hours)
        
        if cleaned_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Cleaned up {cleaned_count} stale sync jobs')
            )
        elif not quiet:
            self.stdout.write('No stale sync jobs found.')
        
        # Show current status if not quiet
        if not quiet:
            running_jobs = SyncJob.objects.filter(status='running')
            if running_jobs.exists():
                self.stdout.write(f'{running_jobs.count()} sync jobs currently running:')
                for job in running_jobs:
                    age_hours = job.get_age_hours()
                    age_text = f'{age_hours:.2f}h' if age_hours else 'unknown age'
                    self.stdout.write(f'  - {job.sync_type.upper()}: {age_text}, {job.progress_percentage}% complete')
            else:
                self.stdout.write('No sync jobs currently running.')