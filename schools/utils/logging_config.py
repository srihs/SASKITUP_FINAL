"""
Logging Configuration for Price Update System

This module provides logging configuration that can be integrated into Django settings.
It defines handlers, formatters, and loggers specifically for price update operations.

Usage in settings.py:
    from schools.utils.logging_config import PRICE_UPDATE_LOGGING_CONFIG

    # Merge with existing LOGGING configuration
    LOGGING['handlers'].update(PRICE_UPDATE_LOGGING_CONFIG['handlers'])
    LOGGING['formatters'].update(PRICE_UPDATE_LOGGING_CONFIG['formatters'])
    LOGGING['loggers'].update(PRICE_UPDATE_LOGGING_CONFIG['loggers'])

Author: Claude Code
Date: 2025-10-10
"""

import os
from pathlib import Path

# Get project base directory
try:
    from django.conf import settings
    BASE_DIR = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent.parent)
except Exception:
    # Fallback if Django not available
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Ensure logs directory exists
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Price update log file path
PRICE_UPDATE_LOG_FILE = LOGS_DIR / 'priceupdate.log'

# Price update logging configuration
PRICE_UPDATE_LOGGING_CONFIG = {
    'formatters': {
        'price_update': {
            'format': '[%(asctime)s] [%(levelname)s] [%(operation)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'price_update_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(PRICE_UPDATE_LOG_FILE),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'price_update',
            'encoding': 'utf-8',
        },
        'price_update_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'price_update',
        },
    },
    'loggers': {
        'price_update': {
            'handlers': ['price_update_file', 'price_update_console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


def configure_price_update_logging():
    """
    Configure price update logging programmatically.

    This function can be called to ensure price update logging is configured
    even if not added to Django settings.

    Returns:
        logging.Logger: Configured price_update logger
    """
    import logging
    from logging.handlers import RotatingFileHandler

    # Get or create logger
    logger = logging.getLogger('price_update')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(operation)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Create file handler
    file_handler = RotatingFileHandler(
        PRICE_UPDATE_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
