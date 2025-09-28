"""
Test suite for wholesale schools models

This module contains comprehensive tests for all wholesale school models:
- WholesaleSchool
- WholesaleCategory
- WholesaleProduct
- WholesaleProductVariation
- WholesaleProductCategoryAssignment
- WholesaleSyncJob
"""

import uuid
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from django.urls import reverse
from freezegun import freeze_time

from schools.models import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment,
    WholesaleSyncJob
)


class WholesaleSchoolModelTest(TestCase):
    """Test cases for WholesaleSchool model"""

    def setUp(self):
        """Set up test data"""
        self.school_data = {
            'cin7_id': 'TEST_SCHOOL_001',
            'name': 'Test High School',
            'description': 'A test high school for sporting excellence',
            'school_code': 'THS001',
            'contact_person': 'John Doe',
            'email': 'contact@testschool.edu',
            'phone': '555-0123',
            'website': 'https://testschool.edu',
            'address_line1': '123 Test Street',
            'address_line2': 'Suite 100',
            'city': 'Test City',
            'region': 'Test Region',
            'postal_code': '12345',
            'country': 'New Zealand',
            'cin7_sku': 'THS-SKU-001',
            'cin7_barcode': '1234567890123',
            'cin7_brand': 'Test Brand',
            'cin7_supplier': 'Test Supplier',
            'cin7_category_path': 'Wholesale Schools > Test High School > Sports'
        }

    def test_school_creation(self):
        """Test basic school creation"""
        school = WholesaleSchool.objects.create(**self.school_data)

        self.assertEqual(school.name, 'Test High School')
        self.assertEqual(school.cin7_id, 'TEST_SCHOOL_001')
        self.assertEqual(school.school_code, 'THS001')
        self.assertTrue(school.is_active)
        self.assertEqual(school.total_products, 0)
        self.assertEqual(school.active_categories, 0)
        self.assertEqual(school.country, 'New Zealand')

    def test_school_creation_minimal_data(self):
        """Test school creation with minimal required data"""
        minimal_data = {
            'cin7_id': 'MIN_001',
            'name': 'Minimal School'
        }
        school = WholesaleSchool.objects.create(**minimal_data)

        self.assertEqual(school.name, 'Minimal School')
        self.assertEqual(school.cin7_id, 'MIN_001')
        self.assertEqual(school.country, 'New Zealand')  # Default value
        self.assertTrue(school.is_active)  # Default value

    def test_school_slug_auto_generation(self):
        """Test that slug is automatically generated from name"""
        school = WholesaleSchool.objects.create(
            cin7_id='SLUG_TEST_001',
            name='Test School With Spaces'
        )

        self.assertEqual(school.slug, 'test-school-with-spaces')

    def test_school_slug_uniqueness(self):
        """Test that slug uniqueness is enforced"""
        WholesaleSchool.objects.create(
            cin7_id='UNIQUE_001',
            name='Unique School'
        )

        with self.assertRaises(IntegrityError):
            WholesaleSchool.objects.create(
                cin7_id='UNIQUE_002',
                name='Unique School'  # Same name, should create same slug
            )

    def test_cin7_id_uniqueness(self):
        """Test that cin7_id must be unique"""
        WholesaleSchool.objects.create(**self.school_data)

        duplicate_data = self.school_data.copy()
        duplicate_data['name'] = 'Different School Name'

        with self.assertRaises(IntegrityError):
            WholesaleSchool.objects.create(**duplicate_data)

    def test_school_str_representation(self):
        """Test string representation of school"""
        school = WholesaleSchool.objects.create(**self.school_data)
        self.assertEqual(str(school), 'Test High School')

    def test_school_get_absolute_url(self):
        """Test get_absolute_url method"""
        school = WholesaleSchool.objects.create(**self.school_data)
        expected_url = reverse('clubs:wholesale-school-detail', kwargs={'slug': school.slug})
        self.assertEqual(school.get_absolute_url(), expected_url)

    def test_full_address_property(self):
        """Test full_address property formatting"""
        school = WholesaleSchool.objects.create(**self.school_data)
        expected_address = '123 Test Street, Suite 100, Test City, Test Region, 12345'
        self.assertEqual(school.full_address, expected_address)

    def test_full_address_property_partial_data(self):
        """Test full_address property with missing address components"""
        partial_data = self.school_data.copy()
        partial_data.update({
            'address_line1': '123 Main St',
            'address_line2': '',  # Empty
            'city': 'Sample City',
            'region': '',  # Empty
            'postal_code': '54321'
        })

        school = WholesaleSchool.objects.create(**partial_data)
        expected_address = '123 Main St, Sample City, 54321'
        self.assertEqual(school.full_address, expected_address)

    def test_email_validation(self):
        """Test email field validation"""
        invalid_data = self.school_data.copy()
        invalid_data['email'] = 'invalid-email'

        school = WholesaleSchool(**invalid_data)
        with self.assertRaises(ValidationError):
            school.full_clean()

    def test_website_validation(self):
        """Test website URL validation"""
        invalid_data = self.school_data.copy()
        invalid_data['website'] = 'not-a-url'

        school = WholesaleSchool(**invalid_data)
        with self.assertRaises(ValidationError):
            school.full_clean()

    @freeze_time("2024-01-15 10:30:00")
    def test_timestamp_fields(self):
        """Test automatic timestamp field population"""
        school = WholesaleSchool.objects.create(**self.school_data)

        self.assertIsNotNone(school.created_at)
        self.assertIsNotNone(school.updated_at)
        self.assertEqual(school.created_at, school.updated_at)

    def test_school_indexing(self):
        """Test that database indexes are properly created"""
        # This test verifies that the model can be queried efficiently
        # by the indexed fields
        schools = []
        for i in range(10):
            school_data = self.school_data.copy()
            school_data['cin7_id'] = f'TEST_{i:03d}'
            school_data['name'] = f'School {i}'
            schools.append(WholesaleSchool.objects.create(**school_data))

        # Test querying by indexed fields
        result = WholesaleSchool.objects.filter(name__icontains='School').count()
        self.assertEqual(result, 10)

        result = WholesaleSchool.objects.filter(cin7_id='TEST_005').first()
        self.assertEqual(result.name, 'School 5')

        result = WholesaleSchool.objects.filter(is_active=True).count()
        self.assertEqual(result, 10)


