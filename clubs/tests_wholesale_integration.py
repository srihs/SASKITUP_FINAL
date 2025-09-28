"""
Test suite for wholesale schools API integration

This module contains comprehensive end-to-end integration tests:
- Complete sync process from CIN7 to database
- Data consistency validation after sync
- Sync job status tracking throughout process
- Category hierarchy creation and validation
- Product-to-school assignment verification
- Error recovery and rollback scenarios
- Multi-school and cross-category relationships
"""

import uuid
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from io import StringIO

from schools.models import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment,
    WholesaleSyncJob
)
from clubs.services.cin7_service import CIN7Service


class WholesaleEndToEndSyncTest(TransactionTestCase):
    """Test complete end-to-end sync process"""

    def setUp(self):
        """Set up mock data for comprehensive testing"""
        self.mock_cin7_products = [
            {
                'ProductId': '001',
                'ProductName': 'School A Football Jersey',
                'ProductDescription': 'High-quality football jersey',
                'ShortDescription': 'Football jersey',
                'SKU': 'SA-FB-001',
                'Barcode': '1234567890001',
                'Brand': 'SportsBrand',
                'Supplier': 'SportsSupplier',
                'UnitOfMeasure': 'Each',
                'SellPrice1': '50.00',
                'SellPrice2': '75.00',
                'CostPrice': '30.00',
                'QtyAvailable': 100,
                'QtyOnHand': 120,
                'QtyCommitted': 20,
                'Weight': '0.5',
                'Length': '10',
                'Width': '8',
                'Height': '2',
                'ImageUrl': 'https://example.com/jersey.jpg',
                'CategoryPath': 'Wholesale Schools > School A > Football > Jerseys',
                'Discontinued': False
            },
            {
                'ProductId': '002',
                'ProductName': 'School A Football Shorts',
                'ProductDescription': 'Comfortable football shorts',
                'ShortDescription': 'Football shorts',
                'SKU': 'SA-FB-002',
                'Barcode': '1234567890002',
                'Brand': 'SportsBrand',
                'Supplier': 'SportsSupplier',
                'UnitOfMeasure': 'Each',
                'SellPrice1': '35.00',
                'SellPrice2': '50.00',
                'CostPrice': '20.00',
                'QtyAvailable': 80,
                'QtyOnHand': 100,
                'QtyCommitted': 20,
                'Weight': '0.3',
                'ImageUrl': 'https://example.com/shorts.jpg',
                'CategoryPath': 'Wholesale Schools > School A > Football > Shorts',
                'Discontinued': False
            },
            {
                'ProductId': '003',
                'ProductName': 'School B Basketball Jersey',
                'ProductDescription': 'Premium basketball jersey',
                'ShortDescription': 'Basketball jersey',
                'SKU': 'SB-BB-001',
                'Barcode': '1234567890003',
                'Brand': 'BasketBrand',
                'Supplier': 'BasketSupplier',
                'UnitOfMeasure': 'Each',
                'SellPrice1': '60.00',
                'SellPrice2': '85.00',
                'CostPrice': '35.00',
                'QtyAvailable': 50,
                'QtyOnHand': 60,
                'QtyCommitted': 10,
                'Weight': '0.4',
                'ImageUrl': 'https://example.com/basketball.jpg',
                'CategoryPath': 'Wholesale Schools > School B > Basketball > Jerseys',
                'Discontinued': False
            },
            {
                'ProductId': '004',
                'ProductName': 'School A Multi-Sport Cap',
                'ProductDescription': 'Versatile sports cap',
                'ShortDescription': 'Sports cap',
                'SKU': 'SA-MS-001',
                'Barcode': '1234567890004',
                'Brand': 'CapBrand',
                'Supplier': 'CapSupplier',
                'UnitOfMeasure': 'Each',
                'SellPrice1': '25.00',
                'CostPrice': '15.00',
                'QtyAvailable': 200,
                'QtyOnHand': 250,
                'QtyCommitted': 50,
                'Weight': '0.2',
                'ImageUrl': 'https://example.com/cap.jpg',
                'CategoryPath': 'Wholesale Schools > School A > Accessories > Caps',
                'Discontinued': False
            }
        ]

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_complete_sync_process(self, mock_get_products, mock_test_connection):
        """Test complete sync process from API to database"""
        # Mock CIN7 service responses
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Execute sync
        call_command('sync_wholesale_schools', verbosity=0)

        # Verify sync job was created and completed
        sync_job = WholesaleSyncJob.objects.first()
        self.assertIsNotNone(sync_job)
        self.assertEqual(sync_job.status, 'completed')
        self.assertEqual(sync_job.progress_percentage, 100)

        # Verify schools were created
        schools = WholesaleSchool.objects.all()
        self.assertEqual(len(schools), 2)
        school_names = [school.name for school in schools]
        self.assertIn('School A', school_names)
        self.assertIn('School B', school_names)

        # Verify products were created
        products = WholesaleProduct.objects.all()
        self.assertEqual(len(products), 4)

        # Verify categories were created with proper hierarchy
        categories = WholesaleCategory.objects.all()
        self.assertGreater(len(categories), 0)

        # Test category hierarchy
        wholesale_schools_cat = WholesaleCategory.objects.filter(
            name='Wholesale Schools',
            parent__isnull=True
        ).first()
        self.assertIsNotNone(wholesale_schools_cat)

        school_a_cat = WholesaleCategory.objects.filter(
            name='School A',
            parent=wholesale_schools_cat
        ).first()
        self.assertIsNotNone(school_a_cat)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_data_consistency_after_sync(self, mock_get_products, mock_test_connection):
        """Test data consistency and relationships after sync"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Test School A data consistency
        school_a = WholesaleSchool.objects.get(name='School A')
        self.assertTrue(school_a.is_active)
        self.assertIsNotNone(school_a.last_synced_at)

        # Test product relationships
        school_a_products = WholesaleProduct.objects.filter(school=school_a)
        self.assertEqual(len(school_a_products), 3)  # Jersey, Shorts, Cap

        # Test specific product data
        jersey = WholesaleProduct.objects.get(cin7_id='001')
        self.assertEqual(jersey.name, 'School A Football Jersey')
        self.assertEqual(jersey.school, school_a)
        self.assertEqual(jersey.wholesale_price, Decimal('50.00'))
        self.assertEqual(jersey.retail_price, Decimal('75.00'))
        self.assertEqual(jersey.cost_price, Decimal('30.00'))
        self.assertEqual(jersey.stock_status, 'in_stock')
        self.assertEqual(jersey.quantity_available, 100)

        # Test product-category assignments
        jersey_assignments = WholesaleProductCategoryAssignment.objects.filter(product=jersey)
        self.assertGreater(len(jersey_assignments), 0)

        # Test categories have proper product counts
        for assignment in jersey_assignments:
            category = assignment.category
            self.assertGreater(category.product_count, 0)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_job_statistics_tracking(self, mock_get_products, mock_test_connection):
        """Test sync job statistics are accurately tracked"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        sync_job = WholesaleSyncJob.objects.first()

        # Verify statistics
        self.assertEqual(sync_job.schools_created, 2)  # School A and School B
        self.assertEqual(sync_job.products_created, 4)  # All 4 products
        self.assertGreater(sync_job.categories_created, 0)  # Various categories
        self.assertEqual(sync_job.errors_count, 0)  # No errors

        # Verify timing
        self.assertIsNotNone(sync_job.started_at)
        self.assertIsNotNone(sync_job.completed_at)
        self.assertGreater(sync_job.completed_at, sync_job.started_at)

        # Verify total items processed
        total_items = sync_job.total_items_processed
        expected_minimum = sync_job.schools_created + sync_job.products_created
        self.assertGreaterEqual(total_items, expected_minimum)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_category_hierarchy_creation(self, mock_get_products, mock_test_connection):
        """Test complete category hierarchy is created correctly"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Test root category
        root_category = WholesaleCategory.objects.filter(
            name='Wholesale Schools',
            level=0,
            parent__isnull=True
        ).first()
        self.assertIsNotNone(root_category)

        # Test school level categories
        school_categories = WholesaleCategory.objects.filter(
            name__in=['School A', 'School B'],
            level=1,
            parent=root_category
        )
        self.assertEqual(len(school_categories), 2)

        # Test sport level categories
        sport_categories = WholesaleCategory.objects.filter(
            name__in=['Football', 'Basketball', 'Accessories'],
            level=2
        )
        self.assertGreater(len(sport_categories), 0)

        # Test product type categories
        product_type_categories = WholesaleCategory.objects.filter(
            name__in=['Jerseys', 'Shorts', 'Caps'],
            level=3
        )
        self.assertGreater(len(product_type_categories), 0)

        # Test hierarchy relationships
        school_a_cat = WholesaleCategory.objects.get(name='School A', level=1)
        football_cat = WholesaleCategory.objects.filter(
            name='Football',
            parent=school_a_cat
        ).first()
        if football_cat:
            jerseys_cat = WholesaleCategory.objects.filter(
                name='Jerseys',
                parent=football_cat
            ).first()
            self.assertIsNotNone(jerseys_cat)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_product_category_assignments(self, mock_get_products, mock_test_connection):
        """Test products are correctly assigned to categories"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Test jersey assignments
        jersey = WholesaleProduct.objects.get(cin7_id='001')
        jersey_categories = jersey.categories.all()
        self.assertGreater(len(jersey_categories), 0)

        # Test primary category assignment
        primary_assignment = WholesaleProductCategoryAssignment.objects.filter(
            product=jersey,
            is_primary=True
        ).first()
        self.assertIsNotNone(primary_assignment)

        # Test that multi-sport cap is in accessories category
        cap = WholesaleProduct.objects.get(cin7_id='004')
        cap_categories = cap.categories.all()
        category_names = [cat.name for cat in cap_categories]
        self.assertIn('Accessories', category_names)

        # Test assignment metadata
        for assignment in WholesaleProductCategoryAssignment.objects.filter(product=jersey):
            self.assertIsNotNone(assignment.assigned_at)
            self.assertEqual(assignment.sort_order, 0)  # Default sort order

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_idempotent_sync_behavior(self, mock_get_products, mock_test_connection):
        """Test that running sync multiple times doesn't create duplicates"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Run sync twice
        call_command('sync_wholesale_schools', verbosity=0)
        call_command('sync_wholesale_schools', verbosity=0)

        # Verify no duplicates were created
        schools = WholesaleSchool.objects.all()
        self.assertEqual(len(schools), 2)

        products = WholesaleProduct.objects.all()
        self.assertEqual(len(products), 4)

        # Verify unique constraints are respected
        cin7_ids = [product.cin7_id for product in products]
        self.assertEqual(len(cin7_ids), len(set(cin7_ids)))

        # Verify second sync updated statistics
        sync_jobs = WholesaleSyncJob.objects.all().order_by('created_at')
        self.assertEqual(len(sync_jobs), 2)

        second_sync = sync_jobs[1]
        self.assertEqual(second_sync.schools_updated, 2)  # Updated existing schools
        self.assertEqual(second_sync.products_updated, 4)  # Updated existing products

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_force_update_behavior(self, mock_get_products, mock_test_connection):
        """Test force update behavior updates existing records"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Initial sync
        call_command('sync_wholesale_schools', verbosity=0)

        # Modify existing data
        school = WholesaleSchool.objects.get(name='School A')
        original_description = school.description
        school.description = 'Modified description'
        school.save()

        product = WholesaleProduct.objects.get(cin7_id='001')
        original_price = product.wholesale_price
        product.wholesale_price = Decimal('999.99')
        product.save()

        # Run force update sync
        call_command('sync_wholesale_schools', force_update=True, verbosity=0)

        # Verify data was restored from API
        school.refresh_from_db()
        product.refresh_from_db()

        self.assertNotEqual(school.description, 'Modified description')
        self.assertNotEqual(product.wholesale_price, Decimal('999.99'))

    def test_error_recovery_and_rollback(self):
        """Test error handling and transaction rollback"""
        with patch('clubs.services.cin7_service.CIN7Service.test_connection') as mock_connection:
            # Test connection failure
            mock_connection.return_value = False

            with self.assertRaises(Exception):
                call_command('sync_wholesale_schools', verbosity=0)

            # Verify no partial data was created
            self.assertEqual(WholesaleSchool.objects.count(), 0)
            self.assertEqual(WholesaleProduct.objects.count(), 0)

        # Test API failure after connection success
        with patch('clubs.services.cin7_service.CIN7Service.test_connection') as mock_connection:
            with patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products') as mock_get_products:
                mock_connection.return_value = True
                mock_get_products.side_effect = Exception("API Error")

                with self.assertRaises(Exception):
                    call_command('sync_wholesale_schools', verbosity=0)

                # Verify sync job recorded the error
                sync_job = WholesaleSyncJob.objects.first()
                if sync_job:
                    self.assertEqual(sync_job.status, 'failed')
                    self.assertGreater(sync_job.errors_count, 0)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_partial_sync_with_limit(self, mock_get_products, mock_test_connection):
        """Test sync with limit option processes correct number of products"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Sync with limit of 2 products
        call_command('sync_wholesale_schools', limit=2, verbosity=0)

        # Verify only first 2 products were processed
        products = WholesaleProduct.objects.all()
        self.assertEqual(len(products), 2)

        # Verify they are the first 2 products from the mock data
        product_ids = [product.cin7_id for product in products]
        self.assertIn('001', product_ids)
        self.assertIn('002', product_ids)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_school_filter_functionality(self, mock_get_products, mock_test_connection):
        """Test school filter option processes only matching schools"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Sync with school filter
        call_command('sync_wholesale_schools', school_filter='School A', verbosity=0)

        # Verify only School A was processed
        schools = WholesaleSchool.objects.all()
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0].name, 'School A')

        # Verify only School A products were processed
        products = WholesaleProduct.objects.all()
        self.assertEqual(len(products), 3)  # Jersey, Shorts, Cap

        for product in products:
            self.assertEqual(product.school.name, 'School A')

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_dry_run_no_database_changes(self, mock_get_products, mock_test_connection):
        """Test dry run mode makes no database changes"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        # Record initial counts
        initial_schools = WholesaleSchool.objects.count()
        initial_products = WholesaleProduct.objects.count()
        initial_categories = WholesaleCategory.objects.count()
        initial_sync_jobs = WholesaleSyncJob.objects.count()

        # Run dry run sync
        call_command('sync_wholesale_schools', dry_run=True, verbosity=0)

        # Verify no changes to database
        self.assertEqual(WholesaleSchool.objects.count(), initial_schools)
        self.assertEqual(WholesaleProduct.objects.count(), initial_products)
        self.assertEqual(WholesaleCategory.objects.count(), initial_categories)
        self.assertEqual(WholesaleSyncJob.objects.count(), initial_sync_jobs)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_updates_school_statistics(self, mock_get_products, mock_test_connection):
        """Test sync updates school product counts and statistics"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Verify school statistics were updated
        school_a = WholesaleSchool.objects.get(name='School A')
        self.assertEqual(school_a.total_products, 3)  # Jersey, Shorts, Cap
        self.assertIsNotNone(school_a.last_synced_at)

        school_b = WholesaleSchool.objects.get(name='School B')
        self.assertEqual(school_b.total_products, 1)  # Basketball Jersey
        self.assertIsNotNone(school_b.last_synced_at)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_cross_category_product_relationships(self, mock_get_products, mock_test_connection):
        """Test products can belong to multiple categories"""
        # Add a product that could belong to multiple categories
        multi_category_product = {
            'ProductId': '005',
            'ProductName': 'School A Training Jersey',
            'ProductDescription': 'Multi-purpose training jersey',
            'SKU': 'SA-TR-001',
            'SellPrice1': '45.00',
            'CategoryPath': 'Wholesale Schools > School A > Football > Training Gear',
        }

        extended_products = self.mock_cin7_products + [multi_category_product]
        mock_test_connection.return_value = True
        mock_get_products.return_value = extended_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Find the training jersey
        training_jersey = WholesaleProduct.objects.get(cin7_id='005')

        # Verify it's assigned to categories
        assignments = WholesaleProductCategoryAssignment.objects.filter(product=training_jersey)
        self.assertGreater(len(assignments), 0)

        # Verify category relationships
        categories = training_jersey.categories.all()
        category_names = [cat.name for cat in categories]
        self.assertIn('Training Gear', category_names)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_handles_empty_product_list(self, mock_get_products, mock_test_connection):
        """Test sync handles empty product list gracefully"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = []

        # Capture output
        out = StringIO()
        call_command('sync_wholesale_schools', verbosity=1, stdout=out)

        output = out.getvalue()
        self.assertIn('No wholesale products found', output)

        # Verify no data was created
        self.assertEqual(WholesaleSchool.objects.count(), 0)
        self.assertEqual(WholesaleProduct.objects.count(), 0)

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_progress_tracking(self, mock_get_products, mock_test_connection):
        """Test sync job progress is tracked throughout process"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        sync_job = WholesaleSyncJob.objects.first()

        # Verify progress reached 100%
        self.assertEqual(sync_job.progress_percentage, 100)

        # Verify final step
        self.assertEqual(sync_job.current_step, 'Sync completed')

        # Verify status progression
        self.assertEqual(sync_job.status, 'completed')

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_data_integrity_constraints(self, mock_get_products, mock_test_connection):
        """Test data integrity constraints are maintained"""
        mock_test_connection.return_value = True
        mock_get_products.return_value = self.mock_cin7_products

        call_command('sync_wholesale_schools', verbosity=0)

        # Test school uniqueness by cin7_id
        schools = WholesaleSchool.objects.all()
        cin7_ids = [school.cin7_id for school in schools]
        self.assertEqual(len(cin7_ids), len(set(cin7_ids)))

        # Test product uniqueness by cin7_id
        products = WholesaleProduct.objects.all()
        product_cin7_ids = [product.cin7_id for product in products]
        self.assertEqual(len(product_cin7_ids), len(set(product_cin7_ids)))

        # Test category uniqueness by cin7_id
        categories = WholesaleCategory.objects.all()
        category_cin7_ids = [cat.cin7_id for cat in categories]
        self.assertEqual(len(category_cin7_ids), len(set(category_cin7_ids)))

        # Test product-category assignment uniqueness
        assignments = WholesaleProductCategoryAssignment.objects.all()
        assignment_pairs = [(a.product_id, a.category_id) for a in assignments]
        self.assertEqual(len(assignment_pairs), len(set(assignment_pairs)))


