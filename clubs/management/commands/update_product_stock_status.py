#!/usr/bin/env python3
"""
Management command to update stock status for all variable products based on their variations.
This command should be run after implementing the new stock tracking system.

Usage:
    python manage.py update_product_stock_status [--dry-run] [--product-type lotto|generic] [--limit N]
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from clubs.models import Product, ProductVariation
from clubs.models_lotto import LottoProduct, LottoProductVariation


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update stock status for variable products based on their variations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without updating the database',
        )
        parser.add_argument(
            '--product-type',
            choices=['lotto', 'generic', 'all'],
            default='all',
            help='Type of products to update (default: all)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of products to process',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        product_type = options['product_type']
        limit = options['limit']
        verbose = options['verbose']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Statistics
        stats = {
            'lotto_updated': 0,
            'lotto_total': 0,
            'generic_updated': 0,
            'generic_total': 0,
            'errors': 0
        }

        try:
            # Process LOTTO products
            if product_type in ['lotto', 'all']:
                self.stdout.write('\n=== Processing LOTTO Products ===')
                stats.update(self._process_lotto_products(dry_run, limit, verbose))

            # Process generic products
            if product_type in ['generic', 'all']:
                self.stdout.write('\n=== Processing Generic Products ===')
                stats.update(self._process_generic_products(dry_run, limit, verbose))

            # Summary
            self.stdout.write(self.style.SUCCESS('\n=== SUMMARY ==='))
            self.stdout.write(f'LOTTO Products: {stats["lotto_updated"]}/{stats["lotto_total"]} updated')
            self.stdout.write(f'Generic Products: {stats["generic_updated"]}/{stats["generic_total"]} updated')
            self.stdout.write(f'Total Updated: {stats["lotto_updated"] + stats["generic_updated"]}')
            if stats['errors'] > 0:
                self.stdout.write(self.style.ERROR(f'Errors: {stats["errors"]}'))

        except Exception as e:
            raise CommandError(f'Command failed: {str(e)}')

    def _process_lotto_products(self, dry_run, limit, verbose):
        """Process LOTTO products"""
        stats = {'lotto_updated': 0, 'lotto_total': 0, 'errors': 0}
        
        # Get variable LOTTO products
        queryset = LottoProduct.objects.filter(
            type='variable'
        ).prefetch_related('variations')
        
        if limit:
            queryset = queryset[:limit]
        
        stats['lotto_total'] = queryset.count()
        self.stdout.write(f'Found {stats["lotto_total"]} variable LOTTO products')

        for product in queryset:
            try:
                if verbose:
                    self.stdout.write(f'Processing LOTTO product: {product.id} - {product.name}')
                
                old_status = product.stock_status
                new_status = product.calculated_stock_status
                
                if old_status != new_status:
                    if verbose:
                        self.stdout.write(f'  Stock status: {old_status} -> {new_status}')
                    
                    if not dry_run:
                        with transaction.atomic():
                            product.stock_status = new_status
                            product.save(update_fields=['stock_status', 'updated_at'])
                    
                    stats['lotto_updated'] += 1
                elif verbose:
                    self.stdout.write(f'  Stock status unchanged: {old_status}')
                    
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(f'Error processing LOTTO product {product.id}: {str(e)}')
                )
                logger.error(f'Error processing LOTTO product {product.id}: {str(e)}')
        
        return stats

    def _process_generic_products(self, dry_run, limit, verbose):
        """Process generic products"""
        stats = {'generic_updated': 0, 'generic_total': 0, 'errors': 0}
        
        # Get variable generic products
        queryset = Product.objects.filter(
            variations__isnull=False
        ).distinct().prefetch_related('variations')
        
        if limit:
            queryset = queryset[:limit]
        
        stats['generic_total'] = queryset.count()
        self.stdout.write(f'Found {stats["generic_total"]} variable generic products')

        for product in queryset:
            try:
                if verbose:
                    self.stdout.write(f'Processing generic product: {product.id} - {product.name}')
                
                old_status = product.stock_status
                new_status = product.calculated_stock_status
                
                if old_status != new_status:
                    if verbose:
                        self.stdout.write(f'  Stock status: {old_status} -> {new_status}')
                    
                    if not dry_run:
                        with transaction.atomic():
                            product.stock_status = new_status
                            product.save(update_fields=['stock_status', 'updated_at'])
                    
                    stats['generic_updated'] += 1
                elif verbose:
                    self.stdout.write(f'  Stock status unchanged: {old_status}')
                    
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(f'Error processing generic product {product.id}: {str(e)}')
                )
                logger.error(f'Error processing generic product {product.id}: {str(e)}')
        
        return stats