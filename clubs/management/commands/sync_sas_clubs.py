#!/usr/bin/env python3
"""
SAS Clubs Synchronization Management Command

This command synchronizes SAS sports clubs data from WooCommerce API to Django models.
It processes Sports → Clubs → Products hierarchy while filtering out schools.

Usage:
    python manage.py sync_sas_clubs [options]

Key Features:
- Sport-based processing with proper hierarchy
- School filtering using category ID and keyword detection
- Comprehensive error handling and logging
- Dry run mode for preview
- Transaction-based processing for data integrity
"""

import json
import logging
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from clubs.models_sas import SASSport, SASClub, SASProduct, SASProductVariation
from clubs.services.woocommerce_service import WooCommerceService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize SAS sports clubs data from WooCommerce API'

    # Valid sport category IDs - only these will be synced as sports
    # This whitelist ensures we only sync legitimate sports, not products/events/apparel
    VALID_SPORT_CATEGORIES = [
        17,   # Athletics
        46,   # Basketball
        358,  # American Flag Football
        462,  # Cricket
        48,   # Hockey
        120,  # Netball
        60,   # Rugby
        51,   # Rugby League
        384,  # Softball
        328,  # Taranaki Hockey
        383,  # Tennis
        99,   # Touch
        319,  # Touch NZ - Referee
    ]

    # Keywords to exclude from club subcategories (products, apparel, events)
    # These help filter out non-club entries within valid sport categories
    EXCLUDE_CLUB_KEYWORDS = [
        'APPAREL', 'GARMENT', 'UNIFORM', 'CLOTHING', 'PRODUCT',
        'REFEREE', 'DEALS', 'Clearance', 'Range', 'Option',
        'Pack', 'Nationals', 'Tournament'
    ]

    # School filtering keywords (case-insensitive)
    SCHOOL_KEYWORDS = [
        'school', 'high school', 'primary school', 'college', 'university',
        'academy', 'institute', 'education', 'learning', 'student',
        'grade', 'matric', 'junior', 'senior', 'prep'
    ]

    # Schools category ID to exclude
    SCHOOLS_CATEGORY_ID = 98
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.woo_service = None
        self.stats = {
            'sports_processed': 0,
            'sports_created': 0,
            'sports_updated': 0,
            'clubs_processed': 0,
            'clubs_created': 0,
            'clubs_updated': 0,
            'clubs_skipped': 0,
            'products_processed': 0,
            'products_created': 0,
            'products_updated': 0,
            'variations_processed': 0,
            'variations_created': 0,
            'variations_updated': 0,
            'errors': 0,
        }
        
    def extract_style_code(self, short_description: str) -> Optional[str]:
        """
        Extract Style Code from HTML short_description.

        Pattern examples:
        - <p>Style Code – JKT 1513 ROYAL AKA</p>
        - <p><strong>Style Code:</strong> TRK 1234 BLUE</p>
        - Style Code &#8211; CAP U15618 NAVY AKA

        Args:
            short_description: HTML content from WooCommerce short_description field

        Returns:
            Extracted style code string or None if not found
        """
        if not short_description:
            return None

        # Try BeautifulSoup first for proper HTML parsing
        try:
            soup = BeautifulSoup(short_description, 'html.parser')

            # Get all text content
            full_text = soup.get_text()

            # Look for "Style Code" followed by separator and value
            # Patterns: "Style Code:" "Style Code –" "Style Code &#8211;" "Style Code -"
            match = re.search(
                r'style\s+code\s*[:\-–—]\s*([^\n<]+?)(?:\s*(?:<br|</p|\n|$))',
                full_text,
                re.IGNORECASE
            )

            if match:
                style_code = match.group(1).strip()
                # Clean up any extra text after / separator (for multi-option products)
                if '/' in style_code:
                    # Take first option only
                    style_code = style_code.split('/')[0].strip()
                # Clean up whitespace
                style_code = re.sub(r'\s+', ' ', style_code)
                return style_code if style_code else None

        except Exception as e:
            # If BeautifulSoup fails, fall through to regex
            logger.debug(f"BeautifulSoup parsing failed: {str(e)}")

        # Fallback to regex pattern matching on raw HTML
        # Handle various separators: : - – — &#8211; (en-dash HTML entity)
        patterns = [
            r'style\s+code\s*(?::|&#8211;|–|—|-)\s*([^\n<]+?)(?:<br|</p|\n|$)',  # Most common pattern
            r'<strong>style\s+code\s*:\s*</strong>\s*([^<]+)',                    # With strong tags
            r'style\s+code\s*:\s*([^<\n]+)',                                      # Simple colon
        ]

        for pattern in patterns:
            match = re.search(pattern, short_description, re.IGNORECASE)
            if match:
                style_code = match.group(1).strip()
                # Clean up multi-option products (take first only)
                if '/' in style_code:
                    style_code = style_code.split('/')[0].strip()
                # Clean up whitespace
                style_code = re.sub(r'\s+', ' ', style_code)
                return style_code if style_code else None

        return None

    def add_arguments(self, parser):
        """Add command line arguments"""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database'
        )
        
        parser.add_argument(
            '--sport-filter',
            type=str,
            help='Sync specific sport only (by category ID or name)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update all existing records'
        )
        
        parser.add_argument(
            '--limit-clubs',
            type=int,
            help='Limit number of clubs to process per sport'
        )
        
        parser.add_argument(
            '--skip-schools',
            action='store_true',
            default=True,
            help='Skip school-related categories (default: True)'
        )
        
        parser.add_argument(
            '--no-skip-schools',
            action='store_true',
            help='Include school-related categories'
        )
        
    def handle(self, *args, **options):
        """Main command handler"""
        self.options = options
        
        # Set up logging level
        if options['verbose']:
            logger.setLevel(logging.DEBUG)
        
        # Determine school filtering
        skip_schools = options['skip_schools'] and not options['no_skip_schools']
        
        try:
            # Initialize WooCommerce service
            self.stdout.write(self.style.NOTICE('Initializing SAS WooCommerce connection...'))
            self.woo_service = WooCommerceService(store_type='SAS')
            
            # Test connection
            if not self.woo_service.test_connection():
                raise CommandError('Failed to connect to SAS WooCommerce API')
            
            self.stdout.write(self.style.SUCCESS('✓ Connected to SAS WooCommerce API'))
            
            if options['dry_run']:
                self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be saved'))
            
            # Start synchronization process
            start_time = time.time()
            self.stdout.write(self.style.NOTICE(f'Starting SAS clubs sync...'))
            
            self._sync_sas_data(
                dry_run=options['dry_run'],
                sport_filter=options.get('sport_filter'),
                force_update=options['force_update'],
                limit_clubs=options.get('limit_clubs'),
                skip_schools=skip_schools
            )
            
            # Print summary
            end_time = time.time()
            duration = end_time - start_time
            self._print_summary(duration)
            
            # Log completion
            logger.info(f"SAS sync completed in {duration:.2f} seconds", extra=self.stats)
            
        except Exception as e:
            error_msg = f"SAS sync failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg, exc_info=True)
            raise CommandError(error_msg)
    
    def _sync_sas_data(self, dry_run=False, sport_filter=None, force_update=False, 
                       limit_clubs=None, skip_schools=True):
        """Main synchronization logic"""
        
        # Step 1: Fetch sport categories (root level)
        self.stdout.write(self.style.NOTICE('📋 Fetching sport categories...'))
        sport_categories = self._fetch_sport_categories(sport_filter, skip_schools)
        
        if not sport_categories:
            self.stdout.write(self.style.WARNING('No sport categories found to process'))
            return
        
        self.stdout.write(f'Found {len(sport_categories)} sport categories to process')
        
        # Step 2: Process each sport
        for sport_data in sport_categories:
            try:
                with transaction.atomic():
                    self._process_sport(
                        sport_data, dry_run, force_update, 
                        limit_clubs, skip_schools
                    )
            except Exception as e:
                self.stats['errors'] += 1
                error_msg = f"Error processing sport {sport_data.get('name', 'Unknown')}: {str(e)}"
                self.stdout.write(self.style.ERROR(f'❌ {error_msg}'))
                logger.error(error_msg, exc_info=True)
                # Continue with next sport
                continue
    
    def _fetch_sport_categories(self, sport_filter=None, skip_schools=True) -> List[Dict]:
        """
        Fetch whitelisted sport categories only.

        Uses VALID_SPORT_CATEGORIES whitelist to ensure only legitimate sports
        are synced, not products/events/apparel/generic categories.
        """
        try:
            sport_categories = []

            # If sport filter is specified, validate it's in the whitelist
            if sport_filter:
                # Try to convert to int if it's a category ID
                try:
                    filter_id = int(sport_filter)
                    if filter_id not in self.VALID_SPORT_CATEGORIES:
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️  Sport filter ID {filter_id} is not in the whitelist. '
                                f'Valid sport IDs: {self.VALID_SPORT_CATEGORIES}'
                            )
                        )
                        return []
                except ValueError:
                    # It's a name filter, we'll check it later
                    pass

            # Iterate through whitelisted sport categories only
            for sport_id in self.VALID_SPORT_CATEGORIES:
                # Apply sport filter if specified
                if sport_filter:
                    # Check if filter matches this sport ID
                    try:
                        filter_id = int(sport_filter)
                        if filter_id != sport_id:
                            continue
                    except ValueError:
                        # Will check name match below after fetching category
                        pass

                # Fetch this specific sport category
                category = self.woo_service.get_category_by_id(sport_id)

                if not category:
                    if self.options['verbose']:
                        self.stdout.write(f'⏭️  Skipping sport ID {sport_id}: Category not found in WooCommerce')
                    continue

                category_name = category.get('name', '')

                # Check name-based sport filter
                if sport_filter:
                    try:
                        int(sport_filter)  # If this works, we already checked ID match above
                    except ValueError:
                        # It's a name filter
                        if sport_filter.lower() not in category_name.lower():
                            continue

                # Only include categories with products
                product_count = category.get('count', 0)
                if product_count > 0:
                    sport_categories.append(category)
                    if self.options['verbose']:
                        self.stdout.write(
                            f'✓ Found valid sport: {category_name} '
                            f'(ID: {sport_id}, Products: {product_count})'
                        )
                else:
                    if self.options['verbose']:
                        self.stdout.write(
                            f'⏭️  Skipping sport {category_name} (ID: {sport_id}): No products'
                        )

            return sport_categories

        except Exception as e:
            logger.error(f"Failed to fetch sport categories: {str(e)}")
            raise
    
    def _process_sport(self, sport_data, dry_run, force_update, limit_clubs, skip_schools):
        """Process a single sport category"""
        sport_name = sport_data['name']
        sport_id = sport_data['id']
        
        self.stdout.write(self.style.NOTICE(f'\n🏃 Processing Sport: {sport_name} (ID: {sport_id})'))
        
        # Create or update SASSport
        sport_obj = None
        if not dry_run:
            sport_obj, sport_created = self._process_sas_sport(sport_data, force_update)
            if sport_created:
                self.stats['sports_created'] += 1
                self.stdout.write(f'  ✨ Created sport: {sport_name}')
            else:
                self.stats['sports_updated'] += 1
                self.stdout.write(f'  🔄 Updated sport: {sport_name}')
        else:
            self.stdout.write(f'  🔍 [DRY RUN] Would create/update sport: {sport_name}')
        
        self.stats['sports_processed'] += 1
        
        # Fetch clubs for this sport
        clubs = self._fetch_clubs_for_sport(sport_id, skip_schools)
        
        if not clubs:
            self.stdout.write(f'  ⚠️  No clubs found for sport: {sport_name}')
            return
        
        # Limit clubs if specified
        if limit_clubs:
            clubs = clubs[:limit_clubs]
        
        self.stdout.write(f'  📋 Processing {len(clubs)} clubs for {sport_name}')
        
        # Process each club
        for club_data in clubs:
            try:
                self._process_club(club_data, sport_obj, dry_run, force_update)
            except Exception as e:
                self.stats['errors'] += 1
                error_msg = f"Error processing club {club_data.get('name', 'Unknown')}: {str(e)}"
                self.stdout.write(f'    ❌ {error_msg}')
                logger.error(error_msg, exc_info=True)
                # Continue with next club
                continue
    
    def _fetch_clubs_for_sport(self, sport_id, skip_schools) -> List[Dict]:
        """
        Fetch club subcategories for a specific sport with enhanced filtering.

        Filters out:
        - School-related clubs (if skip_schools=True)
        - Product/apparel/event subcategories using EXCLUDE_CLUB_KEYWORDS
        """
        try:
            clubs = self.woo_service.get_categories(parent_id=sport_id, per_page=100)

            if not clubs:
                return []

            filtered_clubs = []

            for club in clubs:
                club_name = club['name']

                # Skip school-related clubs if filtering enabled
                if skip_schools and self._is_school_related(club_name):
                    if self.options['verbose']:
                        self.stdout.write(f'    ⏭️  Skipping school-related club: {club_name}')
                    self.stats['clubs_skipped'] += 1
                    continue

                # Skip product/apparel/event subcategories
                if self._is_excluded_subcategory(club_name):
                    if self.options['verbose']:
                        self.stdout.write(
                            f'    ⏭️  Skipping non-club subcategory: {club_name} '
                            f'(matches exclusion keywords)'
                        )
                    self.stats['clubs_skipped'] += 1
                    continue

                # Only include clubs with products
                if club.get('count', 0) > 0:
                    filtered_clubs.append(club)

            return filtered_clubs

        except Exception as e:
            logger.error(f"Failed to fetch clubs for sport {sport_id}: {str(e)}")
            return []
    
    def _process_sas_sport(self, sport_data, force_update) -> Tuple[SASSport, bool]:
        """Create or update SASSport model"""
        woo_category_id = sport_data['id']
        
        # Check if sport already exists
        existing_sport = SASSport.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare sport data
        sport_data_obj = {
            'name': sport_data['name'],
            'woo_category_id': woo_category_id,
            'slug': sport_data.get('slug', slugify(sport_data['name'])),
            'description': sport_data.get('description', ''),
            'product_count': sport_data.get('count', 0),
            'is_active': True,
        }
        
        # Store sport image URL if available
        if sport_data.get('image') and sport_data['image'].get('src'):
            try:
                image_url = self.woo_service.get_image_url(sport_data['image']['src'])
                if image_url:
                    sport_data_obj['image_url'] = image_url
            except Exception as e:
                logger.warning(f"Failed to process sport image: {str(e)}")
        
        # Create or update
        if existing_sport:
            if force_update or self._sport_needs_update(existing_sport, sport_data_obj):
                for key, value in sport_data_obj.items():
                    if key != 'image_url' or value:  # Only update image_url if we have a new one
                        setattr(existing_sport, key, value)
                existing_sport.save()
                return existing_sport, False
            else:
                return existing_sport, False
        else:
            return SASSport.objects.create(**sport_data_obj), True
    
    def _process_club(self, club_data, sport_obj, dry_run, force_update):
        """Process a single club"""
        club_name = club_data['name']
        club_id = club_data['id']
        
        if self.options['verbose']:
            self.stdout.write(f'    🏛️  Processing Club: {club_name} (ID: {club_id})')
        
        # Create or update SASClub
        club_obj = None
        if not dry_run:
            club_obj, club_created = self._process_sas_club(club_data, sport_obj, force_update)
            if club_created:
                self.stats['clubs_created'] += 1
                if self.options['verbose']:
                    self.stdout.write(f'      ✨ Created club: {club_name}')
            else:
                self.stats['clubs_updated'] += 1
                if self.options['verbose']:
                    self.stdout.write(f'      🔄 Updated club: {club_name}')
        else:
            if self.options['verbose']:
                self.stdout.write(f'      🔍 [DRY RUN] Would create/update club: {club_name}')
        
        self.stats['clubs_processed'] += 1
        
        # Fetch and process products for this club
        products = self._fetch_products_for_club(club_id)
        
        if products:
            if self.options['verbose']:
                self.stdout.write(f'      📦 Processing {len(products)} products for {club_name}')
            
            for product_data in products:
                try:
                    self._process_product(product_data, club_obj, dry_run, force_update)
                except Exception as e:
                    self.stats['errors'] += 1
                    error_msg = f"Error processing product {product_data.get('name', 'Unknown')}: {str(e)}"
                    if self.options['verbose']:
                        self.stdout.write(f'        ❌ {error_msg}')
                    logger.error(error_msg, exc_info=True)
                    # Continue with next product
                    continue
        else:
            if self.options['verbose']:
                self.stdout.write(f'      ⚠️  No products found for club: {club_name}')
    
    def _fetch_products_for_club(self, club_id) -> List[Dict]:
        """Fetch products for a specific club"""
        try:
            products = self.woo_service.get_products_by_category(club_id)
            return products if products else []
        except Exception as e:
            logger.error(f"Failed to fetch products for club {club_id}: {str(e)}")
            return []
    
    def _process_sas_club(self, club_data, sport_obj, force_update) -> Tuple[SASClub, bool]:
        """Create or update SASClub model"""
        woo_category_id = club_data['id']
        
        # Check if club already exists
        existing_club = SASClub.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare club data
        club_data_obj = {
            'sport': sport_obj,
            'name': club_data['name'],
            'woo_category_id': woo_category_id,
            'slug': club_data.get('slug', slugify(f"{sport_obj.name}-{club_data['name']}")),
            'description': club_data.get('description', ''),
            'product_count': club_data.get('count', 0),
            'is_active': True,
        }
        
        # Store club image URL if available
        if club_data.get('image') and club_data['image'].get('src'):
            try:
                image_url = self.woo_service.get_image_url(club_data['image']['src'])
                if image_url:
                    club_data_obj['image_url'] = image_url
            except Exception as e:
                logger.warning(f"Failed to process club image: {str(e)}")
        
        # Create or update
        if existing_club:
            if force_update or self._club_needs_update(existing_club, club_data_obj):
                for key, value in club_data_obj.items():
                    if key != 'image_url' or value:  # Only update image_url if we have a new one
                        setattr(existing_club, key, value)
                existing_club.save()
                return existing_club, False
            else:
                return existing_club, False
        else:
            return SASClub.objects.create(**club_data_obj), True
    
    def _process_product(self, product_data, club_obj, dry_run, force_update):
        """Process a single product and its variations"""
        product_name = product_data['name']
        product_id = product_data['id']

        if self.options['verbose']:
            self.stdout.write(f'        📦 Processing Product: {product_name} (ID: {product_id})')

        if not dry_run:
            product_obj, product_created = self._process_sas_product(product_data, club_obj, force_update)
            if product_created:
                self.stats['products_created'] += 1
                if self.options['verbose']:
                    self.stdout.write(f'          ✨ Created product: {product_name}')
            else:
                self.stats['products_updated'] += 1
                if self.options['verbose']:
                    self.stdout.write(f'          🔄 Updated product: {product_name}')

            # Process variations for variable products
            if self.woo_service.is_variable_product(product_data):
                try:
                    self._process_product_variations(product_obj, product_data)
                except Exception as e:
                    self.stats['errors'] += 1
                    error_msg = f"Error processing variations for {product_name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    if self.options['verbose']:
                        self.stdout.write(f'          ❌ {error_msg}')
        else:
            if self.options['verbose']:
                self.stdout.write(f'          🔍 [DRY RUN] Would create/update product: {product_name}')

        self.stats['products_processed'] += 1
    
    def _process_sas_product(self, product_data, club_obj, force_update) -> Tuple[SASProduct, bool]:
        """Create or update SASProduct model"""
        woo_product_id = product_data['id']
        
        # Check if product already exists
        existing_product = SASProduct.objects.filter(woo_product_id=woo_product_id).first()
        
        # Parse pricing information
        try:
            # Get the main price first (this is usually the effective price)
            main_price = Decimal(product_data.get('price', '0') or '0')
            
            # Get regular and sale prices
            regular_price = Decimal(product_data.get('regular_price', '0') or '0') or main_price
            sale_price = Decimal(product_data.get('sale_price', '0') or '0') if product_data.get('sale_price') else None
            
            # Use sale price if available, otherwise use main price
            price = sale_price or main_price
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid price data for product {product_data['name']}: {str(e)}")
            regular_price = sale_price = price = Decimal('0')
        
        # Extract style code from short_description
        short_description = product_data.get('short_description', '')
        style_code = self.extract_style_code(short_description)

        if style_code and self.options.get('verbose'):
            logger.debug(f"Extracted style code '{style_code}' for product {product_data['name']}")

        # Prepare product data
        product_data_obj = {
            'club': club_obj,
            'name': product_data['name'],
            'woo_product_id': woo_product_id,
            'slug': product_data.get('slug', slugify(product_data['name'])),
            'product_type': product_data.get('type', 'simple'),  # Add product_type from WooCommerce
            'price': price,
            'regular_price': regular_price,
            'sale_price': sale_price,
            'description': product_data.get('description', ''),
            'short_description': short_description,
            'sku': product_data.get('sku', ''),
            'style_code': style_code,
            'stock_status': product_data.get('stock_status', 'instock'),
            'weight': product_data.get('weight', ''),
            'dimensions': product_data.get('dimensions', {}),
            'tags': [tag['name'] for tag in product_data.get('tags', [])],
            'attributes': product_data.get('attributes', []),
        }
        
        # Store product image URL if available
        images = product_data.get('images', [])
        if images and images[0].get('src'):
            try:
                image_url = self.woo_service.get_image_url(images[0]['src'])
                if image_url:
                    product_data_obj['image_url'] = image_url
            except Exception as e:
                logger.warning(f"Failed to process product image: {str(e)}")
        
        # Create or update
        if existing_product:
            if force_update or self._product_needs_update(existing_product, product_data_obj):
                for key, value in product_data_obj.items():
                    if key != 'image_url' or value:  # Only update image_url if we have a new one
                        setattr(existing_product, key, value)
                existing_product.save()
                return existing_product, False
            else:
                return existing_product, False
        else:
            return SASProduct.objects.create(**product_data_obj), True

    def _process_product_variations(self, product, product_data):
        """
        Process variations for a variable product

        Args:
            product: SASProduct instance
            product_data: Product data from WooCommerce API
        """
        try:
            # Get variations from WooCommerce
            variations_data = self.woo_service.get_product_variations(product_data['id'])

            if not variations_data:
                if self.options['verbose']:
                    self.stdout.write(f'          ℹ️  No variations found for product: {product.name}')
                return

            if self.options['verbose']:
                self.stdout.write(f'          🔀 Processing {len(variations_data)} variations for: {product.name}')

            # Track processed variation IDs to avoid duplicates
            processed_variation_ids = set()

            for variation_data in variations_data:
                try:
                    # Skip if this WooCommerce variation ID has already been processed
                    woo_variation_id = variation_data.get('id', 0)
                    if woo_variation_id in processed_variation_ids:
                        if self.options['verbose']:
                            self.stdout.write(f'            ⏭️  Skipping duplicate variation ID: {woo_variation_id}')
                        continue

                    processed_variation_ids.add(woo_variation_id)

                    # Extract variation data
                    extracted_data = self.woo_service.extract_variation_data(variation_data, product_data)

                    # Process individual variation
                    self._process_individual_variation(product, extracted_data, product_data)

                except Exception as e:
                    logger.error(f"Error processing variation {variation_data.get('id', 'unknown')}: {str(e)}")
                    if self.options['verbose']:
                        self.stdout.write(f'            ❌ Error processing variation: {str(e)}')
                    continue

        except Exception as e:
            logger.error(f"Error processing variations for product {product.name}: {str(e)}")
            raise

    def _process_individual_variation(self, product, extracted_data, product_data):
        """
        Process individual product variation

        Args:
            product: SASProduct instance
            extracted_data: Extracted variation data from WooCommerceService
            product_data: Parent product data
        """
        woo_variation_id = extracted_data['woo_variation_id']
        variation_type = extracted_data['variation_type']
        variation_value = extracted_data['variation_value']

        # Check if variation already exists by WooCommerce ID
        existing_variation = SASProductVariation.objects.filter(
            woo_variation_id=woo_variation_id
        ).first()

        # If not found by WooCommerce ID, check by unique constraint
        if not existing_variation:
            existing_variation = SASProductVariation.objects.filter(
                product=product,
                variation_type=variation_type,
                variation_value=variation_value
            ).first()

        # Get image data
        image_data = extracted_data.get('image_data', {})
        image_url = None

        # Use intelligent image selection from WooCommerce service
        if image_data.get('should_use_variation_image') and image_data.get('variation_image_url'):
            image_url = image_data['variation_image_url']
        elif image_data.get('fallback_image_url'):
            image_url = image_data['fallback_image_url']

        # Prepare variation data
        variation_data_obj = {
            'product': product,
            'variation_type': variation_type,
            'variation_value': variation_value,
            'price_modifier': extracted_data['price_modifier'],
            'stock_quantity': extracted_data['stock_quantity'],
            'sku_suffix': extracted_data['sku_suffix'],
            'woo_variation_id': woo_variation_id,
            'is_active': extracted_data['is_active'],
            'attributes': extracted_data['attributes'],
            'weight': extracted_data['weight'],
            'dimensions': extracted_data['dimensions'],
        }

        # Extract and add price fields from raw_data
        if 'raw_data' in extracted_data and extracted_data['raw_data']:
            raw_data = extracted_data['raw_data']

            # Parse prices from raw_data
            if 'price' in raw_data and raw_data['price']:
                try:
                    from decimal import Decimal, InvalidOperation
                    variation_data_obj['price'] = Decimal(str(raw_data['price']))
                except (InvalidOperation, ValueError, TypeError):
                    pass

            if 'regular_price' in raw_data and raw_data['regular_price']:
                try:
                    from decimal import Decimal, InvalidOperation
                    variation_data_obj['regular_price'] = Decimal(str(raw_data['regular_price']))
                except (InvalidOperation, ValueError, TypeError):
                    pass

            if 'sale_price' in raw_data and raw_data['sale_price']:
                try:
                    from decimal import Decimal, InvalidOperation
                    variation_data_obj['sale_price'] = Decimal(str(raw_data['sale_price']))
                except (InvalidOperation, ValueError, TypeError):
                    pass

        if image_url:
            variation_data_obj['image_url'] = image_url

        if existing_variation:
            # Update existing variation
            updated = False
            for key, value in variation_data_obj.items():
                if hasattr(existing_variation, key) and getattr(existing_variation, key) != value:
                    setattr(existing_variation, key, value)
                    updated = True

            if updated:
                existing_variation.save()
                self.stats['variations_updated'] += 1
                if self.options['verbose']:
                    self.stdout.write(f'            🔄 Updated variation: {variation_value}')
        else:
            # Create new variation using get_or_create to avoid duplicates
            try:
                variation, created = SASProductVariation.objects.get_or_create(
                    product=product,
                    variation_type=variation_type,
                    variation_value=variation_value,
                    defaults=variation_data_obj
                )

                if created:
                    self.stats['variations_created'] += 1
                    if self.options['verbose']:
                        self.stdout.write(f'            ✨ Created variation: {variation_value}')
                else:
                    # Found existing, update WooCommerce ID if different
                    if variation.woo_variation_id != woo_variation_id:
                        variation.woo_variation_id = woo_variation_id
                        variation.save(update_fields=['woo_variation_id'])
                        self.stats['variations_updated'] += 1
                        if self.options['verbose']:
                            self.stdout.write(f'            🔄 Updated WooCommerce ID for: {variation_value}')

            except Exception as e:
                logger.error(f"Error creating variation {variation_value}: {str(e)}")
                if self.options['verbose']:
                    self.stdout.write(f'            ❌ Error creating variation: {str(e)}')

        self.stats['variations_processed'] += 1

    def _is_school_related(self, name: str) -> bool:
        """Check if a category/club name is school-related"""
        name_lower = name.lower()
        return any(keyword in name_lower for keyword in self.SCHOOL_KEYWORDS)

    def _is_excluded_subcategory(self, name: str) -> bool:
        """
        Check if a subcategory should be excluded based on EXCLUDE_CLUB_KEYWORDS.

        This filters out product/apparel/event subcategories that are not actual clubs.
        Case-insensitive matching against name.
        """
        name_upper = name.upper()
        return any(keyword.upper() in name_upper for keyword in self.EXCLUDE_CLUB_KEYWORDS)
    
    def _sport_needs_update(self, existing_sport, new_data) -> bool:
        """Check if sport needs updating"""
        fields_to_check = ['name', 'description', 'product_count']
        
        for field in fields_to_check:
            if getattr(existing_sport, field) != new_data.get(field):
                return True
        
        return False
    
    def _club_needs_update(self, existing_club, new_data) -> bool:
        """Check if club needs updating"""
        fields_to_check = ['name', 'description', 'product_count']
        
        for field in fields_to_check:
            if getattr(existing_club, field) != new_data.get(field):
                return True
        
        return False
    
    def _product_needs_update(self, existing_product, new_data) -> bool:
        """Check if product needs updating"""
        fields_to_check = ['name', 'price', 'regular_price', 'sale_price', 'stock_status', 'sku']
        
        for field in fields_to_check:
            existing_value = getattr(existing_product, field)
            new_value = new_data.get(field)
            
            # Handle Decimal comparison
            if isinstance(existing_value, Decimal) and new_value is not None:
                try:
                    new_value = Decimal(str(new_value))
                except (InvalidOperation, ValueError):
                    new_value = existing_value
            
            if existing_value != new_value:
                return True
        
        return False
    
    def _print_summary(self, duration):
        """Print synchronization summary"""
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('🎉 SAS CLUBS SYNC SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        # Sports statistics
        self.stdout.write(f'📊 Sports:')
        self.stdout.write(f'  • Processed: {self.stats["sports_processed"]}')
        self.stdout.write(f'  • Created: {self.stats["sports_created"]}')
        self.stdout.write(f'  • Updated: {self.stats["sports_updated"]}')
        
        # Clubs statistics
        self.stdout.write(f'\n🏛️  Clubs:')
        self.stdout.write(f'  • Processed: {self.stats["clubs_processed"]}')
        self.stdout.write(f'  • Created: {self.stats["clubs_created"]}')
        self.stdout.write(f'  • Updated: {self.stats["clubs_updated"]}')
        self.stdout.write(f'  • Skipped (schools): {self.stats["clubs_skipped"]}')
        
        # Products statistics
        self.stdout.write(f'\n📦 Products:')
        self.stdout.write(f'  • Processed: {self.stats["products_processed"]}')
        self.stdout.write(f'  • Created: {self.stats["products_created"]}')
        self.stdout.write(f'  • Updated: {self.stats["products_updated"]}')

        # Variations statistics
        self.stdout.write(f'\n🔀 Variations:')
        self.stdout.write(f'  • Processed: {self.stats["variations_processed"]}')
        self.stdout.write(f'  • Created: {self.stats["variations_created"]}')
        self.stdout.write(f'  • Updated: {self.stats["variations_updated"]}')

        # Summary
        total_processed = (self.stats["sports_processed"] +
                          self.stats["clubs_processed"] +
                          self.stats["products_processed"] +
                          self.stats["variations_processed"])
        
        self.stdout.write(f'\n📈 Summary:')
        self.stdout.write(f'  • Total items processed: {total_processed}')
        self.stdout.write(f'  • Errors: {self.stats["errors"]}')
        self.stdout.write(f'  • Duration: {duration:.2f} seconds')
        
        # Success rate
        if total_processed > 0:
            success_rate = ((total_processed - self.stats["errors"]) / total_processed) * 100
            self.stdout.write(f'  • Success rate: {success_rate:.1f}%')
        
        self.stdout.write(self.style.SUCCESS('='*60))
        
        if self.stats["errors"] > 0:
            self.stdout.write(self.style.WARNING(f'⚠️  {self.stats["errors"]} errors occurred. Check logs for details.'))
        else:
            self.stdout.write(self.style.SUCCESS('✨ Sync completed successfully with no errors!'))