"""
Test suite for wholesale schools performance

This module contains comprehensive performance tests for the wholesale schools feature:
- Large dataset handling and processing
- Query optimization and database performance
- Pagination performance testing
- Sync performance with many products and schools
- Memory usage and resource optimization
- Concurrent access and load testing
"""

import time
import statistics
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import override_settings
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from clubs.models_wholesale import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment,
    WholesaleSyncJob
)


class WholesaleLargeDatasetTest(TestCase):
    """Test performance with large datasets"""

    def setUp(self):
        """Set up large dataset for testing"""
        self.client = Client()

    def create_large_dataset(self, schools_count=50, products_per_school=100, categories_count=20):
        """Create a large dataset for performance testing"""
        schools = []
        categories = []
        products = []

        # Create categories with hierarchy
        for i in range(categories_count):
            if i < 5:  # Root categories
                category = WholesaleCategory.objects.create(
                    cin7_id=f'ROOT_CAT_{i:03d}',
                    name=f'Root Category {i}',
                    level=0
                )
            else:  # Child categories
                parent = categories[i % 5]  # Distribute among root categories
                category = WholesaleCategory.objects.create(
                    cin7_id=f'CHILD_CAT_{i:03d}',
                    name=f'Child Category {i}',
                    parent=parent,
                    level=1
                )
            categories.append(category)

        # Create schools
        for i in range(schools_count):
            school = WholesaleSchool.objects.create(
                cin7_id=f'SCHOOL_{i:04d}',
                name=f'Test School {i:04d}',
                slug=f'test-school-{i:04d}',
                school_code=f'TS{i:04d}',
                city=f'City {i % 10}',  # 10 different cities
                region=f'Region {i % 5}',  # 5 different regions
                total_products=products_per_school
            )
            schools.append(school)

        # Create products
        for school_idx, school in enumerate(schools):
            for product_idx in range(products_per_school):
                global_idx = school_idx * products_per_school + product_idx
                product = WholesaleProduct.objects.create(
                    cin7_id=f'PROD_{global_idx:06d}',
                    name=f'Product {global_idx:06d}',
                    slug=f'product-{global_idx:06d}',
                    school=school,
                    cin7_sku=f'SKU-{global_idx:06d}',
                    wholesale_price=Decimal(f'{20 + (global_idx % 100)}.00'),
                    retail_price=Decimal(f'{30 + (global_idx % 100)}.00'),
                    cost_price=Decimal(f'{10 + (global_idx % 50)}.00'),
                    stock_status='in_stock' if global_idx % 3 == 0 else 'out_of_stock',
                    quantity_available=global_idx % 200
                )
                products.append(product)

                # Assign to random categories (1-3 categories per product)
                num_categories = min(1 + (global_idx % 3), len(categories))
                assigned_categories = categories[global_idx % len(categories):global_idx % len(categories) + num_categories]

                for cat_idx, category in enumerate(assigned_categories):
                    WholesaleProductCategoryAssignment.objects.create(
                        product=product,
                        category=category,
                        is_primary=(cat_idx == 0)
                    )

        return schools, categories, products

    def test_large_dataset_creation_performance(self):
        """Test performance of creating large dataset"""
        start_time = time.time()

        schools, categories, products = self.create_large_dataset(
            schools_count=20,
            products_per_school=50,
            categories_count=10
        )

        end_time = time.time()
        creation_time = end_time - start_time

        # Verify data was created
        self.assertEqual(WholesaleSchool.objects.count(), 20)
        self.assertEqual(WholesaleCategory.objects.count(), 10)
        self.assertEqual(WholesaleProduct.objects.count(), 1000)

        # Performance assertion (should create 1000+ records in reasonable time)
        self.assertLess(creation_time, 30.0, f"Dataset creation took {creation_time:.2f} seconds")

        print(f"Created large dataset in {creation_time:.2f} seconds")

    def test_school_list_query_performance(self):
        """Test school list view performance with large dataset"""
        self.create_large_dataset(schools_count=30, products_per_school=20, categories_count=5)

        # Test without filters
        start_time = time.time()
        response = self.client.get('/clubs/wholesale/schools/')
        end_time = time.time()
        query_time = end_time - start_time

        self.assertEqual(response.status_code, 200)
        self.assertLess(query_time, 2.0, f"School list query took {query_time:.2f} seconds")

        # Test with search filter
        start_time = time.time()
        response = self.client.get('/clubs/wholesale/schools/?search=School 001')
        end_time = time.time()
        search_time = end_time - start_time

        self.assertEqual(response.status_code, 200)
        self.assertLess(search_time, 1.0, f"School search query took {search_time:.2f} seconds")

        print(f"School list: {query_time:.2f}s, Search: {search_time:.2f}s")

    def test_category_list_query_performance(self):
        """Test category list view performance with large dataset"""
        self.create_large_dataset(schools_count=10, products_per_school=30, categories_count=25)

        start_time = time.time()
        response = self.client.get('/clubs/wholesale/categories/')
        end_time = time.time()
        query_time = end_time - start_time

        self.assertEqual(response.status_code, 200)
        self.assertLess(query_time, 2.0, f"Category list query took {query_time:.2f} seconds")

        print(f"Category list query: {query_time:.2f} seconds")

    def test_dashboard_query_performance(self):
        """Test dashboard view performance with large dataset"""
        self.create_large_dataset(schools_count=25, products_per_school=40, categories_count=15)

        start_time = time.time()
        response = self.client.get('/clubs/wholesale/dashboard/')
        end_time = time.time()
        query_time = end_time - start_time

        self.assertEqual(response.status_code, 200)
        self.assertLess(query_time, 3.0, f"Dashboard query took {query_time:.2f} seconds")

        print(f"Dashboard query: {query_time:.2f} seconds")

    def test_product_search_performance(self):
        """Test product search performance with large dataset"""
        self.create_large_dataset(schools_count=15, products_per_school=50, categories_count=10)

        # Test AJAX product search
        search_terms = ['Product', 'SKU-000', '001']
        search_times = []

        for term in search_terms:
            start_time = time.time()
            response = self.client.get(f'/clubs/wholesale/ajax/product-search/?q={term}')
            end_time = time.time()
            search_time = end_time - start_time
            search_times.append(search_time)

            self.assertEqual(response.status_code, 200)

        avg_search_time = statistics.mean(search_times)
        max_search_time = max(search_times)

        self.assertLess(avg_search_time, 0.5, f"Average search time: {avg_search_time:.2f}s")
        self.assertLess(max_search_time, 1.0, f"Max search time: {max_search_time:.2f}s")

        print(f"Product search - Avg: {avg_search_time:.2f}s, Max: {max_search_time:.2f}s")