class WholesaleCategoryModelTest(TestCase):
    """Test cases for WholesaleCategory model"""

    def setUp(self):
        """Set up test data"""
        self.category_data = {
            'cin7_id': 'CAT_001',
            'name': 'Sports Equipment',
            'description': 'Equipment for various sports',
            'level': 0,
            'path': 'Sports Equipment'
        }

    def test_category_creation(self):
        """Test basic category creation"""
        category = WholesaleCategory.objects.create(**self.category_data)

        self.assertEqual(category.name, 'Sports Equipment')
        self.assertEqual(category.cin7_id, 'CAT_001')
        self.assertEqual(category.level, 0)
        self.assertIsNone(category.parent)
        self.assertTrue(category.is_active)
        self.assertEqual(category.product_count, 0)

    def test_category_hierarchy_creation(self):
        """Test creation of hierarchical categories"""
        # Create parent category
        parent = WholesaleCategory.objects.create(
            cin7_id='PARENT_001',
            name='Sports',
            level=0,
            path='Sports'
        )

        # Create child category
        child = WholesaleCategory.objects.create(
            cin7_id='CHILD_001',
            name='Football Equipment',
            parent=parent,
            level=1,
            path='Sports > Football Equipment'
        )

        self.assertEqual(child.parent, parent)
        self.assertEqual(child.level, 1)
        self.assertIn(child, parent.subcategories.all())

    def test_category_slug_auto_generation(self):
        """Test that slug is automatically generated"""
        category = WholesaleCategory.objects.create(
            cin7_id='SLUG_001',
            name='Category With Spaces & Special-Chars!'
        )

        self.assertEqual(category.slug, 'category-with-spaces-special-chars')

    def test_category_str_representation(self):
        """Test string representation"""
        category = WholesaleCategory.objects.create(**self.category_data)
        self.assertEqual(str(category), 'Sports Equipment')

    def test_category_uniqueness_constraints(self):
        """Test cin7_id and slug uniqueness"""
        WholesaleCategory.objects.create(**self.category_data)

        # Test cin7_id uniqueness
        duplicate_data = self.category_data.copy()
        duplicate_data['name'] = 'Different Name'

        with self.assertRaises(IntegrityError):
            WholesaleCategory.objects.create(**duplicate_data)

    def test_category_deletion_cascade(self):
        """Test that deleting parent category cascades to children"""
        parent = WholesaleCategory.objects.create(
            cin7_id='CASCADE_PARENT',
            name='Parent Category'
        )

        child = WholesaleCategory.objects.create(
            cin7_id='CASCADE_CHILD',
            name='Child Category',
            parent=parent
        )

        parent_id = parent.id
        child_id = child.id

        parent.delete()

        # Both parent and child should be deleted
        self.assertFalse(WholesaleCategory.objects.filter(id=parent_id).exists())
        self.assertFalse(WholesaleCategory.objects.filter(id=child_id).exists())

    def test_deep_category_hierarchy(self):
        """Test creation of deep category hierarchy"""
        level0 = WholesaleCategory.objects.create(
            cin7_id='L0', name='Level 0', level=0, path='Level 0'
        )
        level1 = WholesaleCategory.objects.create(
            cin7_id='L1', name='Level 1', parent=level0, level=1, path='Level 0 > Level 1'
        )
        level2 = WholesaleCategory.objects.create(
            cin7_id='L2', name='Level 2', parent=level1, level=2, path='Level 0 > Level 1 > Level 2'
        )

        self.assertEqual(level2.parent.parent, level0)
        self.assertEqual(level0.subcategories.first().subcategories.first(), level2)


