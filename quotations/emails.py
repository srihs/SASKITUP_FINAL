"""
Email utility functions for quotations.

This module handles sending quotation emails to customers with support for:
- Multiple recipients (primary + additional emails)
- HTML and plain text email formats
- Email sending on create and update events
- Comprehensive error handling and logging
"""

import logging
import os
import tempfile
from typing import List, Optional, Tuple
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction
from email.mime.image import MIMEImage
from io import BytesIO
from decimal import Decimal

from .models import Quotation
from authentication.models import AuditLog

logger = logging.getLogger(__name__)

# Check if WeasyPrint is available for PDF generation
try:
    from weasyprint import HTML, CSS
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("WeasyPrint not installed. PDF generation will be disabled.")


def generate_quotation_pdf(quotation: Quotation) -> Optional[bytes]:
    """
    Generate professional PDF quotation using WeasyPrint.

    This function renders the same HTML template used for the quotation preview
    (/quotations/preview/<pk>/) and converts it to PDF using WeasyPrint,
    ensuring consistency between the web preview and the PDF output.

    Args:
        quotation: Quotation instance to generate PDF for

    Returns:
        PDF as bytes if successful, None if failed

    Example:
        >>> pdf_bytes = generate_quotation_pdf(quotation)
        >>> if pdf_bytes:
        >>>     with open('quotation.pdf', 'wb') as f:
        >>>         f.write(pdf_bytes)
    """
    if not PDF_AVAILABLE:
        logger.error("WeasyPrint not available. Cannot generate PDF.")
        return None

    try:
        from .models import SiteSettings

        # Get quotation items with product details
        items = quotation.items.all().select_related('product_content_type').order_by('sort_order', 'created_at')

        # Calculate discount amount
        if quotation.discount_percentage:
            discount_amount = (quotation.subtotal * quotation.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        else:
            discount_amount = quotation.discount_amount

        # Get quotation validity days from settings
        site_settings = SiteSettings.objects.get_settings()
        quotation_validity_days = site_settings.quotation_validity_days

        # Get absolute path to logo
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'sas-logo.png')

        # Prepare context matching the preview view
        context = {
            'quotation': quotation,
            'items': items,
            'discount_amount': discount_amount,
            'quotation_validity_days': quotation_validity_days,
            'logo_path': logo_path,
        }

        # Render the HTML template (use the PDF-specific template)
        html_string = render_to_string(
            'quotations/quotation_preview_pdf.html',
            context
        )

        logger.debug(f"Rendered HTML template for quotation {quotation.quotation_number}")

        # Generate PDF using WeasyPrint
        # Use base_url to resolve relative paths in HTML/CSS
        base_url = f"file://{settings.BASE_DIR}/"

        pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

        logger.info(f"Generated PDF for quotation {quotation.quotation_number} ({len(pdf_bytes)} bytes)")

        return pdf_bytes

    except Exception as e:
        logger.error(f"Failed to generate PDF for quotation {quotation.quotation_number}: {str(e)}", exc_info=True)
        return None


