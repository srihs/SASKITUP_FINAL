# Additional Email Recipients - Quick Reference

## Quick Start

### For Users

1. **Adding Emails When Creating Quotation**:
   - Go to Quotation Cart page
   - Scroll to "Recipient Information" section
   - Find "Additional Email Recipients" field
   - Enter emails separated by semicolons: `email1@example.com; email2@example.com`
   - Click "Generate Quotation"

2. **Editing Additional Emails**:
   - Edit existing quotation
   - Update "Additional Email Recipients" field
   - Save changes

3. **Viewing Recipients**:
   - Open quotation detail page
   - Scroll to billing section
   - See "Additional Recipients" listed below recipient info

### For Developers

#### Get All Recipients

```python
from quotations.models import Quotation

quotation = Quotation.objects.get(pk=uuid)
recipients = quotation.get_all_email_recipients()
# Returns: ['primary@example.com', 'additional1@example.com', 'additional2@example.com']
```

#### Validate Emails

```python
from quotations.views import validate_additional_emails

emails = "test1@example.com; test2@example.com"
is_valid, error_message = validate_additional_emails(emails)

if is_valid:
    # Save to quotation
    quotation.additional_emails = emails
    quotation.save()
else:
    # Show error
    return JsonResponse({'error': error_message}, status=400)
```

#### Send Email (Example)

```python
from django.core.mail import send_mail

quotation = Quotation.objects.get(pk=uuid)
recipients = quotation.get_all_email_recipients()

send_mail(
    subject=f'Quotation {quotation.quotation_number}',
    message='Your quotation is attached.',
    from_email='noreply@saskitup.co.nz',
    recipient_list=recipients,
    fail_silently=False,
)
```

## Field Details

- **Field Name**: `additional_emails`
- **Type**: TextField
- **Format**: Semicolon-separated email addresses
- **Required**: No (optional)
- **Max Length**: Unlimited (TextField)
- **Example**: `"john@school.com; mary@school.com; admin@school.com"`

## Validation Rules

1. **Format**: Emails separated by semicolons (`;`)
2. **Whitespace**: Leading/trailing spaces are trimmed
3. **Empty**: Empty field is valid (optional)
4. **Email Format**: Each email must be valid format (user@domain.com)

### Valid Examples
- `"test@example.com"`
- `"test1@example.com; test2@example.com"`
- `"test@example.com ; test2@example.com"` (spaces ok)
- `""` (empty is ok)

### Invalid Examples
- `"not-an-email"` ❌
- `"test@"` ❌
- `"@example.com"` ❌
- `"test test@example.com"` ❌

## API Endpoints

### Save Quotation with Additional Emails

**POST** `/quotations/save/`

**Form Data**:
```
recipient_name: "John Doe"
recipient_address: "123 Main St"
additional_emails: "email1@example.com; email2@example.com"
institution_id: "tusschool_123" (optional)
```

**Response** (Success):
```json
{
    "success": true,
    "quotation_id": "uuid",
    "quotation_number": "Q-20251014-0001",
    "message": "Quotation generated successfully!",
    "redirect_url": "/quotations/preview/uuid/"
}
```

**Response** (Error):
```json
{
    "success": false,
    "error": "Invalid email address: not-valid-email"
}
```

## Template Variables

### In quotation_cart.html
```django
{% if editing_quotation.additional_emails %}
    {{ editing_quotation.additional_emails }}
{% endif %}
```

### In quotation_detail.html
```django
{% if quotation.additional_emails %}
    {% for email in quotation.additional_emails.split:';' %}
        {{ email.strip }}
    {% endfor %}
{% endif %}
```

## Database

### Table: `quotations`

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| additional_emails | TEXT | YES | NULL |

### Query Examples

```sql
-- Get quotations with additional emails
SELECT quotation_number, additional_emails
FROM quotations
WHERE additional_emails IS NOT NULL AND additional_emails != '';

-- Update additional emails
UPDATE quotations
SET additional_emails = 'new@example.com; other@example.com'
WHERE id = 'uuid';
```

## Common Issues & Solutions

### Issue: Email validation fails on save
**Solution**: Check that each email is valid format. Use semicolons, not commas.

### Issue: Additional emails not showing in detail view
**Solution**: Check that `additional_emails` field is not empty/null in database.

### Issue: Duplicate emails in recipient list
**Solution**: The `get_all_email_recipients()` method automatically removes duplicates.

### Issue: Email sending not working
**Solution**: Email sending is not yet implemented. See EMAIL_INTEGRATION.md for implementation guide.

## File Locations

- **Model**: `/quotations/models.py` (line 296-299)
- **Views**: `/quotations/views.py` (lines 69-92, 1135-1149, 1212-1230)
- **Template (Cart)**: `/quotations/templates/quotations/quotation_cart.html` (lines 933-943, 1421-1485)
- **Template (Detail)**: `/quotations/templates/quotations/quotation_detail.html` (lines 580-589)
- **Migration**: `/quotations/migrations/0006_quotation_additional_emails.py`

## Testing

### Manual Testing Steps

1. Create new quotation
2. Add additional emails: `test1@example.com; test2@example.com`
3. Save quotation
4. View quotation detail page
5. Verify emails are displayed
6. Edit quotation
7. Change emails to: `test3@example.com`
8. Save and verify

### Automated Testing (Future)

```python
from django.test import TestCase
from quotations.models import Quotation
from quotations.views import validate_additional_emails

class AdditionalEmailsTestCase(TestCase):
    def test_valid_emails(self):
        is_valid, _ = validate_additional_emails('test@example.com')
        self.assertTrue(is_valid)

    def test_invalid_email(self):
        is_valid, error = validate_additional_emails('invalid-email')
        self.assertFalse(is_valid)
        self.assertIn('Invalid email', error)

    def test_get_all_recipients(self):
        quotation = Quotation.objects.create(
            created_by=self.user,
            additional_emails='test@example.com'
        )
        recipients = quotation.get_all_email_recipients()
        self.assertIn('test@example.com', recipients)
```

## Support & Documentation

- **Full Documentation**: See `EMAIL_INTEGRATION.md`
- **Implementation Details**: See `IMPLEMENTATION_SUMMARY.md`
- **Django Email Docs**: https://docs.djangoproject.com/en/stable/topics/email/

## Version History

- **v1.0** (Oct 14, 2025): Initial implementation
  - Added additional_emails field
  - Implemented frontend/backend validation
  - Created helper methods
  - Added UI components
