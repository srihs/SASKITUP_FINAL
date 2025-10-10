"""
ProductMatcherService - Flexible product matching across multiple product models

This service provides a unified interface for finding products across different
categories (Wholesale Schools, TUS Schools, SAS Clubs, LOTTO Clubs) using
various matching strategies (SKU, barcode, etc.).
"""
import logging
from typing import Optional, Tuple, Any
from django.db.models import Model


logger = logging.getLogger(__name__)


class ProductMatcherService:
    """
    Service for matching products across different product models based on category.

    Supports:
    - wholesale-schools → WholesaleProduct (cin7_sku, cin7_barcode)
    - retail-schools → TUSProduct (sku, barcode)
    - sas-clubs → SASProduct (sku, barcode)
    - lotto-clubs → LottoProduct (sku, barcode)
    """

    # Category to model mapping
    CATEGORY_MODELS = {
        'wholesale-schools': 'schools.WholesaleProduct',
        'retail-schools': 'schools.TUSProduct',
        'sas-clubs': 'clubs.SASProduct',
        'lotto-clubs': 'clubs.LottoProduct',
    }

    # SKU field mapping
    SKU_FIELDS = {
        'wholesale-schools': 'cin7_sku',
        'retail-schools': 'sku',
        'sas-clubs': 'sku',
        'lotto-clubs': 'sku',
    }

    # Barcode field mapping
    BARCODE_FIELDS = {
        'wholesale-schools': 'cin7_barcode',
        'retail-schools': 'barcode',
        'sas-clubs': 'barcode',
        'lotto-clubs': 'barcode',
    }

    # Price field mapping (for updating retail price)
    PRICE_FIELDS = {
        'wholesale-schools': 'retail_price',
        'retail-schools': 'price',
        'sas-clubs': 'price',
        'lotto-clubs': 'price',
    }

    def __init__(self):
        """Initialize the service and cache model references."""
        self._model_cache = {}

    def _get_model_class(self, category: str) -> Optional[type]:
        """
        Get the model class for a given category.

        Args:
            category: Category identifier (e.g., 'wholesale-schools')

        Returns:
            Model class or None if not found
        """
        if category not in self.CATEGORY_MODELS:
            logger.warning(f"Unknown category: {category}")
            return None

        if category in self._model_cache:
            return self._model_cache[category]

        model_path = self.CATEGORY_MODELS[category]
        app_label, model_name = model_path.split('.')

        try:
            from django.apps import apps
            model_class = apps.get_model(app_label, model_name)
            self._model_cache[category] = model_class
            return model_class
        except Exception as e:
            logger.error(f"Failed to load model {model_path}: {str(e)}")
            return None

    def _match_by_sku(
        self,
        model_class: type,
        sku_field: str,
        product_code: str
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Try exact then case-insensitive SKU match.

        Args:
            model_class: Model class to query
            sku_field: Name of the SKU field
            product_code: Product code to match

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        # Exact match
        try:
            product = model_class.objects.filter(**{sku_field: product_code}).first()
            if product:
                logger.debug(f"Found product by exact SKU: {product_code}")
                return product, 'sku_exact'
        except Exception as e:
            logger.error(f"Error in exact SKU match: {str(e)}")

        # Case-insensitive match
        try:
            product = model_class.objects.filter(**{f"{sku_field}__iexact": product_code}).first()
            if product:
                logger.debug(f"Found product by case-insensitive SKU: {product_code}")
                return product, 'sku_iexact'
        except Exception as e:
            logger.error(f"Error in case-insensitive SKU match: {str(e)}")

        # Space-normalized match (database might have spaces but CSV might not, or vice versa)
        try:
            normalized_code = product_code.replace(' ', '').upper()
            for product in model_class.objects.all():
                sku_value = getattr(product, sku_field, None)
                if sku_value:
                    normalized_db = sku_value.replace(' ', '').upper()
                    if normalized_db == normalized_code:
                        logger.debug(f"Found product by space-normalized SKU: {product_code} -> {sku_value}")
                        return product, 'sku_normalized'
        except Exception as e:
            logger.error(f"Error in space-normalized SKU match: {str(e)}")

        return None, None

    def _match_by_barcode(
        self,
        model_class: type,
        barcode_field: str,
        barcode: str
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Try exact then case-insensitive barcode match.

        Args:
            model_class: Model class to query
            barcode_field: Name of the barcode field
            barcode: Barcode to match

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        # Exact match
        try:
            product = model_class.objects.filter(**{barcode_field: barcode}).first()
            if product:
                logger.debug(f"Found product by exact barcode: {barcode}")
                return product, 'barcode_exact'
        except Exception as e:
            logger.error(f"Error in exact barcode match: {str(e)}")

        # Case-insensitive match
        try:
            product = model_class.objects.filter(**{f"{barcode_field}__iexact": barcode}).first()
            if product:
                logger.debug(f"Found product by case-insensitive barcode: {barcode}")
                return product, 'barcode_iexact'
        except Exception as e:
            logger.error(f"Error in case-insensitive barcode match: {str(e)}")

        return None, None

    def _match_by_variation_suffix(
        self,
        variation_model: type,
        product_code: str,
        field_name: str = 'sku_suffix'
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Generic variation field matching for any variation model.

        Args:
            variation_model: TUSProductVariation, SASProductVariation, or LottoProductVariation
            product_code: Code to match against variation field
            field_name: Field name to match against (default: 'sku_suffix')

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        try:
            # Exact match
            filter_kwargs = {field_name: product_code}
            variation = variation_model.objects.filter(**filter_kwargs).first()
            if variation and variation.product:
                logger.debug(f"Found product by exact variation {field_name}: {product_code}")
                return variation.product, f'{field_name}_exact'

            # Case-insensitive match
            filter_kwargs = {f'{field_name}__iexact': product_code}
            variation = variation_model.objects.filter(**filter_kwargs).first()
            if variation and variation.product:
                logger.debug(f"Found product by case-insensitive variation {field_name}: {product_code}")
                return variation.product, f'{field_name}_iexact'

            # Space-normalized match (e.g., "R9039 -4--7" matches "R9039-4--7" or vice versa)
            # Try this for all SKUs since database might have spaces but CSV might not
            normalized_code = product_code.replace(' ', '').upper()
            # Use select_related to optimize database queries
            for variation in variation_model.objects.select_related('product').all():
                field_value = getattr(variation, field_name, None)
                if field_value:
                    normalized_db = field_value.replace(' ', '').upper()
                    if normalized_db == normalized_code:
                        logger.debug(f"Found product by space-normalized variation {field_name}: {product_code} -> {field_value}")
                        return variation.product, f'{field_name}_normalized'

        except Exception as e:
            logger.error(f"Error matching variation {field_name}: {str(e)}")

        return None, None

    def _match_variation_with_instance(
        self,
        variation_model: type,
        product_code: str,
        field_name: str = 'sku_suffix'
    ) -> Tuple[Optional[Model], Optional[str], Optional[Model]]:
        """
        Generic variation field matching that returns both product and variation instance.

        Args:
            variation_model: TUSProductVariation, SASProductVariation, or LottoProductVariation
            product_code: Code to match against variation field
            field_name: Field name to match against (default: 'sku_suffix')

        Returns:
            Tuple of (product instance or None, match method or None, variation instance or None)
        """
        try:
            # Exact match
            filter_kwargs = {field_name: product_code}
            variation = variation_model.objects.filter(**filter_kwargs).first()
            if variation and variation.product:
                logger.debug(f"Found product by exact variation {field_name}: {product_code}")
                return variation.product, f'{field_name}_exact', variation

            # Case-insensitive match
            filter_kwargs = {f'{field_name}__iexact': product_code}
            variation = variation_model.objects.filter(**filter_kwargs).first()
            if variation and variation.product:
                logger.debug(f"Found product by case-insensitive variation {field_name}: {product_code}")
                return variation.product, f'{field_name}_iexact', variation

            # Space-normalized match (e.g., "R9039 -4--7" matches "R9039-4--7" or vice versa)
            # Try this for all SKUs since database might have spaces but CSV might not
            normalized_code = product_code.replace(' ', '').upper()
            # Use select_related to optimize database queries
            for variation in variation_model.objects.select_related('product').all():
                field_value = getattr(variation, field_name, None)
                if field_value:
                    normalized_db = field_value.replace(' ', '').upper()
                    if normalized_db == normalized_code:
                        logger.debug(f"Found product by space-normalized variation {field_name}: {product_code} -> {field_value}")
                        return variation.product, f'{field_name}_normalized', variation

        except Exception as e:
            logger.error(f"Error matching variation {field_name}: {str(e)}")

        return None, None, None

    def _match_by_style_code(
        self,
        model_class: type,
        product_code: str
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Try exact then case-insensitive style_code match (SAS only).

        Args:
            model_class: Model class to query
            product_code: Product code to match against style_code

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        # Exact match
        try:
            product = model_class.objects.filter(style_code=product_code).first()
            if product:
                logger.debug(f"Found SAS product by exact style_code: {product_code}")
                return product, 'style_code_exact'
        except Exception as e:
            logger.error(f"Error in exact style_code match: {str(e)}")

        # Case-insensitive match
        try:
            product = model_class.objects.filter(style_code__iexact=product_code).first()
            if product:
                logger.debug(f"Found SAS product by case-insensitive style_code: {product_code}")
                return product, 'style_code_iexact'
        except Exception as e:
            logger.error(f"Error in case-insensitive style_code match: {str(e)}")

        return None, None

    def _match_by_partial_sku(
        self,
        model_class: type,
        sku_field: str,
        product_code: str
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Try partial SKU match (contains).

        Args:
            model_class: Model class to query
            sku_field: Name of the SKU field
            product_code: Product code to match

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        try:
            product = model_class.objects.filter(**{f"{sku_field}__icontains": product_code}).first()
            if product:
                logger.debug(f"Found product by partial SKU: {product_code}")
                return product, 'sku_partial'
        except Exception as e:
            logger.error(f"Error in partial SKU match: {str(e)}")

        return None, None

    def _match_by_name(
        self,
        model_class: type,
        identifier: str
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Try exact then contains name match as last resort.

        Args:
            model_class: Model class to query
            identifier: Product identifier to match against name

        Returns:
            Tuple of (product instance or None, match method or None)
        """
        # Exact match
        try:
            product = model_class.objects.filter(name__iexact=identifier).first()
            if product:
                logger.debug(f"Found product by exact name: {identifier}")
                return product, 'name_exact'
        except Exception as e:
            logger.error(f"Error in exact name match: {str(e)}")

        # Contains match
        try:
            product = model_class.objects.filter(name__icontains=identifier).first()
            if product:
                logger.debug(f"Found product by name contains: {identifier}")
                return product, 'name_contains'
        except Exception as e:
            logger.error(f"Error in name contains match: {str(e)}")

        return None, None

    def find_product(
        self,
        category: str,
        product_code: str = '',
        barcode: str = ''
    ) -> Tuple[Optional[Model], Optional[str]]:
        """
        Find a product using category-specific matching strategies with flexible fallbacks.

        Matching Priority by Category:

        TUS Products (retail-schools):
            1-2. Barcode → Variation SKU (exact, case-insensitive) - CSV "Barcode" matches variation.sku
            3-4. Product Code → Variation SKU (exact, case-insensitive)
            5-6. Barcode → Product Barcode (exact, case-insensitive) - fallback
            7-8. Product SKU (exact, case-insensitive)
            9. Product SKU (partial/contains)
            10-11. Name (exact, contains)

        SAS Products (sas-clubs):
            1-2. Barcode → Variation sku_suffix (exact, case-insensitive) - CSV "Barcode" matches variation.sku_suffix
            3-4. Product Code → Variation sku_suffix (exact, case-insensitive)
            5-6. Product SKU (exact, case-insensitive)
            7-8. Barcode → Product Barcode (exact, case-insensitive) - fallback
            9-10. Style Code (exact, case-insensitive)
            11. Product SKU (partial/contains)
            12-13. Name (exact, contains)

        LOTTO Products (lotto-clubs):
            1-2. Variation sku_suffix (exact, case-insensitive)
            3-4. Product SKU (exact, case-insensitive)
            5-6. Barcode (exact, case-insensitive)
            7. Product SKU (partial/contains)
            8-9. Name (exact, contains)

        Wholesale Products (wholesale-schools):
            1-2. SKU (exact, case-insensitive)
            3-4. Barcode (exact, case-insensitive)
            5. SKU (partial/contains)
            6-7. Name (exact, contains)

        Args:
            category: Category identifier (e.g., 'wholesale-schools')
            product_code: Product SKU/code
            barcode: Product barcode

        Returns:
            Tuple of (product instance or None, match method or None)
            Match methods: 'sku_exact', 'sku_iexact', 'sku_partial', 'barcode_exact', 'barcode_iexact',
                          'sku_suffix_exact', 'sku_suffix_iexact', 'variation_sku_suffix_from_barcode_exact',
                          'variation_sku_suffix_from_barcode_iexact', 'style_code_exact', 'style_code_iexact',
                          'name_exact', 'name_contains'
        """
        model_class = self._get_model_class(category)
        if not model_class:
            logger.warning(f"Cannot find products for category: {category}")
            return None, None

        sku_field = self.SKU_FIELDS.get(category)
        barcode_field = self.BARCODE_FIELDS.get(category)

        # TUS: Variation SKU (from barcode), then Variation SKU (from product_code), then Product Barcode, then Product SKU, then partial/name
        if category == 'retail-schools':
            # Priority 1-2: Try barcode against variation SKU FIRST (Excel barcode column contains variation SKU)
            if barcode:
                try:
                    from schools.models_tus import TUSProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        TUSProductVariation, barcode, field_name='sku'
                    )
                    if product:
                        # Return with specific match method to indicate barcode matched variation SKU
                        return product, f'variation_sku_from_barcode_{match_method.split("_")[-1]}'
                except Exception as e:
                    logger.error(f"Error importing TUSProductVariation for barcode matching: {str(e)}")

            # Priority 3-4: Try product_code against variation SKU
            if product_code:
                try:
                    from schools.models_tus import TUSProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        TUSProductVariation, product_code, field_name='sku'
                    )
                    if product:
                        return product, match_method
                except Exception as e:
                    logger.error(f"Error importing TUSProductVariation for product_code matching: {str(e)}")

            # Priority 5-6: Try barcode against product-level barcode field (fallback)
            if barcode and barcode_field:
                product, match_method = self._match_by_barcode(model_class, barcode_field, barcode)
                if product:
                    return product, match_method

            # Priority 7-8: Then try product SKU
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 9: Try partial SKU match
            if product_code and sku_field:
                product, match_method = self._match_by_partial_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 10-11: Finally try name matching
            if product_code:
                product, match_method = self._match_by_name(model_class, product_code)
                if product:
                    return product, match_method

        # SAS: Barcode as sku_suffix FIRST, then Variation sku_suffix, then Product SKU, then barcode, then style_code, then partial/name
        elif category == 'sas-clubs':
            # Priority 1-2: Try barcode against variation sku_suffix first (CSV "Barcode" column → variation.sku_suffix)
            if barcode:
                try:
                    from clubs.models_sas import SASProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        SASProductVariation, barcode, field_name='sku_suffix'
                    )
                    if product:
                        # Return with specific match method to indicate barcode matched sku_suffix
                        return product, f'variation_sku_suffix_from_barcode_{match_method.split("_")[-1]}'
                except Exception as e:
                    logger.error(f"Error matching SAS variation by barcode: {str(e)}")

            # Priority 3-4: Try product_code against variation sku_suffix
            if product_code:
                try:
                    from clubs.models_sas import SASProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        SASProductVariation, product_code, field_name='sku_suffix'
                    )
                    if product:
                        return product, match_method
                except Exception as e:
                    logger.error(f"Error importing SASProductVariation: {str(e)}")

            # Priority 5-6: Then try product SKU
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 7-8: Try barcode against product barcode field (fallback)
            if barcode and barcode_field:
                product, match_method = self._match_by_barcode(model_class, barcode_field, barcode)
                if product:
                    return product, match_method

            # Priority 9-10: Try style_code
            if product_code:
                product, match_method = self._match_by_style_code(model_class, product_code)
                if product:
                    return product, match_method

            # Priority 11: Try partial SKU match
            if product_code and sku_field:
                product, match_method = self._match_by_partial_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 12-13: Finally try name matching
            if product_code:
                product, match_method = self._match_by_name(model_class, product_code)
                if product:
                    return product, match_method

        # LOTTO: Variation sku_suffix FIRST, then Product SKU, then barcode
        elif category == 'lotto-clubs':
            # Priority 1-2: Try variation sku_suffix first
            if product_code:
                try:
                    from clubs.models_lotto import LottoProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        LottoProductVariation, product_code, field_name='sku_suffix'
                    )
                    if product:
                        return product, match_method
                except Exception as e:
                    logger.error(f"Error importing LottoProductVariation: {str(e)}")

            # Priority 3-4: Then try product SKU
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 5-6: Finally try barcode
            if barcode and barcode_field:
                product, match_method = self._match_by_barcode(model_class, barcode_field, barcode)
                if product:
                    return product, match_method

        # Wholesale: Variation cin7_sku FIRST, then Product SKU, then barcode
        elif category == 'wholesale-schools':
            # Priority 1-2: Try variation cin7_sku first
            if product_code:
                try:
                    from schools.models import WholesaleProductVariation
                    product, match_method = self._match_by_variation_suffix(
                        WholesaleProductVariation, product_code, field_name='cin7_sku'
                    )
                    if product:
                        return product, match_method
                except Exception as e:
                    logger.error(f"Error importing WholesaleProductVariation: {str(e)}")

            # Priority 3-4: Try product SKU
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method

            # Priority 5-6: Try barcode
            if barcode and barcode_field:
                product, match_method = self._match_by_barcode(model_class, barcode_field, barcode)
                if product:
                    return product, match_method

        else:
            logger.warning(f"Unknown category matching strategy: {category}")
            return None, None

        # No match found
        logger.debug(f"No product found for category={category}, code={product_code}, barcode={barcode}")
        return None, None

    def find_product_with_variation(
        self,
        category: str,
        product_code: str = '',
        barcode: str = ''
    ) -> Tuple[Optional[Model], Optional[str], Optional[Model]]:
        """
        Find product and return matched variation instance for categories with variations.

        This method is specifically for the price update system which needs to update
        variation-level pricing rather than product-level pricing.

        Returns:
            Tuple of (product instance or None, match method or None, variation instance or None)
            variation will be None for categories without variations or when matched at product level
        """
        model_class = self._get_model_class(category)
        if not model_class:
            logger.warning(f"Cannot find products for category: {category}")
            return None, None, None

        sku_field = self.SKU_FIELDS.get(category)
        barcode_field = self.BARCODE_FIELDS.get(category)

        # TUS (retail-schools): Return variation instance when matched
        if category == 'retail-schools':
            # Priority 1-2: Try barcode against variation SKU
            if barcode:
                try:
                    from schools.models_tus import TUSProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        TUSProductVariation, barcode, field_name='sku'
                    )
                    if product and variation:
                        return product, f'variation_sku_from_barcode_{match_method.split("_")[-1]}', variation
                except Exception as e:
                    logger.error(f"Error matching TUS variation by barcode: {str(e)}")

            # Priority 3-4: Try product_code against variation SKU
            if product_code:
                try:
                    from schools.models_tus import TUSProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        TUSProductVariation, product_code, field_name='sku'
                    )
                    if product and variation:
                        return product, match_method, variation
                except Exception as e:
                    logger.error(f"Error matching TUS variation by product_code: {str(e)}")

            # Priority 5-6: Try barcode against product-level barcode (no variation)
            if barcode and barcode_field:
                product, match_method = self._match_by_barcode(model_class, barcode_field, barcode)
                if product:
                    return product, match_method, None

            # Priority 7-8: Try product SKU (no variation)
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method, None

        # SAS (sas-clubs): Return variation instance when matched
        elif category == 'sas-clubs':
            # Priority 1-2: Try barcode against variation sku_suffix
            if barcode:
                try:
                    from clubs.models_sas import SASProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        SASProductVariation, barcode, field_name='sku_suffix'
                    )
                    if product and variation:
                        return product, f'variation_sku_suffix_from_barcode_{match_method.split("_")[-1]}', variation
                except Exception as e:
                    logger.error(f"Error matching SAS variation by barcode: {str(e)}")

            # Priority 3-4: Try product_code against variation sku_suffix
            if product_code:
                try:
                    from clubs.models_sas import SASProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        SASProductVariation, product_code, field_name='sku_suffix'
                    )
                    if product and variation:
                        return product, match_method, variation
                except Exception as e:
                    logger.error(f"Error matching SAS variation by product_code: {str(e)}")

            # Fallback to product-level matching (no variation)
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method, None

        # LOTTO (lotto-clubs): Return variation instance when matched
        elif category == 'lotto-clubs':
            # Priority 1-2: Try variation sku_suffix
            if product_code:
                try:
                    from clubs.models_lotto import LottoProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        LottoProductVariation, product_code, field_name='sku_suffix'
                    )
                    if product and variation:
                        return product, match_method, variation
                except Exception as e:
                    logger.error(f"Error matching Lotto variation: {str(e)}")

            # Fallback to product-level matching (no variation)
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method, None

        # Wholesale (wholesale-schools): Return variation instance when matched
        elif category == 'wholesale-schools':
            # Priority 1-2: Try variation cin7_sku
            if product_code:
                try:
                    from schools.models import WholesaleProductVariation
                    product, match_method, variation = self._match_variation_with_instance(
                        WholesaleProductVariation, product_code, field_name='cin7_sku'
                    )
                    if product and variation:
                        return product, match_method, variation
                except Exception as e:
                    logger.error(f"Error matching Wholesale variation: {str(e)}")

            # Fallback to product-level matching (no variation)
            if product_code and sku_field:
                product, match_method = self._match_by_sku(model_class, sku_field, product_code)
                if product:
                    return product, match_method, None

        else:
            logger.warning(f"Unknown category: {category}")
            return None, None, None

        # No match found
        logger.debug(f"No product/variation found for category={category}, code={product_code}, barcode={barcode}")
        return None, None, None

    def get_price_field(self, category: str) -> Optional[str]:
        """
        Get the price field name for a given category.

        Args:
            category: Category identifier

        Returns:
            Price field name or None
        """
        return self.PRICE_FIELDS.get(category)

    def get_sku_field(self, category: str) -> Optional[str]:
        """
        Get the SKU field name for a given category.

        Args:
            category: Category identifier

        Returns:
            SKU field name or None
        """
        return self.SKU_FIELDS.get(category)

    def get_barcode_field(self, category: str) -> Optional[str]:
        """
        Get the barcode field name for a given category.

        Args:
            category: Category identifier

        Returns:
            Barcode field name or None
        """
        return self.BARCODE_FIELDS.get(category)

    def get_category_info(self, category: str) -> dict:
        """
        Get comprehensive category information.

        Args:
            category: Category identifier

        Returns:
            Dictionary with model name, SKU field, barcode field, price field
        """
        return {
            'model': self.CATEGORY_MODELS.get(category),
            'sku_field': self.SKU_FIELDS.get(category),
            'barcode_field': self.BARCODE_FIELDS.get(category),
            'price_field': self.PRICE_FIELDS.get(category),
        }
