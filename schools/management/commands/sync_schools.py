from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from schools.services import SchoolAPIService


class Command(BaseCommand):
    help = 'Sync schools data from NZ Government API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            help='Maximum number of schools to sync',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode (fetch data but do not save)',
        )
        parser.add_argument(
            '--all-schools',
            action='store_true',
            help='Sync all schools including closed ones (default: open schools only)',
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        dry_run = options.get('dry_run', False)
        all_schools = options.get('all_schools', False)
        open_only = not all_schools  # By default sync only open schools

        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY RUN mode - no data will be saved'))

        if open_only:
            self.stdout.write(self.style.SUCCESS('Syncing OPEN schools only'))
        else:
            self.stdout.write(self.style.WARNING('Syncing ALL schools (including closed)'))

        self.stdout.write(f"Starting school sync at {timezone.now()}")

        if dry_run:
            # Test API connection for open schools only
            filters = {'Status': 'Open'} if open_only else None
            data = SchoolAPIService.fetch_schools(limit=1, filters=filters)
            if data and data.get('success'):
                total = data['result'].get('total', 0)
                school_type = "open schools" if open_only else "total schools"
                self.stdout.write(self.style.SUCCESS(f"API connection successful. {school_type.title()} available: {total}"))

                # Show sample record
                records = data['result'].get('records', [])
                if records:
                    sample = records[0]
                    self.stdout.write("\nSample school data:")
                    self.stdout.write(f"  School ID: {sample.get('School_Id')}")
                    self.stdout.write(f"  Name: {sample.get('Org_Name')}")
                    self.stdout.write(f"  Type: {sample.get('Org_Type')}")
                    self.stdout.write(f"  City: {sample.get('Add1_City')}")
                    self.stdout.write(f"  Status: {sample.get('Status')}")
                    self.stdout.write(f"  Total Students: {sample.get('Total')}")
            else:
                raise CommandError('Failed to connect to API')
        else:
            # Perform actual sync
            try:
                stats = SchoolAPIService.sync_schools(limit=limit, open_only=open_only)

                self.stdout.write(self.style.SUCCESS("\n" + "="*50))
                self.stdout.write(self.style.SUCCESS("School sync completed successfully!"))
                self.stdout.write(self.style.SUCCESS("="*50))
                self.stdout.write(f"  Total processed: {stats['total']}")
                self.stdout.write(f"  Created: {stats['created']}")
                self.stdout.write(f"  Updated: {stats['updated']}")
                self.stdout.write(f"  Errors: {stats['errors']}")

                if stats['errors'] > 0:
                    self.stdout.write(self.style.WARNING(f"\n⚠️  There were {stats['errors']} errors during sync. Check logs for details."))

            except Exception as e:
                raise CommandError(f'Error during sync: {e}')