class WholesaleQueryOptimizationTest(TestCase):
    """Test database query optimization"""

    def setUp(self):
        """Set up test data for query optimization testing"""
        self.client = Client()

        # Create moderate dataset for query analysis
        self.schools = []
        self.categories = []
        self.products = []

        for i in range(10):
            school = WholesaleSchool.objects.create(
                cin7_id=f'SCHOOL_{i:03d}',
                name=f'School {i:03d}',
                total_products=50
            )
            self.schools.append(school)

        for i in range(15):
            category = WholesaleCategory.objects.create(
                cin7_id=f'CAT_{i:03d}',
                name=f'Category {i:03d}',
                product_count=20
            )
            self.categories.append(category)

        for i in range(500):
            school = self.schools[i % len(self.schools)]
            product = WholesaleProduct.objects.create(
                cin7_id=f'PROD_{i:05d}',
                name=f'Product {i:05d}',
                school=school,
                wholesale_price=Decimal(f'{20 + i % 100}.00')
            )
            self.products.append(product)

            # Assign to categories
            category = self.categories[i % len(self.categories)]
            WholesaleProductCategoryAssignment.objects.create(
                product=product,
                category=category,
                is_primary=True
            )

    def count_queries(self, func):
        """Helper to count database queries"""
        with self.assertNumQueries(0):
            pass  # Reset query count

        initial_queries = len(connection.queries)
        func()
        final_queries = len(connection.queries)
        return final_queries - initial_queries

    def test_school_list_query_optimization(self):
        """Test school list view uses optimal number of queries"""
        def get_school_list():
            return self.client.get('/clubs/wholesale/schools/')

        query_count = self.count_queries(get_school_list)

        # Should use minimal queries regardless of data size
        # Expect: 1 for schools, 1 for cities, 1 for regions, 1 for count
        self.assertLessEqual(query_count, 10, f"School list used {query_count} queries")

        print(f"School list view: {query_count} queries")

    def test_school_detail_query_optimization(self):
        """Test school detail view uses select_related and prefetch_related"""
        school = self.schools[0]

        def get_school_detail():
            return self.client.get(f'/clubs/wholesale/school/{school.slug}/')

        query_count = self.count_queries(get_school_detail)

        # Should use prefetch_related to minimize queries
        # Expect: 1 for school, 1 for categories, 1 for products
        self.assertLessEqual(query_count, 15, f"School detail used {query_count} queries")

        print(f"School detail view: {query_count} queries")

    def test_category_detail_query_optimization(self):
        """Test category detail view optimization"""
        category = self.categories[0]

        def get_category_detail():
            return self.client.get(f'/clubs/wholesale/category/{category.slug}/')

        query_count = self.count_queries(get_category_detail)

        # Should optimize product loading with select_related
        self.assertLessEqual(query_count, 12, f"Category detail used {query_count} queries")

        print(f"Category detail view: {query_count} queries")

    def test_dashboard_query_optimization(self):
        """Test dashboard view aggregation efficiency"""
        def get_dashboard():
            return self.client.get('/clubs/wholesale/dashboard/')

        query_count = self.count_queries(get_dashboard)

        # Dashboard should use efficient aggregations
        self.assertLessEqual(query_count, 15, f"Dashboard used {query_count} queries")

        print(f"Dashboard view: {query_count} queries")

    def test_search_query_optimization(self):
        """Test search queries use database indexes efficiently"""
        def search_schools():
            return self.client.get('/clubs/wholesale/ajax/school-search/?q=School')

        def search_products():
            return self.client.get('/clubs/wholesale/ajax/product-search/?q=Product')

        school_query_count = self.count_queries(search_schools)
        product_query_count = self.count_queries(search_products)

        # Search should be efficient with proper indexing
        self.assertLessEqual(school_query_count, 5, f"School search used {school_query_count} queries")
        self.assertLessEqual(product_query_count, 5, f"Product search used {product_query_count} queries")

        print(f"School search: {school_query_count} queries, Product search: {product_query_count} queries")


