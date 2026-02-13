from django import forms
from django.forms import inlineformset_factory
from .models import Store, StoreOpeningHours, StorePeriod


class StoreForm(forms.ModelForm):
    """Form for creating and editing stores."""

    class Meta:
        model = Store
        fields = [
            'name', 'phone', 'email', 'address_line1', 'address_line2',
            'suburb', 'city', 'postal_code', 'latitude', 'longitude',
            'schools', 'description', 'is_active', 'display_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter store name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+64XXXXXXXXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'store@theuniformshoppe.co.nz'
            }),
            'address_line1': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Street address'
            }),
            'address_line2': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Additional address (optional)'
            }),
            'suburb': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Suburb'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City'
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Postal code (optional)'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '-36.9165',
                'step': '0.000001'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '174.8989',
                'step': '0.000001'
            }),
            'schools': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '10'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional store information (optional)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make schools widget better for selection
        from schools.models import School
        self.fields['schools'].queryset = School.objects.filter(
            status='Open'
        ).order_by('org_name')


class StoreOpeningHoursForm(forms.ModelForm):
    """Form for store opening hours."""

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


# Create an inline formset for opening hours
StoreOpeningHoursFormSet = inlineformset_factory(
    Store,
    StoreOpeningHours,
    form=StoreOpeningHoursForm,
    extra=7,  # 7 days of the week
    max_num=7,
    can_delete=False,
    validate_max=True
)


class StorePeriodAssignmentForm(forms.Form):
    """Form for assigning/unassigning periods to a specific store."""

    periods = forms.ModelMultipleChoiceField(
        queryset=StorePeriod.objects.all().order_by('-start_date'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Assign Periods to this Store'
    )

    def __init__(self, *args, store=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.store = store

        if store:
            # Pre-select periods already assigned to this store
            self.fields['periods'].initial = store.periods.all()
