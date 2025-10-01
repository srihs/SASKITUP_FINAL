# Wholesale Price Update API Documentation

## Overview

The Wholesale Price Update API provides comprehensive backend functionality for managing wholesale school product pricing through a modern web interface. This REST API supports file uploads, price calculations, data retrieval, analytics, and real-time monitoring.

## Base URL

- Development: `http://localhost:8000/api/`
- Production: `https://yourdomain.com/api/`

## Authentication

The API supports two authentication methods:

### Session Authentication
For web applications using the same domain:
```javascript
// Already authenticated via Django session
fetch('/api/products/')
```

### Token Authentication
For external applications or API clients:
```bash
# Get token
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'

# Use token
curl -H "Authorization: Token your-token-here" \
  http://localhost:8000/api/products/
```

## API Documentation

### Interactive Documentation
- **Swagger UI**: `/api/swagger/` - Interactive API explorer
- **ReDoc**: `/api/redoc/` - Clean documentation interface
- **OpenAPI Schema**: `/api/swagger.json` - Machine-readable schema

## Endpoints Overview

### File Upload & Processing
- `POST /api/upload/csv/` - Upload and validate CSV files

### Price Update Operations
- `POST /api/price-updates/` - Execute price updates (preview or actual)
- `POST /api/price-updates/preview/` - Preview changes only
- `POST /api/price-updates/execute/` - Execute changes

### Data Retrieval
- `GET /api/products/` - List wholesale products
- `GET /api/products/{id}/` - Get product details
- `GET /api/products/export_csv/` - Export products to CSV
- `GET /api/products/pricing_statistics/` - Get pricing statistics
- `GET /api/schools/` - List wholesale schools
- `GET /api/schools/{id}/` - Get school details

### Analytics & Reporting
- `GET /api/analytics/` - Comprehensive pricing analysis

### Sync Job Monitoring
- `GET /api/sync-jobs/` - List sync jobs
- `GET /api/sync-jobs/{id}/` - Get job details
- `GET /api/sync-jobs/{id}/status/` - Get real-time job status
- `GET /api/sync-jobs/active/` - Get active jobs

## Detailed Endpoint Documentation

### 1. File Upload & Processing

#### Upload CSV File
```http
POST /api/upload/csv/
Content-Type: multipart/form-data
```

**Parameters:**
- `file` (required): CSV file containing pricing data
- `validate_products` (optional, default: true): Validate product existence
- `allow_partial_matches` (optional, default: false): Allow partial SKU matches
- `delimiter` (optional, default: ','): CSV delimiter character

**CSV Format:**
```csv
sku,cost_price,wholesale_price,retail_price
PROD-001,25.50,80.00,100.00
PROD-002,30.00,85.00,110.00
```

**Response:**
```json
{
  "total_rows": 100,
  "valid_rows": 98,
  "invalid_rows": 2,
  "duplicate_rows": 0,
  "validation_errors": [
    {
      "row": 15,
      "field": "cost_price",
      "message": "Invalid decimal value",
      "severity": "error"
    }
  ],
  "warnings": [
    {
      "row": 25,
      "message": "Product not found, will create new",
      "severity": "warning"
    }
  ],
  "preview_data": [
    {
      "row": 2,
      "data": {
        "sku": "PROD-001",
        "cost_price": "25.50"
      },
      "calculated_changes": {
        "old_cost_price": "20.00",
        "new_cost_price": "25.50",
        "new_margin_75_price": "102.00"
      }
    }
  ]
}
```

**Example Usage:**
```javascript
const formData = new FormData();
formData.append('file', csvFile);
formData.append('validate_products', true);

fetch('/api/upload/csv/', {
  method: 'POST',
  body: formData,
  headers: {
    'Authorization': 'Token your-token-here'
  }
})
.then(response => response.json())
.then(data => {
  console.log('Validation results:', data);
});
```

### 2. Price Update Operations

#### Execute Price Updates
```http
POST /api/price-updates/
Content-Type: application/json
```

