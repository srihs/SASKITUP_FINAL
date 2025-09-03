from django.core.management.base import BaseCommand
from django.utils.text import slugify
from clubs.models import Club


class Command(BaseCommand):
    help = 'Fix any clubs that might have missing or invalid slugs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        clubs = Club.objects.all()
        fixed_count = 0
        
        for club in clubs:
            original_slug = club.slug
            expected_slug = slugify(club.name)
            
            if not club.slug or club.slug != expected_slug:
                if options['dry_run']:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Would update club "{club.name}": slug "{original_slug}" -> "{expected_slug}"'
                        )
                    )
                else:
                    club.slug = expected_slug
                    club.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated club "{club.name}": slug "{original_slug}" -> "{expected_slug}"'
                        )
                    )
                fixed_count += 1
            else:
                if options['verbosity'] >= 2:
                    self.stdout.write(
                        f'Club "{club.name}" already has correct slug: "{club.slug}"'
                    )

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(f'\nDry run completed. {fixed_count} clubs would be updated.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nCompleted! {fixed_count} clubs updated.')
            )