class WholesaleDataValidationTest(TestCase):
    """Test data validation and business logic during sync"""

    def setUp(self):
        """Set up test data"""
        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Validation Test School'
        )

    def test_product_price_validation(self):
        """Test product price field validation"""
        # Test valid prices
        valid_product = WholesaleProduct.objects.create(
            cin7_id='VALID_PROD',
            name='Valid Product',
            school=self.school,
            wholesale_price=Decimal('50.00'),
            retail_price=Decimal('75.00'),
            cost_price=Decimal('30.00')
        )

        self.assertIsNotNone(valid_product.profit_margin)
        self.assertAlmostEqual(float(valid_product.profit_margin), 66.67, places=1)

    def test_stock_status_validation(self):
        """Test stock status field validation"""
        valid_statuses = ['in_stock', 'out_of_stock', 'discontinued', 'on_order']

        for status in valid_statuses:
            product = WholesaleProduct.objects.create(
                cin7_id=f'STOCK_TEST_{status}',
                name=f'Product {status}',
                school=self.school,
                stock_status=status
            )
            self.assertEqual(product.stock_status, status)

    def test_category_hierarchy_validation(self):
        """Test category hierarchy constraints"""
        # Create parent category
        parent = WholesaleCategory.objects.create(
            cin7_id='PARENT_VAL',
            name='Parent Category',
            level=0
        )

        # Create child category
        child = WholesaleCategory.objects.create(
            cin7_id='CHILD_VAL',
            name='Child Category',
            parent=parent,
            level=1
        )

        # Verify relationship
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.subcategories.all())

    def test_product_category_assignment_validation(self):
        """Test product category assignment business rules"""
        category = WholesaleCategory.objects.create(
            cin7_id='CAT_VAL',
            name='Test Category'
        )

        product = WholesaleProduct.objects.create(
            cin7_id='PROD_VAL',
            name='Test Product',
            school=self.school
        )

        # Create first assignment (should be primary)
        assignment1 = WholesaleProductCategoryAssignment.objects.create(
            product=product,
            category=category,
            is_primary=True
        )

        # Test unique constraint for product-category pairs
        with self.assertRaises(Exception):
            WholesaleProductCategoryAssignment.objects.create(
                product=product,
                category=category
            )

    def test_sync_job_state_transitions(self):
        """Test sync job state transition logic"""
        sync_job = WholesaleSyncJob.objects.create()

        # Test initial state
        self.assertEqual(sync_job.status, 'pending')
        self.assertEqual(sync_job.progress_percentage, 0)

        # Test running state
        sync_job.status = 'running'
        sync_job.started_at = timezone.now()
        sync_job.progress_percentage = 50
        sync_job.save()

        self.assertEqual(sync_job.status, 'running')
        self.assertIsNotNone(sync_job.started_at)

        # Test completion
        sync_job.status = 'completed'
        sync_job.completed_at = timezone.now()
        sync_job.progress_percentage = 100
        sync_job.save()

        self.assertIsNotNone(sync_job.duration)
        self.assertGreater(sync_job.completed_at, sync_job.started_at)

    def test_school_slug_generation(self):
        """Test school slug auto-generation and uniqueness"""
        school1 = WholesaleSchool.objects.create(
            cin7_id='SLUG_001',
            name='Test School Name'
        )

        self.assertEqual(school1.slug, 'test-school-name')

        # Test that duplicates are handled
        with self.assertRaises(Exception):
            WholesaleSchool.objects.create(
                cin7_id='SLUG_002',
                name='Test School Name'  # Same name, should conflict on slug
            )

    def test_product_variation_constraints(self):
        """Test product variation uniqueness constraints"""
        product = WholesaleProduct.objects.create(
            cin7_id='VAR_PROD',
            name='Variation Product',
            school=self.school
        )

        # Create first variation
        variation1 = WholesaleProductVariation.objects.create(
            cin7_id='VAR_001',
            product=product,
            variation_type='size',
            variation_value='Large'
        )

        # Test unique constraint on (product, variation_type, variation_value)
        with self.assertRaises(Exception):
            WholesaleProductVariation.objects.create(
                cin7_id='VAR_002',  # Different CIN7 ID
                product=product,
                variation_type='size',
                variation_value='Large'  # Same type and value
            )