**Request Body:**
```json
{
  "items": [
    {
      "product_id": 123,
      "cost_price": "30.00"
    },
    {
      "sku": "PROD-002",
      "cost_price": "25.00",
      "wholesale_price": "80.00"
    }
  ],
  "dry_run": true,
  "force_update": false,
  "calculate_margin_75": true,
  "update_variations": true
}
```

**Parameters:**
- `items`: Array of price update items
- `dry_run` (default: true): Preview only, don't save changes
- `force_update` (default: false): Force update despite warnings
- `calculate_margin_75` (default: true): Auto-calculate 75% margin prices
- `update_variations` (default: true): Update product variations

**Response:**
```json
{
  "total_processed": 2,
  "successful_updates": 2,
  "failed_updates": 0,
  "skipped_updates": 0,
  "success_rate": 100.0,
  "processing_time": 0.45,
  "total_cost_price_updates": 2,
  "total_wholesale_price_updates": 1,
  "total_margin_75_calculations": 2,
  "results": [
    {
      "product_id": 123,
      "product_name": "Test Product",
      "sku": "PROD-001",
      "old_cost_price": "25.00",
      "new_cost_price": "30.00",
      "old_margin_75_price": "100.00",
      "new_margin_75_price": "120.00",
      "new_discount_percentage": "33.33",
      "success": true,
      "errors": [],
      "warnings": [],
      "changes_applied": {
        "cost_price": {
          "old": "25.00",
          "new": "30.00"
        }
      }
    }
  ],
  "errors": [],
  "warnings": []
}
```

**Example Usage:**
```javascript
// Preview changes
const previewData = {
  items: [
    { product_id: 123, cost_price: "30.00" }
  ],
  dry_run: true
};

fetch('/api/price-updates/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Token your-token-here'
  },
  body: JSON.stringify(previewData)
})
.then(response => response.json())
.then(data => {
  if (data.success_rate === 100) {
    // Execute actual update
    const executeData = { ...previewData, dry_run: false };
    return fetch('/api/price-updates/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Token your-token-here'
      },
      body: JSON.stringify(executeData)
    });
  }
});
```

### 3. Data Retrieval

#### List Products
```http
GET /api/products/
```

**Query Parameters:**
- `search`: Search by name, SKU, or school name
- `school`: Filter by school ID
- `category`: Filter by category ID
- `stock_status`: Filter by stock status
- `cost_price__gte`: Minimum cost price
- `cost_price__lte`: Maximum cost price
- `cost_price__isnull`: True/false for missing cost prices
- `page`: Page number
- `page_size`: Items per page (max 100)
- `ordering`: Sort by field (name, cost_price, created_at)

