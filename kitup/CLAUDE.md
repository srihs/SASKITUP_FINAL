# Kitup Project - Technical Documentation

## Overview

The kitup project is the main Django project configuration that orchestrates the LOTTO Club Integration System. It handles project-wide settings, URL routing, WSGI/ASGI configuration, and provides the main entry points for the application.

## Project Structure

```
kitup/                              # Main Django project
├── kitup/                          # Project configuration
│   ├── settings.py                 # Django settings with WooCommerce config
│   ├── urls.py                     # Main URL routing
│   ├── views.py                    # Project-level views
│   ├── wsgi.py                     # WSGI configuration
│   └── asgi.py                     # ASGI configuration
├── clubs/                          # Core clubs application
├── template/                       # HTML templates
├── static/                         # Static files (CSS, JS, images)
├── media/                          # User-uploaded files
└── requirements.txt                # Python dependencies
```

## Configuration and Settings

### Django Settings Configuration

#### Core Settings
```python
# settings.py
import os
from decouple import config

# Basic Django configuration
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production-abc123xyz789')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

LOCAL_APPS = [
    'clubs',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS
```

#### Database Configuration
```python
# Database settings with MySQL support
USE_MYSQL = config('USE_MYSQL', default=False, cast=bool)

if USE_MYSQL:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='3306', cast=int),
            'OPTIONS': {
                'sql_mode': 'traditional',
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            }
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

#### Static and Media Files
```python
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files (user uploads) - now primarily for template assets
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Template configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'template'],  # Custom template directory
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
```

#### Logging Configuration
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'django.log',
            'maxBytes': 1024*1024*15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'clubs': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',  # Log slow queries
            'propagate': False,
        },
    },
}
```

### Environment Variables

#### Required Environment Variables

**Database Configuration**
```bash
# Database Settings
USE_MYSQL=True                      # Enable MySQL instead of SQLite
DB_NAME=saskitup_production         # Database name
DB_USER=saskitup_user              # Database username
DB_PASSWORD=secure_password_here    # Database password
DB_HOST=localhost                   # Database host
DB_PORT=3306                       # Database port
```

**Django Configuration**
```bash
# Django Core Settings
SECRET_KEY=your-super-secret-django-key-here-minimum-50-characters
DEBUG=False                         # Set to False in production
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,localhost
```

**WooCommerce API Credentials**

**LOTTO Store Configuration:**
```bash
LOTTO_WOOCOMMERCE_API_URL=https://lotto-store.co.za/wp-json/wc/v3/
LOTTO_WOOCOMMERCE_API_CONSUMER_KEY=ck_your_lotto_consumer_key_here
LOTTO_WOOCOMMERCE_API_SECRET=cs_your_lotto_consumer_secret_here
```

**SAS Store Configuration:**
```bash
SAS_WOOCOMMERCE_API_URL=https://sas-store.co.za/wp-json/wc/v3/
SAS_WOOCOMMERCE_API_CONSUMER_KEY=ck_your_sas_consumer_key_here
SAS_WOOCOMMERCE_API_SECRET=cs_your_sas_consumer_secret_here
```

### Environment File Template (.env)
```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database Configuration
USE_MYSQL=True
DB_NAME=saskitup_production
DB_USER=saskitup_user
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=3306

# LOTTO WooCommerce API
LOTTO_WOOCOMMERCE_API_URL=https://lotto-store.co.za/wp-json/wc/v3/
LOTTO_WOOCOMMERCE_API_CONSUMER_KEY=ck_your_consumer_key
LOTTO_WOOCOMMERCE_API_SECRET=cs_your_consumer_secret

# SAS WooCommerce API  
SAS_WOOCOMMERCE_API_URL=https://sas-store.co.za/wp-json/wc/v3/
SAS_WOOCOMMERCE_API_CONSUMER_KEY=ck_your_sas_consumer_key
SAS_WOOCOMMERCE_API_SECRET=cs_your_sas_consumer_secret

# Optional: Email configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

## URL Configuration

### Main Project URLs
```python
# kitup/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('clubs/', include('clubs.urls')),
    path('', views.home_redirect),  # Redirect root to clubs dashboard
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
```

### Project-Level Views
```python
# kitup/views.py
from django.shortcuts import redirect

