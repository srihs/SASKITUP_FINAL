"""
Utility for matching wholesale schools with NZ schools database.
"""
from typing import Optional, Dict, Any, List
from difflib import SequenceMatcher
from django.core.cache import cache
from schools.models import School, WholesaleSchool
import logging

logger = logging.getLogger(__name__)


class SchoolMatcher:
    """
    Matches wholesale schools with NZ schools by name for contact details retrieval.
    """

    # Cache timeout in seconds (1 hour)
    CACHE_TIMEOUT = 3600

    # Minimum similarity score for fuzzy matching (0.0 to 1.0)
    MIN_SIMILARITY_SCORE = 0.85

    @classmethod
    def normalize_school_name(cls, name: str) -> str:
        """
        Normalize school name for better matching.

        Args:
            name: School name to normalize

        Returns:
            Normalized school name
        """
        if not name:
            return ""

        # Convert to lowercase
        name = name.lower().strip()

        # Remove common school suffixes for better matching
        replacements = [
            ('school', ''),
            ('college', ''),
            ('high', ''),
            ('primary', ''),
            ('intermediate', ''),
            ('secondary', ''),
            ('grammar', ''),
            ('boys', ''),
            ('girls', ''),
            ('of', ''),
            ('the', ''),
            ('&', 'and'),
            ("'s", ''),
            ('saint', 'st'),
            ('mount', 'mt'),
        ]

        for old, new in replacements:
            name = name.replace(old, new)

        # Remove extra spaces
        name = ' '.join(name.split())

        return name

    @classmethod
    def calculate_similarity(cls, name1: str, name2: str) -> float:
        """
        Calculate similarity score between two school names.

        Args:
            name1: First school name
            name2: Second school name

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Normalize both names
        norm1 = cls.normalize_school_name(name1)
        norm2 = cls.normalize_school_name(name2)

        # Calculate similarity
        return SequenceMatcher(None, norm1, norm2).ratio()

    @classmethod
    def find_matching_nz_school(cls, wholesale_school_name: str) -> Optional[School]:
        """
        Find matching NZ school for a wholesale school name.

        Args:
            wholesale_school_name: Name of the wholesale school

        Returns:
            Matching School object or None
        """
        if not wholesale_school_name:
            return None

        # Check cache first (make cache key safe for memcached)
        safe_name = wholesale_school_name.replace(' ', '_').replace(':', '_')
        cache_key = f"school_match_{safe_name}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            if cached_result == 'not_found':
                return None
            try:
                return School.objects.get(id=cached_result)
            except School.DoesNotExist:
                pass

        # First try exact match (case-insensitive)
        exact_match = School.objects.filter(
            org_name__iexact=wholesale_school_name,
            status='Open'
        ).first()

        if exact_match:
            cache.set(cache_key, exact_match.id, cls.CACHE_TIMEOUT)
            return exact_match

        # Try fuzzy matching
        best_match = None
        best_score = 0.0

        # Get all open schools
        schools = School.objects.filter(status='Open').only('id', 'org_name')

        for school in schools:
            score = cls.calculate_similarity(wholesale_school_name, school.org_name)
            if score > best_score and score >= cls.MIN_SIMILARITY_SCORE:
                best_score = score
                best_match = school

        if best_match:
            logger.info(f"Matched wholesale school '{wholesale_school_name}' to NZ school '{best_match.org_name}' with score {best_score:.2f}")
            cache.set(cache_key, best_match.id, cls.CACHE_TIMEOUT)
            return best_match

        # No match found
        logger.debug(f"No match found for wholesale school: {wholesale_school_name}")
        cache.set(cache_key, 'not_found', cls.CACHE_TIMEOUT)
        return None

    @classmethod
    def get_school_contact_details(cls, wholesale_school: WholesaleSchool) -> Dict[str, Any]:
        """
        Get contact details for a wholesale school by matching with NZ school.

        Args:
            wholesale_school: WholesaleSchool object

        Returns:
            Dictionary with contact details
        """
        # Default values for when no match is found
        default_details = {
            'address': 'No address available',
            'region': 'No region',
            'contact_person': 'Not specified',
            'phone': 'Not specified',
            'email': 'Not specified'
        }

        # First check if wholesale school has its own data
        if any([
            wholesale_school.address_line1,
            wholesale_school.address_line2,
            wholesale_school.city,
            wholesale_school.region
        ]):
            # Use wholesale school's own data if available
            address_parts = []
            if wholesale_school.address_line1:
                address_parts.append(wholesale_school.address_line1)
            if wholesale_school.address_line2:
                address_parts.append(wholesale_school.address_line2)
            if wholesale_school.city:
                address_parts.append(wholesale_school.city)
            if wholesale_school.region:
                address_parts.append(wholesale_school.region)
            if wholesale_school.postal_code:
                address_parts.append(wholesale_school.postal_code)

            return {
                'address': ', '.join(address_parts) if address_parts else default_details['address'],
                'region': wholesale_school.region or default_details['region'],
                'contact_person': wholesale_school.contact_person or default_details['contact_person'],
                'phone': wholesale_school.phone or default_details['phone'],
                'email': wholesale_school.email or default_details['email']
            }

        # Try to find matching NZ school
        nz_school = cls.find_matching_nz_school(wholesale_school.name)

        if nz_school:
            # Build address from NZ school data
            address_parts = []
            if nz_school.add1_line1:
                address_parts.append(nz_school.add1_line1)
            if nz_school.add1_suburb:
                address_parts.append(nz_school.add1_suburb)
            if nz_school.add1_city:
                address_parts.append(nz_school.add1_city)

            # Use regional_council or education_region for region
            region = nz_school.regional_council or nz_school.education_region or default_details['region']

            return {
                'address': ', '.join(address_parts) if address_parts else default_details['address'],
                'region': region,
                'contact_person': nz_school.contact1_name or wholesale_school.contact_person or default_details['contact_person'],
                'phone': nz_school.telephone or wholesale_school.phone or default_details['phone'],
                'email': nz_school.email or wholesale_school.email or default_details['email']
            }

        # Return defaults if no match found
        return default_details

    @classmethod
    def batch_match_schools(cls, wholesale_schools: List[WholesaleSchool]) -> Dict[int, Dict[str, Any]]:
        """
        Batch match multiple wholesale schools with NZ schools.

        Args:
            wholesale_schools: List of WholesaleSchool objects

        Returns:
            Dictionary mapping wholesale school ID to contact details
        """
        results = {}

        for school in wholesale_schools:
            results[school.id] = cls.get_school_contact_details(school)

        return results