class WholesaleProductModelTest(TestCase):
    """Test cases for WholesaleProduct model"""

    def setUp(self):
        """Set up test data"""
        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Test Category'
        )

        self.product_data = {
            'cin7_id': 'PROD_001',
            'name': 'Test Product',
            'school': self.school,
            'description': 'A test product for testing',
            'short_description': 'Test product',
            'cin7_sku': 'TEST-SKU-001',
            'cin7_barcode': '1234567890123',
            'cin7_brand': 'Test Brand',
            'cin7_supplier': 'Test Supplier',
            'cin7_unit_of_measure': 'Each',
            'wholesale_price': Decimal('50.00'),
            'retail_price': Decimal('75.00'),
            'cost_price': Decimal('30.00'),
            'stock_status': 'in_stock',
            'quantity_available': 100,
            'quantity_on_hand': 120,
            'quantity_committed': 20,
            'weight': Decimal('1.500'),
            'dimensions': {'length': 10, 'width': 5, 'height': 3},
            'attributes': {'color': 'blue', 'size': 'medium'},
            'image_url': 'https://example.com/image.jpg'
        }

    def test_product_creation(self):
        """Test basic product creation"""
        product = WholesaleProduct.objects.create(**self.product_data)

        self.assertEqual(product.name, 'Test Product')
        self.assertEqual(product.cin7_id, 'PROD_001')
        self.assertEqual(product.school, self.school)
        self.assertEqual(product.wholesale_price, Decimal('50.00'))
        self.assertEqual(product.stock_status, 'in_stock')
        self.assertTrue(product.is_active)

    def test_product_slug_auto_generation(self):
        """Test slug auto-generation from name and SKU"""
        product = WholesaleProduct.objects.create(**self.product_data)
        expected_slug = 'test-product-test-sku-001'
        self.assertEqual(product.slug, expected_slug)

    def test_product_str_representation(self):
        """Test string representation"""
        product = WholesaleProduct.objects.create(**self.product_data)
        expected_str = f"{product.name} - {self.school.name}"
        self.assertEqual(str(product), expected_str)

    def test_is_in_stock_property(self):
        """Test is_in_stock property logic"""
        # Test in stock
        product = WholesaleProduct.objects.create(**self.product_data)
        self.assertTrue(product.is_in_stock)

        # Test out of stock - quantity zero
        product.quantity_available = 0
        product.save()
        self.assertFalse(product.is_in_stock)

        # Test out of stock - status
        product.quantity_available = 100
        product.stock_status = 'out_of_stock'
        product.save()
        self.assertFalse(product.is_in_stock)

    def test_profit_margin_property(self):
        """Test profit margin calculation"""
        product = WholesaleProduct.objects.create(**self.product_data)

        # Expected: ((50 - 30) / 30) * 100 = 66.67%
        expected_margin = ((Decimal('50.00') - Decimal('30.00')) / Decimal('30.00')) * 100
        self.assertAlmostEqual(float(product.profit_margin), float(expected_margin), places=2)

    def test_profit_margin_property_missing_prices(self):
        """Test profit margin with missing price data"""
        product_data = self.product_data.copy()
        product_data['cost_price'] = None
        product = WholesaleProduct.objects.create(**product_data)

        self.assertIsNone(product.profit_margin)

    def test_profit_margin_property_zero_cost(self):
        """Test profit margin with zero cost price"""
        product_data = self.product_data.copy()
        product_data['cost_price'] = Decimal('0.00')
        product = WholesaleProduct.objects.create(**product_data)

        self.assertIsNone(product.profit_margin)

    def test_primary_category_property(self):
        """Test primary_category property"""
        product = WholesaleProduct.objects.create(**self.product_data)

        # Initially no categories
        self.assertIsNone(product.primary_category)

        # Add category assignment
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=product,
            category=self.category,
            is_primary=True
        )

        self.assertEqual(product.primary_category, self.category)

    def test_product_stock_status_choices(self):
        """Test stock status choices validation"""
        valid_statuses = ['in_stock', 'out_of_stock', 'discontinued', 'on_order']

        for status in valid_statuses:
            product_data = self.product_data.copy()
            product_data['cin7_id'] = f'PROD_{status}'
            product_data['stock_status'] = status
            product = WholesaleProduct.objects.create(**product_data)
            self.assertEqual(product.stock_status, status)

    def test_product_uniqueness_constraints(self):
        """Test cin7_id uniqueness"""
        WholesaleProduct.objects.create(**self.product_data)

        duplicate_data = self.product_data.copy()
        duplicate_data['name'] = 'Different Product'

        with self.assertRaises(IntegrityError):
            WholesaleProduct.objects.create(**duplicate_data)

    def test_product_json_fields(self):
        """Test JSON field storage and retrieval"""
        product = WholesaleProduct.objects.create(**self.product_data)

        # Test dimensions JSON field
        self.assertEqual(product.dimensions['length'], 10)
        self.assertEqual(product.dimensions['width'], 5)

        # Test attributes JSON field
        self.assertEqual(product.attributes['color'], 'blue')
        self.assertEqual(product.attributes['size'], 'medium')

    def test_product_decimal_fields_precision(self):
        """Test decimal field precision handling"""
        product_data = self.product_data.copy()
        product_data.update({
            'wholesale_price': Decimal('99999999.99'),  # Max digits test
            'weight': Decimal('99999.999')  # Max decimal places test
        })

        product = WholesaleProduct.objects.create(**product_data)
        self.assertEqual(product.wholesale_price, Decimal('99999999.99'))
        self.assertEqual(product.weight, Decimal('99999.999'))

    def test_product_school_relationship(self):
        """Test foreign key relationship with school"""
        product = WholesaleProduct.objects.create(**self.product_data)

        # Test forward relationship
        self.assertEqual(product.school, self.school)

        # Test reverse relationship
        self.assertIn(product, self.school.products.all())


