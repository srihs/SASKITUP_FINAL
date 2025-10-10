# Cin7 Price Update - Testing Guide

## 🧪 Quick Start Testing

### 1. Start Development Server

```bash
source env/bin/activate
python manage.py runserver
```

### 2. Navigate to Cin7 Price Update

Open in browser:
```
http://localhost:8000/schools/wholesale/cin7-price-update/
```

### 3. Test Workflow

#### Step 1: Select Price Type
- Choose "Wholesale" (default) or other price type
- Click "Fetch Prices from Cin7"

#### Step 2: Monitor Progress
- Watch real-time progress bar
- Should complete in 30-60 seconds for ~1000 products

#### Step 3: Review Preview
- Check statistics cards:
  - Total Cin7 Products
  - Matched Products
  - Not Found Products
  - Fetch Duration
- Review preview table (first 100 items)
- Verify price calculations look correct

#### Step 4: Apply Updates
- Click "Apply Updates"
- Confirm in modal dialog
- Monitor progress bar
- Review results dashboard

---

## 🔬 Detailed Testing Scenarios

### Scenario 1: API Connection Test

```bash
source env/bin/activate
python manage.py shell
```

```python
from schools.services.cin7_api_service import Cin7ApiService

# Initialize service
service = Cin7ApiService()

# Test connection
result = service.test_connection()
print(f"Connection test: {'✓ PASS' if result else '✗ FAIL'}")
```

**Expected Output**:
```
Cin7ApiService initialized: https://api.cin7.com/api/v1
Testing Cin7 API connection...
Cin7 API request: https://api.cin7.com/api/v1/Products (params: {'rows': 1, 'page': 1})
✓ Cin7 API connection test successful
Connection test: ✓ PASS
```

---

### Scenario 2: Fetch Small Dataset

```python
from schools.services.cin7_api_service import Cin7ApiService

service = Cin7ApiService()

# Fetch first page only (100 products)
products, fetched, total = service.fetch_all_products(price_type='Wholesale')

print(f"Fetched: {fetched} products")
print(f"Total available: {total}")
print(f"\nFirst product:")
print(f"  ID: {products[0].get('Id')}")
print(f"  Code: {products[0].get('Code')}")
print(f"  Name: {products[0].get('Name')}")
```

---

### Scenario 3: Price Calculation Test

```python
from schools.services.cin7_api_service import Cin7ApiService
from decimal import Decimal

service = Cin7ApiService()

# Mock Cin7 product
test_product = {
    'Id': 12345,
    'Code': 'TEST-SKU-001',
    'Name': 'Test Product',
    'Barcode': '1234567890',
    'AvgCost': 10.00,
    'SellPrice1': 35.00
}

# Extract and calculate prices
price_data = service.extract_price_data(test_product)

print("Price Calculations:")
print(f"  Cost: ${price_data['cost']}")
print(f"  RRP: ${price_data['current_retail_nzd_incl']}")
print(f"  75% Margin: ${price_data['margin_75_price']}")
print(f"  Discount: {price_data['discount_percentage']}%")

# Verify calculations
expected_margin = Decimal('10.00') / Decimal('0.25')  # Should be 40.00
expected_discount = ((Decimal('40.00') - Decimal('35.00')) / Decimal('40.00')) * 100  # Should be 12.50%

print(f"\nVerification:")
print(f"  Margin 75% correct: {price_data['margin_75_price'] == expected_margin}")
print(f"  Discount correct: {abs(price_data['discount_percentage'] - expected_discount) < Decimal('0.01')}")
```

**Expected Output**:
```
Price Calculations:
  Cost: $10.00
  RRP: $35.00
  75% Margin: $40.00
  Discount: 12.50%

Verification:
  Margin 75% correct: True
  Discount correct: True
```

---

### Scenario 4: Product Matching Test

```python
from schools.services.cin7_api_service import Cin7ApiService
from schools.services import ProductMatcherService

cin7_service = Cin7ApiService()
matcher = ProductMatcherService()

# Fetch first product from Cin7
products, _, _ = cin7_service.fetch_all_products()
test_product = products[0]

# Extract price data
price_data = cin7_service.extract_price_data(test_product)

# Try to match in database
product, variation, match_method = matcher.find_product(
    category='wholesale-schools',
    product_code=price_data['sku'],
    barcode=price_data['barcode']
)

print(f"Cin7 Product: {price_data['product_name']}")
print(f"SKU: {price_data['sku']}")
print(f"Barcode: {price_data['barcode']}")
print(f"\nMatch Result:")
print(f"  Found: {bool(product or variation)}")
print(f"  Match Method: {match_method}")
if product:
    print(f"  DB Product ID: {product.id}")
if variation:
    print(f"  DB Variation ID: {variation.id}")
```

---

### Scenario 5: Rate Limiting Test

