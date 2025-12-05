# School Matching System

This document explains how wholesale schools are matched with NZ schools database to provide proper address and contact information in the bulk assignment view.

## Overview

The wholesale schools from CIN7 API often lack complete address and contact information, while the NZ schools database contains comprehensive details for all schools in New Zealand. The school matching system automatically matches wholesale schools with their corresponding NZ schools to provide complete contact details.

## How It Works

### 1. Matching Algorithm

The system uses a two-stage matching approach:

1. **Exact Match**: First attempts an exact case-insensitive match between school names
2. **Fuzzy Match**: If no exact match is found, uses similarity scoring to find the best match

### 2. Name Normalization

School names are normalized for better matching by:
- Converting to lowercase
- Removing common suffixes (School, College, High, etc.)
- Standardizing abbreviations (Saint → St, Mount → Mt)
- Removing connecting words (of, the, &)

### 3. Similarity Scoring

Uses Python's `difflib.SequenceMatcher` to calculate similarity scores (0.0 to 1.0):
- Minimum threshold: 0.85 (configurable)
- Exact matches score 1.0
- Similar names like "Wellington Girls" vs "Wellington Girls College" score high

### 4. Caching

Results are cached for 1 hour to improve performance:
- Cache key format: `school_match_{normalized_name}`
- Stores either the matched school ID or 'not_found'

## Usage in Views

The BulkAssignmentView (`authentication/views.py`) uses the `SchoolMatcher` utility:

```python
from authentication.utils.school_matcher import SchoolMatcher

# Batch match all wholesale schools for better performance
school_contact_details = SchoolMatcher.batch_match_schools(list(wholesale_schools))

# Use matched contact details
contact_details = school_contact_details.get(school.id, {})
```

## Data Priority

The system follows this priority order for contact information:

1. **Wholesale School Data**: If the wholesale school has its own address/contact data, use it
2. **Matched NZ School Data**: If a match is found, use the NZ school's complete information
3. **Default Values**: Fall back to "No address available", "Not specified", etc.

## Contact Information Mapping

When a match is found, the following NZ school fields are used:

- **Address**: `add1_line1`, `add1_suburb`, `add1_city`
- **Region**: `regional_council` or `education_region`
- **Contact Person**: `contact1_name`
- **Phone**: `telephone`
- **Email**: `email`

## Management Command

Use the preview command to analyze matching results:

```bash
# Preview all matches
python manage.py preview_school_matching

# Show all schools including unmatched
python manage.py preview_school_matching --show-all

# Export results to CSV
python manage.py preview_school_matching --export matching_results.csv

# Adjust similarity threshold
python manage.py preview_school_matching --min-score 0.75
```

## Files Structure

```
authentication/
├── utils/
│   └── school_matcher.py          # Core matching logic
├── management/commands/
│   └── preview_school_matching.py # Analysis command
├── tests_school_matcher.py        # Unit tests
└── views.py                      # BulkAssignmentView implementation
```

## Performance Considerations

1. **Batch Processing**: Schools are matched in batches to minimize database queries
2. **Caching**: Results are cached to avoid repeated calculations
3. **Query Optimization**: Uses `only()` to fetch minimal fields for similarity calculation
4. **Status Filtering**: Only matches with open schools to avoid closed institutions

## Testing

Run tests to verify functionality:

```bash
# Run all school matcher tests
python manage.py test authentication.tests_school_matcher

# Run specific test
python manage.py test authentication.tests_school_matcher.SchoolMatcherTestCase.test_find_matching_nz_school_exact
```

## Configuration

Key constants in `SchoolMatcher`:

- `CACHE_TIMEOUT`: 3600 seconds (1 hour)
- `MIN_SIMILARITY_SCORE`: 0.85 (adjustable)

## Troubleshooting

### Common Issues

1. **Low Match Rate**: Consider lowering `MIN_SIMILARITY_SCORE`
2. **Cache Issues**: Clear Django cache if results seem stale
3. **Performance**: Ensure database indexes exist on `org_name` and `status` fields

### Logs

The matcher logs successful fuzzy matches at INFO level:
```
Matched wholesale school 'Auckland Grammar' to NZ school 'Auckland Grammar School' with score 0.95
```

### Debugging

Use the preview command to analyze specific schools:
```bash
python manage.py preview_school_matching --show-all --min-score 0.5
```

## Future Enhancements

Potential improvements:
1. Machine learning-based matching
2. Manual override table for edge cases
3. Address-based matching for schools with different names
4. Integration with external school databases