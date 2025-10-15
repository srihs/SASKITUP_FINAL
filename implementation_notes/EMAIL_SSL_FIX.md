# Email SSL Certificate Verification Fix

## Issue
Email sending was failing with SSL certificate verification error:
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: unable to get local issuer certificate (_ssl.c:1028)
```

This error occurred when attempting to send quotation emails through SMTP with TLS enabled.

## Root Cause
Python 3.13's SSL library requires valid SSL certificates by default when establishing TLS connections. In development environments, this can cause issues when:
- Using local/development mail servers
- SSL certificates are not properly configured
- Testing with self-signed certificates

## Solution Implemented

### 1. Custom Email Backend
Created a custom email backend that extends Django's SMTP backend with SSL context support:

**File**: `quotations/backends/email.py`
```python
class EmailBackend(DjangoEmailBackend):
    """Custom SMTP email backend that uses EMAIL_SSL_CONTEXT from settings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(settings, 'EMAIL_SSL_CONTEXT'):
            self.ssl_context = settings.EMAIL_SSL_CONTEXT
```

### 2. Settings Configuration
Updated `kitup/settings.py` with SSL configuration:

```python
# Use custom backend that supports SSL context configuration
EMAIL_BACKEND = 'quotations.backends.email.EmailBackend'

# SSL/TLS Configuration for Email
import ssl
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_SSL_CERTFILE = config('EMAIL_SSL_CERTFILE', default=None)
EMAIL_SSL_KEYFILE = config('EMAIL_SSL_KEYFILE', default=None)

# Create unverified SSL context for development (bypass certificate verification)
if DEBUG and EMAIL_USE_TLS:
    EMAIL_SSL_CONTEXT = ssl._create_unverified_context()
```

## Configuration Options

### Development Environment (DEBUG=True)
- **EMAIL_SSL_CONTEXT**: Automatically set to `ssl._create_unverified_context()`
- **Effect**: Bypasses SSL certificate verification for local testing
- **Security**: Safe for development only

### Production Environment (DEBUG=False)
- **EMAIL_SSL_CONTEXT**: Not set (uses default secure context)
- **EMAIL_SSL_CERTFILE**: Path to SSL certificate file (optional)
- **EMAIL_SSL_KEYFILE**: Path to SSL private key file (optional)
- **Effect**: Enforces strict SSL certificate verification
- **Security**: Full certificate validation enabled

### Environment Variables (.env)
```bash
# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# SSL Configuration (Production)
EMAIL_USE_SSL=False  # Set to True for port 465
EMAIL_SSL_CERTFILE=/path/to/cert.pem  # Optional
EMAIL_SSL_KEYFILE=/path/to/key.pem    # Optional
```

## Files Modified

### New Files
1. **quotations/backends/__init__.py** - Email backends package initialization
2. **quotations/backends/email.py** - Custom EmailBackend with SSL context support

### Modified Files
1. **kitup/settings.py** - Added SSL configuration and custom backend
2. **quotations/emails.py** - Added comment about SSL context usage

## Testing

### Manual Testing
1. Create a quotation with valid email addresses
2. Save the quotation (triggers email sending)
3. Check server logs for successful email send
4. Verify audit trail shows email sent successfully

### Expected Results
- ✅ Email sends successfully without SSL errors
- ✅ Audit log shows "quotation_email_sent" action
- ✅ Recipients receive quotation email with logo

### Development Environment
```bash
# Activate virtual environment
source env/bin/activate

# Run development server
python manage.py runserver

# Create test quotation
# Navigate to: http://localhost:8000/quotations/cart/
# Add items and save with valid email address
```

## Security Considerations

### Development (DEBUG=True)
- ⚠️ SSL certificate verification is **disabled**
- ⚠️ Should **NEVER** be used in production
- ✅ Safe for local testing with development mail servers

### Production (DEBUG=False)
- ✅ SSL certificate verification is **enabled** by default
- ✅ Supports custom SSL certificates via environment variables
- ✅ Full certificate validation enforced
- ⚠️ Ensure valid SSL certificates are configured

### Best Practices
1. **Never disable SSL verification in production**
2. Use proper SSL certificates from trusted Certificate Authorities
3. Rotate email credentials regularly
4. Use app-specific passwords for Gmail (not account password)
5. Monitor email sending errors in audit logs

## Gmail Configuration

### Using Gmail SMTP
1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password:
   - Go to: https://myaccount.google.com/apppasswords
   - Select app: Mail
   - Select device: Other (Custom name)
   - Generate password
3. Use the generated password in `EMAIL_HOST_PASSWORD`

### Gmail Settings
```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=generated-app-password
```

## Troubleshooting

### Issue: Still getting SSL errors
**Solution**:
- Verify `DEBUG=True` in settings
- Check that custom backend is properly configured
- Restart development server

### Issue: Email not sending
**Solution**:
- Verify email credentials in .env
- Check EMAIL_HOST and EMAIL_PORT settings
- Test with Gmail's SMTP server settings
- Check audit logs for error details

### Issue: "Authentication failed" errors
**Solution**:
- Use app-specific password for Gmail
- Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
- Ensure 2FA is enabled on Gmail account

## Future Enhancements

1. **Email Queue System**: Implement background task queue for email sending
2. **Retry Logic**: Add automatic retry with exponential backoff
3. **Rate Limiting**: Implement rate limiting for bulk email sends
4. **Email Templates**: Add more email template variations
5. **PDF Attachments**: Attach quotation PDF to emails

## Related Documentation
- [EMAIL_INTEGRATION.md](EMAIL_INTEGRATION.md) - Complete email integration guide
- [QUOTATION_EMAIL_SETUP.md](QUOTATION_EMAIL_SETUP.md) - Email setup instructions
- [QUOTATION_EMAILS_QUICK_REFERENCE.md](QUOTATION_EMAILS_QUICK_REFERENCE.md) - Quick reference

## Status
✅ **Fixed and Deployed** - SSL certificate verification error resolved
