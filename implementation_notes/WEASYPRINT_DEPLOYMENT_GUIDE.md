# WeasyPrint PDF Generation - Deployment Guide

## Overview

The PDF generation system has been updated to use **WeasyPrint** instead of Playwright. WeasyPrint is a simpler, lighter alternative that doesn't require a headless browser, making deployment much easier on production servers.

## Changes Made

### 1. Updated Implementation

**File**: `quotations/emails.py`

- **Removed**: Playwright dependency (`from playwright.sync_api import sync_playwright`)
- **Added**: WeasyPrint dependency (`from weasyprint import HTML, CSS`)
- **Simplified**: PDF generation now uses `HTML(string=html_string, base_url=base_url).write_pdf()`
- **Removed**: Temporary HTML file creation, browser launch, and page navigation logic

### 2. Updated Dependencies

**File**: `requirements.txt`

- **Added**: `weasyprint==66.0`
- **Kept**: `playwright==1.55.0` (for backward compatibility, can be removed if not used elsewhere)

### 3. Backup Created

**File**: `quotations/emails_playwright_backup.py`

- Contains original Playwright implementation
- Can be restored if needed: `cp quotations/emails_playwright_backup.py quotations/emails.py`

---

## Production Deployment Steps

### Step 1: Deploy Code to Production

```bash
# SSH to production server
ssh user@your-production-server

# Navigate to project directory
cd /path/to/SASKITUP

# Pull latest code
git pull origin master

# Activate virtual environment
source venv/bin/activate  # Or your venv path
```

---

### Step 2: Install WeasyPrint and System Dependencies

#### On Ubuntu/Debian (Linux Production Server)

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info

# Install Python package
pip install weasyprint==66.0

# Verify installation
python -c "from weasyprint import HTML; print('WeasyPrint installed successfully')"
```

**Expected Output**: `WeasyPrint installed successfully`

#### On macOS (Local Development)

```bash
# Install system dependencies via Homebrew
brew install pango libffi gdk-pixbuf

# Install Python package
pip install weasyprint==66.0

# Verify installation
python -c "from weasyprint import HTML; print('WeasyPrint installed successfully')"
```

---

### Step 3: Verify File Permissions

#### Check Logo File

```bash
# Verify logo exists and is readable
ls -la static/assets/images/sas-logo.png

# Should show: -rw-r--r-- permissions
```

**If logo file doesn't exist**:
```bash
# Make sure static files are collected
python manage.py collectstatic --noinput
```

---

### Step 4: Test PDF Generation

#### Via Django Shell

```bash
# Activate virtual environment
source venv/bin/activate

# Start Django shell
python manage.py shell
```

**In Django shell**:
```python
from quotations.models import Quotation
from quotations.emails import generate_quotation_pdf

# Get a test quotation
q = Quotation.objects.first()
print(f"Testing with quotation: {q.quotation_number}")

# Generate PDF
pdf_bytes = generate_quotation_pdf(q)

# Check result
if pdf_bytes:
    print(f"SUCCESS: PDF generated ({len(pdf_bytes)} bytes)")
    # Save to file for verification
    with open('/tmp/test_quotation.pdf', 'wb') as f:
        f.write(pdf_bytes)
    print("PDF saved to /tmp/test_quotation.pdf")
else:
    print("FAILED: PDF generation returned None")

# Exit shell
exit()
```

**Expected Output**:
```
Testing with quotation: QUO-2025-0001
SUCCESS: PDF generated (245678 bytes)
PDF saved to /tmp/test_quotation.pdf
```

#### Download and Verify Test PDF

```bash
# On your local machine, download the test PDF
scp user@production-server:/tmp/test_quotation.pdf ~/Downloads/

# Open and verify the PDF contains:
# - Company logo
# - Quotation details
# - Items table
# - Totals
# - Terms and conditions
```

---

### Step 5: Restart Application Server

```bash
# For Gunicorn with systemd
sudo systemctl restart gunicorn

# For Gunicorn manually
pkill gunicorn
gunicorn --bind 0.0.0.0:8000 config.wsgi:application --daemon

# For uWSGI
sudo systemctl restart uwsgi

# For Apache with mod_wsgi
sudo systemctl restart apache2

