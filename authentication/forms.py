"""
Forms for authentication app
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import User, SalesRepSchoolAssignment, SalesRepClubAssignment


class EmailAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form that uses email instead of username
    """
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autofocus': True
        })
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })
    )

    error_messages = {
        'invalid_login': 'Please enter a correct email and password. Note that both fields may be case-sensitive.',
        'inactive': 'This account is inactive.',
    }


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with email as primary identifier"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter email address'
        })
    )

    class Meta:
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'user_type')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username (optional - auto-generated from email)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make username optional - it will be auto-generated from email if not provided
        self.fields['username'].required = False
        self.fields['username'].help_text = 'Optional - will be auto-generated from email if not provided'

    def clean_email(self):
        """Validate email is unique (case-insensitive)"""
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError('A user with this email address already exists.')
        return email

    def clean_username(self):
        """Auto-generate username from email if not provided"""
        username = self.cleaned_data.get('username')
        email = self.cleaned_data.get('email')

        if not username and email:
            # Generate username from email (part before @)
            base_username = email.split('@')[0]
            username = base_username

            # Ensure username is unique
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

        return username


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form with email as primary identifier"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter email address'
        })
    )

    class Meta:
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'user_type', 'is_active')

    def clean_email(self):
        """Validate email is unique (case-insensitive) for current user"""
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            existing = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError('A user with this email address already exists.')
        return email


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
            'email', 'username', 'first_name', 'last_name',
            'user_type', 'employee_id', 'phone',
            'street_address', 'suburb', 'city', 'postcode',
            'department', 'hire_date', 'is_active', 'is_staff', 'is_active_sales_rep'
        ]
        # Note: email_verified is referenced in template but not in model
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address (used for login)',
                'autofocus': True
            }),
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username (optional - auto-generated)'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
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
            'street_address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter street number and name'
            }),
            'suburb': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter suburb'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter town/city'
            }),
            'postcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter postcode'
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
            # Make username optional for new users (auto-generated from email)
            self.fields['username'].required = False
        else:
            # For editing, username should still be present but not required
            self.fields['username'].required = False

        # Add help text
        self.fields['email'].help_text = "Email address - used for login and as username (required)"
        self.fields['username'].help_text = "Will be automatically set to email address"
        self.fields['user_type'].help_text = "Select the user's role in the system"

    def clean_email(self):
        """Validate email is unique (case-insensitive)"""
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            existing = User.objects.filter(email__iexact=email)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError('A user with this email address already exists.')
        return email

    def clean_username(self):
        """Set username to email address"""
        email = self.cleaned_data.get('email')

        # Username is always set to email
        if email:
            username = email
        else:
            # Fallback for edge cases
            username = self.cleaned_data.get('username') or ''

        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        user_type = cleaned_data.get('user_type')
        employee_id = cleaned_data.get('employee_id')
        email = cleaned_data.get('email')

        # Email is required
        if not email:
            raise ValidationError({'email': 'Email address is required'})

        # Password validation
        if password1 or password2:
            # Check if passwords match
            if password1 != password2:
                raise ValidationError({
                    'password2': "Passwords don't match. Please ensure both password fields contain the same value."
                })

            # Validate password strength (only if password is provided)
            if password1:
                try:
                    validate_password(password1, self.instance)
                except ValidationError as e:
                    raise ValidationError({'password1': e.messages})

        # For new users, password is required
        if not self.is_edit and not password1:
            raise ValidationError({
                'password1': 'Password is required for new users.'
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

        # Auto-set is_active_sales_rep for sales reps and account managers
        # This is required by the middleware (authentication/middleware.py lines 52-54)
        # which logs out sales_rep/account_manager users if is_active_sales_rep is False
        if user.user_type in ['sales_rep', 'account_manager']:
            user.is_active_sales_rep = True

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
    """Form for creating sales rep and account manager assignments"""

    class Meta:
        model = SalesRepSchoolAssignment
        fields = [
            'sales_rep', 'tus_school', 'wholesale_school', 'territory_name',
            'priority_level', 'notes'
        ]
        widgets = {
            'sales_rep': forms.Select(attrs={'class': 'form-control'}),
            'tus_school': forms.Select(attrs={'class': 'form-control'}),
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

        # Filter sales_rep to only show sales representatives and account managers
        self.fields['sales_rep'].queryset = User.objects.filter(
            user_type__in=['sales_rep', 'account_manager'],
            is_active=True
        )

        # Add help text
        self.fields['tus_school'].help_text = "Select TUS school (leave wholesale school blank)"
        self.fields['wholesale_school'].help_text = "Select wholesale school (leave TUS school blank)"

        # Make fields optional for the clean method to handle validation
        self.fields['tus_school'].required = False
        self.fields['wholesale_school'].required = False

    def clean(self):
        cleaned_data = super().clean()
        tus_school = cleaned_data.get('tus_school')
        wholesale_school = cleaned_data.get('wholesale_school')

        # Ensure exactly one school type is selected
        if not tus_school and not wholesale_school:
            raise ValidationError(
                "Please select either a TUS school or wholesale school."
            )

        if tus_school and wholesale_school:
            raise ValidationError(
                "Please select only one type of school (TUS OR wholesale)."
            )

        return cleaned_data


class ClubAssignmentForm(forms.ModelForm):
    """Form for creating club assignments for sales reps and account managers"""

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

        # Filter sales_rep to only show sales representatives and account managers
        self.fields['sales_rep'].queryset = User.objects.filter(
            user_type__in=['sales_rep', 'account_manager'],
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


class CustomerRegistrationForm(forms.ModelForm):
    """Form for customer self-registration"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autofocus': True
        }),
        help_text='This will be your username for logging in'
    )

    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )

    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )

    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your phone number (optional)'
        })
    )

    # Structured address fields
    street_address = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter street number and name'
        }),
        help_text='Street number and name'
    )

    suburb = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter suburb'
        }),
        help_text='Suburb'
    )

    city = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter town/city'
        }),
        help_text='Town or city'
    )

    postcode = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter postcode'
        }),
        help_text='Postcode (required)'
    )

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a password'
        }),
        help_text='Password must be at least 8 characters long'
    )

    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password'
        })
    )

    terms_accepted = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='I agree to the Terms and Conditions',
        error_messages={'required': 'You must accept the terms and conditions to register'}
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'street_address', 'suburb', 'city', 'postcode']

    def clean_email(self):
        """Validate email is unique (case-insensitive)"""
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError('An account with this email address already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        # Check if passwords match
        if password1 and password2:
            if password1 != password2:
                raise ValidationError({
                    'password2': "Passwords don't match. Please ensure both password fields are the same."
                })

            # Validate password strength
            try:
                validate_password(password1)
            except ValidationError as e:
                raise ValidationError({'password1': e.messages})

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)

        # Set password
        password = self.cleaned_data.get('password1')
        user.set_password(password)

        # Set user type to customer
        user.user_type = 'customer'

        # Set username to email
        user.username = self.cleaned_data.get('email')

        # Set user as active
        user.is_active = True

        if commit:
            user.save()

        return user