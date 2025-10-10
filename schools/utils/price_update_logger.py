"""
PriceUpdateLogger - Dedicated logging system for price update operations

This module provides specialized logging functionality for tracking price update
operations across all product categories. It creates a separate log file with
detailed tracking of matches, updates, errors, and performance metrics.

Features:
- Separate log file (priceupdate.log) with rotation
- Thread-safe logging for concurrent operations
- Detailed match tracking with method identification
- Price change auditing (old vs new values)
- Performance timing for operation phases
- Structured summary statistics

Author: Claude Code
Date: 2025-10-10
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from threading import Lock


class PriceUpdateLogger:
    """
    Specialized logger for price update operations with dedicated log file.

    Provides thread-safe logging with automatic rotation and structured
    message formatting for tracking price update operations.
    """

    # Class-level lock for thread safety
    _lock = Lock()
    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern to ensure single logger instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PriceUpdateLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the price update logger with dedicated log file."""
        # Prevent re-initialization
        if PriceUpdateLogger._initialized:
            return

        with self._lock:
            if PriceUpdateLogger._initialized:
                return

            # Create logger instance
            self.logger = logging.getLogger('price_update')
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False  # Prevent duplicate logs

            # Clear any existing handlers
            self.logger.handlers.clear()

            # Determine log file path
            # Try logs/ directory first, fall back to project root
            try:
                from django.conf import settings
                base_dir = settings.BASE_DIR
            except Exception:
                # Fallback if Django not available
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            # Try logs directory
            logs_dir = os.path.join(base_dir, 'logs')
            if not os.path.exists(logs_dir):
                try:
                    os.makedirs(logs_dir, exist_ok=True)
                    log_file = os.path.join(logs_dir, 'priceupdate.log')
                except (OSError, PermissionError):
                    # Fall back to project root
                    log_file = os.path.join(base_dir, 'priceupdate.log')
            else:
                log_file = os.path.join(logs_dir, 'priceupdate.log')

            # Create rotating file handler
            # 10MB max size, keep 5 backup files
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.INFO)

            # Create formatter with operation field
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(operation)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)

            # Add handler to logger
            self.logger.addHandler(file_handler)

            # Also add console handler for immediate feedback
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            PriceUpdateLogger._initialized = True

            # Log initialization (direct to logger to avoid _log call during init)
            self.logger.log(logging.INFO, f'Price update logger initialized: {log_file}', extra={'operation': 'INIT'})

    def _log(self, operation: str, message: str, level: int = logging.INFO):
        """
        Internal logging method with operation context.

        Args:
            operation: Operation type (START, MATCH, UPDATE, ERROR, etc.)
            message: Log message
            level: Logging level (default: INFO)
        """
        with self._lock:
            self.logger.log(level, message, extra={'operation': operation})

    def log_start(self, total_items: int, category: str = 'unknown'):
        """
        Log the start of a price update operation.

        Args:
            total_items: Total number of items to process
            category: Product category being updated
        """
        self._log(
            'START',
            f'Price update started: {total_items} items | Category: {category}'
        )

    def log_match(
        self,
        row_number: int,
        product_code: str,
        target_type: str,
        target_id: int,
        match_method: str
    ):
        """
        Log a successful product/variation match.

        Args:
            row_number: Row number in CSV/Excel file
            product_code: Product code that was matched
            target_type: 'Product' or 'Variation'
            target_id: Database ID of matched target
            match_method: Matching method used (e.g., 'sku_exact', 'sku_suffix_normalized')
        """
        self._log(
            'MATCH',
            f'Row {row_number}: Matched "{product_code}" to {target_type} #{target_id} via {match_method}'
        )

    def log_no_match(
        self,
        row_number: int,
        product_code: str,
        barcode: str,
        tried_fields: list
    ):
        """
        Log a failed product match.

        Args:
            row_number: Row number in CSV/Excel file
            product_code: Product code that failed to match
            barcode: Barcode that failed to match
            tried_fields: List of fields/methods attempted
        """
        tried_str = ', '.join(tried_fields) if tried_fields else 'no fields'
        identifier = product_code or barcode or 'unknown'

        self._log(
            'NO_MATCH',
            f'Row {row_number}: No match for "{identifier}" (tried: {tried_str})',
            level=logging.WARNING
        )

    def log_update(
        self,
        target_type: str,
        target_id: int,
        old_cost: Optional[Decimal],
        new_cost: Optional[Decimal],
        old_margin: Optional[Decimal],
        new_margin: Optional[Decimal],
        old_retail: Optional[Decimal],
        new_retail: Optional[Decimal]
    ):
        """
        Log a price update with before/after values.

        Args:
            target_type: 'Product' or 'Variation'
            target_id: Database ID of updated target
            old_cost: Previous cost price
            new_cost: New cost price
            old_margin: Previous margin price
            new_margin: New margin price
            old_retail: Previous retail price
            new_retail: New retail price
        """
        changes = []

        if new_cost is not None and new_cost != old_cost:
            old_val = f'${old_cost:.2f}' if old_cost else 'N/A'
            new_val = f'${new_cost:.2f}'
            changes.append(f'cost {old_val} → {new_val}')

        if new_margin is not None and new_margin != old_margin:
            old_val = f'${old_margin:.2f}' if old_margin else 'N/A'
            new_val = f'${new_margin:.2f}'
            changes.append(f'margin {old_val} → {new_val}')

        if new_retail is not None and new_retail != old_retail:
            old_val = f'${old_retail:.2f}' if old_retail else 'N/A'
            new_val = f'${new_retail:.2f}'
            changes.append(f'retail {old_val} → {new_val}')

        if changes:
            changes_str = ', '.join(changes)
            self._log(
                'UPDATE',
                f'{target_type} #{target_id}: {changes_str}'
            )

    def log_error(
        self,
        row_number: int,
        product_code: str,
        error_message: str
    ):
        """
        Log an error during processing.

        Args:
            row_number: Row number in CSV/Excel file
            product_code: Product code being processed
            error_message: Error description
        """
        identifier = product_code or 'unknown'
        self._log(
            'ERROR',
            f'Row {row_number}: Error processing "{identifier}" - {error_message}',
            level=logging.ERROR
        )

    def log_summary(self, stats: Dict[str, Any]):
        """
        Log operation summary with statistics.

        Args:
            stats: Dictionary containing:
                - total_items: Total items processed
                - matched: Successfully matched items
                - no_match: Items not found
                - errors: Items with errors
                - duration_seconds: Total operation time
                - category: Product category
        """
        total = stats.get('total_items', 0)
        matched = stats.get('matched', 0)
        no_match = stats.get('no_match', 0)
        errors = stats.get('errors', 0)
        duration = stats.get('duration_seconds', 0)
        category = stats.get('category', 'unknown')

        # Calculate percentages
        match_pct = (matched / total * 100) if total > 0 else 0
        no_match_pct = (no_match / total * 100) if total > 0 else 0
        error_pct = (errors / total * 100) if total > 0 else 0

        # Calculate throughput
        throughput = total / duration if duration > 0 else 0

        summary = (
            f'Completed: {matched} matched ({match_pct:.1f}%), '
            f'{no_match} no match ({no_match_pct:.1f}%), '
            f'{errors} errors ({error_pct:.1f}%) | '
            f'Duration: {duration:.1f}s | '
            f'Throughput: {throughput:.0f} items/s | '
            f'Category: {category}'
        )

        self._log('SUMMARY', summary)

    def log_performance(self, phase: str, duration_seconds: float, items_count: Optional[int] = None):
        """
        Log performance timing for a specific phase.

        Args:
            phase: Phase name (e.g., 'preload', 'matching', 'update')
            duration_seconds: Time taken for this phase
            items_count: Number of items processed (optional)
        """
        if items_count:
            rate = items_count / duration_seconds if duration_seconds > 0 else 0
            message = f'Phase: {phase} | Duration: {duration_seconds:.2f}s | Items: {items_count} | Rate: {rate:.0f} items/s'
        else:
            message = f'Phase: {phase} | Duration: {duration_seconds:.2f}s'

        self._log('PERFORMANCE', message)

    def log_bulk_update_start(self, chunk_number: int, chunk_size: int, total_items: int):
        """
        Log the start of a bulk update chunk.

        Args:
            chunk_number: Current chunk number (1-indexed)
            chunk_size: Items in this chunk
            total_items: Total items being processed
        """
        progress_pct = ((chunk_number - 1) * chunk_size / total_items * 100) if total_items > 0 else 0

        self._log(
            'BULK_UPDATE',
            f'Processing chunk {chunk_number}: {chunk_size} items ({progress_pct:.1f}% complete)'
        )

    def log_validation_error(self, row_number: int, field_name: str, field_value: Any, error_reason: str):
        """
        Log a data validation error.

        Args:
            row_number: Row number in CSV/Excel file
            field_name: Field that failed validation
            field_value: Invalid value
            error_reason: Reason for validation failure
        """
        self._log(
            'VALIDATION',
            f'Row {row_number}: Invalid {field_name} value "{field_value}" - {error_reason}',
            level=logging.WARNING
        )

    def log_category_switch(self, from_category: str, to_category: str):
        """
        Log a category switch during processing.

        Args:
            from_category: Previous category
            to_category: New category
        """
        self._log(
            'CATEGORY',
            f'Switching category: {from_category} → {to_category}'
        )

    def log_backup_created(self, target_type: str, target_id: int, backup_data: Dict[str, Any]):
        """
        Log price backup creation.

        Args:
            target_type: 'Product' or 'Variation'
            target_id: Database ID
            backup_data: Backup price data
        """
        self._log(
            'BACKUP',
            f'{target_type} #{target_id}: Backup created with {len(backup_data)} fields'
        )


# Lazy singleton instance - only initialized when first accessed
_price_logger_instance = None

def get_price_logger():
    """
    Get the singleton PriceUpdateLogger instance.
    Uses lazy initialization to avoid blocking imports.

    Usage:
        from schools.utils.price_update_logger import get_price_logger
        logger = get_price_logger()
        logger.log_start(100, 'wholesale-schools')
    """
    global _price_logger_instance
    if _price_logger_instance is None:
        _price_logger_instance = PriceUpdateLogger()
    return _price_logger_instance
