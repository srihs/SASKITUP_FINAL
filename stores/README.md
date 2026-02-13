# Store Locations App

This Django app manages The Uniform Shoppe's physical store locations, their operating hours, and which schools they service.

## Features

- **Store Management**: Track all store locations with complete contact and address information
- **Opening Hours**: Define specific opening/closing times for each day of the week
- **School Assignments**: Link stores to the schools they service
- **GPS Coordinates**: Optional location mapping support
- **Public Display**: Customer-facing views to display store information

## Models

### Store
Represents a physical store location with:
- Name, address, and contact information (phone, email)
- GPS coordinates for mapping
- Many-to-many relationship with School model
- Display order for controlling list presentation
- Active/inactive status

### StoreOpeningHours
Defines operating hours for each store:
- Day of week (Monday-Sunday)
- Opening and closing times
- Closed flag for days when store is not open
- Optional notes (e.g., "Appointment only")
- Unique constraint on store + day_of_week

## Admin Interface

**Access Control**: Only superusers can add, edit, or delete stores and opening hours.

### Store Admin Features:
- Inline editing of opening hours (all 7 days)
- Horizontal filter for selecting schools
- Search by name, city, suburb, address, phone, email
- Filter by active status, city, suburb
- Displays school count in list view

### Opening Hours Admin:
- Can be managed inline from Store admin or separately
- Automatically enforces one entry per day per store
- Clear display of day names and formatted hours

## URLs

- `/stores/` - List all active stores
- `/stores/<id>/` - Detail view for a specific store

## Templates

### store_list.html
Displays all active stores in a card grid with:
- Store name and address
- Contact information
- Summary of opening hours (first 3 days)
- Number of schools serviced
- Link to full details

### store_detail.html
Detailed view showing:
- Complete store information
- Full weekly opening hours
- All schools serviced by the store
- Link to Google Maps (if GPS coordinates provided)
- List of schools with links to school detail pages

## Usage

### Adding a Store

1. Go to Django Admin > Stores > Add Store
2. Fill in basic information (name, address, contact details)
3. Optionally add GPS coordinates
4. Select schools this store services
5. Add opening hours for each day of the week in the inline form
6. Save

### Viewing Stores

- Admin users: Use Django admin interface
- All users: Navigate to `/stores/` to see public list
- Click on any store to see full details

### API Integration

The models are designed to work with Django REST Framework if needed in the future. Consider adding:
- `stores/api_urls.py` for API endpoints
- `stores/serializers.py` for API serialization
- `stores/api_views.py` for API views

## Permissions

- **View Access**: All authenticated users can view store listings
- **Edit Access**: Only superusers can add, edit, or delete stores
- This ensures store information remains accurate and controlled

## Future Enhancements

Potential additions:
- Store images/photos
- Integration with Google Maps API for embedded maps
- Holiday hours management
- Special events/announcements per store
- Store-specific inventory tracking
- Appointment booking system
