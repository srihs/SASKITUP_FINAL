"""
Test suite for sync_wholesale_schools management command

This module contains comprehensive tests for the sync_wholesale_schools Django management command:
- Command execution and option parsing
- Dry-run functionality testing
- Filtering options (limit, school-filter)
- Force-update behavior testing
- Error handling and rollback scenarios
- Sync job tracking and statistics
- Transaction handling
"""

import uuid
from io import StringIO
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from freezegun import freeze_time

from clubs.management.commands.sync_wholesale_schools import Command
from clubs.models_wholesale import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment,
    WholesaleSyncJob
)
from clubs.services.cin7_service import CIN7Service


class SyncWholesaleSchoolsCommandTest(TestCase):
    """Test basic command functionality"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()
        self.out = StringIO()
        self.err = StringIO()

    def test_command_help_text(self):
        """Test command help text"""
        self.assertEqual(self.command.help, 'Sync wholesale schools data from CIN7 API')

    def test_add_arguments(self):
        """Test command line argument parsing"""
        parser = Mock()
        self.command.add_arguments(parser)

        # Verify all expected arguments are added
        expected_calls = [
            'dry-run', 'force-update', 'limit', 'school-filter'
        ]

        added_arguments = [call[1][0] for call in parser.add_argument.call_args_list]
        for expected_arg in expected_calls:
            self.assertIn(f'--{expected_arg}', added_arguments)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    @patch.object(Command, '_print_summary')
    def test_command_execution_basic(self, mock_print_summary, mock_cin7_service):
        """Test basic command execution"""
        # Mock CIN7 service
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        # Execute command
        call_command('sync_wholesale_schools', verbosity=0)

        # Verify service was called
        mock_service.test_connection.assert_called_once()
        mock_service.get_all_wholesale_products.assert_called_once()
        mock_print_summary.assert_called_once()

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_command_dry_run_option(self, mock_cin7_service):
        """Test dry-run option functionality"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        # Execute with dry-run
        call_command('sync_wholesale_schools', dry_run=True, verbosity=0)

        # Verify no sync job is created in dry-run mode
        self.assertEqual(WholesaleSyncJob.objects.count(), 0)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_command_connection_failure(self, mock_cin7_service):
        """Test command behavior when CIN7 connection fails"""
        mock_service = Mock()
        mock_service.test_connection.return_value = False
        mock_cin7_service.return_value = mock_service

        with self.assertRaises(CommandError) as context:
            call_command('sync_wholesale_schools', verbosity=0)

        self.assertIn('Failed to connect to CIN7 API', str(context.exception))

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_command_limit_option(self, mock_cin7_service):
        """Test limit option functionality"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True

        # Return more products than limit
        products = [{'ProductId': str(i), 'ProductName': f'Product {i}'} for i in range(20)]
        mock_service.get_all_wholesale_products.return_value = products
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        call_command('sync_wholesale_schools', limit=10, dry_run=True, verbosity=0)

        # Verify organize_products_by_school was called with limited products
        organize_call_args = mock_service.organize_products_by_school.call_args[0][0]
        self.assertEqual(len(organize_call_args), 10)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_command_school_filter_option(self, mock_cin7_service):
        """Test school filter option functionality"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []

        # Mock schools data
        schools_data = {
            'Test High School': {'info': {}, 'products': []},
            'Another School': {'info': {}, 'products': []},
            'Different Academy': {'info': {}, 'products': []}
        }
        mock_service.organize_products_by_school.return_value = schools_data
        mock_cin7_service.return_value = mock_service

        # Mock _process_school to track which schools are processed
        with patch.object(Command, '_process_school') as mock_process:
            call_command('sync_wholesale_schools', school_filter='High', dry_run=True, verbosity=0)

            # Should only process schools matching filter
            mock_process.assert_called_once()
            processed_school_name = mock_process.call_args[0][0]
            self.assertEqual(processed_school_name, 'Test High School')

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_command_no_products_found(self, mock_cin7_service):
        """Test command behavior when no products are found"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_cin7_service.return_value = mock_service

        # Capture output
        out = StringIO()
        call_command('sync_wholesale_schools', dry_run=True, verbosity=1, stdout=out)

        output = out.getvalue()
        self.assertIn('No wholesale products found', output)

    def test_command_verbosity_levels(self):
        """Test different verbosity levels"""
        with patch('clubs.management.commands.sync_wholesale_schools.CIN7Service') as mock_cin7_service:
            mock_service = Mock()
            mock_service.test_connection.return_value = True
            mock_service.get_all_wholesale_products.return_value = []
            mock_service.organize_products_by_school.return_value = {}
            mock_cin7_service.return_value = mock_service

            # Test verbosity 0 (minimal output)
            out0 = StringIO()
            call_command('sync_wholesale_schools', dry_run=True, verbosity=0, stdout=out0)
            output0 = out0.getvalue()

            # Test verbosity 2 (detailed output)
            out2 = StringIO()
            call_command('sync_wholesale_schools', dry_run=True, verbosity=2, stdout=out2)
            output2 = out2.getvalue()

            # Verbosity 2 should have more output
            self.assertGreater(len(output2), len(output0))


class SyncCommandSchoolProcessingTest(TestCase):
    """Test school processing logic"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()

    def test_process_school_record_new_school(self):
        """Test processing a new school record"""
        school_info = {
            'name': 'New Test School',
            'code': 'NTS001',
            'description': 'A new test school',
            'brand': 'Test Brand',
            'category_path': 'Wholesale Schools > New Test School'
        }

        school, created = self.command._process_school_record('New Test School', school_info)

        self.assertTrue(created)
        self.assertEqual(school.name, 'New Test School')
        self.assertEqual(school.school_code, 'NTS001')
        self.assertTrue(school.is_active)

    def test_process_school_record_existing_school(self):
        """Test processing an existing school record"""
        # Create existing school
        existing_school = WholesaleSchool.objects.create(
            cin7_id='EXISTING_001',
            name='Existing School',
            school_code='ES001'
        )

        school_info = {
            'name': 'Existing School',
            'code': 'ES001',
            'description': 'Updated description'
        }

        school, created = self.command._process_school_record('Existing School', school_info)

        self.assertFalse(created)
        self.assertEqual(school.id, existing_school.id)

    def test_process_school_record_force_update(self):
        """Test force update of existing school"""
        self.command.force_update = True

        # Create existing school
        existing_school = WholesaleSchool.objects.create(
            cin7_id='FORCE_001',
            name='Force Update School',
            description='Original description'
        )

        school_info = {
            'name': 'Force Update School',
            'description': 'Updated description'
        }

        school, created = self.command._process_school_record('Force Update School', school_info)

        self.assertFalse(created)
        school.refresh_from_db()
        self.assertEqual(school.description, 'Updated description')

    def test_process_school_record_dry_run(self):
        """Test school processing in dry-run mode"""
        self.command.dry_run = True

        school_info = {
            'name': 'Dry Run School',
            'code': 'DRS001'
        }

        school, created = self.command._process_school_record('Dry Run School', school_info)

        # School should not be saved to database
        self.assertEqual(WholesaleSchool.objects.count(), 0)
        self.assertTrue(hasattr(school, 'name'))
        self.assertEqual(school.name, 'Dry Run School')

    def test_process_school_record_code_lookup(self):
        """Test school lookup by school code"""
        # Create school with specific code
        existing_school = WholesaleSchool.objects.create(
            cin7_id='CODE_001',
            name='Original Name',
            school_code='UNIQUE_CODE'
        )

        school_info = {
            'name': 'Different Name',
            'code': 'UNIQUE_CODE'
        }

        school, created = self.command._process_school_record('Different Name', school_info)

        # Should find existing school by code, not name
        self.assertFalse(created)
        self.assertEqual(school.id, existing_school.id)


