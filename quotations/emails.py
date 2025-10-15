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
from typing import List, Optional, Tuple
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction
from email.mime.image import MIMEImage
from io import BytesIO

from .models import Quotation
from authentication.models import AuditLog

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not installed. PDF generation will be disabled.")


def generate_quotation_pdf(quotation: Quotation) -> Optional[bytes]:
    """
    Generate professional PDF quotation using reportlab.

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
    if not REPORTLAB_AVAILABLE:
        logger.error("reportlab not available. Cannot generate PDF.")
        return None

    try:
        from .models import SiteSettings

        # Create PDF buffer
        buffer = BytesIO()

        # Create document with margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Container for PDF elements
        elements = []

        # Get styles
        styles = getSampleStyleSheet()

        # Define custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=6,
            spaceBefore=12
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333')
        )

        small_style = ParagraphStyle(
            'CustomSmall',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#666666')
        )

        # Add company logo if available
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'sas-logo.png')
        if os.path.exists(logo_path):
            try:
                logo = Image(logo_path, width=2*inch, height=0.75*inch)
                elements.append(logo)
                elements.append(Spacer(1, 0.25*inch))
            except Exception as e:
                logger.warning(f"Could not add logo to PDF: {e}")

        # Company header
        company_data = [
            ['SAS CORPORATE'],
            ['521 ROSEBANK ROAD, AVONDALE, AUCKLAND, NEW ZEALAND'],
            ['Email: CUSTOMERSERVICES@SAS.CO.NZ | Phone: 09 2998412']
        ]

        company_table = Table(company_data, colWidths=[6.5*inch])
        company_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, 0), 12),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(company_table)
        elements.append(Spacer(1, 0.3*inch))

        # Quotation title
        elements.append(Paragraph(f"QUOTATION", title_style))
        elements.append(Spacer(1, 0.2*inch))

        # Quotation details and customer info side by side
        quotation_info = [
            ['<b>Quotation Number:</b>', quotation.quotation_number],
            ['<b>Date:</b>', quotation.created_at.strftime('%d %B %Y')],
            ['<b>Valid Until:</b>', quotation.expires_at.strftime('%d %B %Y') if quotation.expires_at else 'N/A'],
            ['<b>Status:</b>', quotation.get_status_display()],
        ]

        customer_info = [
            ['<b>Customer Information</b>', ''],
            ['<b>Institution:</b>', quotation.institution_name if quotation.institution else 'N/A'],
            ['<b>Type:</b>', quotation.institution_type if quotation.institution else 'N/A'],
            ['<b>Recipient:</b>', quotation.recipient_name or 'N/A'],
        ]

        # Create two-column layout for quotation and customer info
        info_data = []
        for i in range(max(len(quotation_info), len(customer_info))):
            row = []
            if i < len(quotation_info):
                row.extend(quotation_info[i])
            else:
                row.extend(['', ''])

            row.append('')  # Spacer column

            if i < len(customer_info):
                row.extend(customer_info[i])
            else:
                row.extend(['', ''])

            info_data.append(row)

        info_table = Table(info_data, colWidths=[1.5*inch, 1.5*inch, 0.25*inch, 1.5*inch, 1.5*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.3*inch))

        # Items table
        elements.append(Paragraph("ITEMS", heading_style))
        elements.append(Spacer(1, 0.1*inch))

        # Get quotation items
        items = quotation.items.all().select_related('product_content_type').order_by('sort_order', 'created_at')

        # Table header
        table_data = [['No.', 'Product Name', 'SKU', 'Size', 'Unit Price', 'Qty', 'Total']]

        # Add items
        for idx, item in enumerate(items, 1):
            # Get size from variations
            size = item.variations.get('size', 'N/A') if item.variations else 'N/A'

            table_data.append([
                str(idx),
                item.product_name,
                item.product_sku or 'N/A',
                size,
                f"${item.unit_price:,.2f}",
                str(item.quantity),
                f"${item.line_total:,.2f}"
            ])

        # Create items table
        items_table = Table(
            table_data,
            colWidths=[0.4*inch, 2.2*inch, 1*inch, 0.8*inch, 0.9*inch, 0.5*inch, 1*inch]
        )

        items_table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # No. column
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Product name
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),    # SKU
            ('ALIGN', (3, 1), (3, -1), 'CENTER'),  # Size
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),  # Price columns
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),

            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))

        elements.append(items_table)
        elements.append(Spacer(1, 0.3*inch))

        # Totals section
        subtotal = quotation.subtotal
        discount = quotation.discount_amount
        if quotation.discount_percentage:
            discount = (subtotal * quotation.discount_percentage / 100)

        gst = quotation.tax_amount
        total = quotation.total

        totals_data = [
            ['Subtotal:', f"${subtotal:,.2f}"],
        ]

        if discount > 0:
            totals_data.append([
                f'Discount ({quotation.discount_percentage}%):' if quotation.discount_percentage else 'Discount:',
                f"-${discount:,.2f}"
            ])

        totals_data.extend([
            [f'GST ({quotation.tax_percentage}%):', f"${gst:,.2f}"],
            ['<b>Total:</b>', f"<b>${total:,.2f}</b>"],
        ])

        totals_table = Table(totals_data, colWidths=[5*inch, 1.5*inch])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#333333')),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#333333')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        elements.append(totals_table)
        elements.append(Spacer(1, 0.3*inch))

        # Terms and conditions
        if quotation.terms_and_conditions:
            elements.append(Paragraph("TERMS AND CONDITIONS", heading_style))
            elements.append(Spacer(1, 0.1*inch))

            # Split terms into paragraphs
            terms_paragraphs = quotation.terms_and_conditions.split('\n')
            for para in terms_paragraphs:
                if para.strip():
                    elements.append(Paragraph(para.strip(), normal_style))
                    elements.append(Spacer(1, 0.05*inch))

            elements.append(Spacer(1, 0.2*inch))

        # Customer notes
        if quotation.customer_notes:
            elements.append(Paragraph("NOTES", heading_style))
            elements.append(Spacer(1, 0.1*inch))
            elements.append(Paragraph(quotation.customer_notes, normal_style))
            elements.append(Spacer(1, 0.2*inch))

        # Footer
        validity_days = getattr(SiteSettings.objects.first(), 'quotation_validity_days', 30)
        footer_text = f"This quotation is valid for {validity_days} days from the date of issue. Thank you for your business!"
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph(footer_text, small_style))

        # Build PDF
        doc.build(elements)

        # Get PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()

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
    Send quotation email to all recipients.

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

        # Prepare email subject
        action_text = "Updated" if is_update else "New"
        subject = f"{action_text} Quotation {quotation.quotation_number}"

        # Add institution name if available
        if quotation.institution:
            subject += f" - {quotation.institution_name}"

        # Get quotation items
        items = quotation.items.select_related(
            'product_content_type'
        ).all()

        # Context for email templates
        email_context = {
            'quotation': quotation,
            'items': items,
            'is_update': is_update,
            'institution_name': quotation.institution_name,
            'quotation_url': _get_quotation_url(quotation),
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
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

        # Create email with primary recipient
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=_get_from_email(),
            to=[recipients[0]],  # Primary recipient
            cc=recipients[1:] if len(recipients) > 1 else [],  # Additional as CC
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

        # Send email
        # Django automatically uses settings.EMAIL_SSL_CONTEXT if defined
        email.send(fail_silently=False)

        # Log successful email send
        _log_email_sent(quotation, recipients, is_update, request)

        logger.info(
            f"Quotation {quotation.quotation_number} email sent to "
            f"{len(recipients)} recipient(s): {', '.join(recipients)}"
        )

        return True, None

    except Exception as e:
        error_msg = f"Failed to send quotation {quotation.quotation_number} email: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Log failed email attempt
        _log_email_failed(quotation, str(e), is_update, request)

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
