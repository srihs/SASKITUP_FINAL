# Production PDF Generation Deployment Guide

## Overview

This guide provides step-by-step instructions to deploy and troubleshoot PDF generation on your production server. The system uses Playwright with headless Chromium to generate quotation PDFs.

## Quick Reference

**Files Involved**:
- `quotations/emails.py` - PDF generation logic
- `quotations/templates/quotations/quotation_preview_pdf.html` - PDF template
- `static/assets/images/sas-logo.png` - Logo file
- `requirements.txt` - Contains playwright==1.55.0

**System Requirements**:
- Python package: `playwright==1.55.0`
- Browser: Chromium (installed via Playwright)
- Temp directory: `/tmp/` (writable)
- Logo file: `static/assets/images/sas-logo.png` (readable)

---

## Step 1: Deploy Code to Production

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

## Step 2: Install Playwright and Chromium

### Install Python Package

```bash
# Install/update Playwright package
pip install playwright==1.55.0

# Verify installation
python -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"
```

**Expected Output**: `Playwright installed successfully`

### Install Chromium Browser

```bash
# Install Chromium browser binaries
playwright install chromium

# Verify Chromium installation
playwright install --list
```

**Expected Output**:
```
chromium v1150 [✓]
  executable: /home/user/.cache/ms-playwright/chromium-1150/chrome-linux/chrome
```

**If you see errors** about missing system dependencies:

```bash
# On Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# Then retry
playwright install chromium
```

---

## Step 3: Verify File Permissions

### Check Temp Directory

```bash
# Test temp directory access
python -c "import tempfile; f = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False); print(f'Created temp file: {f.name}'); f.close()"

# Check /tmp permissions
ls -ld /tmp
```

**Expected /tmp permissions**: `drwxrwxrwt` or `chmod 1777`

**If /tmp is not writable**:
```bash
# Fix permissions (requires root/sudo)
sudo chmod 1777 /tmp
```

### Check Logo File

```bash
# Navigate to project root
cd /path/to/SASKITUP

# Check logo file exists and is readable
ls -la static/assets/images/sas-logo.png

# Verify absolute path resolves correctly
python -c "import os; logo_path = os.path.join(os.getcwd(), 'static/assets/images/sas-logo.png'); print(f'Logo path: {logo_path}'); print(f'Exists: {os.path.exists(logo_path)}'); print(f'Readable: {os.access(logo_path, os.R_OK)}')"
```

**Expected Output**:
```
-rw-r--r-- 1 user group 12345 Jan 01 12:00 static/assets/images/sas-logo.png
Logo path: /path/to/SASKITUP/static/assets/images/sas-logo.png
Exists: True
Readable: True
```

### Check Chromium Browser Permissions

```bash
# Find Chromium executable
CHROMIUM_PATH=$(playwright install --list | grep chromium | grep executable | awk '{print $2}')

# Check permissions
ls -la $CHROMIUM_PATH

# Verify executable
test -x $CHROMIUM_PATH && echo "Chromium is executable" || echo "Chromium is NOT executable"
```

**If Chromium is not executable**:
```bash
chmod +x $CHROMIUM_PATH
```

---

## Step 4: Test PDF Generation

### Manual Test via Django Shell

```bash
# Activate virtual environment
source venv/bin/activate

# Start Django shell
python manage.py shell
```