class SyncCommandProductProcessingTest(TestCase):
    """Test product processing logic"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()
        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.product_data = {
            'cin7_id': 'PROD_001',
            'name': 'Test Product',
            'description': 'A test product',
            'cin7_sku': 'TEST-001',
            'wholesale_price': Decimal('50.00'),
            'stock_status': 'in_stock',
            'quantity_available': 100
        }

    def test_process_product_new_product(self):
        """Test processing a new product"""
        product, created = self.command._process_product(self.school, self.product_data)

        self.assertTrue(created)
        self.assertEqual(product.name, 'Test Product')
        self.assertEqual(product.school, self.school)
        self.assertEqual(product.wholesale_price, Decimal('50.00'))

    def test_process_product_existing_product(self):
        """Test processing an existing product"""
        # Create existing product
        existing_product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Original Name',
            school=self.school
        )

        product, created = self.command._process_product(self.school, self.product_data)

        self.assertFalse(created)
        self.assertEqual(product.id, existing_product.id)

    def test_process_product_force_update(self):
        """Test force update of existing product"""
        self.command.force_update = True

        # Create existing product
        existing_product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Original Name',
            school=self.school,
            description='Original description'
        )

        product, created = self.command._process_product(self.school, self.product_data)

        self.assertFalse(created)
        product.refresh_from_db()
        self.assertEqual(product.description, 'A test product')

    def test_process_product_missing_cin7_id(self):
        """Test product processing with missing cin7_id"""
        product_data_no_id = self.product_data.copy()
        product_data_no_id['cin7_id'] = ''

        product, created = self.command._process_product(self.school, product_data_no_id)

        # Should generate temporary ID
        self.assertTrue(product.cin7_id.startswith('temp_'))

    def test_process_product_dry_run(self):
        """Test product processing in dry-run mode"""
        self.command.dry_run = True

        product, created = self.command._process_product(self.school, self.product_data)

        # Product should not be saved to database
        self.assertEqual(WholesaleProduct.objects.count(), 0)
        self.assertTrue(hasattr(product, 'name'))
        self.assertEqual(product.name, 'Test Product')


class SyncCommandCategoryProcessingTest(TestCase):
    """Test category processing logic"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()

    def test_process_category_path_simple(self):
        """Test processing simple category path"""
        category_path = "Wholesale Schools > Test School > Sports"
        categories_processed = set()

        categories = self.command._process_category_path(category_path, categories_processed)

        self.assertEqual(len(categories), 3)
        category_names = [cat.name for cat in categories]
        self.assertIn('Wholesale Schools', category_names)
        self.assertIn('Test School', category_names)
        self.assertIn('Sports', category_names)

    def test_process_category_path_empty(self):
        """Test processing empty category path"""
        categories = self.command._process_category_path('', set())
        self.assertEqual(len(categories), 0)

    def test_process_category_path_hierarchy(self):
        """Test category hierarchy is properly created"""
        category_path = "Level 1 > Level 2 > Level 3"
        categories_processed = set()

        categories = self.command._process_category_path(category_path, categories_processed)

        # Verify hierarchy
        level1 = categories[0]
        level2 = categories[1]
        level3 = categories[2]

        self.assertIsNone(level1.parent)
        self.assertEqual(level2.parent, level1)
        self.assertEqual(level3.parent, level2)

    def test_create_category_new(self):
        """Test creating a new category"""
        category, created = self.command._create_category('New Category')

        self.assertTrue(created)
        self.assertEqual(category.name, 'New Category')
        self.assertEqual(category.level, 0)

    def test_create_category_with_parent(self):
        """Test creating category with parent"""
        parent = WholesaleCategory.objects.create(
            cin7_id='PARENT_001',
            name='Parent Category'
        )

        category, created = self.command._create_category('Child Category', parent, level=1)

        self.assertTrue(created)
        self.assertEqual(category.parent, parent)
        self.assertEqual(category.level, 1)

    def test_create_category_dry_run(self):
        """Test category creation in dry-run mode"""
        self.command.dry_run = True

        category, created = self.command._create_category('Dry Run Category')

        # Category should not be saved to database
        self.assertEqual(WholesaleCategory.objects.count(), 0)
        self.assertTrue(hasattr(category, 'name'))

    def test_assign_product_to_category(self):
        """Test product category assignment"""
        school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )
        product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product',
            school=school
        )
        category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Test Category'
        )

        self.command._assign_product_to_category(product, category)

        # Verify assignment was created
        assignment = WholesaleProductCategoryAssignment.objects.get(
            product=product,
            category=category
        )
        self.assertTrue(assignment.is_primary)  # First assignment should be primary

    def test_assign_product_to_category_secondary(self):
        """Test secondary product category assignment"""
        school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )
        product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product',
            school=school
        )

        # Create categories
        primary_category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Primary Category'
        )
        secondary_category = WholesaleCategory.objects.create(
            cin7_id='CAT_002',
            name='Secondary Category'
        )

        # Assign to primary first
        self.command._assign_product_to_category(product, primary_category)

        # Assign to secondary
        self.command._assign_product_to_category(product, secondary_category)

        # Verify assignments
        primary_assignment = WholesaleProductCategoryAssignment.objects.get(
            product=product, category=primary_category
        )
        secondary_assignment = WholesaleProductCategoryAssignment.objects.get(
            product=product, category=secondary_category
        )

        self.assertTrue(primary_assignment.is_primary)
        self.assertFalse(secondary_assignment.is_primary)


