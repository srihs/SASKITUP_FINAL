"""
Test suite for wholesale schools views

This module contains comprehensive tests for all wholesale school views:
- Dashboard view with statistics and sync management
- School list and detail views with filtering and search
- Category list and detail views
- Product detail views
- AJAX endpoints for search and sync
- Permission and authentication testing
- Error handling and 404 responses
"""

import json
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone

from clubs.models_wholesale import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment,
    WholesaleSyncJob
)


class WholesaleDashboardViewTest(TestCase):
    """Test wholesale dashboard view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test schools
        self.school1 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School 1',
            total_products=10
        )
        self.school2 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_002',
            name='Test School 2',
            total_products=5
        )

        # Create test categories
        self.category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Test Category',
            product_count=15
        )

        # Create test products
        self.product1 = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product 1',
            school=self.school1,
            stock_status='in_stock'
        )
        self.product2 = WholesaleProduct.objects.create(
            cin7_id='PROD_002',
            name='Test Product 2',
            school=self.school1,
            stock_status='out_of_stock'
        )

        # Create test sync job
        self.sync_job = WholesaleSyncJob.objects.create(
            status='completed',
            schools_created=2,
            products_created=2,
            categories_created=1,
            completed_at=timezone.now()
        )

    def test_dashboard_view_status_code(self):
        """Test dashboard view returns 200"""
        response = self.client.get('/clubs/wholesale/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_view_context_data(self):
        """Test dashboard view context data"""
        response = self.client.get('/clubs/wholesale/dashboard/')

        self.assertEqual(response.context['total_schools'], 2)
        self.assertEqual(response.context['total_categories'], 1)
        self.assertEqual(response.context['total_products'], 2)
        self.assertEqual(response.context['in_stock_products'], 1)

    def test_dashboard_view_top_schools(self):
        """Test top schools ordering in dashboard"""
        response = self.client.get('/clubs/wholesale/dashboard/')

        top_schools = response.context['top_schools']
        self.assertEqual(len(top_schools), 2)
        # Should be ordered by total_products descending
        self.assertEqual(top_schools[0], self.school1)  # 10 products
        self.assertEqual(top_schools[1], self.school2)  # 5 products

    def test_dashboard_view_sync_information(self):
        """Test sync information in dashboard"""
        response = self.client.get('/clubs/wholesale/dashboard/')

        self.assertIsNotNone(response.context['last_sync'])
        self.assertEqual(response.context['recent_sync_stats']['schools_created'], 2)
        self.assertEqual(response.context['recent_sync_stats']['products_created'], 2)

    def test_dashboard_view_running_sync(self):
        """Test dashboard with running sync"""
        running_sync = WholesaleSyncJob.objects.create(
            status='running',
            current_step='Processing products...',
            progress_percentage=50
        )

        response = self.client.get('/clubs/wholesale/dashboard/')

        self.assertEqual(response.context['sync_job'], running_sync)

    def test_dashboard_view_template_used(self):
        """Test correct template is used"""
        response = self.client.get('/clubs/wholesale/dashboard/')
        self.assertTemplateUsed(response, 'clubs/wholesale/dashboard.html')

    def test_dashboard_view_inactive_schools_excluded(self):
        """Test inactive schools are excluded from dashboard"""
        # Create inactive school
        WholesaleSchool.objects.create(
            cin7_id='INACTIVE_001',
            name='Inactive School',
            is_active=False,
            total_products=20
        )

        response = self.client.get('/clubs/wholesale/dashboard/')

        # Should still show only 2 active schools
        self.assertEqual(response.context['total_schools'], 2)
        top_schools = response.context['top_schools']
        self.assertEqual(len(top_schools), 2)


class WholesaleSchoolListViewTest(TestCase):
    """Test wholesale school list view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test schools with different attributes
        self.school1 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Auckland High School',
            school_code='AHS001',
            contact_person='John Doe',
            email='contact@auckland.edu',
            city='Auckland',
            region='Auckland Region'
        )
        self.school2 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_002',
            name='Wellington College',
            school_code='WC002',
            contact_person='Jane Smith',
            email='admin@wellington.edu',
            city='Wellington',
            region='Wellington Region'
        )
        self.school3 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_003',
            name='Christchurch Academy',
            school_code='CA003',
            city='Christchurch',
            region='Canterbury'
        )

    def test_school_list_view_status_code(self):
        """Test school list view returns 200"""
        response = self.client.get('/clubs/wholesale/schools/')
        self.assertEqual(response.status_code, 200)

    def test_school_list_view_context_data(self):
        """Test school list view context"""
        response = self.client.get('/clubs/wholesale/schools/')

        self.assertEqual(len(response.context['schools']), 3)
        self.assertEqual(response.context['total_schools'], 3)
        self.assertIn('cities', response.context)
        self.assertIn('regions', response.context)

    def test_school_list_view_search_functionality(self):
        """Test search functionality"""
        response = self.client.get('/clubs/wholesale/schools/?search=Auckland')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school1)

    def test_school_list_view_search_by_contact_person(self):
        """Test search by contact person"""
        response = self.client.get('/clubs/wholesale/schools/?search=Jane')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school2)

    def test_school_list_view_search_by_school_code(self):
        """Test search by school code"""
        response = self.client.get('/clubs/wholesale/schools/?search=CA003')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school3)

    def test_school_list_view_search_by_email(self):
        """Test search by email"""
        response = self.client.get('/clubs/wholesale/schools/?search=wellington.edu')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school2)

    def test_school_list_view_filter_by_city(self):
        """Test filtering by city"""
        response = self.client.get('/clubs/wholesale/schools/?city=Auckland')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school1)

    def test_school_list_view_filter_by_region(self):
        """Test filtering by region"""
        response = self.client.get('/clubs/wholesale/schools/?region=Canterbury')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school3)

    def test_school_list_view_combined_filters(self):
        """Test combined search and filters"""
        response = self.client.get('/clubs/wholesale/schools/?search=College&region=Wellington Region')

        schools = response.context['schools']
        self.assertEqual(len(schools), 1)
        self.assertEqual(schools[0], self.school2)

    def test_school_list_view_no_results(self):
        """Test search with no results"""
        response = self.client.get('/clubs/wholesale/schools/?search=NonexistentSchool')

        schools = response.context['schools']
        self.assertEqual(len(schools), 0)

    def test_school_list_view_pagination(self):
        """Test pagination functionality"""
        # Create 20 more schools to test pagination
        for i in range(20):
            WholesaleSchool.objects.create(
                cin7_id=f'SCHOOL_{i+10:03d}',
                name=f'Test School {i+10}'
            )

        response = self.client.get('/clubs/wholesale/schools/')

        # Should have pagination (paginate_by = 18)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['schools']), 18)

    def test_school_list_view_inactive_schools_excluded(self):
        """Test inactive schools are excluded"""
        # Create inactive school
        WholesaleSchool.objects.create(
            cin7_id='INACTIVE_001',
            name='Inactive School',
            is_active=False
        )

        response = self.client.get('/clubs/wholesale/schools/')

        schools = response.context['schools']
        school_names = [school.name for school in schools]
        self.assertNotIn('Inactive School', school_names)

    def test_school_list_view_ordering(self):
        """Test schools are ordered by name"""
        response = self.client.get('/clubs/wholesale/schools/')

        schools = list(response.context['schools'])
        school_names = [school.name for school in schools]
        self.assertEqual(school_names, sorted(school_names))

    def test_school_list_view_distinct_filters(self):
        """Test distinct cities and regions in context"""
        response = self.client.get('/clubs/wholesale/schools/')

        cities = list(response.context['cities'])
        regions = list(response.context['regions'])

        self.assertIn('Auckland', cities)
        self.assertIn('Wellington', cities)
        self.assertIn('Christchurch', cities)

        self.assertIn('Auckland Region', regions)
        self.assertIn('Wellington Region', regions)
        self.assertIn('Canterbury', regions)