**In Django shell**:
```python
# Import required modules
from quotations.models import Quotation
from quotations.emails import generate_quotation_pdf
import os

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

### Download and Verify Test PDF

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

## Step 5: Check Application Logs

### Enable Debug Logging (Temporarily)

Edit your production settings to enable PDF generation logging:

```python
# settings.py or your production settings file
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/path/to/logs/django.log',
        },
    },
    'loggers': {
        'quotations.emails': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

### Monitor Logs During PDF Generation

```bash
# Tail the log file
tail -f /path/to/logs/django.log

# In another terminal, trigger PDF generation (send quotation email or download PDF)
# Watch for log entries like:
# - "Generating PDF for quotation..."
# - "Generated PDF for quotation XXX (NNNN bytes)"
# - "Failed to generate PDF: [error message]"
```

---

## Step 6: Restart Application Server

After installing Playwright and Chromium, restart your application server:

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

## Troubleshooting Common Issues

### Issue 1: "Executable doesn't exist at ..."

**Symptom**: Error message about missing Chromium executable

**Diagnosis**:
```bash
playwright install --list
```

**Fix**:
```bash
# Reinstall Chromium
playwright install chromium

# Verify installation
playwright install --list | grep chromium
```

---

### Issue 2: "Playwright not installed"

**Symptom**: ImportError or "Playwright not installed" in logs

**Diagnosis**:
```bash
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

**Fix**:
```bash
pip install playwright==1.55.0
playwright install chromium
```

---

### Issue 3: Permission Denied on /tmp

**Symptom**: "Permission denied" when creating temp files

**Diagnosis**:
```bash
ls -ld /tmp
python -c "import tempfile; f = tempfile.NamedTemporaryFile(delete=False); print(f.name)"
```

**Fix**:
```bash
# Check if application user can write to /tmp
sudo -u your-app-user touch /tmp/test_file
sudo -u your-app-user rm /tmp/test_file

# Fix permissions if needed
sudo chmod 1777 /tmp
```

---

### Issue 4: Logo Not Displaying in PDF

**Symptom**: PDF generates but logo is missing

**Diagnosis**:
```bash
# Check logo file exists
ls -la /path/to/SASKITUP/static/assets/images/sas-logo.png

# Check Django STATIC_ROOT
python manage.py findstatic assets/images/sas-logo.png
```

**Fix**:
```bash
# Run collectstatic to gather static files
python manage.py collectstatic --noinput

# Verify logo is in STATIC_ROOT
ls -la /path/to/static_root/assets/images/sas-logo.png

# Check logo path in code (should be absolute path)
grep -n "logo_path" quotations/emails.py
```

---

### Issue 5: PDF Generation Takes Too Long

**Symptom**: Request timeout or very slow PDF generation

**Diagnosis**:
```bash
# Time the PDF generation
time python manage.py shell -c "from quotations.models import Quotation; from quotations.emails import generate_quotation_pdf; q = Quotation.objects.first(); pdf = generate_quotation_pdf(q); print(len(pdf) if pdf else 'Failed')"
```

**Expected**: ~1-2 seconds for first generation, ~0.5-1 second for subsequent

**Fix**:
```bash
# Check server resources
free -h  # Memory
df -h    # Disk space
top      # CPU usage

# Increase timeout in web server config (e.g., Gunicorn)
gunicorn --timeout 120 config.wsgi:application
```

---

### Issue 6: Chromium Crashes or "Browser closed"

**Symptom**: "Browser closed" or Chromium crash errors

**Diagnosis**:
```bash
# Check system dependencies
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux/chrome | grep "not found"

# Check for shared memory issues
df -h /dev/shm
```

**Fix**:
```bash
# Install missing system dependencies (Ubuntu/Debian)
sudo apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2

# Increase shared memory if needed
sudo mount -o remount,size=2G /dev/shm
```

---

### Issue 7: "No module named 'playwright'"

**Symptom**: ImportError even after installation

**Diagnosis**:
```bash
# Check which Python/pip you're using
which python
which pip

# Check installed packages
pip list | grep playwright

# Check virtual environment
echo $VIRTUAL_ENV
```

**Fix**:
```bash
# Ensure you're in the correct virtual environment
source /path/to/venv/bin/activate

# Reinstall in correct environment
pip install playwright==1.55.0
playwright install chromium

# Restart application server
sudo systemctl restart gunicorn
```

---

## Verification Checklist

After deployment, verify the following:

- [ ] Playwright package installed: `pip show playwright`
- [ ] Chromium browser installed: `playwright install --list | grep chromium`
- [ ] `/tmp` directory writable: `touch /tmp/test && rm /tmp/test`
- [ ] Logo file accessible: `ls -la static/assets/images/sas-logo.png`
- [ ] Manual PDF generation works: Test via Django shell
- [ ] Application server restarted: `systemctl status gunicorn`
- [ ] PDF generation from web interface works: Send test quotation email
- [ ] PDF contains logo: Download and verify PDF
- [ ] Logs show successful generation: Check django.log
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

### 2. Disk Space Monitoring

Monitor `/tmp` directory usage:

```bash
# Add to cron
0 * * * * df -h /tmp | tail -1 | awk '{print $5}' | sed 's/%//' | while read usage; do [ $usage -gt 80 ] && echo "WARNING: /tmp usage at ${usage}%" | mail -s "Disk Space Alert" ops@example.com; done
```

### 3. Playwright Updates

Keep Playwright updated for security and performance:

```bash
# Check for updates
pip list --outdated | grep playwright

# Update Playwright
pip install --upgrade playwright
playwright install chromium

# Restart application
sudo systemctl restart gunicorn
```

### 4. Log Rotation

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

---

## Rollback Plan

If PDF generation fails after deployment:

```bash
# 1. Check application is still running
systemctl status gunicorn

# 2. Review recent logs
tail -100 /path/to/logs/django.log

# 3. If critical, disable PDF generation temporarily
# Edit quotations/emails.py or add environment variable:
export DISABLE_PDF_GENERATION=true

# 4. Restart application
sudo systemctl restart gunicorn

# 5. Emails will send without PDF attachments (graceful degradation is built-in)
```

---

## Contact Information

**For Issues**:
1. Check this guide's troubleshooting section
2. Review application logs: `/path/to/logs/django.log`
3. Test PDF generation via Django shell (Step 4)
4. Review Playwright documentation: https://playwright.dev/python/

**Documentation References**:
- [PLAYWRIGHT_PDF_IMPLEMENTATION.md](quotations/PLAYWRIGHT_PDF_IMPLEMENTATION.md)
- [PDF_GENERATION_UPDATE.md](quotations/PDF_GENERATION_UPDATE.md)

---

## Quick Deployment Commands

**Complete deployment in one go**:

```bash
#!/bin/bash
# deploy_pdf_generation.sh

set -e  # Exit on error

echo "=== PDF Generation Production Deployment ==="

# Navigate to project
cd /path/to/SASKITUP
source venv/bin/activate

# Install Playwright
echo "Installing Playwright..."
pip install playwright==1.55.0

# Install Chromium
echo "Installing Chromium browser..."
playwright install chromium

# Verify installation
echo "Verifying installation..."
playwright install --list | grep chromium || { echo "ERROR: Chromium not installed"; exit 1; }

# Test temp directory
echo "Testing temp directory..."
python -c "import tempfile; f = tempfile.NamedTemporaryFile(delete=False); print(f'Temp file created: {f.name}'); import os; os.unlink(f.name)" || { echo "ERROR: Cannot write to temp directory"; exit 1; }

# Check logo file
echo "Checking logo file..."
test -f static/assets/images/sas-logo.png || { echo "WARNING: Logo file not found"; }

# Test PDF generation
echo "Testing PDF generation..."
python manage.py shell -c "
from quotations.models import Quotation
from quotations.emails import generate_quotation_pdf
q = Quotation.objects.first()
if q:
    pdf = generate_quotation_pdf(q)
    print('SUCCESS: PDF generated' if pdf else 'ERROR: PDF generation failed')
else:
    print('WARNING: No quotations found for testing')
"

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
chmod +x deploy_pdf_generation.sh
./deploy_pdf_generation.sh
```

---

## Summary

**What This Fixes**: PDF generation not working on production server

**Key Steps**:
1. Install Playwright package: `pip install playwright==1.55.0`
2. Install Chromium browser: `playwright install chromium`
3. Verify permissions on `/tmp` and logo file
4. Test PDF generation via Django shell
5. Restart application server
6. Monitor logs for success/errors

**Expected Outcome**: Quotation PDFs generate successfully on production, attached to emails and available for download.

**Time Estimate**: 15-30 minutes for full deployment and testing
