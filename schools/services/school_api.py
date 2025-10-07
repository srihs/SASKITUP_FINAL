import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional
from django.utils import timezone
from django.conf import settings
from schools.models import School

logger = logging.getLogger(__name__)


class SchoolAPIService:
    """Service for integrating with NZ Government Schools API"""

    BASE_URL = "https://catalogue.data.govt.nz/api/3/action/datastore_search"
    RESOURCE_ID = "4b292323-9fcc-41f8-814b-3c7b19cf14b3"
    DEFAULT_LIMIT = 100

    @classmethod
    def fetch_schools(cls, limit: int = None, offset: int = 0, filters: Dict = None) -> Dict:
        """
        Fetch schools data from the API

        Args:
            limit: Number of records to fetch (None for all)
            offset: Number of records to skip
            filters: Dictionary of filters to apply (e.g., {'Status': 'Open'})

        Returns:
            API response as dictionary
        """
        params = {
            'resource_id': cls.RESOURCE_ID,
            'offset': offset,
        }

        if limit is not None:
            params['limit'] = limit

        # Add filters to the query
        if filters:
            # Build query string for filters
            query_parts = []
            for field, value in filters.items():
                query_parts.append(f'{field}:"{value}"')
            if query_parts:
                params['q'] = ' AND '.join(query_parts)

        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('success'):
                return data
            else:
                logger.error(f"API returned error: {data}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching schools data: {e}")
            return None
        except ValueError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return None

    @classmethod
    def parse_datetime(cls, date_str: str) -> Optional[datetime]:
        """Parse datetime string from API"""
        if not date_str:
            return None
        try:
            # API returns datetime in ISO format
            dt = datetime.fromisoformat(date_str.replace('T00:00:00', ''))
            # Make it timezone aware
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except (ValueError, AttributeError):
            return None

    @classmethod
    def parse_school_data(cls, record: Dict) -> Dict:
        """
        Parse school record from API into model-compatible format

        Args:
            record: School record from API

        Returns:
            Dictionary with cleaned data for model creation
        """
        # Parse numeric fields safely
        def safe_int(value, default=0):
            try:
                return int(value) if value else default
            except (ValueError, TypeError):
                return default

        def safe_decimal(value, default=None):
            try:
                return float(value) if value else default
            except (ValueError, TypeError):
                return default

        return {
            'school_id': str(record.get('School_Id', '')),
            'org_name': record.get('Org_Name', ''),

            # Contact information
            'telephone': record.get('Telephone', ''),
            'fax': record.get('Fax', ''),
            'email': record.get('Email', ''),
            'contact1_name': record.get('Contact1_Name', ''),
            'url': record.get('URL', ''),

            # Physical address
            'add1_line1': record.get('Add1_Line1', ''),
            'add1_suburb': record.get('Add1_Suburb', ''),
            'add1_city': record.get('Add1_City', ''),

            # Postal address
            'add2_line1': record.get('Add2_Line1', ''),
            'add2_suburb': record.get('Add2_Suburb', ''),
            'add2_city': record.get('Add2_City', ''),
            'add2_postal_code': record.get('Add2_Postal_Code', ''),

            # Classification
            'urban_rural_indicator': record.get('Urban_Rural_Indicator', ''),
            'org_type': record.get('Org_Type', ''),
            'definition': record.get('Definition', ''),
            'authority': record.get('Authority', ''),
            'school_donations': record.get('School_Donations', ''),
            'coed_status': record.get('CoEd_Status', ''),
            'kme_peak_body': record.get('KMEPeakBody', ''),

            # Geographic/administrative regions
            'takiwa': record.get('Takiwā', ''),
            'territorial_authority': record.get('Territorial_Authority', ''),
            'regional_council': record.get('Regional_Council', ''),
            'local_office_name': record.get('Local_Office_Name', ''),
            'education_region': record.get('Education_Region', ''),
            'general_electorate': record.get('General_Electorate', ''),
            'maori_electorate': record.get('Māori_Electorate', ''),

            # Statistical area
            'statistical_area_2_code': record.get('Statistical_Area_2_Code', ''),
            'statistical_area_2_description': record.get('Statistical_Area_2_Description', ''),
            'ward': record.get('Ward', ''),

            # Community of Learning
            'col_id': record.get('Col_Id', ''),
            'col_name': record.get('Col_Name', ''),

            # Location
            'latitude': safe_decimal(record.get('Latitude')),
            'longitude': safe_decimal(record.get('Longitude')),

            # School characteristics
            'enrolment_scheme': record.get('Enrolment_Scheme', ''),
            'eqi_index': record.get('EQi_Index', ''),

            # Roll information
            'roll_date': cls.parse_datetime(record.get('Roll_Date')),
            'total': safe_int(record.get('Total')),
            'european': safe_int(record.get('European')),
            'maori': safe_int(record.get('Māori')),
            'pacific': safe_int(record.get('Pacific')),
            'asian': safe_int(record.get('Asian')),
            'melaa': safe_int(record.get('MELAA')),
            'other': safe_int(record.get('Other')),
            'international': safe_int(record.get('International')),

            # Other characteristics
            'isolation_index': record.get('Isolation_Index', ''),
            'language_of_instruction': record.get('Language_of_Instruction', ''),
            'boarding_facilities': record.get('BoardingFacilities', ''),
            'cohort_entry': record.get('CohortEntry', ''),
            'status': record.get('Status', ''),
            'date_school_opened': cls.parse_datetime(record.get('DateSchoolOpened')),
        }

    @classmethod
    def sync_schools(cls, limit: Optional[int] = None, open_only: bool = True) -> Dict[str, int]:
        """
        Sync schools from API to database

        Args:
            limit: Maximum number of schools to sync (None for all)
            open_only: If True, only sync schools with status 'Open' (default: True)

        Returns:
            Dictionary with sync statistics
        """
        stats = {
            'created': 0,
            'updated': 0,
            'errors': 0,
            'total': 0
        }

        offset = 0
        batch_size = cls.DEFAULT_LIMIT if limit is None or limit > cls.DEFAULT_LIMIT else limit

        # Set filters for open schools only
        filters = {'Status': 'Open'} if open_only else None

        while True:
            # Fetch batch from API
            if limit is not None and offset >= limit:
                break

            current_batch_size = batch_size
            if limit is not None and offset + batch_size > limit:
                current_batch_size = limit - offset

            logger.info(f"Fetching schools batch: offset={offset}, limit={current_batch_size}")
            data = cls.fetch_schools(limit=current_batch_size, offset=offset, filters=filters)

            if not data or not data.get('result'):
                logger.error("No data received from API")
                break

            records = data['result'].get('records', [])
            if not records:
                logger.info("No more records to process")
                break

            # Process each school record
            for record in records:
                stats['total'] += 1

                try:
                    school_data = cls.parse_school_data(record)
                    school_id = school_data['school_id']

                    if not school_id:
                        logger.warning(f"Skipping record with no school_id: {record}")
                        stats['errors'] += 1
                        continue

                    # Update or create school
                    school, created = School.objects.update_or_create(
                        school_id=school_id,
                        defaults={**school_data, 'last_synced': timezone.now()}
                    )

                    if created:
                        stats['created'] += 1
                        logger.info(f"Created school: {school.org_name} (ID: {school_id})")
                    else:
                        stats['updated'] += 1
                        logger.info(f"Updated school: {school.org_name} (ID: {school_id})")

                except Exception as e:
                    logger.error(f"Error processing school record: {e}, Record: {record}")
                    stats['errors'] += 1

            # Move to next batch
            offset += current_batch_size

            # Check if we've processed all available records
            total_records = data['result'].get('total', 0)
            if offset >= total_records:
                break

        logger.info(f"School sync completed. Stats: {stats}")
        return stats

    @classmethod
    def search_schools(cls, query: str, filters: Dict = None) -> List[School]:
        """
        Search schools in the database

        Args:
            query: Search query string
            filters: Additional filters to apply

        Returns:
            List of matching School objects
        """
        schools = School.objects.all()

        if query:
            schools = schools.filter(
                org_name__icontains=query
            ) | schools.filter(
                school_id__icontains=query
            ) | schools.filter(
                add1_city__icontains=query
            ) | schools.filter(
                regional_council__icontains=query
            )

        if filters:
            if filters.get('org_type'):
                schools = schools.filter(org_type=filters['org_type'])
            if filters.get('regional_council'):
                schools = schools.filter(regional_council=filters['regional_council'])
            if filters.get('authority'):
                schools = schools.filter(authority=filters['authority'])
            if filters.get('status'):
                schools = schools.filter(status=filters['status'])

        return schools

    @classmethod
    def get_filter_options(cls) -> Dict[str, List]:
        """
        Get available filter options from database

        Returns:
            Dictionary of filter options
        """
        return {
            'org_types': School.objects.values_list('org_type', flat=True).distinct().exclude(org_type='').order_by('org_type'),
            'regional_councils': School.objects.values_list('regional_council', flat=True).distinct().exclude(regional_council='').order_by('regional_council'),
            'authorities': School.objects.values_list('authority', flat=True).distinct().exclude(authority='').order_by('authority'),
            'statuses': School.objects.values_list('status', flat=True).distinct().exclude(status='').order_by('status'),
        }