```python
import time
from schools.services.cin7_api_service import Cin7ApiService

service = Cin7ApiService()

print("Testing rate limiting (3 calls/second)...")
print("Making 5 rapid requests:")

start_time = time.time()
for i in range(5):
    request_start = time.time()
    service._make_request('Products', {'rows': 1, 'page': 1})
    request_time = time.time() - request_start
    print(f"  Request {i+1}: {request_time:.2f}s")

total_time = time.time() - start_time
print(f"\nTotal time: {total_time:.2f}s")
print(f"Expected: ~2s (rate limit enforced)" if total_time > 1.5 else f"Warning: Rate limiting may not be working")
```

**Expected Output**:
```
Testing rate limiting (3 calls/second)...
Making 5 rapid requests:
  Request 1: 0.25s
  Request 2: 0.23s
  Request 3: 0.24s
  Request 4: 1.02s  (rate limit sleep)
  Request 5: 0.22s

Total time: ~2.0s
Expected: ~2s (rate limit enforced)
```

---

## 🐛 Troubleshooting

### Issue: "Failed to connect to Cin7 API"

**Check**:
```python
from decouple import config

print(f"API URL: {config('CIN7_API_URL')}")
print(f"Username: {config('CIN7_API_USERNAME')}")
print(f"API Key: {config('CIN7_API_KEY')[:5]}...")  # First 5 chars only
```

**Solution**:
- Verify credentials in `.env` file
- Check network connectivity
- Test URL in browser (should prompt for auth)

---

### Issue: "No products fetched"

**Check**:
```python
from schools.services.cin7_api_service import Cin7ApiService

service = Cin7ApiService()
response = service._make_request('Products', {'rows': 1, 'page': 1})

print(f"Response type: {type(response)}")
print(f"Response: {response}")
```

**Solution**:
- Check Cin7 API response format
- Verify pagination parameters
- Check for API errors in logs

---

### Issue: "Products not matching in database"

**Check**:
```python
from schools.models import WholesaleProduct

# Check SKU format in database
products = WholesaleProduct.objects.all()[:5]
for p in products:
    print(f"SKU: '{p.cin7_sku}' (type: {type(p.cin7_sku)})")
```

**Solution**:
- Verify SKU field names match
- Check for whitespace/case differences
- Review ProductMatcherService configuration

---

## ✅ Validation Checklist

### Pre-Production Testing

- [ ] API connection test passes
- [ ] Can fetch products from Cin7
- [ ] Price calculations are correct (75% margin + discount)
- [ ] Products match in database correctly
- [ ] Preview table displays properly
- [ ] Progress bar updates in real-time
- [ ] Bulk updates work correctly
- [ ] Audit logs are created
- [ ] Error handling works (test with bad credentials)
- [ ] Rate limiting is enforced

### Production Readiness

- [ ] Tested with small dataset (10-50 products)
- [ ] Verified price changes in database
- [ ] Performance is acceptable (<60s for 1000 products)
- [ ] No errors in Django logs
- [ ] Frontend UI is responsive
- [ ] All statistics are accurate
- [ ] Can handle "not found" products gracefully

---

## 📊 Performance Benchmarks

### Expected Timings

| Operation | Volume | Expected Time |
|-----------|--------|---------------|
| API Connection Test | 1 request | <1s |
| Fetch Products | 100 products | 5-10s |
| Fetch Products | 1,000 products | 30-60s |
| Price Calculations | 10,000 items | 1-2s |
| Database Updates | 1,000 records | 10-20s |
| Database Updates | 10,000 records | 20-30s |

### Performance Monitoring

Monitor these metrics during testing:

```python
from schools.services.cin7_api_service import Cin7ApiService
import time

service = Cin7ApiService()

# Fetch with timing
start = time.time()
products, fetched, total = service.fetch_all_products(price_type='Wholesale')
fetch_time = time.time() - start

# Calculate rates
fetch_rate = fetched / fetch_time if fetch_time > 0 else 0

print(f"Performance Metrics:")
print(f"  Products fetched: {fetched}")
print(f"  Time: {fetch_time:.2f}s")
print(f"  Rate: {fetch_rate:.1f} products/sec")
print(f"  API calls made: {service.daily_calls}")
```

---

## 🎯 Success Criteria

Implementation is successful if:

✅ Can connect to Cin7 API
✅ Can fetch products with proper rate limiting
✅ Price calculations match requirements:
   - 75% Margin = Cost ÷ 0.25
   - Discount = ((Margin - RRP) ÷ Margin) × 100
✅ Products match correctly in database (>80% match rate)
✅ Bulk updates complete without errors
✅ Progress tracking works in real-time
✅ UI is responsive and user-friendly
✅ Performance meets benchmarks
✅ Error handling is comprehensive
✅ Audit trail is complete

---

## 📞 Support

If you encounter issues:

1. Check Django logs: `tail -f /var/log/django/debug.log`
2. Check browser console for JavaScript errors
3. Review audit logs in Django admin
4. Test individual components using scenarios above
5. Contact development team with specific error messages

---

**Happy Testing! 🚀**
