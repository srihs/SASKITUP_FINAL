# Django Clubs App

A comprehensive Django application for managing LOTTO and SAS sports clubs with WooCommerce integration.

## Features

- **Club Management**: Create and manage sports clubs with detailed information
- **Category Management**: Organize products into club-specific categories
- **Product Management**: Comprehensive product catalog with pricing and inventory
- **WooCommerce Integration**: Sync data from WooCommerce stores
- **Image Management**: Automatic image downloading and local storage
- **Admin Interface**: Full-featured Django admin interface
- **API Support**: RESTful endpoints for external integration

## Models

### Club
- Club information (name, contact details, address)
- Club type (LOTTO/SAS) and sport classification
- Logo image and website links
- WooCommerce category integration
- Activity status management

### ClubCategory  
- Product categories within each club
- Category descriptions and images
- Product count tracking
- WooCommerce category mapping

### Product
- Comprehensive product information
- Pricing with sale support
- Inventory management
- Product images and attributes
- WooCommerce product integration

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

2. Configure MySQL database in your .env file:
```bash
DB_NAME=your_database_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=3306
```

3. Configure WooCommerce API credentials:
```bash
# LOTTO Store
LOTTO_WOOCOMMERCE_API_URL=https://your-lotto-store.com/wp-json/wc/v3/
LOTTO_WOOCOMMERCE_API_CONSUMER_KEY=your_consumer_key
LOTTO_WOOCOMMERCE_API_SECRET=your_consumer_secret

# SAS Store  
SAS_WOOCOMMERCE_API_URL=https://your-sas-store.com/wp-json/wc/v3/
SAS_WOOCOMMERCE_API_CONSUMER_KEY=your_consumer_key
SAS_WOOCOMMERCE_API_SECRET=your_consumer_secret
```

4. Run migrations:
```bash
python manage.py makemigrations clubs
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

## Management Commands

### sync_lotto_clubs

Synchronizes club data from WooCommerce API.

```bash
# Sync LOTTO clubs
python manage.py sync_lotto_clubs --store-type LOTTO

# Sync SAS clubs  
python manage.py sync_lotto_clubs --store-type SAS

# Dry run (no database changes)
python manage.py sync_lotto_clubs --dry-run

# Force update existing records
python manage.py sync_lotto_clubs --force-update

# Limit number of clubs processed
python manage.py sync_lotto_clubs --limit 10

# Custom parent category ID
python manage.py sync_lotto_clubs --parent-category-id 25
```

## WooCommerce Service

The `WooCommerceService` class provides comprehensive API integration:

```python
from clubs.services.woocommerce_service import WooCommerceService

# Initialize service
woo_service = WooCommerceService(store_type='LOTTO')

# Test connection
if woo_service.test_connection():
    print("Connected successfully!")

# Get categories with products
categories = woo_service.get_categories_with_products(parent_id=23)

# Get products by category
products = woo_service.get_products_by_category(category_id=123)

# Download images
filename, content_file = woo_service.download_image(image_url, 'clubs')
```

## Admin Interface

Access the admin interface at `/admin/` with comprehensive management features:

- **Club Management**: CRUD operations with bulk actions
- **Category Management**: Product count updates and filtering
- **Product Management**: Inventory management and pricing updates
- **Bulk Operations**: Mass updates and status changes
- **Advanced Filtering**: Multi-level filtering and search
- **Linked Navigation**: Easy navigation between related records

## API Endpoints

The app includes URL configuration for future API development:

- Club list/detail endpoints
- Category management endpoints  
- Product catalog endpoints
- Search and filtering capabilities

## File Structure

```
clubs/
├── management/
│   └── commands/
│       └── sync_lotto_clubs.py
├── services/
│   └── woocommerce_service.py
├── admin.py
├── apps.py
├── models.py
├── urls.py
├── views.py
└── README.md
```

## Configuration

### Media Storage

Images are automatically organized in media folders:
- `clubs/images/` - Club logos
- `categories/images/` - Category images  
- `products/images/` - Product images

### Logging

Comprehensive logging configuration includes:
- Console output for development
- File logging for production
- App-specific logger for clubs module

### Database Optimization

- Indexed fields for performance
- Foreign key relationships with select_related
- Bulk operations for data synchronization
- Transaction management for data integrity

## Error Handling

- Comprehensive exception handling in API calls
- Retry logic for failed requests
- Graceful degradation when services unavailable
- Detailed error logging and user feedback

## Security

- API credential management via environment variables
- Request authentication and rate limiting
- Input validation and sanitization
- Secure file upload handling

## Performance

- Efficient database queries with select_related
- Image optimization and local storage
- Bulk operations for large datasets
- Connection pooling and retry strategies