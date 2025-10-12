"""
Forms for quotations app.
"""

from django import forms
from decimal import Decimal
from .models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    """
    Form for managing site-wide settings.
    Includes GST percentage and quotation validity days.
    """

    class Meta:
        model = SiteSettings
        fields = ['gst_percentage', 'quotation_validity_days']
        widgets = {
            'gst_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '15.00',
                'min': '0',
                'max': '100',
                'step': '0.01',
            }),
            'quotation_validity_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '30',
                'min': '1',
                'max': '365',
            }),
        }
        labels = {
            'gst_percentage': 'GST Percentage (%)',
            'quotation_validity_days': 'Quotation Validity (days)',
        }
        help_texts = {
            'gst_percentage': 'GST/VAT percentage applied to all new quotations (0-100)',
            'quotation_validity_days': 'Default number of days a quotation remains valid (1-365)',
        }

    def clean_gst_percentage(self):
        """Validate GST percentage is within range"""
        value = self.cleaned_data.get('gst_percentage')
        if value is not None:
            if value < Decimal('0.00') or value > Decimal('100.00'):
                raise forms.ValidationError('GST percentage must be between 0 and 100.')
        return value

    def clean_quotation_validity_days(self):
        """Validate quotation validity days is within range"""
        value = self.cleaned_data.get('quotation_validity_days')
        if value is not None:
            if value < 1 or value > 365:
                raise forms.ValidationError('Quotation validity must be between 1 and 365 days.')
        return value