def send_quotation_email(
    quotation: Quotation,
    is_update: bool = False,
    request=None
) -> Tuple[bool, Optional[str]]:
    """
    Send quotation email to all recipients with CC to sales rep and account manager.
    Also sends separate internal notification emails to sales rep and account manager.

    Args:
        quotation: Quotation instance to send
        is_update: True if this is an update email, False if new quotation
        request: HTTP request object for audit logging (optional)

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
        - (True, None) if email sent successfully
        - (False, error_message) if email failed to send

    Example:
        >>> success, error = send_quotation_email(quotation, is_update=False)
        >>> if not success:
        >>>     logger.error(f"Failed to send email: {error}")
    """
    try:
        # Get all recipients
        recipients = quotation.get_all_email_recipients()

        if not recipients:
            error_msg = f"No email recipients for quotation {quotation.quotation_number}"
            logger.warning(error_msg)
            return False, error_msg

        # Collect CC recipients (sales rep and account manager)
        cc_recipients = []
        if quotation.assigned_sales_rep and quotation.assigned_sales_rep.email:
            cc_recipients.append(quotation.assigned_sales_rep.email)
        if quotation.account_manager and quotation.account_manager.email:
            cc_recipients.append(quotation.account_manager.email)

        # Remove duplicates from CC list
        cc_recipients = list(set(cc_recipients))

        # Prepare email subject
        action_text = "Updated" if is_update else "New"
        subject = f"{action_text} Quotation {quotation.quotation_number}"

        # Add institution name if available
        if quotation.institution:
            subject += f" - {quotation.institution_name}"

        # Get quotation items with addons (only base items, not addon items themselves)
        items = quotation.items.filter(is_addon=False).select_related(
            'product_content_type'
        ).prefetch_related('addons').all()

        # Calculate discount amount for email display
        from decimal import Decimal
        discount_amount = Decimal('0.00')
        if quotation.discount_percentage:
            discount_amount = (quotation.subtotal * quotation.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        elif quotation.discount_amount:
            discount_amount = quotation.discount_amount

        # Context for email templates
        email_context = {
            'quotation': quotation,
            'items': items,
            'is_update': is_update,
            'institution_name': quotation.institution_name,
            'quotation_url': _get_quotation_url(quotation),
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'discount_amount': discount_amount,
        }

        # Render HTML email template
        # NOTE: Template will be created after user provides design
        html_content = render_to_string(
            'quotations/emails/quotation_email.html',
            email_context
        )

        # Render plain text email template
        text_content = render_to_string(
            'quotations/emails/quotation_email.txt',
            email_context
        )

        # Build combined CC list (additional emails + staff)
        combined_cc = []
        if len(recipients) > 1:
            combined_cc.extend(recipients[1:])  # Additional customer emails
        combined_cc.extend(cc_recipients)  # Sales rep and account manager
        # Remove duplicates while preserving order
        combined_cc = list(dict.fromkeys(combined_cc))

        # Create email with primary recipient
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=_get_from_email(),
            to=[recipients[0]],  # Primary recipient
            cc=combined_cc if combined_cc else [],  # Combined CC list
        )

        # Attach HTML version
        email.attach_alternative(html_content, "text/html")

        # Embed company logo
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'sas-logo.png')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as logo_file:
                logo_image = MIMEImage(logo_file.read())
                logo_image.add_header('Content-ID', '<company_logo>')
                logo_image.add_header('Content-Disposition', 'inline', filename='sas-logo.png')
                email.attach(logo_image)

        # Attach PDF quotation
        try:
            pdf_bytes = generate_quotation_pdf(quotation)
            if pdf_bytes:
                email.attach(
                    f'Quotation_{quotation.quotation_number}.pdf',
                    pdf_bytes,
                    'application/pdf'
                )
                logger.info(f"Attached PDF to email for quotation {quotation.quotation_number}")
            else:
                logger.warning(f"PDF generation returned None for quotation {quotation.quotation_number}")
        except Exception as pdf_error:
            # Don't fail the entire email if PDF generation fails
            logger.error(f"Failed to attach PDF for quotation {quotation.quotation_number}: {str(pdf_error)}", exc_info=True)

        # Send customer email
        # Django automatically uses settings.EMAIL_SSL_CONTEXT if defined
        email.send(fail_silently=False)

        # Log successful customer email send
        _log_email_sent(quotation, recipients, is_update=is_update, request=request)

        logger.info(
            f"Quotation {quotation.quotation_number} email sent to "
            f"{len(recipients)} recipient(s): {', '.join(recipients)}"
        )

        # Send internal notification emails to sales rep and account manager
        internal_recipients = []
        if quotation.assigned_sales_rep and quotation.assigned_sales_rep.email:
            internal_recipients.append(quotation.assigned_sales_rep)
        if quotation.account_manager and quotation.account_manager.email:
            internal_recipients.append(quotation.account_manager)

        # Send internal notifications if there are staff assigned
        if internal_recipients:
            try:
                # Generate PDF once for all emails (reuse from customer email)
                pdf_bytes = generate_quotation_pdf(quotation)

                _send_internal_notifications(
                    quotation=quotation,
                    internal_recipients=internal_recipients,
                    is_update=is_update,
                    pdf_bytes=pdf_bytes,
                    request=request
                )
            except Exception as internal_error:
                # Don't fail the entire operation if internal emails fail
                logger.error(
                    f"Failed to send internal notifications for quotation {quotation.quotation_number}: {str(internal_error)}",
                    exc_info=True
                )

        return True, None

    except Exception as e:
        error_msg = f"Failed to send quotation {quotation.quotation_number} email: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Log failed email attempt
        _log_email_failed(quotation, str(e), is_update=is_update, request=request)

        return False, error_msg


