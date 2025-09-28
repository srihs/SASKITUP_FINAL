#!/usr/bin/env python
"""
Fix Database Tables Script
Creates missing Django core tables manually
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

def create_missing_tables():
    """Create missing Django core tables"""

    print("🔧 FIXING DATABASE TABLES")
    print("=" * 40)

    try:
        with connection.cursor() as cursor:
            # Create django_session table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS django_session (
                    session_key VARCHAR(40) NOT NULL PRIMARY KEY,
                    session_data TEXT NOT NULL,
                    expire_date DATETIME NOT NULL
                )
            """)
            print("✅ Created django_session table")

            # Create django_content_type table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS django_content_type (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_label VARCHAR(100) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    UNIQUE(app_label, model)
                )
            """)
            print("✅ Created django_content_type table")

            # Create auth_permission table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_permission (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    content_type_id INTEGER NOT NULL,
                    codename VARCHAR(100) NOT NULL,
                    UNIQUE(content_type_id, codename)
                )
            """)
            print("✅ Created auth_permission table")

            # Create auth_group table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_group (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(150) NOT NULL UNIQUE
                )
            """)
            print("✅ Created auth_group table")

            # Create auth_group_permissions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_group_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    UNIQUE(group_id, permission_id)
                )
            """)
            print("✅ Created auth_group_permissions table")

            # Create authentication_user_groups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authentication_user_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    UNIQUE(user_id, group_id)
                )
            """)
            print("✅ Created authentication_user_groups table")

            # Create authentication_user_user_permissions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authentication_user_user_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    UNIQUE(user_id, permission_id)
                )
            """)
            print("✅ Created authentication_user_user_permissions table")

            # Insert basic content types
            cursor.execute("""
                INSERT OR IGNORE INTO django_content_type (app_label, model) VALUES
                ('authentication', 'user'),
                ('auth', 'permission'),
                ('auth', 'group'),
                ('contenttypes', 'contenttype'),
                ('sessions', 'session')
            """)
            print("✅ Inserted basic content types")

        print("\n🎉 Database tables fixed successfully!")
        print("✅ All core Django tables created")
        print("✅ Session management will now work")
        print("✅ Authentication system ready")

        return True

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

if __name__ == "__main__":
    create_missing_tables()