class WholesaleProductVariationModelTest(TestCase):
    """Test cases for WholesaleProductVariation model"""

    def setUp(self):
        """Set up test data"""
        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product',
            school=self.school
        )

        self.variation_data = {
            'cin7_id': 'VAR_001',
            'product': self.product,
            'variation_type': 'size',
            'variation_value': 'Large',
            'variation_description': 'Large size variation',
            'cin7_sku': 'TEST-VAR-001',
            'cin7_barcode': '1234567890456',
            'wholesale_price': Decimal('55.00'),
            'retail_price': Decimal('80.00'),
            'cost_price': Decimal('35.00'),
            'quantity_available': 50,
            'quantity_on_hand': 60,
            'quantity_committed': 10,
            'weight': Decimal('1.800'),
            'dimensions': {'length': 12, 'width': 6, 'height': 4},
            'image_url': 'https://example.com/variation.jpg'
        }

    def test_variation_creation(self):
        """Test basic variation creation"""
        variation = WholesaleProductVariation.objects.create(**self.variation_data)

        self.assertEqual(variation.variation_type, 'size')
        self.assertEqual(variation.variation_value, 'Large')
        self.assertEqual(variation.product, self.product)
        self.assertEqual(variation.wholesale_price, Decimal('55.00'))
        self.assertTrue(variation.is_active)

    def test_variation_type_choices(self):
        """Test variation type choices"""
        valid_types = ['size', 'color', 'style', 'material', 'other']

        for var_type in valid_types:
            variation_data = self.variation_data.copy()
            variation_data['cin7_id'] = f'VAR_{var_type}'
            variation_data['variation_type'] = var_type
            variation = WholesaleProductVariation.objects.create(**variation_data)
            self.assertEqual(variation.variation_type, var_type)

    def test_variation_str_representation(self):
        """Test string representation"""
        variation = WholesaleProductVariation.objects.create(**self.variation_data)
        expected_str = f"{self.product.name} - size: Large"
        self.assertEqual(str(variation), expected_str)

    def test_variation_is_in_stock_property(self):
        """Test is_in_stock property"""
        variation = WholesaleProductVariation.objects.create(**self.variation_data)
        self.assertTrue(variation.is_in_stock)

        variation.quantity_available = 0
        variation.save()
        self.assertFalse(variation.is_in_stock)

    def test_variation_uniqueness_constraint(self):
        """Test unique_together constraint"""
        WholesaleProductVariation.objects.create(**self.variation_data)

        # Try to create duplicate variation
        duplicate_data = self.variation_data.copy()
        duplicate_data['cin7_id'] = 'VAR_002'  # Different cin7_id

        with self.assertRaises(IntegrityError):
            WholesaleProductVariation.objects.create(**duplicate_data)

    def test_variation_cin7_id_uniqueness(self):
        """Test cin7_id uniqueness across variations"""
        WholesaleProductVariation.objects.create(**self.variation_data)

        # Create different product
        product2 = WholesaleProduct.objects.create(
            cin7_id='PROD_002',
            name='Product 2',
            school=self.school
        )

        duplicate_data = self.variation_data.copy()
        duplicate_data['product'] = product2
        duplicate_data['variation_value'] = 'Small'  # Different value

        with self.assertRaises(IntegrityError):
            WholesaleProductVariation.objects.create(**duplicate_data)

    def test_variation_product_relationship(self):
        """Test foreign key relationship with product"""
        variation = WholesaleProductVariation.objects.create(**self.variation_data)

        # Test forward relationship
        self.assertEqual(variation.product, self.product)

        # Test reverse relationship
        self.assertIn(variation, self.product.variations.all())

    def test_variation_optional_fields(self):
        """Test creation with minimal data"""
        minimal_data = {
            'cin7_id': 'VAR_MIN',
            'product': self.product,
            'variation_type': 'color',
            'variation_value': 'Red'
        }

        variation = WholesaleProductVariation.objects.create(**minimal_data)
        self.assertEqual(variation.variation_type, 'color')
        self.assertEqual(variation.variation_value, 'Red')
        self.assertEqual(variation.quantity_available, 0)  # Default value