class WholesalePaginationPerformanceTest(TestCase):
    """Test pagination performance with large datasets"""

    def setUp(self):
        """Set up large dataset for pagination testing"""
        self.client = Client()

        # Create enough data to test pagination
        for i in range(100):  # 100 schools for pagination testing
            WholesaleSchool.objects.create(
                cin7_id=f'SCHOOL_{i:04d}',
                name=f'Pagination Test School {i:04d}',
                slug=f'pagination-test-school-{i:04d}',
                total_products=10
            )

        for i in range(150):  # 150 categories for pagination testing
            WholesaleCategory.objects.create(
                cin7_id=f'CAT_{i:04d}',
                name=f'Pagination Test Category {i:04d}',
                slug=f'pagination-test-category-{i:04d}',
                product_count=5
            )

    def test_school_list_pagination_performance(self):
        """Test school list pagination performance"""
        pages_to_test = [1, 2, 3, 5]  # Test various pages
        page_times = []

        for page in pages_to_test:
            start_time = time.time()
            response = self.client.get(f'/clubs/wholesale/schools/?page={page}')
            end_time = time.time()
            page_time = end_time - start_time
            page_times.append(page_time)

            self.assertEqual(response.status_code, 200)
            self.assertLess(page_time, 1.0, f"Page {page} took {page_time:.2f} seconds")

        # Verify pagination performance is consistent across pages
        avg_time = statistics.mean(page_times)
        max_time = max(page_times)
        time_variance = statistics.variance(page_times) if len(page_times) > 1 else 0

        self.assertLess(avg_time, 0.5, f"Average pagination time: {avg_time:.2f}s")
        self.assertLess(time_variance, 0.1, f"Pagination time variance: {time_variance:.2f}")

        print(f"Pagination - Avg: {avg_time:.2f}s, Max: {max_time:.2f}s, Variance: {time_variance:.2f}")

    def test_category_list_pagination_performance(self):
        """Test category list pagination performance"""
        pages_to_test = [1, 2, 3, 6]  # Test various pages
        page_times = []

        for page in pages_to_test:
            start_time = time.time()
            response = self.client.get(f'/clubs/wholesale/categories/?page={page}')
            end_time = time.time()
            page_time = end_time - start_time
            page_times.append(page_time)

            self.assertEqual(response.status_code, 200)

        avg_time = statistics.mean(page_times)
        self.assertLess(avg_time, 0.5, f"Category pagination avg time: {avg_time:.2f}s")

        print(f"Category pagination average: {avg_time:.2f} seconds")

    def test_pagination_memory_usage(self):
        """Test pagination doesn't load all records into memory"""
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Load first page
        response1 = self.client.get('/clubs/wholesale/schools/?page=1')
        self.assertEqual(response1.status_code, 200)

        # Load last page
        response2 = self.client.get('/clubs/wholesale/schools/?page=6')
        self.assertEqual(response2.status_code, 200)

        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be minimal for pagination
        self.assertLess(memory_increase, 50, f"Memory increased by {memory_increase:.2f} MB")

        print(f"Memory usage increase: {memory_increase:.2f} MB")