def home_redirect(request):
    """
    Redirect root URL to clubs dashboard
    """
    return redirect('clubs:dashboard')
```

## WSGI and ASGI Configuration

### WSGI Configuration
```python
# kitup/wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
application = get_wsgi_application()
```

### ASGI Configuration (for future async support)
```python
# kitup/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
application = get_asgi_application()
```

## Dependencies

### Core Requirements
```txt
# requirements.txt

# Django and Core Dependencies
Django>=5.2.5
mysqlclient>=2.1.1                 # MySQL database adapter
python-decouple>=3.8               # Environment variable management
Pillow>=10.0.0                     # Image processing (for admin)

# API Integration
requests>=2.31.0                   # HTTP library for API calls
urllib3>=2.0.0                     # HTTP client

# Utilities
python-slugify>=8.0.1             # URL-friendly slugs
```

### Production Dependencies
```txt
# requirements-prod.txt
-r requirements.txt

# Production Server
gunicorn>=21.2.0                   # WSGI HTTP server
whitenoise>=6.5.0                  # Static file serving

# Monitoring and Performance
sentry-sdk[django]>=1.32.0        # Error tracking

# Security
django-csp>=3.7                   # Content Security Policy
django-cors-headers>=4.3.0        # CORS handling
```

## Deployment Configuration

### Production Settings Adjustments
```python
# Production-specific settings (can be added to settings.py)
if not DEBUG:
    # Security settings
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    
    # Static files with WhiteNoise
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

### Gunicorn Configuration
```python
# gunicorn_config.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
user = "www-data"
group = "www-data"
```

## Installation and Setup

### 1. Environment Setup
```bash
# Clone repository
git clone <repository-url>
cd SASKITUP

# Create virtual environment
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Setup
```bash
# Create MySQL database (if using MySQL)
mysql -u root -p
CREATE DATABASE saskitup_production CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'saskitup_user'@'localhost' IDENTIFIED BY 'secure_password_here';
GRANT ALL PRIVILEGES ON saskitup_production.* TO 'saskitup_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# Run Django migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 3. Development Server
```bash
# Start development server
python manage.py runserver

# Access the application
# Dashboard: http://localhost:8000/
# Admin: http://localhost:8000/admin/
```

## Performance Considerations

### Database Optimization
```python
# Database connection pooling (production)
DATABASES = {
    'default': {
        # ... existing configuration
        'OPTIONS': {
            'sql_mode': 'traditional',
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'MAX_CONNS': 20,
            'CONN_MAX_AGE': 300,  # 5 minutes
        }
    }
}
```

### Caching (Future Enhancement)
```python
# Redis caching configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Session storage
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

## Security Features

### Security Middleware
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

### CSRF and CORS Protection
```python
# CSRF settings
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True

# Content Security Policy (future)
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
```

## Monitoring and Logging

### Log File Locations
- **Main Log**: `/django.log` (rotating, 15MB max, 10 backups)
- **Console Output**: Development server output
- **Database Queries**: Slow query logging (WARNING level)

### Log Analysis Commands
```bash
# Monitor real-time logs
tail -f django.log

# Search for sync operations
grep "sync_lotto_clubs" django.log

# Check error rates
grep "ERROR" django.log | wc -l
```

## Future Enhancements

### API Development
```python
# RESTful API configuration (planned)
INSTALLED_APPS += [
    'rest_framework',
    'django_filters',
    'drf_yasg',  # Swagger documentation
]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ]
}
```

### Celery Integration (Planned)
```python
# Asynchronous task processing
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
```

## Project Management Commands

### Common Management Tasks
```bash
# Database operations
python manage.py makemigrations
python manage.py migrate
python manage.py dbshell

# User management
python manage.py createsuperuser
python manage.py changepassword <username>

# Static files
python manage.py collectstatic --noinput

# Development utilities
python manage.py shell
python manage.py runserver 0.0.0.0:8000

# Clubs-specific commands
python manage.py sync_lotto_clubs --store-type LOTTO
python manage.py sync_lotto_clubs --store-type SAS --dry-run
```

This project configuration provides a robust foundation for the LOTTO Club Integration System with proper separation of concerns, security best practices, and scalability considerations.