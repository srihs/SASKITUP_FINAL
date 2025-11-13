"""
Management command to sync Bespoke products from CIN7

Usage:
    python manage.py sync_bespoke_products
"""

from django.core.management.base import BaseCommand
from bespoke.services.cin7_sync_service import BespokeCin7SyncService
from clubs.models import SyncJob


class Command(BaseCommand):
    help = 'Sync Bespoke products from CIN7 "Quotation Base Library" category'

    def add_arguments(self, parser):
        parser.add_argument(
            '--job-id',
            type=str,
            help='SyncJob ID for progress tracking',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Bespoke product sync from CIN7...'))

        # Get SyncJob if job_id provided
        sync_job = None
        job_id = options.get('job_id')
        if job_id:
            try:
                sync_job = SyncJob.objects.get(id=job_id)
                self.stdout.write(f'Using SyncJob: {job_id}')
            except SyncJob.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'SyncJob {job_id} not found, continuing without progress tracking'))

        try:
            # Initialize and run sync with SyncJob
            sync_service = BespokeCin7SyncService(sync_job=sync_job)
            sync_log = sync_service.sync_all()

            # Report results
            if sync_log.status == 'completed':
                self.stdout.write(self.style.SUCCESS('✅ Sync completed successfully!'))
                self.stdout.write(f'  Categories synced: {sync_log.categories_synced}')
                self.stdout.write(f'  Products synced: {sync_log.products_synced}')
                self.stdout.write(f'  Variations synced: {sync_log.variations_synced}')
                self.stdout.write(f'  Duration: {sync_log.duration_seconds}s')

                if sync_log.errors_count > 0:
                    self.stdout.write(self.style.WARNING(f'  Errors encountered: {sync_log.errors_count}'))
            else:
                self.stdout.write(self.style.ERROR('❌ Sync failed!'))
                self.stdout.write(f'  Error: {sync_log.error_message}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Sync failed with exception: {str(e)}'))
            raise