class SyncCommandSyncJobTrackingTest(TestCase):
    """Test sync job tracking functionality"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_sync_job_creation(self, mock_cin7_service):
        """Test sync job is created and tracked"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        call_command('sync_wholesale_schools', verbosity=0)

        # Verify sync job was created
        sync_job = WholesaleSyncJob.objects.first()
        self.assertIsNotNone(sync_job)
        self.assertEqual(sync_job.status, 'completed')
        self.assertEqual(sync_job.progress_percentage, 100)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_sync_job_statistics_tracking(self, mock_cin7_service):
        """Test sync job statistics are properly tracked"""
        # Create test data
        school_data = {
            'Test School': {
                'info': {'name': 'Test School'},
                'products': [
                    {'cin7_id': 'PROD_001', 'name': 'Product 1', 'category_path': 'Cat > Sub'},
                    {'cin7_id': 'PROD_002', 'name': 'Product 2', 'category_path': 'Cat > Sub'}
                ]
            }
        }

        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = school_data
        mock_cin7_service.return_value = mock_service

        call_command('sync_wholesale_schools', verbosity=0)

        # Verify statistics
        sync_job = WholesaleSyncJob.objects.first()
        self.assertEqual(sync_job.schools_created, 1)
        self.assertEqual(sync_job.products_created, 2)
        self.assertGreater(sync_job.categories_created, 0)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_sync_job_error_tracking(self, mock_cin7_service):
        """Test sync job error tracking"""
        mock_service = Mock()
        mock_service.test_connection.side_effect = Exception("Connection failed")
        mock_cin7_service.return_value = mock_service

        with self.assertRaises(CommandError):
            call_command('sync_wholesale_schools', verbosity=0)

        # Verify error was tracked
        sync_job = WholesaleSyncJob.objects.first()
        self.assertEqual(sync_job.status, 'failed')
        self.assertGreater(sync_job.errors_count, 0)
        self.assertTrue(len(sync_job.error_messages) > 0)

    def test_sync_job_not_created_in_dry_run(self):
        """Test sync job is not created in dry-run mode"""
        with patch('clubs.management.commands.sync_wholesale_schools.CIN7Service') as mock_cin7_service:
            mock_service = Mock()
            mock_service.test_connection.return_value = True
            mock_service.get_all_wholesale_products.return_value = []
            mock_service.organize_products_by_school.return_value = {}
            mock_cin7_service.return_value = mock_service

            call_command('sync_wholesale_schools', dry_run=True, verbosity=0)

            # No sync job should be created
            self.assertEqual(WholesaleSyncJob.objects.count(), 0)