**Response:**
```json
{
  "count": 1250,
  "next": "http://localhost:8000/api/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 123,
      "name": "School Shirt - Blue",
      "sku": "SHIRT-BLUE-001",
      "school": 1,
      "school_name": "Springfield High",
      "category": 5,
      "category_name": "Uniforms",
      "cost_price": "25.00",
      "wholesale_price": "80.00",
      "retail_price": "100.00",
      "margin_75_price": "100.00",
      "discount_percentage": "20.00",
      "stock_status": "instock",
      "current_discount_percentage": 20.0,
      "current_profit_margin": 68.75,
      "pricing_status": "normal",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Export Products to CSV
```http
GET /api/products/export_csv/
```

Returns a CSV file with all filtered products.

**Response Headers:**
```
Content-Type: text/csv
Content-Disposition: attachment; filename="wholesale_products_20240115_103000.csv"
```

#### Get Pricing Statistics
```http
GET /api/products/pricing_statistics/
```

**Response:**
```json
{
  "total_products": 1250,
  "products_with_cost": 1200,
  "products_with_wholesale": 1180,
  "products_with_margin_75": 1150,
  "avg_cost_price": "28.50",
  "avg_wholesale_price": "85.75",
  "avg_margin_75_price": "114.00",
  "avg_discount_percentage": "25.30",
  "min_cost_price": "5.00",
  "max_cost_price": "150.00",
  "high_discount_products": 45,
  "low_margin_products": 12,
  "negative_margin_products": 3,
  "missing_cost_price": 50,
  "missing_wholesale_price": 70
}
```

### 4. Analytics & Reporting

#### Get Pricing Analytics
```http
GET /api/analytics/
```

**Response:**
```json
{
  "report_type": "summary",
  "generated_at": "2024-01-15T10:30:00Z",
  "generated_by": "admin",
  "statistics": {
    // Same as pricing statistics above
  },
  "issues": [
    {
      "product_id": 456,
      "product_name": "Problem Product",
      "school_name": "Test School",
      "sku": "PROB-001",
      "issue_type": "high_discount",
      "severity": "medium",
      "current_cost_price": "30.00",
      "current_wholesale_price": "40.00",
      "current_discount_percentage": "75.00",
      "description": "Product has high discount of 75.0%",
      "recommended_action": "Review pricing strategy"
    }
  ],
  "filters_applied": {},
  "total_records": 1250,
  "export_format": "json"
}
```

### 5. Sync Job Monitoring

#### List Sync Jobs
```http
GET /api/sync-jobs/
```

**Response:**
```json
{
  "count": 25,
  "results": [
    {
      "id": 15,
      "job_type": "csv_import",
      "status": "running",
      "progress_current": 150,
      "progress_total": 500,
      "message": "Processing products...",
      "error_details": null,
      "result_data": {},
      "started_at": "2024-01-15T10:25:00Z",
      "completed_at": null,
      "created_by": "admin",
      "progress_percentage": 30.0,
      "estimated_completion": "2024-01-15T10:35:00Z"
    }
  ]
}
```

#### Get Real-time Job Status
```http
GET /api/sync-jobs/{id}/status/
```

This endpoint provides real-time updates for monitoring job progress.

## Error Handling

All API endpoints return consistent error responses:

### HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation errors)
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `413` - Request Entity Too Large (file uploads)
- `500` - Internal Server Error

### Error Response Format
```json
{
  "success": false,
  "message": "Validation failed",
  "errors": [
    "Cost price must be a positive number",
    "Product with SKU 'INVALID' not found"
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Field-specific Validation Errors
```json
{
  "success": false,
  "errors": {
    "cost_price": ["Enter a valid decimal number"],
    "sku": ["This field is required"]
  }
}
```

## Rate Limiting

The API implements rate limiting to ensure fair usage:

- **General endpoints**: 100 requests per minute
- **File uploads**: 20 requests per minute
- **Large exports**: 10 requests per minute

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642248600
```

## Pagination

List endpoints support pagination with these query parameters:

- `page`: Page number (starts at 1)
- `page_size`: Items per page (default: 20, max: 100)

Pagination response format:
```json
{
  "count": 1250,
  "next": "http://localhost:8000/api/products/?page=3",
  "previous": "http://localhost:8000/api/products/?page=1",
  "results": [...]
}
```

## Filtering and Searching

Most list endpoints support filtering and searching:

### Search
Use the `search` parameter for full-text search:
```
GET /api/products/?search=school shirt
```

### Filtering
Use field-specific filters:
```
GET /api/products/?school=1&stock_status=instock&cost_price__gte=20.00
```

### Ordering
Use the `ordering` parameter:
```
GET /api/products/?ordering=-created_at,name
```

## Frontend Integration Examples

### React/JavaScript Example

```javascript
class WholesalePricingAPI {
  constructor(baseURL, token) {
    this.baseURL = baseURL;
    this.token = token;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const headers = {
      'Authorization': `Token ${this.token}`,
      'Content-Type': 'application/json',
      ...options.headers
    };

    const response = await fetch(url, {
      ...options,
      headers
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  }

  // Upload and validate CSV
  async uploadCSV(file, options = {}) {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(options).forEach(([key, value]) => {
      formData.append(key, value);
    });

    const response = await fetch(`${this.baseURL}/upload/csv/`, {
      method: 'POST',
      headers: {
        'Authorization': `Token ${this.token}`
      },
      body: formData
    });

    return response.json();
  }

  // Preview price changes
  async previewPriceUpdates(items) {
    return this.request('/price-updates/', {
      method: 'POST',
      body: JSON.stringify({
        items,
        dry_run: true,
        calculate_margin_75: true
      })
    });
  }

  // Execute price updates
  async executePriceUpdates(items) {
    return this.request('/price-updates/', {
      method: 'POST',
      body: JSON.stringify({
        items,
        dry_run: false,
        calculate_margin_75: true
      })
    });
  }

  // Get products with filters
  async getProducts(filters = {}) {
    const params = new URLSearchParams(filters);
    return this.request(`/products/?${params}`);
  }

  // Get pricing analytics
  async getPricingAnalytics() {
    return this.request('/analytics/');
  }

  // Monitor sync job
  async monitorSyncJob(jobId, callback) {
    const poll = async () => {
      try {
        const status = await this.request(`/sync-jobs/${jobId}/status/`);
        callback(status);

        if (status.status === 'running') {
          setTimeout(poll, 2000); // Poll every 2 seconds
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
    };

    poll();
  }
}

// Usage
const api = new WholesalePricingAPI('/api', 'your-token-here');

// Upload CSV and preview changes
document.getElementById('csv-upload').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    try {
      const validation = await api.uploadCSV(file, {
        validate_products: true
      });

      console.log('Validation results:', validation);

      if (validation.valid_rows > 0) {
        // Show preview and allow user to proceed
        showPreview(validation.preview_data);
      }
    } catch (error) {
      console.error('Upload failed:', error);
    }
  }
});
```

### Vue.js Integration

```javascript
// Vue.js composable for pricing API
import { ref, reactive } from 'vue';

export function usePricingAPI() {
  const loading = ref(false);
  const error = ref(null);
  const results = reactive({
    validation: null,
    preview: null,
    execution: null
  });

  const uploadCSV = async (file) => {
    loading.value = true;
    error.value = null;

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/upload/csv/', {
        method: 'POST',
        body: formData
      });

      results.validation = await response.json();
    } catch (err) {
      error.value = err.message;
    } finally {
      loading.value = false;
    }
  };

  const previewChanges = async (items) => {
    loading.value = true;

    try {
      const response = await fetch('/api/price-updates/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items,
          dry_run: true
        })
      });

      results.preview = await response.json();
    } catch (err) {
      error.value = err.message;
    } finally {
      loading.value = false;
    }
  };

  return {
    loading,
    error,
    results,
    uploadCSV,
    previewChanges
  };
}
```

## Testing

The API includes comprehensive test coverage. Run tests with:

```bash
# Run all API tests
python manage.py test clubs.tests.test_api

