"""
Management command to assign all retail schools and general LOTTO/SAS clubs to customers.
Usage: python manage.py assign_customer_institutions
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from quotations.models import CustomerInstitutionAssignment
from schools.models_tus import TUSSchool
from clubs.models_lotto import LottoClub
from clubs.models_sas import SASClub

User = get_user_model()


class Command(BaseCommand):
    help = 'Assign all retail schools and general LOTTO/SAS clubs to all customers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--customer-email',
            type=str,
            help='Assign to specific customer email (optional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be assigned without actually creating records',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        customer_email = options.get('customer_email')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get customers to assign
        if customer_email:
            customers = User.objects.filter(email__iexact=customer_email, user_type='customer')
            if not customers.exists():
                self.stdout.write(self.style.ERROR(f'No customer found with email: {customer_email}'))
                return
        else:
            customers = User.objects.filter(user_type='customer', is_active=True)

        if not customers.exists():
            self.stdout.write(self.style.WARNING('No customers found'))
            return

        self.stdout.write(f'Found {customers.count()} customer(s) to process')

        # Get all retail schools
        tus_schools = TUSSchool.objects.filter(is_active=True)
        self.stdout.write(f'Found {tus_schools.count()} active TUS retail schools')

        # Get all LOTTO clubs
        lotto_clubs = LottoClub.objects.filter(is_active=True)
        self.stdout.write(f'Found {lotto_clubs.count()} active LOTTO clubs')

        # Get all SAS clubs
        sas_clubs = SASClub.objects.filter(is_active=True)
        self.stdout.write(f'Found {sas_clubs.count()} active SAS clubs')

        total_assignments = 0

        for customer in customers:
            self.stdout.write(f'\nProcessing customer: {customer.email}')
            customer_assignments = 0

            # Assign all TUS schools
            tus_ct = ContentType.objects.get_for_model(TUSSchool)
            for school in tus_schools:
                if not dry_run:
                    assignment, created = CustomerInstitutionAssignment.objects.get_or_create(
                        customer=customer,
                        institution_content_type=tus_ct,
                        institution_object_id=school.id,
                        defaults={'is_active': True}
                    )
                    if created:
                        customer_assignments += 1
                        self.stdout.write(f'  ✓ Assigned TUS School: {school.name}')
                    else:
                        self.stdout.write(f'  - Already assigned: {school.name}')
                else:
                    self.stdout.write(f'  [DRY RUN] Would assign TUS School: {school.name}')
                    customer_assignments += 1

            # Assign all LOTTO clubs
            lotto_ct = ContentType.objects.get_for_model(LottoClub)
            for club in lotto_clubs:
                if not dry_run:
                    assignment, created = CustomerInstitutionAssignment.objects.get_or_create(
                        customer=customer,
                        institution_content_type=lotto_ct,
                        institution_object_id=club.id,
                        defaults={'is_active': True}
                    )
                    if created:
                        customer_assignments += 1
                        self.stdout.write(f'  ✓ Assigned LOTTO Club: {club.name}')
                    else:
                        self.stdout.write(f'  - Already assigned: {club.name}')
                else:
                    self.stdout.write(f'  [DRY RUN] Would assign LOTTO Club: {club.name}')
                    customer_assignments += 1

            # Assign all SAS clubs
            sas_ct = ContentType.objects.get_for_model(SASClub)
            for club in sas_clubs:
                if not dry_run:
                    assignment, created = CustomerInstitutionAssignment.objects.get_or_create(
                        customer=customer,
                        institution_content_type=sas_ct,
                        institution_object_id=club.id,
                        defaults={'is_active': True}
                    )
                    if created:
                        customer_assignments += 1
                        self.stdout.write(f'  ✓ Assigned SAS Club: {club.name}')
                    else:
                        self.stdout.write(f'  - Already assigned: {club.name}')
                else:
                    self.stdout.write(f'  [DRY RUN] Would assign SAS Club: {club.name}')
                    customer_assignments += 1

            total_assignments += customer_assignments
            self.stdout.write(self.style.SUCCESS(f'Customer {customer.email}: {customer_assignments} assignments'))

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\n[DRY RUN] Would create {total_assignments} total assignments'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully created {total_assignments} total assignments'))

        # Show summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write('SUMMARY:')
        self.stdout.write(f'Customers processed: {customers.count()}')
        self.stdout.write(f'TUS Schools: {tus_schools.count()}')
        self.stdout.write(f'LOTTO Clubs: {lotto_clubs.count()}')
        self.stdout.write(f'SAS Clubs: {sas_clubs.count()}')
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'Total assignments created: {total_assignments}'))
        else:
            self.stdout.write(self.style.WARNING(f'Total assignments (DRY RUN): {total_assignments}'))
        self.stdout.write('='*60)