class WholesaleSchoolDetailViewTest(TestCase):
    """Test wholesale school detail view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School',
            slug='test-school',
            description='A test school'
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

        # Assign product to category
        WholesaleProductCategoryAssignment.objects.create(
            product=self.product,
            category=self.category
        )

    def test_school_detail_view_status_code(self):
        """Test school detail view returns 200"""
        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_school_detail_view_context_data(self):
        """Test school detail view context"""
        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')

        self.assertEqual(response.context['school'], self.school)
        self.assertIn('categories', response.context)
        self.assertIn('products', response.context)

    def test_school_detail_view_categories_with_products(self):
        """Test categories shown have products"""
        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')

        categories = response.context['categories']
        self.assertIn(self.category, categories)

    def test_school_detail_view_products_for_school(self):
        """Test products shown belong to school"""
        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')

        products = response.context['products']
        self.assertIn(self.product, products)

    def test_school_detail_view_404_for_nonexistent_school(self):
        """Test 404 for nonexistent school"""
        response = self.client.get('/clubs/wholesale/school/nonexistent-school/')
        self.assertEqual(response.status_code, 404)

    def test_school_detail_view_404_for_inactive_school(self):
        """Test 404 for inactive school"""
        inactive_school = WholesaleSchool.objects.create(
            cin7_id='INACTIVE_001',
            name='Inactive School',
            slug='inactive-school',
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/school/{inactive_school.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_school_detail_view_inactive_products_excluded(self):
        """Test inactive products are excluded"""
        inactive_product = WholesaleProduct.objects.create(
            cin7_id='INACTIVE_PROD',
            name='Inactive Product',
            school=self.school,
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')

        products = response.context['products']
        self.assertNotIn(inactive_product, products)

    def test_school_detail_view_template_used(self):
        """Test correct template is used"""
        response = self.client.get(f'/clubs/wholesale/school/{self.school.slug}/')
        self.assertTemplateUsed(response, 'clubs/wholesale/school_detail.html')


class WholesaleCategoryListViewTest(TestCase):
    """Test wholesale category list view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        # Create test categories with hierarchy
        self.parent_category = WholesaleCategory.objects.create(
            cin7_id='PARENT_001',
            name='Parent Category',
            level=0,
            product_count=10
        )
        self.child_category = WholesaleCategory.objects.create(
            cin7_id='CHILD_001',
            name='Child Category',
            parent=self.parent_category,
            level=1,
            product_count=5
        )
        self.other_category = WholesaleCategory.objects.create(
            cin7_id='OTHER_001',
            name='Other Category',
            level=0,
            product_count=0,
            description='A category with no products'
        )

    def test_category_list_view_status_code(self):
        """Test category list view returns 200"""
        response = self.client.get('/clubs/wholesale/categories/')
        self.assertEqual(response.status_code, 200)

    def test_category_list_view_context_data(self):
        """Test category list view context"""
        response = self.client.get('/clubs/wholesale/categories/')

        self.assertEqual(len(response.context['categories']), 3)
        self.assertEqual(response.context['total_categories'], 3)

    def test_category_list_view_search_functionality(self):
        """Test search functionality"""
        response = self.client.get('/clubs/wholesale/categories/?search=Parent')

        categories = response.context['categories']
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0], self.parent_category)

    def test_category_list_view_search_by_description(self):
        """Test search by description"""
        response = self.client.get('/clubs/wholesale/categories/?search=no products')

        categories = response.context['categories']
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0], self.other_category)

    def test_category_list_view_filter_by_level(self):
        """Test filtering by level"""
        response = self.client.get('/clubs/wholesale/categories/?level=0')

        categories = response.context['categories']
        self.assertEqual(len(categories), 2)  # parent_category and other_category

    def test_category_list_view_filter_by_min_products(self):
        """Test filtering by minimum products"""
        response = self.client.get('/clubs/wholesale/categories/?min_products=5')

        categories = response.context['categories']
        category_names = [cat.name for cat in categories]
        self.assertIn('Parent Category', category_names)
        self.assertIn('Child Category', category_names)
        self.assertNotIn('Other Category', category_names)

    def test_category_list_view_combined_filters(self):
        """Test combined filters"""
        response = self.client.get('/clubs/wholesale/categories/?level=1&min_products=1')

        categories = response.context['categories']
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0], self.child_category)

    def test_category_list_view_ordering(self):
        """Test categories are ordered by level then name"""
        response = self.client.get('/clubs/wholesale/categories/')

        categories = list(response.context['categories'])

        # Should have level 0 categories first, then level 1
        levels = [cat.level for cat in categories]
        self.assertTrue(all(levels[i] <= levels[i+1] for i in range(len(levels)-1)))

    def test_category_list_view_pagination(self):
        """Test pagination functionality"""
        # Create enough categories to trigger pagination
        for i in range(25):
            WholesaleCategory.objects.create(
                cin7_id=f'CAT_{i+10:03d}',
                name=f'Category {i+10}'
            )

        response = self.client.get('/clubs/wholesale/categories/')

        # Should have pagination (paginate_by = 24)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['categories']), 24)

    def test_category_list_view_inactive_categories_excluded(self):
        """Test inactive categories are excluded"""
        WholesaleCategory.objects.create(
            cin7_id='INACTIVE_CAT',
            name='Inactive Category',
            is_active=False
        )

        response = self.client.get('/clubs/wholesale/categories/')

        categories = response.context['categories']
        category_names = [cat.name for cat in categories]
        self.assertNotIn('Inactive Category', category_names)


