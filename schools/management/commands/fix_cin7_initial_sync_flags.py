"""
Management command to fix is_initial_sync flags on existing Cin7Product records.

This command is needed after database migrations or resets that cleared the is_initial_sync flags.
Without these flags, the sync system incorrectly triggers initial sync mode, causing unnecessary
record deletions and API calls.

Usage:
    python manage.py fix_cin7_initial_sync_flags
    python manage.py fix_cin7_initial_sync_flags --price-type Wholesale
    python manage.py fix_cin7_initial_sync_flags --dry-run

Author: Claude Code
Date: 2025-12-02
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from schools.models import Cin7Product


class Command(BaseCommand):
    help = 'Fix is_initial_sync flags on existing Cin7Product records after migration reset'

    def add_arguments(self, parser):
        parser.add_argument(
            '--price-type',
            type=str,
            help='Fix only a specific price type (e.g., Wholesale, TUS, LOTTO)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )

    def handle(self, *args, **options):
        price_type = options.get('price_type')
        dry_run = options.get('dry_run', False)

        self.stdout.write(self.style.SUCCESS('=== Cin7Product is_initial_sync Flag Fix ==='))
        self.stdout.write('')

        # Build queryset
        queryset = Cin7Product.objects.all()
        if price_type:
            queryset = queryset.filter(price_type=price_type)
            self.stdout.write(f'Filtering for price_type: {price_type}')
        else:
            self.stdout.write('Processing all price types')

        # Get statistics
        total_records = queryset.count()
        missing_flag_count = queryset.filter(is_initial_sync=False).count()

        self.stdout.write('')
        self.stdout.write(f'Total records: {total_records:,}')
        self.stdout.write(f'Records missing is_initial_sync=True: {missing_flag_count:,}')
        self.stdout.write('')

        if missing_flag_count == 0:
            self.stdout.write(self.style.SUCCESS('✓ All records already have is_initial_sync=True'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            self.stdout.write('')
            self.stdout.write(f'Would update {missing_flag_count:,} records to set is_initial_sync=True')

            # Show breakdown by price_type
            if not price_type:
                self.stdout.write('')
                self.stdout.write('Breakdown by price_type:')
                for pt in queryset.values('price_type').distinct():
                    pt_name = pt['price_type']
                    pt_total = queryset.filter(price_type=pt_name).count()
                    pt_missing = queryset.filter(price_type=pt_name, is_initial_sync=False).count()
                    self.stdout.write(f'  {pt_name}: {pt_missing:,} / {pt_total:,} records')

            return

        # Confirm before proceeding
        if missing_flag_count > 10000:
            self.stdout.write(self.style.WARNING(
                f'⚠️  WARNING: This will update {missing_flag_count:,} records'
            ))
            confirm = input('Are you sure you want to proceed? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Aborted by user'))
                return

        # Perform the update
        self.stdout.write('Updating records...')

        with transaction.atomic():
            updated = queryset.filter(is_initial_sync=False).update(is_initial_sync=True)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully updated {updated:,} records'))
        self.stdout.write('')

        # Verify the fix
        remaining = queryset.filter(is_initial_sync=False).count()
        if remaining == 0:
            self.stdout.write(self.style.SUCCESS('✓ All records now have is_initial_sync=True'))
        else:
            self.stdout.write(self.style.WARNING(f'⚠️  {remaining:,} records still missing flag'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Fix Complete ==='))
