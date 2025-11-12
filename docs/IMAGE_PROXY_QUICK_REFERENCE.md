# Image Proxy - Quick Reference Guide

## For Developers

### Adding Proxy Support to New Templates

1. **Load the template tag at the top of your template:**
```django
{% load image_proxy %}
```

2. **Apply the filter to image URLs:**
```django
{# Before #}
<img src="{{ product.image_url }}" alt="{{ product.name }}">

{# After #}
<img src="{{ product.image_url|proxy_image_url }}" alt="{{ product.name }}">
```

3. **The filter automatically:**
   - Proxies URLs from protected domains (Lotto, BallStore)
   - Returns original URL for non-protected domains
   - Handles empty/None values gracefully

### Protected Domains

The proxy only handles these domains:
- `dev-lottosports.it.sas.co.nz` (Lotto WordPress)
- `theballstore.co.nz` (BallStore WordPress)

All other domains pass through unchanged.

### Example Usage

```django
{% load static %}
{% load image_proxy %}

{# Product listing #}
{% for product in products %}
  <img src="{{ product.image_url|proxy_image_url }}" alt="{{ product.name }}">
{% endfor %}

{# Product detail #}
<img src="{{ product.featured_image_url|proxy_image_url }}" class="img-fluid">

{# Variations #}
{% for variation in variations %}
  <img src="{{ variation.image|proxy_image_url }}" class="thumbnail">
{% endfor %}
```

## For System Administrators

### Environment Setup

Add to `.env` file:
```bash
# Image Proxy Credentials (HTTP Basic Auth)
USERNAME=sas-admin
PASSWORD=gXbPuQUDOUMAymdN0nIe
```

### Testing the Proxy

**Direct URL test:**
```bash
curl "http://localhost:8000/quotations/proxy-image/?url=https://dev-lottosports.it.sas.co.nz/wp-content/uploads/test.jpg" -o test.jpg
```

**Run test suite:**
```bash
source env/bin/activate
python test_image_proxy.py
```

### Monitoring

**Watch proxy logs:**
```bash
tail -f django.log | grep "Image proxy"
```

**Common log messages:**
- `Image proxy called without URL parameter` - Missing URL parameter
- `Image proxy rejected unauthorized domain` - Blocked domain
- `Image proxy failed to fetch image` - Image not found or auth failed
- `Image proxy timeout` - Request took too long

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Images not loading | Check credentials in `.env` file |
| 403 Forbidden | URL is not from allowed domain |
| 404 Not Found | Image doesn't exist or URL parameter missing |
| 504 Gateway Timeout | Image server is slow, check network |
| 401 Unauthorized | Credentials are incorrect |

### Security Notes

✅ **Safe:**
- Credentials only in environment variables
- Domain whitelist prevents abuse
- No credentials exposed to browser

❌ **Don't:**
- Hardcode credentials in code
- Add unverified domains to whitelist
- Disable timeout (prevents DOS)

## API Reference

### Proxy View

**Endpoint:** `/quotations/proxy-image/`

**Method:** `GET`

**Parameters:**
- `url` (required): Full URL of image to proxy

**Response:**
- `200 OK`: Image data with proper content-type
- `403 Forbidden`: URL not from allowed domain
- `404 Not Found`: Missing URL or image not found
- `504 Gateway Timeout`: Request timeout
- `500 Internal Server Error`: Other error

**Example:**
```
GET /quotations/proxy-image/?url=https://dev-lottosports.it.sas.co.nz/image.jpg
```

### Template Filter

**Name:** `proxy_image_url`

**Input:** Image URL (string)

**Output:** Proxied URL or original URL

**Example:**
```django
{{ "https://dev-lottosports.it.sas.co.nz/image.jpg"|proxy_image_url }}
{# Output: /quotations/proxy-image/?url=https%3A%2F%2F... #}

{{ "https://example.com/image.jpg"|proxy_image_url }}
{# Output: https://example.com/image.jpg (unchanged) #}
```

## Performance Tips

1. **Browser Caching:** Images are cached by browser for session
2. **Timeout:** 10-second timeout prevents hanging requests
3. **Streaming:** Large images don't consume server memory
4. **Consider CDN:** For production, add CDN caching layer

## Adding New Protected Domains

Edit `quotations/views.py` and `quotations/templatetags/image_proxy.py`:

```python
# In both files, update:
allowed_domains = [
    'dev-lottosports.it.sas.co.nz',
    'theballstore.co.nz',
    'new-domain.com',  # Add new domain
]
```

**Important:** Only add trusted domains you control!