# Run specific test class
python manage.py test clubs.tests.test_api.CSVFileUploadAPITestCase

# Run with coverage
coverage run --source='.' manage.py test clubs.tests.test_api
coverage report
```

## Performance Considerations

### Optimization Features
- Database query optimization with `select_related` and `prefetch_related`
- Pagination for large datasets
- CSV streaming for large exports
- Efficient bulk operations for price updates
- Caching for frequently accessed data

### Best Practices
- Use appropriate page sizes for list endpoints
- Implement client-side caching for static data
- Use WebSocket connections for real-time updates (planned feature)
- Batch price updates when possible
- Monitor API response times and set timeouts

## Security

### Data Protection
- All endpoints require authentication
- File upload validation and size limits
- SQL injection prevention through Django ORM
- CSRF protection for web clients
- Input validation and sanitization

### Access Control
- User-based authentication
- Permission-based access control
- Rate limiting to prevent abuse
- Secure file upload handling

## Support and Troubleshooting

### Common Issues

**1. File Upload Fails**
- Check file size (max 10MB)
- Ensure CSV format with required columns
- Verify authentication headers

**2. Price Update Errors**
- Validate decimal format for prices
- Check product existence before updates
- Use preview mode to test changes

**3. Authentication Issues**
- Verify token validity
- Check token header format: `Authorization: Token your-token`
- Ensure user has necessary permissions

### Getting Help
- Check the interactive API documentation at `/api/swagger/`
- Review error messages for specific guidance
- Contact support at support@saskitup.co.za

This comprehensive API provides all the functionality needed for a modern wholesale price update system, with robust error handling, comprehensive documentation, and extensive testing coverage.