class WholesaleSyncPerformanceTest(TransactionTestCase):
    """Test sync performance with large datasets"""

    def generate_large_product_dataset(self, count=1000):
        """Generate large dataset for sync testing"""
        products = []
        for i in range(count):
            school_idx = i // 100  # 100 products per school
            products.append({
                'ProductId': f'{i:06d}',
                'ProductName': f'Performance Test Product {i:06d}',
                'ProductDescription': f'Description for product {i:06d}',
                'SKU': f'PERF-{i:06d}',
                'SellPrice1': f'{20 + (i % 100)}.00',
                'SellPrice2': f'{30 + (i % 100)}.00',
                'CostPrice': f'{10 + (i % 50)}.00',
                'QtyAvailable': i % 200,
                'CategoryPath': f'Wholesale Schools > Performance School {school_idx} > Category {i % 10}',
            })
        return products

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_large_sync_performance(self, mock_get_products, mock_test_connection):
        """Test sync performance with large number of products"""
        mock_test_connection.return_value = True

        # Test with different dataset sizes
        dataset_sizes = [100, 500, 1000]
        sync_times = []

        for size in dataset_sizes:
            # Generate dataset
            products = self.generate_large_product_dataset(size)
            mock_get_products.return_value = products

            # Time the sync
            start_time = time.time()
            call_command('sync_wholesale_schools', verbosity=0)
            end_time = time.time()
            sync_time = end_time - start_time
            sync_times.append(sync_time)

            # Verify sync completed
            sync_job = WholesaleSyncJob.objects.first()
            self.assertEqual(sync_job.status, 'completed')

            # Performance assertion
            self.assertLess(sync_time, size * 0.1, f"Sync of {size} products took {sync_time:.2f}s")

            # Clean up for next test
            WholesaleSchool.objects.all().delete()
            WholesaleProduct.objects.all().delete()
            WholesaleCategory.objects.all().delete()
            WholesaleSyncJob.objects.all().delete()

            print(f"Synced {size} products in {sync_time:.2f} seconds")

        # Verify performance scales reasonably
        if len(sync_times) >= 2:
            time_per_product_100 = sync_times[0] / dataset_sizes[0]
            time_per_product_500 = sync_times[1] / dataset_sizes[1]

            # Performance shouldn't degrade significantly with larger datasets
            degradation_factor = time_per_product_500 / time_per_product_100
            self.assertLess(degradation_factor, 3.0, f"Performance degraded by factor of {degradation_factor:.2f}")

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_memory_efficiency(self, mock_get_products, mock_test_connection):
        """Test sync memory usage with large datasets"""
        import psutil
        import os

        mock_test_connection.return_value = True

        # Generate large dataset
        products = self.generate_large_product_dataset(500)
        mock_get_products.return_value = products

        # Monitor memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Run sync
        call_command('sync_wholesale_schools', verbosity=0)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory usage should be reasonable
        self.assertLess(memory_increase, 200, f"Memory usage increased by {memory_increase:.2f} MB")

        print(f"Sync memory usage: {memory_increase:.2f} MB for 500 products")

    @patch('clubs.services.cin7_service.CIN7Service.test_connection')
    @patch('clubs.services.cin7_service.CIN7Service.get_all_wholesale_products')
    def test_sync_with_existing_data_performance(self, mock_get_products, mock_test_connection):
        """Test sync performance when updating existing data"""
        mock_test_connection.return_value = True

        # Initial sync
        products = self.generate_large_product_dataset(300)
        mock_get_products.return_value = products

        start_time = time.time()
        call_command('sync_wholesale_schools', verbosity=0)
        initial_sync_time = time.time() - start_time

        # Update sync (same data)
        start_time = time.time()
        call_command('sync_wholesale_schools', verbosity=0)
        update_sync_time = time.time() - start_time

        # Update sync should be faster or similar
        self.assertLessEqual(update_sync_time, initial_sync_time * 1.5,
                            f"Update sync took {update_sync_time:.2f}s vs initial {initial_sync_time:.2f}s")

        print(f"Initial sync: {initial_sync_time:.2f}s, Update sync: {update_sync_time:.2f}s")

    def test_bulk_operations_performance(self):
        """Test bulk database operations performance"""
        # Test bulk create performance
        schools_data = []
        for i in range(1000):
            schools_data.append(WholesaleSchool(
                cin7_id=f'BULK_{i:05d}',
                name=f'Bulk School {i:05d}',
                slug=f'bulk-school-{i:05d}'
            ))

        start_time = time.time()
        WholesaleSchool.objects.bulk_create(schools_data, batch_size=100)
        bulk_create_time = time.time() - start_time

        self.assertEqual(WholesaleSchool.objects.count(), 1000)
        self.assertLess(bulk_create_time, 5.0, f"Bulk create took {bulk_create_time:.2f}s")

        print(f"Bulk created 1000 schools in {bulk_create_time:.2f} seconds")

        # Test bulk update performance
        schools = WholesaleSchool.objects.all()
        for school in schools:
            school.total_products = 50

        start_time = time.time()
        WholesaleSchool.objects.bulk_update(schools, ['total_products'], batch_size=100)
        bulk_update_time = time.time() - start_time

        self.assertLess(bulk_update_time, 3.0, f"Bulk update took {bulk_update_time:.2f}s")

        print(f"Bulk updated 1000 schools in {bulk_update_time:.2f} seconds")


