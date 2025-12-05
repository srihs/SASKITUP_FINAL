# Quotation Email Integration Guide

## Overview

The Quotation model now supports additional email recipients through the `additional_emails` field. This document provides implementation guidance for integrating email sending functionality.

## Database Schema

### Quotation Model Fields

- **`additional_emails`** (TextField, optional): Semicolon-separated email addresses
  - Stored in database as plain text
  - Validated on save using Django's `validate_email`
  - Displayed in quotation detail view

## Helper Methods

### `Quotation.get_all_email_recipients()`

Returns a list of all email recipients for a quotation, including:
1. Primary recipient (created_by user email)
2. Additional email addresses from `additional_emails` field

**Returns**: List of unique email addresses (duplicates removed)

**Example**:
```python
quotation = Quotation.objects.get(pk=some_uuid)
recipients = quotation.get_all_email_recipients()
# ['user@example.com', 'additional1@example.com', 'additional2@example.com']
```

## Validation

### Frontend Validation (JavaScript)

Location: `quotations/templates/quotations/quotation_cart.html`

Functions:
- `validateEmail(email)`: Validates single email using regex
- `validateAdditionalEmails()`: Validates all semicolon-separated emails

Validation occurs before form submission.

### Backend Validation (Python)

Location: `quotations/views.py`

Function: `validate_additional_emails(emails_string)`

**Parameters**:
- `emails_string`: String of semicolon-separated email addresses

**Returns**: Tuple `(is_valid: bool, error_message: str or None)`

**Usage**:
```python
is_valid, error_message = validate_additional_emails(request.POST.get('additional_emails'))
if not is_valid:
    return JsonResponse({'success': False, 'error': error_message}, status=400)
```

## Email Sending Implementation

When implementing email functionality, follow this pattern:

### Example Implementation

```python
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_quotation_email(quotation):
    """
    Send quotation to all recipients.

    Args:
        quotation: Quotation instance
    """
    # Get all recipients
    recipients = quotation.get_all_email_recipients()

    if not recipients:
        logger.warning(f"No recipients for quotation {quotation.quotation_number}")
        return False

    # Prepare email content
    subject = f"Quotation {quotation.quotation_number} - {quotation.institution_name}"

    # Render HTML template
    html_content = render_to_string('quotations/emails/quotation_email.html', {
        'quotation': quotation,
        'items': quotation.items.all(),
    })

    # Render plain text template
    text_content = render_to_string('quotations/emails/quotation_email.txt', {
        'quotation': quotation,
        'items': quotation.items.all(),
    })

    # Create email
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipients[0]],  # Primary recipient
        cc=recipients[1:] if len(recipients) > 1 else [],  # Additional recipients as CC
    )

    # Attach HTML version
    email.attach_alternative(html_content, "text/html")

    # Optionally attach PDF
    # pdf_file = generate_quotation_pdf(quotation)
    # email.attach(f'quotation_{quotation.quotation_number}.pdf', pdf_file, 'application/pdf')

    # Send email
    try:
        email.send(fail_silently=False)
        logger.info(f"Quotation {quotation.quotation_number} sent to {len(recipients)} recipients")
        return True
    except Exception as e:
        logger.error(f"Failed to send quotation {quotation.quotation_number}: {str(e)}")
        return False
```

### Alternative: BCC Instead of CC

If you want to hide additional recipients from each other, use BCC:

```python
email = EmailMultiAlternatives(
    subject=subject,
    body=text_content,
    from_email=settings.DEFAULT_FROM_EMAIL,
    to=[recipients[0]],  # Primary recipient
    bcc=recipients[1:] if len(recipients) > 1 else [],  # Additional recipients as BCC
)
```

## UI Components

### Quotation Cart Form

Location: `quotations/templates/quotations/quotation_cart.html`

Input field with:
- Label: "Additional Email Recipients (Optional)"
- Placeholder: "email1@example.com; email2@example.com"
- Help text explaining semicolon separation
- Client-side validation with error display
- Pre-populated when editing existing quotation

### Quotation Detail View

Location: `quotations/templates/quotations/quotation_detail.html`

Displays additional recipients:
- Section header: "Additional Recipients:"
- Each email displayed with envelope icon
- Separated in a bordered section for clarity

## Email Templates (To Be Created)

### HTML Template

Create: `quotations/templates/quotations/emails/quotation_email.html`

Should include:
- Company branding/logo
- Quotation number and date
- Institution name
- Line items with prices
- Totals (subtotal, GST, total)
- Terms and conditions
- Contact information

### Plain Text Template

Create: `quotations/templates/quotations/emails/quotation_email.txt`

Plain text version of HTML template for email clients that don't support HTML.

## Configuration

### Django Settings

Add to `settings.py`:

```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Or your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@example.com'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'SASKITUP Quotations <noreply@saskitup.co.nz>'

# For development, use console backend to print emails to console
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

## Integration Points

### When to Send Emails

1. **Quotation Created** (SaveQuotationView):
   ```python
   # After quotation.save() in SaveQuotationView
   if not is_editing:
       send_quotation_email(quotation)
   ```

2. **Quotation Approved** (ApproveQuotationView):
   ```python
   # After quotation.approve()
   send_quotation_approval_email(quotation)
   ```

3. **Manual Resend** (Create new view):
   ```python
   class ResendQuotationEmailView(LoginRequiredMixin, View):
       def post(self, request, pk):
           quotation = get_object_or_404(Quotation, pk=pk)
           # Check permissions
           success = send_quotation_email(quotation)
           return JsonResponse({'success': success})
   ```

## Security Considerations

1. **Email Validation**: Always validate email addresses on both frontend and backend
2. **Rate Limiting**: Implement rate limiting to prevent email spam
3. **Permissions**: Verify user has permission to send quotation emails
4. **Logging**: Log all email sending attempts for audit trail
5. **Error Handling**: Gracefully handle email sending failures

## Testing

### Unit Tests

```python
from django.test import TestCase
from quotations.models import Quotation

class QuotationEmailTests(TestCase):
    def test_get_all_email_recipients_with_additional_emails(self):
        quotation = Quotation.objects.create(
            created_by=self.user,
            additional_emails='test1@example.com; test2@example.com'
        )
        recipients = quotation.get_all_email_recipients()
        self.assertEqual(len(recipients), 3)  # user + 2 additional

    def test_get_all_email_recipients_removes_duplicates(self):
        quotation = Quotation.objects.create(
            created_by=self.user,  # user.email = 'user@example.com'
            additional_emails='user@example.com; test@example.com'
        )
        recipients = quotation.get_all_email_recipients()
        self.assertEqual(len(recipients), 2)  # No duplicates

    def test_validate_additional_emails_invalid(self):
        is_valid, error = validate_additional_emails('invalid-email')
        self.assertFalse(is_valid)
        self.assertIn('Invalid email address', error)
```

## Future Enhancements

1. **Email Templates**: Create professional HTML email templates
2. **PDF Attachments**: Generate and attach PDF version of quotation
3. **Email Tracking**: Track when emails are opened/clicked
4. **Scheduled Sending**: Allow scheduling of quotation emails
5. **Email History**: Store sent email history in database
6. **Custom Messages**: Allow users to add custom message to email body
7. **Reply-To**: Configure reply-to address for quotation discussions

## Support

For questions or issues, contact the development team or refer to:
- Django Email Documentation: https://docs.djangoproject.com/en/stable/topics/email/
- Django Email Backends: https://docs.djangoproject.com/en/stable/topics/email/#email-backends