class WholesaleProductCategoryAssignmentModelTest(TestCase):
    """Test cases for WholesaleProductCategoryAssignment model"""

    def setUp(self):
        """Set up test data"""
        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Test Category'
        )

        self.product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product',
            school=self.school
        )

    def test_assignment_creation(self):
        """Test basic assignment creation"""
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category,
            is_primary=True,
            sort_order=1,
            cin7_category_id='CIN7_CAT_001'
        )

        self.assertEqual(assignment.product, self.product)
        self.assertEqual(assignment.category, self.category)
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.sort_order, 1)

    def test_assignment_str_representation(self):
        """Test string representation"""
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

        expected_str = f"{self.product.name} -> {self.category.name}"
        self.assertEqual(str(assignment), expected_str)

    def test_assignment_uniqueness_constraint(self):
        """Test unique_together constraint"""
        WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

        # Try to create duplicate assignment
        with self.assertRaises(IntegrityError):
            WholesaleProductCategoryAssignment.objects.create(
                product=self.product,
                category=self.category
            )

    def test_assignment_default_values(self):
        """Test default field values"""
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

        self.assertFalse(assignment.is_primary)  # Default False
        self.assertEqual(assignment.sort_order, 0)  # Default 0

    def test_assignment_relationships(self):
        """Test foreign key relationships"""
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

        # Test product relationship
        self.assertIn(assignment, self.product.category_assignments.all())

        # Test category relationship
        self.assertIn(assignment, self.category.product_assignments.all())

    def test_multiple_category_assignments(self):
        """Test product assigned to multiple categories"""
        category2 = WholesaleCategory.objects.create(
            cin7_id='CAT_002',
            name='Second Category'
        )

        # Create two assignments
        assignment1 = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category,
            is_primary=True,
            sort_order=1
        )

        assignment2 = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=category2,
            is_primary=False,
            sort_order=2
        )

        # Test that product has two categories
        self.assertEqual(self.product.category_assignments.count(), 2)
        self.assertEqual(self.product.categories.count(), 2)

        # Test primary category identification
        primary_assignment = self.product.category_assignments.filter(is_primary=True).first()
        self.assertEqual(primary_assignment, assignment1)

    @freeze_time("2024-01-15 10:30:00")
    def test_assignment_timestamps(self):
        """Test timestamp field population"""
        assignment = WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

        self.assertIsNotNone(assignment.assigned_at)