class WholesaleConcurrentAccessTest(TestCase):
    """Test concurrent access and load handling"""

    def setUp(self):
        """Set up test data for concurrent access testing"""
        self.client = Client()

        # Create moderate dataset
        for i in range(20):
            school = WholesaleSchool.objects.create(
                cin7_id=f'CONCURRENT_{i:03d}',
                name=f'Concurrent Test School {i:03d}',
                total_products=25
            )

            for j in range(25):
                WholesaleProduct.objects.create(
                    cin7_id=f'PROD_C_{i:03d}_{j:03d}',
                    name=f'Product {i:03d}-{j:03d}',
                    school=school,
                    wholesale_price=Decimal('50.00')
                )

    def test_concurrent_view_access(self):
        """Test multiple simultaneous view requests"""
        import threading
        import queue

        results = queue.Queue()
        num_threads = 10

        def make_request(url, result_queue):
            try:
                start_time = time.time()
                response = self.client.get(url)
                end_time = time.time()
                result_queue.put({
                    'status_code': response.status_code,
                    'response_time': end_time - start_time
                })
            except Exception as e:
                result_queue.put({'error': str(e)})

        # Test concurrent requests to different views
        urls = [
            '/clubs/wholesale/dashboard/',
            '/clubs/wholesale/schools/',
            '/clubs/wholesale/categories/',
            '/clubs/wholesale/ajax/school-search/?q=Test',
            '/clubs/wholesale/ajax/product-search/?q=Product'
        ]

        threads = []
        for i in range(num_threads):
            url = urls[i % len(urls)]
            thread = threading.Thread(target=make_request, args=(url, results))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)

        # Collect results
        response_times = []
        errors = []
        while not results.empty():
            result = results.get()
            if 'error' in result:
                errors.append(result['error'])
            else:
                self.assertEqual(result['status_code'], 200)
                response_times.append(result['response_time'])

        # Verify no errors
        self.assertEqual(len(errors), 0, f"Concurrent access errors: {errors}")

        # Verify reasonable response times
        if response_times:
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)

            self.assertLess(avg_response_time, 2.0, f"Average response time: {avg_response_time:.2f}s")
            self.assertLess(max_response_time, 5.0, f"Max response time: {max_response_time:.2f}s")

            print(f"Concurrent access - Avg: {avg_response_time:.2f}s, Max: {max_response_time:.2f}s")

    def test_search_performance_under_load(self):
        """Test search performance under simulated load"""
        search_terms = ['Test', 'School', 'Product', 'Concurrent', '001']
        search_times = []

        # Simulate load with multiple rapid searches
        for _ in range(20):  # 20 rapid searches
            for term in search_terms:
                start_time = time.time()
                response = self.client.get(f'/clubs/wholesale/ajax/school-search/?q={term}')
                end_time = time.time()
                search_time = end_time - start_time
                search_times.append(search_time)

                self.assertEqual(response.status_code, 200)

        avg_search_time = statistics.mean(search_times)
        max_search_time = max(search_times)

        # Performance should remain acceptable under load
        self.assertLess(avg_search_time, 0.5, f"Average search time under load: {avg_search_time:.2f}s")
        self.assertLess(max_search_time, 2.0, f"Max search time under load: {max_search_time:.2f}s")

        print(f"Search under load - Avg: {avg_search_time:.2f}s, Max: {max_search_time:.2f}s")


