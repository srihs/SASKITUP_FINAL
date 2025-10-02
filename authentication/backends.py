"""
Custom authentication backend for email-based login
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using their email address
    instead of username. Also supports case-insensitive email matching.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate a user based on email address and password.

        Args:
            request: The HttpRequest object
            username: The email address (despite the parameter name)
            password: The user's password

        Returns:
            User object if authentication successful, None otherwise
        """
        if username is None or password is None:
            return None

        try:
            # Try to find user by email (case-insensitive)
            # Also support username for backward compatibility during transition
            user = User.objects.get(
                Q(email__iexact=username) | Q(username=username)
            )
        except User.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # If multiple users exist with the same email (shouldn't happen with unique constraint)
            # try exact match first, then case-insensitive
            user = User.objects.filter(
                Q(email__iexact=username) | Q(username=username)
            ).first()
            if not user:
                return None

        # Check password and if user is active
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None

    def get_user(self, user_id):
        """
        Get a user by their ID.

        Args:
            user_id: The user's primary key

        Returns:
            User object if found, None otherwise
        """
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

        return user if self.user_can_authenticate(user) else None
