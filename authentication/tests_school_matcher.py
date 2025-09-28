"""
Tests for school matching utility.
"""
from django.test import TestCase
from unittest.mock import MagicMock, patch
from authentication.utils.school_matcher import SchoolMatcher
from schools.models import School, WholesaleSchool


class SchoolMatcherTestCase(TestCase):
    """Test cases for SchoolMatcher utility."""

    def setUp(self):
        """Set up test data."""
        # Create some NZ schools for testing
        self.nz_school1 = School.objects.create(
            school_id='1001',
            org_name='Auckland Grammar School',
            add1_line1='Mountain Road',
            add1_suburb='Epsom',
            add1_city='Auckland',
            regional_council='Auckland Council',
            contact1_name='John Smith',
            telephone='09-123-4567',
            email='info@ags.school.nz',
            status='Open'
        )

        self.nz_school2 = School.objects.create(
            school_id='1002',
            org_name='Wellington Girls College',
            add1_line1='Pipitea Street',
            add1_suburb='Thorndon',
            add1_city='Wellington',
            regional_council='Greater Wellington',
            contact1_name='Jane Doe',
            telephone='04-987-6543',
            email='admin@wgc.school.nz',
            status='Open'
        )

        self.nz_school3 = School.objects.create(
            school_id='1003',
            org_name='Christchurch Boys High School',
            add1_line1='Straven Road',
            add1_suburb='Riccarton',
            add1_city='Christchurch',
            regional_council='Canterbury',
            contact1_name='Robert Johnson',
            telephone='03-555-1234',
            email='office@cbhs.school.nz',
            status='Open'
        )

        # Create wholesale schools
        self.wholesale_school1 = WholesaleSchool.objects.create(
            cin7_id='WS001',
            name='Auckland Grammar School',
            slug='auckland-grammar-school',
            is_active=True
        )

        self.wholesale_school2 = WholesaleSchool.objects.create(
            cin7_id='WS002',
            name='Wellington Girls',  # Slightly different name
            slug='wellington-girls',
            is_active=True
        )

        self.wholesale_school3 = WholesaleSchool.objects.create(
            cin7_id='WS003',
            name='Unknown School',  # No matching NZ school
            slug='unknown-school',
            is_active=True
        )

    def test_normalize_school_name(self):
        """Test school name normalization."""
        test_cases = [
            ('Auckland Grammar School', 'auckland'),
            ('St John\'s College', 'st john'),
            ('Mount Albert Grammar School', 'mt albert'),
            ('Girls High School', ''),
            ('The Kings School', 'kings'),
        ]

        for input_name, expected_normalized in test_cases:
            normalized = SchoolMatcher.normalize_school_name(input_name)
            self.assertEqual(normalized, expected_normalized)

    def test_calculate_similarity(self):
        """Test similarity calculation between school names."""
        # Exact match
        score = SchoolMatcher.calculate_similarity(
            'Auckland Grammar School',
            'Auckland Grammar School'
        )
        self.assertEqual(score, 1.0)

        # High similarity
        score = SchoolMatcher.calculate_similarity(
            'Wellington Girls College',
            'Wellington Girls'
        )
        self.assertGreater(score, 0.8)

        # Low similarity
        score = SchoolMatcher.calculate_similarity(
            'Auckland Grammar School',
            'Christchurch Boys High School'
        )
        self.assertLess(score, 0.5)

    def test_find_matching_nz_school_exact(self):
        """Test finding NZ school with exact name match."""
        match = SchoolMatcher.find_matching_nz_school('Auckland Grammar School')
        self.assertEqual(match, self.nz_school1)

    def test_find_matching_nz_school_fuzzy(self):
        """Test finding NZ school with fuzzy name match."""
        # Should find Wellington Girls College even with slightly different name
        match = SchoolMatcher.find_matching_nz_school('Wellington Girls')
        self.assertEqual(match, self.nz_school2)

    def test_find_matching_nz_school_no_match(self):
        """Test when no matching NZ school is found."""
        match = SchoolMatcher.find_matching_nz_school('Unknown School')
        self.assertIsNone(match)

    def test_get_school_contact_details_with_match(self):
        """Test getting contact details when NZ school match is found."""
        details = SchoolMatcher.get_school_contact_details(self.wholesale_school1)

        self.assertEqual(details['address'], 'Mountain Road, Epsom, Auckland')
        self.assertEqual(details['region'], 'Auckland Council')
        self.assertEqual(details['contact_person'], 'John Smith')
        self.assertEqual(details['phone'], '09-123-4567')
        self.assertEqual(details['email'], 'info@ags.school.nz')

    def test_get_school_contact_details_no_match(self):
        """Test getting contact details when no NZ school match is found."""
        details = SchoolMatcher.get_school_contact_details(self.wholesale_school3)

        self.assertEqual(details['address'], 'No address available')
        self.assertEqual(details['region'], 'No region')
        self.assertEqual(details['contact_person'], 'Not specified')
        self.assertEqual(details['phone'], 'Not specified')
        self.assertEqual(details['email'], 'Not specified')

    def test_get_school_contact_details_with_wholesale_data(self):
        """Test when wholesale school has its own contact data."""
        # Add contact data to wholesale school
        self.wholesale_school3.address_line1 = '123 Test Street'
        self.wholesale_school3.city = 'Test City'
        self.wholesale_school3.region = 'Test Region'
        self.wholesale_school3.contact_person = 'Test Person'
        self.wholesale_school3.phone = '555-0000'
        self.wholesale_school3.email = 'test@example.com'
        self.wholesale_school3.save()

        details = SchoolMatcher.get_school_contact_details(self.wholesale_school3)

        self.assertEqual(details['address'], '123 Test Street, Test City, Test Region')
        self.assertEqual(details['region'], 'Test Region')
        self.assertEqual(details['contact_person'], 'Test Person')
        self.assertEqual(details['phone'], '555-0000')
        self.assertEqual(details['email'], 'test@example.com')

    def test_batch_match_schools(self):
        """Test batch matching of multiple schools."""
        wholesale_schools = [
            self.wholesale_school1,
            self.wholesale_school2,
            self.wholesale_school3
        ]

        results = SchoolMatcher.batch_match_schools(wholesale_schools)

        # Check that all schools have results
        self.assertEqual(len(results), 3)
        self.assertIn(self.wholesale_school1.id, results)
        self.assertIn(self.wholesale_school2.id, results)
        self.assertIn(self.wholesale_school3.id, results)

        # Check first school has matched data
        details1 = results[self.wholesale_school1.id]
        self.assertEqual(details1['address'], 'Mountain Road, Epsom, Auckland')
        self.assertEqual(details1['contact_person'], 'John Smith')

        # Check third school has default data (no match)
        details3 = results[self.wholesale_school3.id]
        self.assertEqual(details3['address'], 'No address available')
        self.assertEqual(details3['contact_person'], 'Not specified')

    @patch('authentication.utils.school_matcher.cache')
    def test_caching(self, mock_cache):
        """Test that matching results are cached."""
        mock_cache.get.return_value = None  # No cached value

        # First call should set cache
        SchoolMatcher.find_matching_nz_school('Auckland Grammar School')
        mock_cache.set.assert_called_once()

        # Reset mock
        mock_cache.reset_mock()
        mock_cache.get.return_value = self.nz_school1.id

        # Second call should use cache
        match = SchoolMatcher.find_matching_nz_school('Auckland Grammar School')
        mock_cache.get.assert_called_once()
        self.assertEqual(match, self.nz_school1)

    def test_closed_schools_excluded(self):
        """Test that closed schools are not matched."""
        # Create a closed school
        closed_school = School.objects.create(
            school_id='9999',
            org_name='Closed School',
            status='Closed'
        )

        match = SchoolMatcher.find_matching_nz_school('Closed School')
        self.assertIsNone(match)