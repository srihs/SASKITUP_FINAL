# Schools App

Django app for managing New Zealand school data from the government API.

## Features

- **School Database**: Comprehensive list of NZ schools with search and filtering
- **School Detail Pages**: Detailed information for each school including enrollment data
- **API Integration**: Syncs with NZ Government Schools API
- **Admin Interface**: Django admin integration for data management
- **Responsive UI**: Clean, responsive interface consistent with existing design

## Models

### School
Main model for storing school information with fields:
- Basic info: School ID, name, type, authority, status
- Contact: Phone, fax, email, contact person, website
- Location: Physical and postal addresses, coordinates
- Administrative: Regional council, territorial authority, education region
- Enrollment: Student counts by ethnicity, total enrollment
- Characteristics: Co-ed status, language of instruction, boarding facilities

## API Integration

### Data Source
- **API URL**: https://catalogue.data.govt.nz/api/3/action/datastore_search
- **Resource ID**: 4b292323-9fcc-41f8-814b-3c7b19cf14b3
- **Total Schools**: ~2,574 schools

### Management Commands

```bash
# Test API connection
python manage.py sync_schools --dry-run

# Sync all schools
python manage.py sync_schools

# Sync limited number
python manage.py sync_schools --limit 100
```

## URL Structure

- `/schools/` - School database list
- `/schools/school/<school_id>/` - School detail page
- `/schools/search/` - AJAX search endpoint
- `/schools/retail/` - Retail schools (placeholder)
- `/schools/wholesale/` - Wholesale schools (placeholder)

## Navigation

Added to main navigation under "Schools" section:
- School Database
- Retail Schools
- Wholesale Schools

## Usage Examples

### Search and Filter Schools
```python
from schools.services import SchoolAPIService

# Search schools
schools = SchoolAPIService.search_schools(
    query="Auckland",
    filters={'org_type': 'Full Primary'}
)

# Get filter options
options = SchoolAPIService.get_filter_options()
```

### Sync Data
```python
from schools.services import SchoolAPIService

# Sync schools from API
stats = SchoolAPIService.sync_schools(limit=50)
print(f"Created: {stats['created']}, Updated: {stats['updated']}")
```

## File Structure

```
schools/
├── models.py              # School model
├── views.py               # List, detail, and placeholder views
├── services.py            # API integration service
├── urls.py                # URL configuration
├── admin.py               # Django admin configuration
├── management/
│   └── commands/
│       └── sync_schools.py # Management command
└── templates/schools/
    ├── school_list.html    # Main database page
    ├── school_detail.html  # Individual school page
    ├── retail_schools.html # Placeholder page
    └── wholesale_schools.html # Placeholder page
```

## Implementation Notes

- Model fields mapped to API response structure
- Timezone-aware datetime handling
- Error handling for API failures
- Pagination for large datasets
- Search across multiple fields
- Database indexes for performance
- Admin interface with organized fieldsets