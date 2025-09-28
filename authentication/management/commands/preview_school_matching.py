"""
Management command to preview school matching results for wholesale schools.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from schools.models import WholesaleSchool, School
from authentication.utils.school_matcher import SchoolMatcher
import csv

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


class Command(BaseCommand):
    help = 'Preview how wholesale schools match with NZ schools database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export',
            type=str,
            help='Export results to CSV file',
        )
        parser.add_argument(
            '--show-all',
            action='store_true',
            help='Show all schools including those with no matches',
        )
        parser.add_argument(
            '--min-score',
            type=float,
            default=0.85,
            help='Minimum similarity score for fuzzy matching (default: 0.85)',
        )

    def handle(self, *args, **options):
        """Execute the command."""
        export_file = options.get('export')
        show_all = options.get('show_all')
        min_score = options.get('min_score')

        # Temporarily set the minimum similarity score if provided
        original_min_score = SchoolMatcher.MIN_SIMILARITY_SCORE
        SchoolMatcher.MIN_SIMILARITY_SCORE = min_score

        try:
            # Get all active wholesale schools
            wholesale_schools = WholesaleSchool.objects.filter(is_active=True).order_by('name')
            total_schools = wholesale_schools.count()

            self.stdout.write(f"\nAnalyzing {total_schools} wholesale schools...\n")

            results = []
            matched_count = 0
            unmatched_count = 0

            for ws in wholesale_schools:
                # Find matching NZ school
                nz_school = SchoolMatcher.find_matching_nz_school(ws.name)

                if nz_school:
                    matched_count += 1
                    similarity_score = SchoolMatcher.calculate_similarity(ws.name, nz_school.org_name)

                    result = {
                        'Wholesale School': ws.name,
                        'NZ School Match': nz_school.org_name,
                        'Score': f"{similarity_score:.2f}",
                        'Address': f"{nz_school.add1_line1}, {nz_school.add1_suburb}, {nz_school.add1_city}" if nz_school.add1_line1 else "N/A",
                        'Contact': nz_school.contact1_name or "N/A",
                        'Phone': nz_school.telephone or "N/A",
                        'Email': nz_school.email or "N/A",
                        'Match Type': 'Exact' if similarity_score == 1.0 else 'Fuzzy',
                    }
                    results.append(result)
                else:
                    unmatched_count += 1
                    if show_all:
                        result = {
                            'Wholesale School': ws.name,
                            'NZ School Match': 'NO MATCH FOUND',
                            'Score': '0.00',
                            'Address': ws.address_line1 or "N/A",
                            'Contact': ws.contact_person or "N/A",
                            'Phone': ws.phone or "N/A",
                            'Email': ws.email or "N/A",
                            'Match Type': 'None',
                        }
                        results.append(result)

            # Display summary
            self.stdout.write(self.style.SUCCESS(f"\n=== MATCHING SUMMARY ==="))
            self.stdout.write(f"Total Wholesale Schools: {total_schools}")
            self.stdout.write(self.style.SUCCESS(f"✓ Matched: {matched_count} ({matched_count/total_schools*100:.1f}%)"))
            self.stdout.write(self.style.WARNING(f"✗ Unmatched: {unmatched_count} ({unmatched_count/total_schools*100:.1f}%)"))
            self.stdout.write(f"Minimum Similarity Score: {min_score}")

            # Display results table
            if results:
                self.stdout.write(f"\n=== MATCHING RESULTS ===\n")

                # Prepare table data
                headers = list(results[0].keys())
                rows = [list(r.values()) for r in results]

                # Display using tabulate or fallback to simple table
                if HAS_TABULATE:
                    table = tabulate(rows, headers=headers, tablefmt='grid')
                    self.stdout.write(table)
                else:
                    # Simple fallback table
                    # Print headers
                    header_line = " | ".join(f"{h:20s}" for h in headers)
                    self.stdout.write(header_line)
                    self.stdout.write("-" * len(header_line))

                    # Print rows
                    for row in rows:
                        row_line = " | ".join(f"{str(cell):20s}" for cell in row)
                        self.stdout.write(row_line)

                # Export to CSV if requested
                if export_file:
                    with open(export_file, 'w', newline='') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=headers)
                        writer.writeheader()
                        writer.writerows(results)
                    self.stdout.write(self.style.SUCCESS(f"\nResults exported to: {export_file}"))

            # Show unmatched schools if not showing all
            if not show_all and unmatched_count > 0:
                self.stdout.write(f"\n=== UNMATCHED WHOLESALE SCHOOLS ===")
                unmatched = []
                for ws in wholesale_schools:
                    if not SchoolMatcher.find_matching_nz_school(ws.name):
                        unmatched.append(ws.name)

                for name in unmatched[:20]:  # Show first 20
                    self.stdout.write(f"  • {name}")

                if len(unmatched) > 20:
                    self.stdout.write(f"  ... and {len(unmatched) - 20} more")

                self.stdout.write(f"\nTip: Use --show-all to see all schools in the results table")

            # Suggest possible improvements
            if unmatched_count > 0:
                self.stdout.write(f"\n=== SUGGESTIONS ===")
                self.stdout.write(f"• Try lowering the minimum similarity score (currently {min_score})")
                self.stdout.write(f"  Example: --min-score 0.7")
                self.stdout.write(f"• Some wholesale schools may not exist in the NZ schools database")
                self.stdout.write(f"• Check for data quality issues in wholesale school names")

        finally:
            # Restore original minimum similarity score
            SchoolMatcher.MIN_SIMILARITY_SCORE = original_min_score