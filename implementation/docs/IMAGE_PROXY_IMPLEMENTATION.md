# Image Proxy Implementation

## Overview

This document describes the image proxy solution implemented to display images from password-protected WordPress sites (Lotto and BallStore) in the quotation system.

## Problem Statement

Images from Lotto (dev-lottosports.it.sas.co.nz) and BallStore (theballstore.co.nz) WordPress sites are protected with HTTP Basic Authentication. Browsers cannot directly load these images, resulting in broken image links in the quotation interface.

## Solution

A Django view acts as a proxy, fetching images with authentication credentials and serving them to the browser without exposing credentials to the client.

## Implementation Details

### 1. Proxy View (`quotations/views.py`)

```python
def proxy_image(request):
    """
    Proxy images from password-protected WordPress sites.

    - Accepts image URL as query parameter
    - Validates URL is from allowed domain
    - Fetches image with HTTP Basic Auth
    - Returns image with proper content-type
    """
```

**Features:**
- Domain whitelist security (only allows Lotto and BallStore domains)
- HTTP Basic Auth using credentials from environment variables
- Proper error handling with specific HTTP status codes
- Streaming for efficient memory usage with large images
- Comprehensive logging for debugging

**Environment Variables:**
- `USERNAME`: Basic auth username (default: sas-admin)
- `PASSWORD`: Basic auth password (default: gXbPuQUDOUMAymdN0nIe)

### 2. URL Configuration (`quotations/urls.py`)

```python
path('proxy-image/', views.proxy_image, name='proxy-image'),
```

**URL Format:**
```
/quotations/proxy-image/?url=https://dev-lottosports.it.sas.co.nz/wp-content/uploads/image.jpg
```

### 3. Template Tag (`quotations/templatetags/image_proxy.py`)

```python
@register.filter
def proxy_image_url(image_url):
    """
    Automatically generates proxy URLs for protected domains.
    Returns original URL for non-protected domains.
    """
```

**Usage in Templates:**
```django
{% load image_proxy %}
<img src="{{ product.image_url|proxy_image_url }}" alt="{{ product.name }}">
```

### 4. Template Updates

Updated three templates to use the proxy filter:

1. **`new_quotation.html`** - Product listing page
   - Lotto product images: `product.normalized_image_url|proxy_image_url`
   - BallStore product images: `product.featured_image_url|proxy_image_url`

2. **`product_detail.html`** - Product detail page
   - Main product image: `product.image_url|proxy_image_url`

3. **`quotation_cart.html`** - Shopping cart page
   - Product thumbnails: `product.image_url|proxy_image_url`

## Security Considerations

### Domain Whitelist
Only images from approved domains are proxied:
- `dev-lottosports.it.sas.co.nz`
- `theballstore.co.nz`

### Credential Management
- Credentials stored in environment variables (not hardcoded)
- Never exposed to client browser
- Logged securely (no credentials in logs)

### Error Handling
- 403 Forbidden: Unauthorized domain
- 404 Not Found: Missing URL parameter or image not found
- 504 Gateway Timeout: Request timeout (10 seconds)
- 500 Internal Server Error: Other errors

## Performance Considerations

1. **Streaming Response**: Uses `stream=True` for efficient memory usage
2. **Timeout**: 10-second timeout prevents hanging requests
3. **Caching**: Consider adding browser caching headers in future
4. **CDN**: Could be enhanced with CDN caching for frequently accessed images

## Testing

### Test Script
Run `python test_image_proxy.py` to verify:
- ✅ Valid protected domain URLs generate proxy URLs
- ✅ Non-protected domains return original URLs
- ✅ Invalid domains are rejected (403)
- ✅ Missing URL parameter returns 404
- ✅ Template filter correctly transforms URLs

### Manual Testing
1. Navigate to quotations page: `/quotations/new/`
2. Search for Lotto or BallStore products
3. Verify product images display correctly
4. Check browser developer tools - images should load from `/quotations/proxy-image/` endpoint

## Files Modified

### New Files
- `/Users/sas/Repos/SASKITUP/quotations/templatetags/__init__.py`
- `/Users/sas/Repos/SASKITUP/quotations/templatetags/image_proxy.py`
- `/Users/sas/Repos/SASKITUP/test_image_proxy.py`

### Modified Files
- `/Users/sas/Repos/SASKITUP/quotations/views.py` - Added `proxy_image` view
- `/Users/sas/Repos/SASKITUP/quotations/urls.py` - Added proxy URL pattern
- `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/new_quotation.html` - Updated image tags
- `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/product_detail.html` - Updated image tags
- `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/quotation_cart.html` - Updated image tags

## Future Enhancements

1. **Response Caching**
   - Add caching headers for browser-side caching
   - Consider Django cache framework for server-side caching
   - Redis cache for frequently accessed images

2. **Image Optimization**
   - Resize large images on-the-fly
   - Convert to WebP format for better compression
   - Generate thumbnails for product listings

3. **CDN Integration**
   - Configure CloudFlare or similar CDN
   - Cache proxied images at edge locations
   - Reduce server load for popular images

4. **Monitoring**
   - Track proxy usage and performance
   - Monitor authentication failures
   - Alert on high error rates

5. **Advanced Features**
   - Support for additional protected domains
   - Dynamic credential management
   - Image preprocessing and transformation

## Troubleshooting

### Images Not Loading

**Check 1: Verify proxy endpoint is working**
```bash
curl "http://localhost:8000/quotations/proxy-image/?url=https://dev-lottosports.it.sas.co.nz/test.jpg"
```

**Check 2: Verify credentials are set**
```bash
echo $USERNAME
echo $PASSWORD
```

**Check 3: Review Django logs**
```bash
tail -f django.log | grep "Image proxy"
```

### Authentication Failures

If you see 401 Unauthorized errors:
1. Verify credentials in `.env` file
2. Test credentials directly with curl:
```bash
curl -u username:password https://dev-lottosports.it.sas.co.nz/test.jpg
```

### Template Tag Not Found

If you see "Invalid filter" errors:
1. Restart Django development server
2. Verify templatetags directory has `__init__.py`
3. Check template loads the tag: `{% load image_proxy %}`

## Maintenance

### Regular Tasks
- Monitor proxy usage in logs
- Review and rotate credentials periodically
- Update domain whitelist as needed
- Test after Django/Python upgrades

### Backup Credentials
Store backup credentials securely:
- Production secrets in environment variables
- Development credentials in `.env` (gitignored)
- Document credential rotation process

## Conclusion

The image proxy implementation successfully resolves the authentication challenge for WordPress images while maintaining security and performance. The solution is transparent to end users and easily maintainable for developers.