class WholesaleSyncJobModelTest(TestCase):
    """Test cases for WholesaleSyncJob model"""

    def test_sync_job_creation(self):
        """Test basic sync job creation"""
        sync_job = WholesaleSyncJob.objects.create()

        self.assertEqual(sync_job.status, 'pending')  # Default status
        self.assertEqual(sync_job.progress_percentage, 0)
        self.assertEqual(sync_job.schools_created, 0)
        self.assertEqual(sync_job.errors_count, 0)
        self.assertIsInstance(sync_job.id, uuid.UUID)

    def test_sync_job_str_representation(self):
        """Test string representation"""
        sync_job = WholesaleSyncJob.objects.create(status='running')
        expected_str = f"Wholesale Sync Job {sync_job.id} - running"
        self.assertEqual(str(sync_job), expected_str)

    def test_sync_job_status_choices(self):
        """Test status field choices"""
        valid_statuses = ['pending', 'running', 'completed', 'failed', 'cancelled']

        for status in valid_statuses:
            sync_job = WholesaleSyncJob.objects.create(status=status)
            self.assertEqual(sync_job.status, status)

    @freeze_time("2024-01-15 10:00:00")
    def test_sync_job_duration_property(self):
        """Test duration property calculation"""
        sync_job = WholesaleSyncJob.objects.create(
            started_at=timezone.now()
        )

        # Job not completed yet
        self.assertIsNone(sync_job.duration)

        # Complete the job 30 minutes later
        with freeze_time("2024-01-15 10:30:00"):
            sync_job.completed_at = timezone.now()
            sync_job.save()

            expected_duration = timezone.timedelta(minutes=30)
            self.assertEqual(sync_job.duration, expected_duration)

    def test_sync_job_statistics_tracking(self):
        """Test statistics field functionality"""
        sync_job = WholesaleSyncJob.objects.create()

        # Update statistics
        sync_job.schools_created = 5
        sync_job.schools_updated = 3
        sync_job.products_created = 25
        sync_job.products_updated = 15
        sync_job.categories_created = 8
        sync_job.categories_updated = 4
        sync_job.variations_created = 12
        sync_job.variations_updated = 6
        sync_job.save()

        # Test total_items_processed property
        expected_total = 5 + 3 + 25 + 15 + 8 + 4 + 12 + 6
        self.assertEqual(sync_job.total_items_processed, expected_total)

    def test_sync_job_error_tracking(self):
        """Test error tracking functionality"""
        sync_job = WholesaleSyncJob.objects.create()

        # Add error messages
        sync_job.error_messages = [
            "Failed to connect to API",
            "Invalid product data for PROD_001"
        ]
        sync_job.errors_count = 2
        sync_job.save()

        self.assertEqual(sync_job.errors_count, 2)
        self.assertEqual(len(sync_job.error_messages), 2)
        self.assertIn("Failed to connect to API", sync_job.error_messages)

    def test_sync_job_json_fields_default(self):
        """Test JSON fields have proper defaults"""
        sync_job = WholesaleSyncJob.objects.create()

        self.assertEqual(sync_job.error_messages, [])  # Default empty list

    def test_sync_job_progress_tracking(self):
        """Test progress tracking functionality"""
        sync_job = WholesaleSyncJob.objects.create()

        # Update progress
        sync_job.progress_percentage = 75
        sync_job.current_step = "Processing products"
        sync_job.save()

        self.assertEqual(sync_job.progress_percentage, 75)
        self.assertEqual(sync_job.current_step, "Processing products")

    def test_sync_job_ordering(self):
        """Test default ordering by creation date"""
        # Create multiple sync jobs
        job1 = WholesaleSyncJob.objects.create()
        job2 = WholesaleSyncJob.objects.create()
        job3 = WholesaleSyncJob.objects.create()

        # Get all jobs - should be ordered by created_at descending
        jobs = list(WholesaleSyncJob.objects.all())

        self.assertEqual(jobs[0], job3)  # Most recent first
        self.assertEqual(jobs[1], job2)
        self.assertEqual(jobs[2], job1)  # Oldest last