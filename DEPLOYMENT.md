# SASKITUP Django Application - Docker Deployment Guide

**Version:** 1.0
**Last Updated:** 2025-01-20
**Branch:** dev → main
**Docker Support:** Yes (Dockerfile + docker-compose.yml)

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Environment Configuration](#environment-configuration)
4. [Database Setup](#database-setup)
5. [Docker Deployment](#docker-deployment)
6. [Post-Deployment Tasks](#post-deployment-tasks)
7. [Superuser Creation](#superuser-creation)
8. [Health Checks & Monitoring](#health-checks--monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Rollback Procedures](#rollback-procedures)

---

## System Requirements

### Server Requirements
- **OS:** Ubuntu 20.04+ / Debian 11+ / RHEL 8+
- **RAM:** Minimum 2GB, Recommended 4GB+
- **CPU:** 2+ cores recommended
- **Storage:** Minimum 10GB free space
- **Docker:** Version 20.10+
- **Docker Compose:** Version 2.0+

### External Services Required
- **MySQL Database:** Version 8.0+ (external, not containerized)
- **SMTP Server:** Gmail (or alternative email provider)
- **APIs:**
  - CIN7 API access
  - WooCommerce API access (LOTTO, SAS, TUS, BallStore sites)
  - Google Maps & Places API

### Network Requirements
- **Inbound:** Port 8000 (application) or custom port
- **Outbound:** HTTPS (443) for API calls, SMTP port 587

---

## Pre-Deployment Checklist

### Code Preparation

```bash
# 1. Clone repository
git clone <repository-url>
cd SASKITUP

# 2. Checkout production branch (merge dev → main first if needed)
git checkout main

# 3. Verify latest code
git pull origin main
git log --oneline -5

# Latest commit should be:
# 1eaa510 Add shipping cost, delivery details, institute emails, and CIN7 sales order enhancements
```

### File Verification

Ensure these critical files exist:
- ✅ `Dockerfile` - Container build configuration
- ✅ `docker-compose.yml` - Service orchestration
- ✅ `.env.docker` - Environment template (with placeholders)
- ✅ `requirements.txt` - Python dependencies
- ✅ `manage.py` - Django management script

---

## Environment Configuration

### Step 1: Create Production Environment File

```bash
# Copy template
cp .env.docker .env.docker.production

# Edit with production credentials
nano .env.docker.production
```

### Step 2: Configure Production Settings

**CRITICAL:** Update ALL placeholder values in `.env.docker.production`:

```bash
# ==========================================
# DATABASE CONFIGURATION (External MySQL)
# ==========================================
USE_MYSQL=True
DB_NAME=cpq_kitup
DB_USER=<your_production_db_user>
DB_PASSWORD=<your_secure_db_password>
DB_HOST=<mysql_server_hostname_or_ip>
DB_PORT=3306

# For Docker connecting to MySQL on host machine:
# DB_HOST=host.docker.internal

# For external MySQL server:
# DB_HOST=mysql.yourcompany.com OR 10.0.1.50

# ==========================================
# DJANGO SECURITY
# ==========================================
# Generate new secret key:
# python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
SECRET_KEY=<generate_new_secret_key_here>
DEBUG=False

# Allowed hosts (comma-separated, no spaces)
# Add ALL domains and IPs that will access the application
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,dev-saskitup.it.sas.co.nz,your.server.ip

# CSRF Trusted Origins (comma-separated, include http:// or https://)
# CRITICAL: Must include the full URL with protocol for CSRF protection
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com,https://dev-saskitup.it.sas.co.nz

# ==========================================
# EMAIL CONFIGURATION
# ==========================================
EMAIL_BACKEND=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@sascreative.co.nz
# Gmail App Password (not regular password!)
# Generate at: https://myaccount.google.com/apppasswords
EMAIL_HOST_PASSWORD=<your_gmail_app_password>

# ==========================================
# CIN7 API CONFIGURATION
# ==========================================
CIN7_API_USERNAME=SASSports2NZ
CIN7_API_KEY=<your_cin7_api_key>
CIN7_API_URL=https://api.cin7.com/api/v1
CIN7_WHOLE_SALE_ID=190

# ==========================================
# LOTTO SPORTS SITE CONFIGURATION
# ==========================================
LOTTO_SITE_URL=https://dev-lottosports.it.sas.co.nz
LOTTO_WOOCOMMERCE_API_URL=https://lottosports.co.nz/wp-json/wc/v3/
LOTTO_WOOCOMMERCE_API_CONSUMER_KEY=<your_lotto_consumer_key>
LOTTO_WOOCOMMERCE_API_SECRET=<your_lotto_consumer_secret>

# ==========================================
# SAS WOOCOMMERCE API CONFIGURATION
# ==========================================
SAS_WOOCOMMERCE_API_URL=https://sas.co.nz/wp-json/wc/v3/
SAS_WOOCOMMERCE_API_CONSUMER_KEY=<your_sas_consumer_key>
SAS_WOOCOMMERCE_API_SECRET=<your_sas_consumer_secret>

# ==========================================
# TUS WOOCOMMERCE API CONFIGURATION
# ==========================================
TUS_WOOCOMMERCE_API_URL=https://theuniformshoppe.co.nz/wp-json/wc/v3/
TUS_WOOCOMMERCE_API_CONSUMER_KEY=<your_tus_consumer_key>
TUS_WOOCOMMERCE_API_SECRET=<your_tus_consumer_secret>

# ==========================================
# BALLSTORE WOOCOMMERCE API CONFIGURATION
# ==========================================
BS_WOOCOMMERCE_API_URL=https://theballstore.co.nz/wp-json/wc/v3/
BS_WOOCOMMERCE_API_CONSUMER_KEY=<your_ballstore_consumer_key>
BS_WOOCOMMERCE_API_SECRET=<your_ballstore_consumer_secret>

# ==========================================
# SITE CREDENTIALS
# ==========================================
# Lotto Site
USERNAME=sas-admin
PASSWORD=<your_lotto_site_password>

# ==========================================
# SYNC CONFIGURATION
# ==========================================
USE_TWO_PHASE_SYNC=False

# ==========================================
# GOOGLE MAPS & PLACES API
# ==========================================
GOOGLE_MAPS_API_KEY=<your_google_maps_api_key>
```

### Step 3: Security Checklist

Before deploying, verify:
- [ ] `DEBUG=False` is set
- [ ] `SECRET_KEY` is unique and not the default value
- [ ] `ALLOWED_HOSTS` includes your production domain/IP
- [ ] All API keys are production keys (not development)
- [ ] Database credentials are for production database
- [ ] Email credentials use App Password (not regular password)
- [ ] `.env.docker.production` is NOT committed to git

---

## Database Setup

### Step 1: Create Database

Connect to your MySQL server and create the database:

```sql
-- Connect to MySQL
mysql -u root -p

-- Create database
CREATE DATABASE cpq_kitup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create dedicated user
CREATE USER 'saskitup_user'@'%' IDENTIFIED BY 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON cpq_kitup.* TO 'saskitup_user'@'%';

-- Apply changes
FLUSH PRIVILEGES;

-- Verify
SHOW DATABASES;
SELECT User, Host FROM mysql.user WHERE User = 'saskitup_user';

-- Exit
EXIT;
```

### Step 2: Test Database Connection

```bash
# Test from Docker host
mysql -h <DB_HOST> -u saskitup_user -p cpq_kitup

# If using host.docker.internal, test local MySQL
mysql -u saskitup_user -p cpq_kitup
```

### Step 3: Configure MySQL for Docker

If MySQL is on the same server, allow Docker network access:

```bash
# Edit MySQL config
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

# Change bind-address
bind-address = 0.0.0.0  # Allow external connections
# OR for localhost-only Docker:
bind-address = 127.0.0.1

# Restart MySQL
sudo systemctl restart mysql
```

---

## Docker Deployment

### Step 1: Update docker-compose.yml

Edit `docker-compose.yml` to use production environment file:

```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: saskitup_web
    ports:
      - "8000:8000"  # Change port if needed (e.g., "80:8000")
    env_file:
      - .env.docker.production  # Point to production env file
    volumes:
      # Persistent media files (uploads, logos, etc.)
      - ./media:/app/media
      # Persistent static files
      - ./staticfiles:/app/staticfiles
      # Persistent logs
      - ./logs:/app/logs
      # REMOVE this line for production (development only):
      # - .:/app
    restart: unless-stopped
    networks:
      - saskitup_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  saskitup_network:
    driver: bridge

volumes:
  media_files:
  static_files:
  logs:
```

### Step 2: Build Docker Image

```bash
# Build the image
docker build -t saskitup:latest .

# Verify image created
docker images | grep saskitup

# Expected output:
# saskitup  latest  <image-id>  <timestamp>  <size>
```

### Step 3: Test Configuration (Dry Run)

```bash
# Test with docker-compose (don't start yet)
docker-compose -f docker-compose.yml config

# Check for syntax errors - should output parsed YAML
```

### Step 4: Start Services

```bash
# Start in detached mode
docker-compose up -d

# Check container status
docker-compose ps

# Expected output:
# NAME               STATUS        PORTS
# saskitup_web       Up (healthy)  0.0.0.0:8000->8000/tcp
```

### Step 5: Monitor Startup

```bash
# Watch logs in real-time
docker-compose logs -f web

# Wait for:
# "Booting worker with pid: XXXX"
# "Listening at: http://0.0.0.0:8000"

# Press Ctrl+C to exit log view (container keeps running)
```

---

## Post-Deployment Tasks

### Step 1: Run Database Migrations

**CRITICAL:** Must be done before first use!

```bash
# Execute migrations inside container
docker-compose exec web python manage.py migrate

# Expected output:
# Operations to perform:
#   Apply all migrations...
# Running migrations:
#   Applying contenttypes.0001_initial... OK
#   Applying auth.0001_initial... OK
#   ... (multiple lines)
#   Applying quotations.0013_quotation_cin7_contact_fields... OK
#   ... OK

# Verify migrations
docker-compose exec web python manage.py showmigrations

# All should have [X] marks
```

### Step 2: Collect Static Files

```bash
# Collect static assets (CSS, JS, images)
docker-compose exec web python manage.py collectstatic --noinput

# Expected output:
# X static files copied to '/app/staticfiles'
```

### Step 3: Verify File Permissions

```bash
# Check volume permissions
docker-compose exec web ls -la /app/media
docker-compose exec web ls -la /app/staticfiles
docker-compose exec web ls -la /app/logs

# All should be owned by 'djangouser'
```

---

## Superuser Creation

### Create Django Admin Superuser

```bash
# Method 1: Interactive (recommended)
docker-compose exec web python manage.py createsuperuser

# When prompted, provide:
# Username: srimal@sas.co.nz
# Email address: srimal@sas.co.nz
# Password: <enter secure password>
# Password (again): <confirm password>
# Superuser created successfully.
```

**Alternative: Non-Interactive Method**

```bash
# Create superuser with single command (Python shell)
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
user = User.objects.create_superuser(
    username='srimal@sas.co.nz',
    email='srimal@sas.co.nz',
    password='your_secure_password'
);
user.user_type = 'admin';
user.save();
print(f'Superuser created: {user.email}')
"
```

**Method 3: Using Helper Script (Optional)**

```bash
# Use the included helper script for easier superuser creation
docker-compose exec -it web python manage.py shell < scripts/create_superuser.py

# The script will prompt for:
# - Email address (e.g., srimal@sas.co.nz)
# - Password (hidden input)
# - Password confirmation
# - Postcode (optional - press Enter to skip)
# - First name (optional)
# - Last name (optional)
```

**Note:** Postcode is optional for admin users. It's only required for customer users who need delivery addresses.

### Verify Superuser

```bash
# Check user created
docker-compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
user = User.objects.get(email='srimal@sas.co.nz');
print(f'User: {user.email}, Staff: {user.is_staff}, Superuser: {user.is_superuser}')
"

# Expected output:
# User: srimal@sas.co.nz, Staff: True, Superuser: True
```

### Access Admin Panel

```bash
# Admin URL: http://your-server:8000/admin/
# Login with: srimal@sas.co.nz / <password>
```

---

## Health Checks & Monitoring

### Application Health

```bash
# Check container health
docker-compose ps

# Detailed health check
docker inspect saskitup_web | grep -A 10 Health

# Manual health check
curl -f http://localhost:8000/ || echo "Health check failed"
```

### Log Monitoring

```bash
# View application logs
docker-compose logs -f web

# View specific number of lines
docker-compose logs --tail=100 web

# View logs with timestamps
docker-compose logs -f -t web

# View Django logs on host
tail -f logs/django.log
```

### Database Connectivity

```bash
# Test database connection from container
docker-compose exec web python manage.py dbshell

# Should connect to MySQL prompt
# Type 'exit' to quit
```

### System Resources

```bash
# Check container resource usage
docker stats saskitup_web

# Expected:
# CPU: < 10% (idle), < 80% (under load)
# MEM: 200-500MB typical
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check detailed logs
docker-compose logs web

# Common issues:
# 1. Database connection failed → Check DB_HOST, DB_USER, DB_PASSWORD
# 2. Port already in use → Change port in docker-compose.yml
# 3. Permission denied → Check volume permissions
```

### Database Connection Errors

```bash
# Error: (2002, "Can't connect to MySQL server")
# Solution: Check DB_HOST setting

# If MySQL is on host machine:
DB_HOST=host.docker.internal  # macOS/Windows
DB_HOST=172.17.0.1           # Linux (Docker bridge IP)

# Verify MySQL allows connections:
mysql -u root -p -e "SELECT User, Host FROM mysql.user;"
```

### Static Files Not Loading

```bash
# Re-collect static files
docker-compose exec web python manage.py collectstatic --clear --noinput

# Check ALLOWED_HOSTS includes your domain
docker-compose exec web python manage.py shell -c "
from django.conf import settings;
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS);
print('DEBUG:', settings.DEBUG);
print('STATIC_ROOT:', settings.STATIC_ROOT)
"
```

### Email Not Sending

```bash
# Test email configuration
docker-compose exec web python manage.py shell

# In shell:
from django.core.mail import send_mail
send_mail(
    'Test Email',
    'This is a test from SASKITUP',
    'noreply@sascreative.co.nz',
    ['your-test-email@example.com'],
    fail_silently=False,
)
# Should return: 1

# Check logs for errors
docker-compose logs web | grep -i email
```

### Permission Errors

```bash
# Fix media/static/logs permissions
docker-compose exec web chown -R djangouser:djangouser /app/media /app/staticfiles /app/logs

# Or from host:
sudo chown -R 1000:1000 media/ staticfiles/ logs/
```

### Container Keeps Restarting

```bash
# Check exit code
docker inspect saskitup_web | grep -A 5 State

# View last 50 log lines
docker-compose logs --tail=50 web

# Common causes:
# 1. Migration errors → Check migrations output
# 2. Missing dependencies → Rebuild image
# 3. Configuration errors → Check .env.docker.production
```

---

## Rollback Procedures

### Quick Rollback

```bash
# Stop current deployment
docker-compose down

# Checkout previous working commit
git log --oneline -10  # Find previous commit
git checkout <previous-commit-hash>

# Rebuild and restart
docker-compose build
docker-compose up -d

# Verify rollback
docker-compose logs -f web
```

### Database Rollback

```bash
# If migrations cause issues, rollback to previous migration:
docker-compose exec web python manage.py showmigrations quotations

# Rollback to specific migration (example):
docker-compose exec web python manage.py migrate quotations 0012

# Note: This only works for compatible migrations!
# For complex changes, restore from database backup.
```

### Emergency Stop

```bash
# Immediate shutdown
docker-compose down --remove-orphans

# Clean restart
docker-compose up -d --force-recreate
```

---

## Maintenance Commands

### Restart Application

```bash
# Graceful restart
docker-compose restart web

# Force recreate
docker-compose up -d --force-recreate web
```

### Update Application

```bash
# Pull latest code
git pull origin main

# Rebuild image
docker-compose build --no-cache

# Apply migrations
docker-compose exec web python manage.py migrate

# Restart services
docker-compose up -d
```

### Database Backup

```bash
# Backup database from host
docker-compose exec web python manage.py dumpdata > backup_$(date +%Y%m%d_%H%M%S).json

# Or MySQL dump
mysqldump -h <DB_HOST> -u <DB_USER> -p cpq_kitup > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Clean Up

```bash
# Remove old images
docker image prune -a

# Remove unused volumes
docker volume prune

# View disk usage
docker system df
```

---

## Security Recommendations

### Production Checklist

- [ ] Change default SECRET_KEY
- [ ] Set DEBUG=False
- [ ] Configure proper ALLOWED_HOSTS
- [ ] Use environment-specific API keys
- [ ] Enable HTTPS (reverse proxy with nginx/traefik)
- [ ] Configure firewall rules
- [ ] Regular security updates
- [ ] Database backups scheduled
- [ ] Log monitoring enabled
- [ ] Rate limiting configured (if needed)

### Reverse Proxy Setup (Optional but Recommended)

```nginx
# nginx configuration example
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/SASKITUP/staticfiles/;
    }

    location /media/ {
        alias /path/to/SASKITUP/media/;
    }
}
```

---

## Contact & Support

**Developer:** Claude AI Assistant
**Repository:** <your-git-repo-url>
**Documentation:** This file

**For Issues:**
1. Check logs: `docker-compose logs web`
2. Review troubleshooting section above
3. Contact: srimal@sas.co.nz

---

## Quick Reference Card

```bash
# Start application
docker-compose up -d

# Stop application
docker-compose down

# View logs
docker-compose logs -f web

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Access Django shell
docker-compose exec web python manage.py shell

# Access container bash
docker-compose exec web bash

# Restart application
docker-compose restart web

# Check status
docker-compose ps

# Check health
curl http://localhost:8000/
```

---

**End of Deployment Guide**
