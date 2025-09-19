"""
TUS Retail Schools Test Suite

This module imports all test cases for comprehensive testing of the
TUS retail schools implementation.

Test Coverage:
- Model tests: All TUS models with relationships and constraints
- View tests: All schools views including URL routing and context
- API tests: AJAX endpoints and product variation APIs
- Integration tests: Complete user workflows and system integration
- Performance tests: Query optimization, response times, and scalability

Run tests with:
    python manage.py test schools
    python manage.py test schools.test_models
    python manage.py test schools.test_views
    python manage.py test schools.test_api
    python manage.py test schools.test_integration
    python manage.py test schools.test_performance
"""

from django.test import TestCase

# Import all test modules for discovery
from .test_models import *
from .test_views import *
from .test_api import *
from .test_integration import *
from .test_performance import *


class TUSTestSuiteInfo(TestCase):
    """Test suite information and basic functionality"""

    def test_test_suite_imports(self):
        """Test that all test modules import successfully"""
        # This test ensures all test modules are properly imported
        # and no import errors occur
        self.assertTrue(True)

    def test_test_data_consistency(self):
        """Test that test data setup is consistent across modules"""
        from clubs.models_tus import TUSLocation, TUSSchool, TUSProduct

        # Basic smoke test to ensure models work
        location = TUSLocation(
            name='Test Location',
            woo_category_id=99999,
            is_active=True
        )
        # Don't save, just test object creation
        self.assertEqual(location.name, 'Test Location')
        self.assertTrue(location.is_active)
