# Email Configuration Guide

## Overview
This guide explains how to configure email sending for quotations in development and production environments.

## Quick Start

### Development/Testing (No Gmail Setup Required)
Use console backend to print emails to terminal:

```bash
# In .env file
EMAIL_BACKEND=console
```

**Result**: Emails will be printed to your terminal/console instead of being sent. Perfect for testing email content and functionality without SMTP credentials.

### Production (Real Email Sending)
Use SMTP backend with Gmail App Password:

```bash
# In .env file
EMAIL_BACKEND=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password-here
```

## Email Backend Options

### Console Backend (Development)
**Configuration**:
```bash
EMAIL_BACKEND=console
```

**Features**:
- ✅ No SMTP credentials needed
- ✅ Instant testing without external services
- ✅ Email content printed to terminal
- ✅ Perfect for development and debugging
- ✅ No SSL certificate issues
- ✅ No authentication errors

**Output Example**:
```
Content-Type: multipart/alternative;
 boundary="===============1234567890=="
MIME-Version: 1.0
Subject: New Quotation Q-20251015-0001 - Test School
From: SASKITUP Quotations <srimal@sascreative.co.nz>
To: customer@example.com
Date: Tue, 15 Oct 2025 06:30:00 -0000
Message-ID: <...>

--===============1234567890==
Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit

Dear Valued Customer,

Thank you for your interest in SAS SPORTS LTD...
[Full email content displayed here]
```

### SMTP Backend (Production)
**Configuration**:
```bash
EMAIL_BACKEND=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
```

**Features**:
- ✅ Real email sending via Gmail SMTP
- ✅ SSL/TLS encryption
- ✅ Multiple recipients support (CC)
- ✅ HTML and plain text formats
- ✅ Embedded logo images
- ✅ Custom SSL context for development

**Requirements**:
1. Gmail account with 2-Factor Authentication enabled
2. Generated App Password (not your regular password)
3. Valid SMTP credentials

## Gmail App Password Setup

### Why App Password is Required
Gmail requires App Passwords for security when using SMTP:
- Regular account passwords are not accepted
- App Passwords provide secure access without exposing your main password
- Each app gets its own unique password
- You can revoke app access anytime

### How to Generate App Password

1. **Enable 2-Factor Authentication**:
   - Go to: https://myaccount.google.com/security
   - Find "2-Step Verification"
   - Follow the setup process if not already enabled

2. **Generate App Password**:
   - Go to: https://myaccount.google.com/apppasswords
   - Sign in if prompted
   - Select app: **Mail**
   - Select device: **Other (Custom name)**
   - Enter name: **SASKITUP** or **Quotation System**
   - Click **Generate**

3. **Copy the Password**:
   - You'll see a 16-character password like: `abcd efgh ijkl mnop`
   - Copy this password (remove spaces)

4. **Update .env File**:
   ```bash
   EMAIL_HOST_PASSWORD=abcdefghijklmnop  # No spaces
   ```

5. **Restart Django Server**:
   ```bash
   # Stop server (Ctrl+C)
   source env/bin/activate
   python manage.py runserver
   ```

## Configuration Examples

### Example 1: Development with Console Backend
```bash
# .env file
EMAIL_BACKEND=console
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=dev@example.com
EMAIL_HOST_PASSWORD=not-needed-for-console
```

**Use case**: Testing quotation email content and functionality during development.

### Example 2: Production with Gmail SMTP
```bash
# .env file
EMAIL_BACKEND=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=sales@saskitup.co.nz
EMAIL_HOST_PASSWORD=abcdefghijklmnop  # 16-char App Password
DEFAULT_FROM_EMAIL=SAS Sports <sales@saskitup.co.nz>
```

**Use case**: Production environment sending real emails to customers.

### Example 3: Custom SMTP Server
```bash
# .env file
EMAIL_BACKEND=smtp
EMAIL_HOST=mail.yourdomain.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@yourdomain.com
EMAIL_HOST_PASSWORD=your-smtp-password
```

**Use case**: Using your own mail server instead of Gmail.

## Troubleshooting

### Issue: "Username and Password not accepted"
**Error**:
```
SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')
```

**Solutions**:
1. ✅ Use App Password, not regular password
2. ✅ Enable 2-Factor Authentication on Gmail
3. ✅ Generate new App Password at https://myaccount.google.com/apppasswords
4. ✅ Remove all spaces from App Password
5. ✅ Restart Django server after updating .env

### Issue: SSL Certificate Verification Failed
**Error**:
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Solutions**:
1. ✅ Already fixed with custom email backend
2. ✅ Ensure DEBUG=True in development
3. ✅ Settings automatically create unverified SSL context
4. ✅ No action needed - handled automatically