def send_quotation_approval_email(
    quotation: Quotation,
    request=None
) -> Tuple[bool, Optional[str]]:
    """
    Send quotation approval notification email.

    This is a specialized email for when quotations are approved/confirmed.

    Args:
        quotation: Approved quotation instance
        request: HTTP request object for audit logging (optional)

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Get all recipients
        recipients = quotation.get_all_email_recipients()

        if not recipients:
            error_msg = f"No email recipients for quotation {quotation.quotation_number}"
            logger.warning(error_msg)
            return False, error_msg

        # Prepare email subject
        subject = f"Quotation {quotation.quotation_number} Approved"

        if quotation.institution:
            subject += f" - {quotation.institution_name}"

        # Context for email templates
        email_context = {
            'quotation': quotation,
            'items': quotation.items.all(),
            'approved_by': quotation.approved_by,
            'approved_at': quotation.approved_at,
            'quotation_url': _get_quotation_url(quotation),
        }

        # Render templates
        html_content = render_to_string(
            'quotations/emails/quotation_approval_email.html',
            email_context
        )

        text_content = render_to_string(
            'quotations/emails/quotation_approval_email.txt',
            email_context
        )

        # Create and send email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=_get_from_email(),
            to=[recipients[0]],
            cc=recipients[1:] if len(recipients) > 1 else [],
        )

        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        # Log successful email send
        _log_email_sent(quotation, recipients, is_approval=True, request=request)

        logger.info(
            f"Quotation approval email for {quotation.quotation_number} "
            f"sent to {len(recipients)} recipient(s)"
        )

        return True, None

    except Exception as e:
        error_msg = f"Failed to send approval email for {quotation.quotation_number}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def _send_internal_notifications(
    quotation: Quotation,
    internal_recipients: List,
    is_update: bool = False,
    pdf_bytes: Optional[bytes] = None,
    request=None
) -> None:
    """
    Send internal notification emails to sales rep and account manager.

    Args:
        quotation: Quotation instance
        internal_recipients: List of User objects (sales rep and/or account manager)
        is_update: True if this is an update notification
        pdf_bytes: Pre-generated PDF bytes (optional, will generate if not provided)
        request: HTTP request object for audit logging (optional)
    """
    # Prepare subject
    subject = f"{'Quotation Updated' if is_update else 'New Quotation Generated'} for {quotation.institution_name if quotation.institution_name != 'No Institution' else 'Customer'}"

    # Get company logo path
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'sas-logo.png')

    # Generate PDF if not provided
    if pdf_bytes is None:
        pdf_bytes = generate_quotation_pdf(quotation)

    # Send to each internal recipient
    for recipient_user in internal_recipients:
        try:
            # Context for internal notification template
            internal_context = {
                'quotation': quotation,
                'recipient_name': recipient_user.first_name or recipient_user.get_full_name(),
                'is_update': is_update,
                'institution_name': quotation.institution_name,
                'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            }

            # Render internal notification templates
            html_content = render_to_string(
                'quotations/emails/quotation_internal_notification.html',
                internal_context
            )

            text_content = render_to_string(
                'quotations/emails/quotation_internal_notification.txt',
                internal_context
            )

            # Create email
            internal_email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=_get_from_email(),
                to=[recipient_user.email],
            )

            # Attach HTML version
            internal_email.attach_alternative(html_content, "text/html")

            # Embed company logo
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as logo_file:
                    logo_image = MIMEImage(logo_file.read())
                    logo_image.add_header('Content-ID', '<company_logo>')
                    logo_image.add_header('Content-Disposition', 'inline', filename='sas-logo.png')
                    internal_email.attach(logo_image)

            # Attach PDF quotation if available
            if pdf_bytes:
                internal_email.attach(
                    f'Quotation_{quotation.quotation_number}.pdf',
                    pdf_bytes,
                    'application/pdf'
                )

            # Send email
            internal_email.send(fail_silently=False)

            # Log successful internal notification
            _log_internal_notification_sent(
                quotation=quotation,
                recipient=recipient_user,
                is_update=is_update,
                request=request
            )

            logger.info(
                f"Internal notification for quotation {quotation.quotation_number} "
                f"sent to {recipient_user.get_full_name()} ({recipient_user.email})"
            )

        except Exception as e:
            logger.error(
                f"Failed to send internal notification to {recipient_user.email} "
                f"for quotation {quotation.quotation_number}: {str(e)}",
                exc_info=True
            )
            # Continue to next recipient even if one fails


def _get_from_email() -> str:
    """
    Get the FROM email address for quotation emails.

    Returns:
        Email address string, defaults to DEFAULT_FROM_EMAIL or a fallback
    """
    return getattr(
        settings,
        'DEFAULT_FROM_EMAIL',
        'SASKITUP Quotations <noreply@saskitup.co.nz>'
    )


def _get_quotation_url(quotation: Quotation) -> str:
    """
    Get the full URL for viewing a quotation.

    Args:
        quotation: Quotation instance

    Returns:
        Full URL string for quotation detail page
    """
    # TODO: Build full URL with domain
    # For now, return relative URL
    return f"/quotations/{quotation.pk}/"


def _log_email_sent(
    quotation: Quotation,
    recipients: List[str],
    is_update: bool = False,
    is_approval: bool = False,
    request=None
) -> None:
    """
    Log successful email send to audit trail.

    Args:
        quotation: Quotation instance
        recipients: List of recipient email addresses
        is_update: True if this was an update email
        is_approval: True if this was an approval email
        request: HTTP request object (optional)
    """
    if is_approval:
        action_type = 'quotation_approval_email_sent'
        description = f'Approval email sent for quotation {quotation.quotation_number}'
    elif is_update:
        action_type = 'quotation_update_email_sent'
        description = f'Update email sent for quotation {quotation.quotation_number}'
    else:
        action_type = 'quotation_email_sent'
        description = f'Email sent for quotation {quotation.quotation_number}'

    description += f' to {len(recipients)} recipient(s): {", ".join(recipients)}'

    AuditLog.log_action(
        user=quotation.created_by,
        action_type=action_type,
        description=description,
        request=request,
        affected_model='Quotation',
        affected_object_id=str(quotation.id),
        quotation_id=str(quotation.id),
        quotation_number=quotation.quotation_number,
        email_recipients='; '.join(recipients),
        recipient_count=len(recipients)
    )


def _log_email_failed(
    quotation: Quotation,
    error_message: str,
    is_update: bool = False,
    request=None
) -> None:
    """
    Log failed email send attempt to audit trail.

    Args:
        quotation: Quotation instance
        error_message: Error message describing the failure
        is_update: True if this was an update email
        request: HTTP request object (optional)
    """
    action_type = 'quotation_email_failed'
    description = (
        f'Failed to send {"update" if is_update else "new"} quotation email '
        f'for {quotation.quotation_number}: {error_message}'
    )

    AuditLog.log_action(
        user=quotation.created_by,
        action_type=action_type,
        description=description,
        request=request,
        affected_model='Quotation',
        affected_object_id=str(quotation.id),
        quotation_id=str(quotation.id),
        quotation_number=quotation.quotation_number,
        error_message=error_message
    )


def _log_internal_notification_sent(
    quotation: Quotation,
    recipient,
    is_update: bool = False,
    request=None
) -> None:
    """
    Log successful internal notification email to audit trail.

    Args:
        quotation: Quotation instance
        recipient: User object who received the notification
        is_update: True if this was an update notification
        request: HTTP request object (optional)
    """
    action_type = 'quotation_internal_notification_sent'
    description = (
        f'Internal {"update" if is_update else "new quotation"} notification sent for '
        f'quotation {quotation.quotation_number} to {recipient.get_full_name()} ({recipient.email})'
    )

    AuditLog.log_action(
        user=quotation.created_by,
        action_type=action_type,
        description=description,
        request=request,
        affected_model='Quotation',
        affected_object_id=str(quotation.id),
        quotation_id=str(quotation.id),
        quotation_number=quotation.quotation_number,
        notification_recipient=recipient.email,
        recipient_name=recipient.get_full_name(),
        recipient_type='sales_rep' if recipient.is_sales_rep else 'account_manager'
    )


def validate_email_configuration() -> Tuple[bool, Optional[str]]:
    """
    Validate that email configuration is properly set up.

    Returns:
        Tuple of (is_configured: bool, error_message: Optional[str])

    Example:
        >>> is_configured, error = validate_email_configuration()
        >>> if not is_configured:
        >>>     print(f"Email not configured: {error}")
    """
    # Check if email backend is configured
    email_backend = getattr(settings, 'EMAIL_BACKEND', None)

    if not email_backend:
        return False, "EMAIL_BACKEND not configured in settings"

    # If using console backend, that's fine for development
    if email_backend == 'django.core.mail.backends.console.EmailBackend':
        return True, None

    # For SMTP backend, check required settings
    if email_backend == 'django.core.mail.backends.smtp.EmailBackend':
        required_settings = ['EMAIL_HOST', 'EMAIL_PORT']
        missing = [s for s in required_settings if not getattr(settings, s, None)]

        if missing:
            return False, f"Missing email settings: {', '.join(missing)}"

    return True, None
