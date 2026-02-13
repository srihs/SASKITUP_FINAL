from django import forms
from django.forms import inlineformset_factory
from .models import StorePeriod, StoreOpeningHours, Store


class StorePeriodForm(forms.ModelForm):
    """Form for creating and editing store periods."""

    class Meta:
        model = StorePeriod
        fields = ['name', 'period_type', 'stores', 'start_date', 'end_date', 'priority', 'is_active', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., "Term 1 2024" or "Christmas Period 2024"'
            }),
            'period_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'stores': forms.CheckboxSelectMultiple(),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description or notes about this period'
            })
        }

    def __init__(self, *args, **kwargs):
        # Remove store parameter for backward compatibility
        kwargs.pop('store', None)
        super().__init__(*args, **kwargs)
        # Make stores field optional (not required)
        self.fields['stores'].required = False


class PeriodOpeningHoursForm(forms.ModelForm):
    """Form for period-specific opening hours."""

    class Meta:
        model = StoreOpeningHours
        fields = ['day_of_week', 'opening_time', 'closing_time', 'is_closed', 'notes']
        widgets = {
            'day_of_week': forms.Select(attrs={
                'class': 'form-control',
                'readonly': 'readonly'
            }),
            'opening_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'closing_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'is_closed': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., "By appointment only"'
            })
        }


# Create an inline formset for period opening hours
PeriodOpeningHoursFormSet = inlineformset_factory(
    StorePeriod,
    StoreOpeningHours,
    form=PeriodOpeningHoursForm,
    extra=7,
    max_num=7,
    can_delete=False,
    validate_max=True,
    fk_name='period'
)