class WholesaleCategoryDetailViewTest(TestCase):
    """Test wholesale category detail view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.category = WholesaleCategory.objects.create(
            cin7_id='CAT_001',
            name='Test Category',
            slug='test-category'
        )

        self.subcategory = WholesaleCategory.objects.create(
            cin7_id='SUBCAT_001',
            name='Test Subcategory',
            parent=self.category
        )

        self.product_in_stock = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='In Stock Product',
            school=self.school,
            stock_status='in_stock'
        )

        self.product_out_of_stock = WholesaleProduct.objects.create(
            cin7_id='PROD_002',
            name='Out of Stock Product',
            school=self.school,
            stock_status='out_of_stock'
        )

        # Assign products to category
        WholesaleProductCategoryAssignment.objects.create(
            product=self.product_in_stock,
            category=self.category
        )
        WholesaleProductCategoryAssignment.objects.create(
            product=self.product_out_of_stock,
            category=self.category
        )

    def test_category_detail_view_status_code(self):
        """Test category detail view returns 200"""
        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_category_detail_view_context_data(self):
        """Test category detail view context"""
        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        self.assertEqual(response.context['category'], self.category)
        self.assertIn('subcategories', response.context)
        self.assertIn('products', response.context)
        self.assertIn('in_stock_products', response.context)
        self.assertIn('out_of_stock_products', response.context)

    def test_category_detail_view_subcategories(self):
        """Test subcategories are shown"""
        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        subcategories = response.context['subcategories']
        self.assertIn(self.subcategory, subcategories)

    def test_category_detail_view_products_in_category(self):
        """Test products in category are shown"""
        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        products = response.context['products']
        self.assertIn(self.product_in_stock, products)
        self.assertIn(self.product_out_of_stock, products)

    def test_category_detail_view_stock_statistics(self):
        """Test stock statistics are calculated"""
        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        self.assertEqual(response.context['in_stock_products'], 1)
        self.assertEqual(response.context['out_of_stock_products'], 1)

    def test_category_detail_view_404_for_nonexistent_category(self):
        """Test 404 for nonexistent category"""
        response = self.client.get('/clubs/wholesale/category/nonexistent-category/')
        self.assertEqual(response.status_code, 404)

    def test_category_detail_view_404_for_inactive_category(self):
        """Test 404 for inactive category"""
        inactive_category = WholesaleCategory.objects.create(
            cin7_id='INACTIVE_CAT',
            name='Inactive Category',
            slug='inactive-category',
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/category/{inactive_category.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_category_detail_view_inactive_products_excluded(self):
        """Test inactive products are excluded"""
        inactive_product = WholesaleProduct.objects.create(
            cin7_id='INACTIVE_PROD',
            name='Inactive Product',
            school=self.school,
            is_active=False
        )

        WholesaleProductCategoryAssignment.objects.create(
            product=inactive_product,
            category=self.category
        )

        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        products = response.context['products']
        self.assertNotIn(inactive_product, products)

    def test_category_detail_view_inactive_subcategories_excluded(self):
        """Test inactive subcategories are excluded"""
        inactive_subcategory = WholesaleCategory.objects.create(
            cin7_id='INACTIVE_SUB',
            name='Inactive Subcategory',
            parent=self.category,
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/category/{self.category.slug}/')

        subcategories = response.context['subcategories']
        self.assertNotIn(inactive_subcategory, subcategories)


class WholesaleProductDetailViewTest(TestCase):
    """Test wholesale product detail view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.product = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Test Product',
            slug='test-product',
            school=self.school,
            description='A test product'
        )

        self.variation1 = WholesaleProductVariation.objects.create(
            cin7_id='VAR_001',
            product=self.product,
            variation_type='size',
            variation_value='Large'
        )

        self.variation2 = WholesaleProductVariation.objects.create(
            cin7_id='VAR_002',
            product=self.product,
            variation_type='color',
            variation_value='Blue'
        )

    def test_product_detail_view_status_code(self):
        """Test product detail view returns 200"""
        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_product_detail_view_context_data(self):
        """Test product detail view context"""
        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')

        self.assertEqual(response.context['product'], self.product)
        self.assertIn('variations', response.context)

    def test_product_detail_view_variations(self):
        """Test product variations are shown"""
        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')

        variations = response.context['variations']
        self.assertIn(self.variation1, variations)
        self.assertIn(self.variation2, variations)

    def test_product_detail_view_variations_ordering(self):
        """Test variations are ordered by type and value"""
        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')

        variations = list(response.context['variations'])
        # Should be ordered by variation_type, variation_value
        self.assertTrue(
            variations[0].variation_type <= variations[1].variation_type
        )

    def test_product_detail_view_404_for_nonexistent_product(self):
        """Test 404 for nonexistent product"""
        response = self.client.get('/clubs/wholesale/product/nonexistent-product/')
        self.assertEqual(response.status_code, 404)

    def test_product_detail_view_404_for_inactive_product(self):
        """Test 404 for inactive product"""
        inactive_product = WholesaleProduct.objects.create(
            cin7_id='INACTIVE_PROD',
            name='Inactive Product',
            slug='inactive-product',
            school=self.school,
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/product/{inactive_product.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_product_detail_view_inactive_variations_excluded(self):
        """Test inactive variations are excluded"""
        inactive_variation = WholesaleProductVariation.objects.create(
            cin7_id='INACTIVE_VAR',
            product=self.product,
            variation_type='style',
            variation_value='Classic',
            is_active=False
        )

        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')

        variations = response.context['variations']
        self.assertNotIn(inactive_variation, variations)

    def test_product_detail_view_template_used(self):
        """Test correct template is used"""
        response = self.client.get(f'/clubs/wholesale/product/{self.product.slug}/')
        self.assertTemplateUsed(response, 'clubs/wholesale/product_detail.html')


class WholesaleSyncExecuteViewTest(TestCase):
    """Test wholesale sync execute endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

    @patch('clubs.views.CIN7Service')
    @patch('threading.Thread')
    def test_sync_execute_success(self, mock_thread, mock_cin7_service):
        """Test successful sync execution"""
        # Mock CIN7 service
        mock_service = Mock()
        mock_service.test_connection.return_value = True
        mock_service.get_all_wholesale_products.return_value = []
        mock_service.organize_products_by_school.return_value = {}
        mock_cin7_service.return_value = mock_service

        response = self.client.post('/clubs/wholesale/sync/execute/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('job_id', data)

    def test_sync_execute_already_running(self):
        """Test sync execute when sync is already running"""
        # Create running sync job
        running_sync = WholesaleSyncJob.objects.create(
            status='running',
            current_step='Processing...'
        )

        response = self.client.post('/clubs/wholesale/sync/execute/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('already running', data['error'])
        self.assertEqual(data['job_id'], str(running_sync.id))

    def test_sync_execute_method_not_allowed(self):
        """Test sync execute with GET method"""
        response = self.client.get('/clubs/wholesale/sync/execute/')
        self.assertEqual(response.status_code, 405)

    @patch('clubs.views.CIN7Service')
    def test_sync_execute_connection_failure(self, mock_cin7_service):
        """Test sync execute with connection failure"""
        mock_cin7_service.side_effect = Exception("Connection failed")

        response = self.client.post('/clubs/wholesale/sync/execute/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_sync_execute_creates_sync_job(self):
        """Test sync execute creates sync job"""
        initial_count = WholesaleSyncJob.objects.count()

        with patch('clubs.views.CIN7Service'):
            with patch('threading.Thread'):
                self.client.post('/clubs/wholesale/sync/execute/')

        # Should create one sync job
        self.assertEqual(WholesaleSyncJob.objects.count(), initial_count + 1)

    def test_sync_execute_csrf_exempt(self):
        """Test sync execute is CSRF exempt"""
        # This test verifies the view is properly decorated with @csrf_exempt
        response = self.client.post(
            '/clubs/wholesale/sync/execute/',
            content_type='application/json'
        )
        # Should not get 403 CSRF error
        self.assertNotEqual(response.status_code, 403)


class WholesaleSyncStatusViewTest(TestCase):
    """Test wholesale sync status endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

    def test_sync_status_with_running_sync(self):
        """Test sync status with running sync"""
        sync_job = WholesaleSyncJob.objects.create(
            status='running',
            progress_percentage=50,
            current_step='Processing products...',
            schools_created=5,
            products_created=25
        )

        response = self.client.get('/clubs/wholesale/sync/status/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['sync_running'])
        self.assertEqual(data['status'], 'running')
        self.assertEqual(data['progress'], 50)
        self.assertEqual(data['current_step'], 'Processing products...')
        self.assertEqual(data['schools_created'], 5)
        self.assertEqual(data['products_created'], 25)

    def test_sync_status_no_running_sync(self):
        """Test sync status with no running sync"""
        response = self.client.get('/clubs/wholesale/sync/status/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertFalse(data['sync_running'])
        self.assertIsNone(data['status'])

    def test_sync_status_completed_sync(self):
        """Test sync status ignores completed sync"""
        WholesaleSyncJob.objects.create(
            status='completed',
            progress_percentage=100
        )

        response = self.client.get('/clubs/wholesale/sync/status/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertFalse(data['sync_running'])

    def test_sync_status_failed_sync(self):
        """Test sync status with failed sync"""
        sync_job = WholesaleSyncJob.objects.create(
            status='failed',
            current_step='Sync failed',
            errors_count=3
        )

        response = self.client.get('/clubs/wholesale/sync/status/')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['sync_running'])  # Failed syncs are still "active"
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['errors_count'], 3)


class WholesaleSchoolSearchAjaxTest(TestCase):
    """Test wholesale school search AJAX endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        self.school1 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Auckland High School',
            school_code='AHS001'
        )
        self.school2 = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_002',
            name='Wellington College',
            school_code='WC002'
        )
        self.inactive_school = WholesaleSchool.objects.create(
            cin7_id='INACTIVE_001',
            name='Auckland Academy',
            is_active=False
        )

    def test_school_search_ajax_success(self):
        """Test successful school search"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=Auckland')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['name'], 'Auckland High School')

    def test_school_search_ajax_empty_query(self):
        """Test school search with empty query"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_school_search_ajax_short_query(self):
        """Test school search with short query"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=A')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)  # Minimum 2 characters

    def test_school_search_ajax_no_results(self):
        """Test school search with no matching results"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=Nonexistent')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_school_search_ajax_inactive_schools_excluded(self):
        """Test inactive schools are excluded from search"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=Academy')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_school_search_ajax_limit(self):
        """Test search results are limited"""
        # Create 15 schools with similar names
        for i in range(15):
            WholesaleSchool.objects.create(
                cin7_id=f'TEST_{i:03d}',
                name=f'Test School {i}'
            )

        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=Test')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 10)  # Limited to 10 results

    def test_school_search_ajax_fields_returned(self):
        """Test correct fields are returned"""
        response = self.client.get('/clubs/wholesale/ajax/school-search/?q=Auckland')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        result = data['results'][0]
        expected_fields = ['id', 'name', 'slug', 'school_code', 'city', 'region']
        for field in expected_fields:
            self.assertIn(field, result)


class WholesaleProductSearchAjaxTest(TestCase):
    """Test wholesale product search AJAX endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()

        self.school = WholesaleSchool.objects.create(
            cin7_id='SCHOOL_001',
            name='Test School'
        )

        self.product1 = WholesaleProduct.objects.create(
            cin7_id='PROD_001',
            name='Football Jersey',
            school=self.school,
            cin7_sku='FB-001',
            wholesale_price=Decimal('50.00')
        )
        self.product2 = WholesaleProduct.objects.create(
            cin7_id='PROD_002',
            name='Basketball Shoes',
            school=self.school,
            cin7_sku='BB-002'
        )
        self.inactive_product = WholesaleProduct.objects.create(
            cin7_id='INACTIVE_PROD',
            name='Football Boots',
            school=self.school,
            is_active=False
        )

    def test_product_search_ajax_success(self):
        """Test successful product search"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=Football')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['name'], 'Football Jersey')

    def test_product_search_ajax_by_sku(self):
        """Test product search by SKU"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=BB-002')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['name'], 'Basketball Shoes')

    def test_product_search_ajax_inactive_products_excluded(self):
        """Test inactive products are excluded"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=Boots')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_product_search_ajax_fields_returned(self):
        """Test correct fields are returned"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=Football')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        result = data['results'][0]
        expected_fields = [
            'id', 'name', 'slug', 'cin7_sku', 'wholesale_price',
            'retail_price', 'stock_status', 'school_name'
        ]
        for field in expected_fields:
            self.assertIn(field, result)

    def test_product_search_ajax_price_formatting(self):
        """Test price fields are properly formatted"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=Football')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        result = data['results'][0]
        self.assertEqual(result['wholesale_price'], '50.00')

    def test_product_search_ajax_empty_query(self):
        """Test product search with empty query"""
        response = self.client.get('/clubs/wholesale/ajax/product-search/?q=')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)