# Verify server is running
ps aux | grep gunicorn  # or uwsgi/apache2
```

---

## Troubleshooting

### Issue 1: "ImportError: cannot import name 'HTML' from 'weasyprint'"

**Diagnosis**:
```bash
pip show weasyprint
```

**Fix**:
```bash
pip install weasyprint==66.0
python -c "from weasyprint import HTML; print('OK')"
```

---

### Issue 2: "OSError: cannot load library 'libpango-1.0-0'"

**Symptom**: Missing system libraries error on Linux

**Diagnosis**:
```bash
python -c "from weasyprint import HTML"
```

**Fix (Ubuntu/Debian)**:
```bash
sudo apt-get update
sudo apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info

# Retry
python -c "from weasyprint import HTML; print('OK')"
```

**Fix (CentOS/RHEL)**:
```bash
sudo yum install -y \
    pango \
    libffi-devel \
    gdk-pixbuf2

# Retry
python -c "from weasyprint import HTML; print('OK')"
```

---

### Issue 3: "Logo not displaying in PDF"

**Symptom**: PDF generates but logo is missing

**Diagnosis**:
```bash
# Check logo file exists
ls -la static/assets/images/sas-logo.png

# Check if collectstatic was run
ls -la /path/to/static_root/assets/images/sas-logo.png

# Check logo path in code
grep -n "logo_path" quotations/emails.py
```

**Fix**:
```bash
# Run collectstatic
python manage.py collectstatic --noinput

# Verify logo is accessible
python -c "import os; logo = 'static/assets/images/sas-logo.png'; print(f'Exists: {os.path.exists(logo)}'); print(f'Readable: {os.access(logo, os.R_OK)}')"
```

---

### Issue 4: "PDF generation returns None"

**Symptom**: `generate_quotation_pdf()` returns None instead of PDF bytes

**Diagnosis**:
```bash
# Check Django logs
tail -100 /path/to/logs/django.log

# Look for error messages like:
# - "WeasyPrint not available. Cannot generate PDF."
# - "Failed to generate PDF for quotation XXX: [error]"
```

**Fix**:
```bash
# Re-run installation
pip install --upgrade weasyprint==66.0

# Test import
python -c "from weasyprint import HTML; print('OK')"

# Check permissions on static files
ls -la static/assets/images/sas-logo.png

# Restart application
sudo systemctl restart gunicorn
```

---

### Issue 5: "Template rendering error"

**Symptom**: Error in HTML template rendering

**Diagnosis**:
```bash
# Test template rendering
python manage.py shell -c "
from django.template.loader import render_to_string
from quotations.models import Quotation
q = Quotation.objects.first()
context = {'quotation': q, 'items': [], 'discount_amount': 0, 'quotation_validity_days': 30, 'logo_path': '/path/to/logo.png'}
html = render_to_string('quotations/quotation_preview_pdf.html', context)
print('Template rendered successfully')
"
```

**Fix**:
- Ensure template exists: `quotations/templates/quotations/quotation_preview_pdf.html`
- Check template syntax and context variables
- Verify all required context variables are provided

---

## Comparison: WeasyPrint vs Playwright

| Feature | WeasyPrint | Playwright |
|---------|------------|-----------|
| **Installation** | Python package + system libs | Python package + browser download |
| **System Dependencies** | libpango, libffi, gdk-pixbuf (~10MB) | Chromium browser (~200MB) |
| **Deployment Complexity** | Simple (apt-get install) | Complex (browser permissions, dependencies) |
| **PDF Generation Speed** | ~0.5-1 second | ~1-2 seconds |
| **CSS Support** | Good (CSS Paged Media) | Excellent (full browser engine) |
| **Memory Usage** | Low (~50-100MB) | Higher (~200-400MB) |
| **Production Suitability** | Excellent | Good (requires more resources) |
| **Maintenance** | Minimal | Requires browser updates |

---

## Advantages of WeasyPrint

1. **Simpler Deployment**: No browser installation required
2. **Lower Resource Usage**: Uses ~75% less memory than Playwright
3. **Faster Installation**: System dependencies are smaller
4. **Better for Production**: Designed specifically for PDF generation
5. **No Security Concerns**: No headless browser to manage
6. **Easier Troubleshooting**: Fewer moving parts

---

## Rollback to Playwright (If Needed)

If you need to revert to Playwright for any reason:

```bash
# 1. Restore backup
cp quotations/emails_playwright_backup.py quotations/emails.py

