# Geocoding Feature Documentation

## Overview

The geocoding feature automatically detects the city name from a New Zealand postcode when the city field is empty during shipping calculation. This enhancement uses the Google Geocoding API to improve user experience by auto-filling the city field.

## Feature Implementation

### Files Modified/Created

1. **`quotations/utils_geocoding.py`** (NEW)
   - Core geocoding utility module
   - Google Geocoding API integration
   - Result caching (24-hour cache)
   - Error handling and logging

2. **`quotations/views.py`** (MODIFIED)
   - `CalculateShippingView.post()` method updated
   - Added geocoding fallback when city is empty but postcode is provided
   - Returns geocoded city in JSON response

3. **`quotations/templates/quotations/quotation_cart.html`** (MODIFIED)
   - Enhanced JavaScript to auto-fill city field from geocoding result
   - Added success toast notification when city is auto-filled

4. **`test_geocoding.py`** (NEW)
   - Test script for geocoding functionality
   - Validates API integration with various NZ postcodes

### Configuration

#### Required Environment Variables

The Google Maps API key is already configured in `.env`:

```bash
GOOGLE_MAPS_API_KEY=AIzaSyDSkkPacSCfwCkDAys4ICkgZ21yMv1W82o
```

#### Django Settings

The API key is loaded in `kitup/settings.py`:

```python
# Line 364
GOOGLE_MAPS_API_KEY = config('GOOGLE_MAPS_API_KEY', default='')
```

## How It Works

### User Flow

1. **User enters postcode without city:**
   - User fills in postcode: `2121`
   - City field is left empty
   - User triggers shipping calculation (by entering suburb or postcode)

2. **Automatic geocoding:**
   - Backend detects empty city with valid postcode
   - Calls Google Geocoding API: `2121, NZ`
   - API returns: `Tuakau 2121, New Zealand`
   - City extracted: `Tuakau`

3. **Auto-fill city:**
   - Response includes `geocoded_city: "Tuakau"`
   - Frontend auto-fills city field
   - Success notification displayed: "City auto-filled from postcode: Tuakau"
   - Shipping cost calculated and displayed

### Backend Logic

```python
# In CalculateShippingView.post()

# Get address components
city = request.POST.get('city', '').strip()
suburb = request.POST.get('suburb', '').strip()
postcode = request.POST.get('postcode', '').strip()

# If city is empty but postcode exists, try geocoding
geocoded_city = None
if not city and postcode:
    from .utils_geocoding import get_city_from_postcode
    geocode_result = get_city_from_postcode(postcode)
    if geocode_result and geocode_result.get('city'):
        city = geocode_result['city']
        geocoded_city = city

# Validate required parameters
if not city:
    return JsonResponse({
        'success': False,
        'error': 'City is required for shipping calculation. Please provide a city or valid postcode.'
    }, status=400)

# Continue with shipping calculation...

# Return geocoded city in response
return JsonResponse({
    'success': True,
    'shipping_cost': str(total_shipping_cost),
    'geocoded_city': geocoded_city,  # Will be None if not geocoded
    # ... other fields
})
```

### Frontend Logic

```javascript
.then(data => {
    if (data.success) {
        // If city was geocoded from postcode, auto-fill the city field
        if (data.geocoded_city) {
            $('#recipient_city').val(data.geocoded_city);
            console.log('Auto-filled city from postcode:', data.geocoded_city);
            toastr.success('City auto-filled from postcode: ' + data.geocoded_city);
        }

        // Update shipping display and recalculate totals
        updateShippingDisplay(data);
        recalculateTotalsWithShipping(data.shipping_cost);
    }
})
```

## Caching Strategy

To minimize API calls and improve performance, geocoding results are cached for 24 hours.

### Cache Implementation

```python
from django.core.cache import cache

def get_city_from_postcode(postcode, country='NZ'):
    # Check cache first
    cache_key = f'geocode_postcode_{country}_{postcode}'
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    # Make API call...

    # Cache the result for 24 hours (86400 seconds)
    cache.set(cache_key, geocode_result, timeout=86400)
    return geocode_result
```

### Cache Benefits

- **Reduced API calls**: Same postcode requests use cached results
- **Faster response**: No network delay for cached postcodes
- **Cost savings**: Google Geocoding API usage minimized
- **Improved UX**: Instant auto-fill for cached postcodes

## Testing

### Manual Testing

1. **Test with postcode 2121:**
   ```
   City: (empty)
   Suburb: Tuakau
   Postcode: 2121

   Expected: City auto-filled to "Tuakau"
   Shipping calculated successfully
   ```

2. **Test with postcode 7010:**
   ```
   City: (empty)
   Suburb: Stoke
   Postcode: 7010

   Expected: City auto-filled to "Nelson"
   Shipping calculated successfully
   ```

3. **Test with invalid postcode:**
   ```
   City: (empty)
   Suburb: Test
   Postcode: 9999

   Expected: Error message "City is required..."
   ```

