#!/usr/bin/env python
"""
MySQL Demo User Setup Script
Creates demo users for testing the authentication system in MySQL
"""

import os
import sys
import django
from django.db import connection

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
sys.path.append('/Users/sas/Repos/SASKITUP')

try:
    django.setup()
except Exception as e:
    print(f"Django setup error: {e}")
    exit(1)

def setup_mysql_demo_users():
    """Create demo users in MySQL database"""

    print("🔧 SETTING UP MYSQL DEMO USERS")
    print("=" * 40)

    try:
        from authentication.models import User
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone

        # Check if authentication_user table exists and create if needed
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authentication_user (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    password VARCHAR(128) NOT NULL,
                    last_login DATETIME(6) NULL,
                    is_superuser TINYINT(1) NOT NULL DEFAULT 0,
                    username VARCHAR(150) NOT NULL UNIQUE,
                    first_name VARCHAR(150) NOT NULL DEFAULT '',
                    last_name VARCHAR(150) NOT NULL DEFAULT '',
                    email VARCHAR(254) NOT NULL DEFAULT '',
                    is_staff TINYINT(1) NOT NULL DEFAULT 0,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    date_joined DATETIME(6) NOT NULL,
                    user_type VARCHAR(20) NOT NULL DEFAULT 'sales_rep',
                    phone VARCHAR(20) NOT NULL DEFAULT '',
                    department VARCHAR(100) NOT NULL DEFAULT '',
                    hire_date DATE NULL,
                    employee_id VARCHAR(50) NULL UNIQUE,
                    is_active_sales_rep TINYINT(1) NOT NULL DEFAULT 1,
                    last_login_ip VARCHAR(39) NULL,
                    created_at DATETIME(6) NOT NULL,
                    updated_at DATETIME(6) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Ensured authentication_user table exists")

        # Check if users already exist
        if User.objects.exists():
            print("✅ Users already exist in database")
            users = User.objects.all()
            for user in users:
                print(f"   - {user.username} ({user.get_user_type_display()})")
            return True

        print("Creating demo users...")

        now = timezone.now()

        # Create Admin user
        admin_user = User.objects.create(
            username='admin',
            email='admin@saskitup.com',
            password=make_password('admin123'),
            user_type='admin',
            first_name='Admin',
            last_name='User',
            is_staff=True,
            is_superuser=True,
            employee_id='EMP001',
            department='Administration',
            date_joined=now,
            created_at=now,
            updated_at=now
        )
        print(f"✅ Created admin user: {admin_user}")

        # Create Sales Rep user
        sales_rep = User.objects.create(
            username='salesrep1',
            email='salesrep1@saskitup.com',
            password=make_password('salesrep123'),
            user_type='sales_rep',
            first_name='Sales',
            last_name='Representative',
            employee_id='EMP002',
            department='Sales',
            phone='+64-21-123-4567',
            date_joined=now,
            created_at=now,
            updated_at=now
        )
        print(f"✅ Created sales rep: {sales_rep}")

        # Create Customer user
        customer_user = User.objects.create(
            username='customer1',
            email='customer1@saskitup.com',
            password=make_password('customer123'),
            user_type='customer',
            first_name='John',
            last_name='Customer',
            phone='+64-21-987-6543',
            date_joined=now,
            created_at=now,
            updated_at=now
        )
        print(f"✅ Created customer: {customer_user}")

        print("\n🎉 MySQL demo users created successfully!")
        print("\nLogin credentials:")
        print("Admin: username=admin, password=admin123")
        print("Sales Rep: username=salesrep1, password=salesrep123")
        print("Customer: username=customer1, password=customer123")

        return True

    except Exception as e:
        print(f"❌ Error creating users: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    setup_mysql_demo_users()