"""
Forms for authentication app
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import User, SalesRepSchoolAssignment, SalesRepClubAssignment


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form"""
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'user_type')


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form"""
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'user_type', 'is_active')


class UserForm(forms.ModelForm):
    """Enhanced form for creating and editing users"""

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        }),
        required=False,
        help_text='Leave blank to keep current password when editing'
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        }),
        required=False
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'user_type', 'employee_id', 'phone', 'department',
            'hire_date', 'is_active', 'is_staff', 'is_active_sales_rep'
        ]
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'user_type': forms.Select(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter employee ID'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'department': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter department'
            }),
            'hire_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active_sales_rep': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.is_edit = kwargs.pop('is_edit', False)
        super().__init__(*args, **kwargs)

        # Make password required for new users
        if not self.is_edit:
            self.fields['password1'].required = True
            self.fields['password2'].required = True

        # Add help text
        self.fields['user_type'].help_text = "Select the user's role in the system"
        self.fields['employee_id'].help_text = "Required for sales representatives"
        self.fields['is_active_sales_rep'].help_text = "Whether this sales rep is actively working assignments"

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        user_type = cleaned_data.get('user_type')
        employee_id = cleaned_data.get('employee_id')

        # Password validation
        if password1 or password2:
            if password1 != password2:
                raise ValidationError("Passwords don't match")

            if password1:
                try:
                    validate_password(password1, self.instance)
                except ValidationError as e:
                    raise ValidationError({'password1': e.messages})

        # Sales rep specific validation
        if user_type == 'sales_rep' and not employee_id:
            raise ValidationError({
                'employee_id': 'Sales representatives must have an employee ID'
            })

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')

        if password:
            user.set_password(password)

        # Auto-set staff status for admins
        if user.user_type == 'admin':
            user.is_staff = True

        if commit:
            user.save()
        return user


class UserSearchForm(forms.Form):
    """Form for searching and filtering users"""

    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by username, name, email, or employee ID'
        })
    )

    user_type = forms.ChoiceField(
        choices=[('', 'All Types')] + User.USER_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    is_active = forms.ChoiceField(
        choices=[
            ('', 'All Statuses'),
            ('true', 'Active'),
            ('false', 'Inactive')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    department = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by department'
        })
    )


class SalesRepAssignmentForm(forms.ModelForm):
    """Form for creating sales rep assignments"""

    class Meta:
        model = SalesRepSchoolAssignment
        fields = [
            'sales_rep', 'school', 'wholesale_school', 'territory_name',
            'priority_level', 'notes'
        ]
        widgets = {
            'sales_rep': forms.Select(attrs={'class': 'form-control'}),
            'school': forms.Select(attrs={'class': 'form-control'}),
            'wholesale_school': forms.Select(attrs={'class': 'form-control'}),
            'territory_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter territory name'
            }),
            'priority_level': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter notes about this assignment'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter sales_rep to only show sales representatives
        self.fields['sales_rep'].queryset = User.objects.filter(
            user_type='sales_rep',
            is_active=True
        )

        # Add help text
        self.fields['school'].help_text = "Select regular school (leave wholesale school blank)"
        self.fields['wholesale_school'].help_text = "Select wholesale school (leave regular school blank)"

        # Make fields optional for the clean method to handle validation
        self.fields['school'].required = False
        self.fields['wholesale_school'].required = False

    def clean(self):
        cleaned_data = super().clean()
        school = cleaned_data.get('school')
        wholesale_school = cleaned_data.get('wholesale_school')

        # Ensure exactly one school type is selected
        if not school and not wholesale_school:
            raise ValidationError(
                "Please select either a regular school or wholesale school."
            )

        if school and wholesale_school:
            raise ValidationError(
                "Please select only one type of school (regular OR wholesale)."
            )

        return cleaned_data


class ClubAssignmentForm(forms.ModelForm):
    """Form for creating club assignments"""

    class Meta:
        model = SalesRepClubAssignment
        fields = [
            'sales_rep', 'territory_name',
            'priority_level', 'notes'
        ]
        widgets = {
            'sales_rep': forms.Select(attrs={'class': 'form-control'}),
            'territory_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter territory name'
            }),
            'priority_level': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter notes about this assignment'
            }),
        }

    # TODO: Add custom club selection field for GenericForeignKey

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter sales_rep to only show sales representatives
        self.fields['sales_rep'].queryset = User.objects.filter(
            user_type='sales_rep',
            is_active=True
        )


class BulkUserActionForm(forms.Form):
    """Form for bulk user actions"""

    ACTION_CHOICES = [
        ('activate', 'Activate Selected Users'),
        ('deactivate', 'Deactivate Selected Users'),
        ('delete', 'Delete Selected Users'),
        ('change_type', 'Change User Type'),
        ('export', 'Export Selected Users'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    user_ids = forms.CharField(
        widget=forms.HiddenInput()
    )

    # Optional fields for specific actions
    new_user_type = forms.ChoiceField(
        choices=User.USER_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def clean_user_ids(self):
        user_ids = self.cleaned_data.get('user_ids', '')
        if not user_ids:
            raise ValidationError("No users selected")

        try:
            ids = [int(id_str) for id_str in user_ids.split(',')]
            return ids
        except ValueError:
            raise ValidationError("Invalid user IDs")

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        new_user_type = cleaned_data.get('new_user_type')

        if action == 'change_type' and not new_user_type:
            raise ValidationError({
                'new_user_type': 'User type is required for this action'
            })

        return cleaned_data


class UserProfileForm(forms.ModelForm):
    """Form for users to edit their own profile"""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'department': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter department'
            }),
        }


class PasswordChangeForm(forms.Form):
    """Form for users to change their password"""

    current_password = forms.CharField(
        label='Current Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter current password'
        })
    )

    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        })
    )

    new_password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError("Current password is incorrect")
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')

        if new_password1 and new_password2:
            if new_password1 != new_password2:
                raise ValidationError("New passwords don't match")

            try:
                validate_password(new_password1, self.user)
            except ValidationError as e:
                raise ValidationError({'new_password1': e.messages})

        return cleaned_data

    def save(self):
        password = self.cleaned_data.get('new_password1')
        self.user.set_password(password)
        self.user.save()
        return self.user