# 2. Reinstall Playwright
pip install playwright==1.55.0
playwright install chromium

# 3. Restart application
sudo systemctl restart gunicorn
```

---

## Verification Checklist

After deployment, verify the following:

- [ ] WeasyPrint package installed: `pip show weasyprint`
- [ ] System dependencies installed (Ubuntu): `dpkg -l | grep libpango`
- [ ] Logo file accessible: `ls -la static/assets/images/sas-logo.png`
- [ ] Manual PDF generation works: Test via Django shell
- [ ] Application server restarted: `systemctl status gunicorn`
- [ ] PDF generation from web interface works: Send test quotation email
- [ ] PDF contains logo: Download and verify PDF
- [ ] No errors in application logs: `tail -f /path/to/logs/django.log`

---

## Production Best Practices

### 1. Monitor PDF Generation

Add monitoring for PDF generation failures:

```python
# In your monitoring system
if pdf_generation_failures > threshold:
    alert_ops_team()
```

### 2. Log Rotation

Ensure Django logs are rotated:

```bash
# /etc/logrotate.d/django
/path/to/logs/django.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 www-data www-data
    sharedscripts
    postrotate
        systemctl reload gunicorn > /dev/null
    endscript
}
```

### 3. Regular Updates

Keep WeasyPrint updated for security and performance:

```bash
# Check for updates
pip list --outdated | grep weasyprint

# Update WeasyPrint
pip install --upgrade weasyprint

# Restart application
sudo systemctl restart gunicorn
```

---

## Quick Deployment Script

```bash
#!/bin/bash
# deploy_weasyprint.sh

set -e  # Exit on error

echo "=== WeasyPrint PDF Generation Deployment ==="

# Navigate to project
cd /path/to/SASKITUP
source venv/bin/activate

# Install system dependencies (Ubuntu/Debian)
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info

# Install WeasyPrint
echo "Installing WeasyPrint..."
pip install weasyprint==66.0

# Verify installation
echo "Verifying installation..."
python -c "from weasyprint import HTML; print('WeasyPrint installed successfully')" || { echo "ERROR: WeasyPrint not installed"; exit 1; }

# Check logo file
echo "Checking logo file..."
test -f static/assets/images/sas-logo.png || { echo "WARNING: Logo file not found"; }

# Test PDF generation (optional - requires database connection)
# echo "Testing PDF generation..."
# python manage.py shell -c "
# from quotations.models import Quotation
# from quotations.emails import generate_quotation_pdf
# q = Quotation.objects.first()
# if q:
#     pdf = generate_quotation_pdf(q)
#     print('SUCCESS: PDF generated' if pdf else 'ERROR: PDF generation failed')
# else:
#     print('WARNING: No quotations found for testing')
# "

# Restart application
echo "Restarting application server..."
sudo systemctl restart gunicorn

echo "=== Deployment Complete ==="
echo "Next steps:"
echo "1. Test PDF generation from web interface"
echo "2. Monitor logs: tail -f /path/to/logs/django.log"
echo "3. Send test quotation email"
```

**Make executable and run**:
```bash
chmod +x deploy_weasyprint.sh
./deploy_weasyprint.sh
```

---

## Support

**For Issues**:
1. Check this guide's troubleshooting section
2. Review application logs: `/path/to/logs/django.log`
3. Test PDF generation via Django shell
4. Review WeasyPrint documentation: https://doc.courtbouillon.org/weasyprint/

**Test Files**:
- Simple test script: `test_weasyprint.py` (no database required)
- Django shell test: See "Test PDF Generation" section above

---

## Summary

**What Changed**: PDF generation now uses WeasyPrint instead of Playwright

**Why**: Simpler deployment, lower resource usage, better suited for production

**Key Steps on Production**:
1. Install system dependencies: `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info`
2. Install WeasyPrint: `pip install weasyprint==66.0`
3. Verify installation: `python -c "from weasyprint import HTML; print('OK')"`
4. Test PDF generation: Via Django shell
5. Restart application: `sudo systemctl restart gunicorn`

**Expected Outcome**: Quotation PDFs generate successfully on production with minimal server resources

**Time Estimate**: 10-15 minutes for full deployment and testing