@override_settings(DEBUG=False)  # Test with production-like settings
class WholesaleProductionPerformanceTest(TestCase):
    """Test performance with production-like settings"""

    def setUp(self):
        """Set up production-like test environment"""
        self.client = Client()

        # Create realistic dataset size
        for i in range(50):
            school = WholesaleSchool.objects.create(
                cin7_id=f'PROD_{i:04d}',
                name=f'Production School {i:04d}',
                total_products=100
            )

            # Create categories
            for j in range(5):
                WholesaleCategory.objects.create(
                    cin7_id=f'PROD_CAT_{i:04d}_{j:02d}',
                    name=f'Category {i:04d}-{j:02d}',
                    product_count=20
                )

    def test_production_response_times(self):
        """Test response times match production requirements"""
        endpoints = [
            ('/clubs/wholesale/dashboard/', 3.0),  # Dashboard: max 3s
            ('/clubs/wholesale/schools/', 2.0),    # List views: max 2s
            ('/clubs/wholesale/categories/', 2.0),
            ('/clubs/wholesale/ajax/school-search/?q=Production', 0.5),  # Search: max 0.5s
            ('/clubs/wholesale/ajax/product-search/?q=Product', 0.5),
        ]

        for endpoint, max_time in endpoints:
            start_time = time.time()
            response = self.client.get(endpoint)
            end_time = time.time()
            response_time = end_time - start_time

            self.assertEqual(response.status_code, 200)
            self.assertLess(response_time, max_time,
                           f"{endpoint} took {response_time:.2f}s (max: {max_time}s)")

            print(f"{endpoint}: {response_time:.2f}s")

    def test_database_connection_efficiency(self):
        """Test database connection usage is efficient"""
        from django.db import connections

        # Reset connection queries
        for connection in connections.all():
            connection.queries.clear()

        # Make several requests
        endpoints = [
            '/clubs/wholesale/dashboard/',
            '/clubs/wholesale/schools/',
            '/clubs/wholesale/categories/'
        ]

        total_queries = 0
        for endpoint in endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)

        # Count total queries across all connections
        for connection in connections.all():
            total_queries += len(connection.queries)

        # Should use reasonable number of queries
        self.assertLess(total_queries, 50, f"Total queries: {total_queries}")

        print(f"Total database queries for all views: {total_queries}")


if __name__ == '__main__':
    import unittest
    unittest.main()