### Issue: Emails Not Showing in Terminal
**Problem**: Using console backend but no output

**Solutions**:
1. ✅ Check EMAIL_BACKEND=console in .env
2. ✅ Restart Django server
3. ✅ Look in terminal where `python manage.py runserver` is running
4. ✅ Check for email sending errors in logs

### Issue: Switching from Console to SMTP
**Steps**:
1. Update .env: `EMAIL_BACKEND=smtp`
2. Add Gmail App Password
3. Restart Django server
4. Test quotation creation

## Testing Email Functionality

### Test with Console Backend
1. Set `EMAIL_BACKEND=console` in .env
2. Start Django server
3. Create a new quotation with email addresses
4. Save quotation
5. Check terminal output for email content

### Test with SMTP Backend
1. Set `EMAIL_BACKEND=smtp` in .env
2. Configure Gmail App Password
3. Start Django server
4. Create a new quotation with valid email
5. Save quotation
6. Check recipient's inbox

### Verify Email in Audit Trail
1. Go to: http://localhost:8000/auth/audit-logs/
2. Filter by: "Email Sent (New)" or "Email Failed"
3. Check description for recipients and status
4. Click Details to see full information

## Email Content

### New Quotation Email
- **Subject**: New Quotation Q-20251015-0001 - Institution Name
- **Greeting**: "Thank you for your interest in SAS SPORTS LTD"
- **Content**: Product list, pricing, terms
- **Delivery**: 4-6 weeks from order confirmation
- **Closing**: "Best regards, SAS Sports (Pvt) Ltd"

### Updated Quotation Email
- **Subject**: Updated Quotation Q-20251015-0001 - Institution Name
- **Greeting**: "Thank you for your continued interest in SAS Sports"
- **Content**: Updated product list, pricing, terms
- **Delivery**: 6-8 weeks from order confirmation
- **Supersession**: Notice about superseding previous version
- **Closing**: "Warm regards, SAS Sports (Pvt) Ltd"

## Environment Variables Reference

### Required Settings
```bash
EMAIL_BACKEND=console|smtp  # Backend type
EMAIL_HOST=smtp.gmail.com   # SMTP server
EMAIL_PORT=587              # SMTP port
EMAIL_USE_TLS=True          # Enable TLS
```

### Authentication Settings
```bash
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Display Name <email@domain.com>
```

### Optional Settings
```bash
EMAIL_USE_SSL=False                    # Use SSL instead of TLS (port 465)
EMAIL_SSL_CERTFILE=/path/to/cert.pem  # Custom SSL cert
EMAIL_SSL_KEYFILE=/path/to/key.pem    # Custom SSL key
EMAIL_TIMEOUT=10                       # Connection timeout
```

## Production Deployment Checklist

- [ ] Set `EMAIL_BACKEND=smtp`
- [ ] Configure valid Gmail account
- [ ] Enable 2-Factor Authentication
- [ ] Generate Gmail App Password
- [ ] Update EMAIL_HOST_USER
- [ ] Update EMAIL_HOST_PASSWORD
- [ ] Set DEFAULT_FROM_EMAIL
- [ ] Test email sending
- [ ] Verify emails received
- [ ] Check audit trail logs
- [ ] Monitor for errors
- [ ] Set up email monitoring/alerting

## Security Best Practices

1. **Never commit .env file** - Contains sensitive credentials
2. **Use App Passwords** - Never use account password
3. **Rotate credentials** - Change App Password periodically
4. **Monitor audit logs** - Check for email failures
5. **Use SSL/TLS** - Always enable encryption
6. **Limit access** - Only authorized apps get App Password
7. **Revoke unused** - Remove old App Passwords
8. **Production SSL** - Use proper certificates in production

## Related Documentation
- [EMAIL_SSL_FIX.md](EMAIL_SSL_FIX.md) - SSL certificate verification fix
- [EMAIL_INTEGRATION.md](EMAIL_INTEGRATION.md) - Complete email integration
- [QUOTATION_EMAIL_SETUP.md](QUOTATION_EMAIL_SETUP.md) - Email setup guide
- [QUOTATION_EMAILS_QUICK_REFERENCE.md](QUOTATION_EMAILS_QUICK_REFERENCE.md) - Quick reference

## Support Links
- Gmail App Passwords: https://myaccount.google.com/apppasswords
- Gmail Security Settings: https://myaccount.google.com/security
- Google 2FA Setup: https://www.google.com/landing/2step/
- SMTP Troubleshooting: https://support.google.com/mail/?p=BadCredentials

## Current Status
✅ **Console Backend Active** - Emails print to terminal for development testing
🔄 **SMTP Backend Ready** - Configure Gmail App Password when ready for production