class SyncCommandTransactionTest(TransactionTestCase):
    """Test transaction handling (using TransactionTestCase for rollback testing)"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_transaction_rollback_on_error(self, mock_cin7_service):
        """Test that errors cause transaction rollback"""
        # Create school data that will cause an error during processing
        school_data = {
            'Error School': {
                'info': {'name': 'Error School'},
                'products': [{'cin7_id': 'PROD_ERROR'}]
            }
        }

        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = school_data
        mock_cin7_service.return_value = mock_service

        # Mock _process_product to raise an exception
        with patch.object(self.command, '_process_product') as mock_process:
            mock_process.side_effect = Exception("Processing error")

            # Execute command
            try:
                call_command('sync_wholesale_schools', verbosity=0)
            except CommandError:
                pass

            # Verify no partial data was saved due to transaction rollback
            self.assertEqual(WholesaleSchool.objects.filter(name='Error School').count(), 0)

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_successful_transaction_commit(self, mock_cin7_service):
        """Test successful transaction commit"""
        school_data = {
            'Success School': {
                'info': {'name': 'Success School'},
                'products': [
                    {'cin7_id': 'PROD_001', 'name': 'Product 1', 'category_path': ''}
                ]
            }
        }

        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = school_data
        mock_cin7_service.return_value = mock_service

        call_command('sync_wholesale_schools', verbosity=0)

        # Verify data was successfully committed
        self.assertTrue(WholesaleSchool.objects.filter(name='Success School').exists())
        self.assertTrue(WholesaleProduct.objects.filter(cin7_id='PROD_001').exists())


class SyncCommandOutputTest(TestCase):
    """Test command output and summary"""

    def setUp(self):
        """Set up test data"""
        self.command = Command()

    @patch('clubs.management.commands.sync_wholesale_schools.CIN7Service')
    def test_summary_output(self, mock_cin7_service):
        """Test summary output formatting"""
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        out = StringIO()
        call_command('sync_wholesale_schools', verbosity=1, stdout=out)

        output = out.getvalue()
        self.assertIn('WHOLESALE SCHOOLS SYNC SUMMARY', output)
        self.assertIn('Statistics:', output)
        self.assertIn('Schools created:', output)
        self.assertIn('Products created:', output)

    def test_print_summary_with_sync_job(self):
        """Test summary printing with sync job data"""
        # Create a sync job with statistics
        sync_job = WholesaleSyncJob.objects.create(
            status='completed',
            schools_created=5,
            products_created=25,
            categories_created=10
        )

        self.command.sync_job = sync_job

        out = StringIO()
        self.command.stdout = out
        self.command._print_summary()

        output = out.getvalue()
        self.assertIn('Schools created: 5', output)
        self.assertIn('Products created: 25', output)
        self.assertIn('Categories created: 10', output)

    def test_print_summary_dry_run(self):
        """Test summary printing for dry run"""
        self.command.dry_run = True
        self.command.sync_job = None

        out = StringIO()
        self.command.stdout = out
        self.command._print_summary()

        output = out.getvalue()
        self.assertIn('DRY RUN - No changes were made', output)

    def test_print_summary_with_errors(self):
        """Test summary printing with errors"""
        sync_job = WholesaleSyncJob.objects.create(
            status='completed',
            errors_count=3,
            error_messages=[
                'Error 1: Connection timeout',
                'Error 2: Invalid data',
                'Error 3: Duplicate entry'
            ]
        )

        self.command.sync_job = sync_job

        out = StringIO()
        self.command.stdout = out
        self.command._print_summary()

        output = out.getvalue()
        self.assertIn('Errors: 3', output)
        self.assertIn('Errors encountered:', output)
        self.assertIn('Error 1: Connection timeout', output)