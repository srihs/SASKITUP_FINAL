#!/usr/bin/env python
"""
Helper script to create a superuser for SASKITUP Django application.
This script handles the postcode requirement automatically.

Usage:
    python manage.py shell < scripts/create_superuser.py

Or in Docker:
    docker-compose exec web python manage.py shell < scripts/create_superuser.py
"""

from django.contrib.auth import get_user_model
import getpass
import sys

User = get_user_model()

print("=" * 70)
print("SASKITUP Superuser Creation")
print("=" * 70)

# Get user input
email = input("\nEmail address: ").strip()
if not email:
    print("Error: Email is required")
    sys.exit(1)

# Validate email format
if '@' not in email:
    print("Error: Invalid email format")
    sys.exit(1)

# Check if user already exists
if User.objects.filter(email__iexact=email).exists():
    print(f"Error: User with email '{email}' already exists")
    sys.exit(1)

# Get password
password = getpass.getpass("Password: ")
password2 = getpass.getpass("Password (again): ")

if password != password2:
    print("Error: Passwords don't match")
    sys.exit(1)

if not password:
    print("Error: Password cannot be blank")
    sys.exit(1)

# Get postcode (with default)
postcode = input("Postcode [0000]: ").strip()
if not postcode:
    postcode = "0000"

# Optional: Get first and last name
first_name = input("First name [optional]: ").strip()
last_name = input("Last name [optional]: ").strip()

# Create superuser
try:
    user = User.objects.create_superuser(
        username=email,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name
    )

    # Set required fields
    user.postcode = postcode
    user.user_type = 'admin'
    user.is_staff = True
    user.is_superuser = True
    user.save()

    print("\n" + "=" * 70)
    print("✅ Superuser created successfully!")
    print("=" * 70)
    print(f"Email: {user.email}")
    print(f"Username: {user.username}")
    print(f"User Type: {user.get_user_type_display()}")
    print(f"Superuser: {user.is_superuser}")
    print(f"Staff: {user.is_staff}")
    print("=" * 70)
    print(f"\nYou can now login at: http://your-server:8000/admin/")
    print(f"Login with: {user.email}")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ Error creating superuser: {e}")
    sys.exit(1)