4. **Test with city already provided:**
   ```
   City: Auckland
   Suburb: CBD
   Postcode: 0600

   Expected: No geocoding performed
   Shipping calculated with provided city
   ```

### Automated Testing

Run the test script:

```bash
source env/bin/activate
python test_geocoding.py
```

**Test Results:**
```
✓ 2121 → Tuakau
✓ 7010 → Nelson
✓ 0600 → Auckland
✓ 6011 → Wellington
✓ 8011 → Christchurch
✓ 9810 → Invercargill
✓ 3210 → Hamilton
✓ 5010 → Lower Hutt
✗ 9999 → Invalid (expected failure)
✓ Cache hit test passed
```

## Error Handling

### Graceful Degradation

The feature is designed to degrade gracefully when:

1. **API key missing:**
   - Warning logged: "Google Maps API key not configured"
   - Returns None, continues without geocoding
   - User must enter city manually

2. **API call fails:**
   - Network errors caught and logged
   - Returns None, continues without geocoding
   - User sees error: "City is required..."

3. **No results found:**
   - Invalid postcode handled gracefully
   - Warning logged: "No results for postcode X"
   - Returns None, user must enter city

4. **API timeout:**
   - 5-second timeout configured
   - Caught and logged
   - Returns None, continues without geocoding

### Error Scenarios

| Scenario | Behavior | User Experience |
|----------|----------|-----------------|
| No API key | Skip geocoding | Manual city entry required |
| Network error | Skip geocoding | Manual city entry required |
| Invalid postcode | Return error | "City is required..." message |
| API timeout | Skip geocoding | Manual city entry required |
| City already provided | Skip geocoding | Use provided city |

## API Usage and Costs

### Google Geocoding API

- **Pricing**: $5.00 per 1000 requests (as of Nov 2025)
- **Free tier**: $200 monthly credit (40,000 requests)
- **Caching**: 24-hour cache reduces API calls significantly

### Expected Usage

For a typical e-commerce site:
- **With caching**: ~100-500 API calls/month
- **Cost**: $0.50-$2.50/month (well within free tier)
- **Cache hit rate**: Estimated 80-90% for common postcodes

## Logging

All geocoding operations are logged for monitoring and debugging.

### Log Levels

- **INFO**: Successful geocoding operations
- **WARNING**: API key missing, invalid postcodes, no results
- **ERROR**: Network errors, API failures, unexpected exceptions

### Example Logs

```
INFO: Geocoding postcode 2121 for country NZ
INFO: Successfully geocoded postcode 2121 to city: Tuakau

WARNING: Google Maps API key not configured - geocoding disabled
WARNING: No city/locality found in geocoding results for postcode 9999

ERROR: Network error during geocoding for postcode 2121: Connection timeout
ERROR: Google Geocoding API error: OVER_QUERY_LIMIT for postcode 2121
```

## Maintenance

### Cache Management

Django cache backend can be configured in `settings.py`:

```python
# Default: Database cache (already configured)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cache_table',
    }
}

# Optional: Redis cache (better performance)
# CACHES = {
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': 'redis://127.0.0.1:6379/1',
#     }
# }
```

### Monitoring

Monitor geocoding performance using logs:

```bash
# Check geocoding success rate
grep "Successfully geocoded" django.log | wc -l

# Check for errors
grep "ERROR.*geocoding" django.log

# Check cache hits
grep "Cache hit for postcode" django.log | wc -l
```

## Future Enhancements

1. **Postcode validation:**
   - Validate NZ postcode format before API call
   - Reduce invalid API requests

2. **Multi-country support:**
   - Extend to support AU, UK postcodes
   - Auto-detect country from address

3. **Address autocomplete:**
   - Use Google Places Autocomplete
   - Full address auto-fill from partial input

4. **Improved caching:**
   - Implement Redis for better cache performance
   - Longer cache duration for verified postcodes

5. **Analytics:**
   - Track geocoding usage and success rates
   - Identify common postcodes for pre-caching

## Troubleshooting

### City not auto-filling

**Check:**
1. Browser console for errors
2. Network tab for API response
3. Django logs for geocoding errors
4. API key configuration

**Common issues:**
- JavaScript disabled
- CSRF token missing
- API key invalid
- Network connectivity

### API quota exceeded

**Solutions:**
1. Increase cache duration
2. Implement request throttling
3. Pre-cache common postcodes
4. Upgrade Google Cloud billing

### Incorrect city returned

**Investigation:**
1. Check Google Geocoding API response
2. Verify postcode validity
3. Review address component extraction logic
4. Consider alternative geocoding services

## References

- [Google Geocoding API Documentation](https://developers.google.com/maps/documentation/geocoding)
- [Django Cache Framework](https://docs.djangoproject.com/en/5.2/topics/cache/)
- [NZ Postcode Information](https://www.nzpost.co.nz/tools/address-postcode-finder)
