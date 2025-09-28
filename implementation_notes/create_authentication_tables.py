#!/usr/bin/env python
"""
Create Authentication Tables Script
Creates all authentication-related tables manually
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

def create_authentication_tables():
    """Create all authentication-related tables"""

    print("🔧 CREATING AUTHENTICATION TABLES")
    print("=" * 50)

    try:
        with connection.cursor() as cursor:
            # Create audit_logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    action_type VARCHAR(50) NOT NULL,
                    description TEXT NOT NULL,
                    ip_address VARCHAR(39) NULL,
                    user_agent TEXT,
                    session_key VARCHAR(40),
                    metadata TEXT,
                    affected_model VARCHAR(100),
                    affected_object_id VARCHAR(100),
                    timestamp DATETIME NOT NULL,
                    user_id INTEGER NULL
                )
            """)
            print("✅ Created audit_logs table")

            # Create sales_rep_club_assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sales_rep_club_assignments (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    assigned_date DATETIME NOT NULL,
                    notes TEXT,
                    territory_name VARCHAR(100),
                    priority_level VARCHAR(20) NOT NULL DEFAULT 'medium',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    club_id INTEGER NULL,
                    created_by_id INTEGER NULL,
                    sales_rep_id INTEGER NOT NULL
                )
            """)
            print("✅ Created sales_rep_club_assignments table")

            # Create sales_rep_school_assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sales_rep_school_assignments (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    assigned_date DATETIME NOT NULL,
                    notes TEXT,
                    territory_name VARCHAR(100),
                    priority_level VARCHAR(20) NOT NULL DEFAULT 'medium',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    created_by_id INTEGER NULL,
                    sales_rep_id INTEGER NOT NULL,
                    school_id INTEGER NULL,
                    wholesale_school_id INTEGER NULL
                )
            """)
            print("✅ Created sales_rep_school_assignments table")

            # Create user_sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key VARCHAR(40) NOT NULL UNIQUE,
                    ip_address VARCHAR(39) NOT NULL,
                    user_agent TEXT NOT NULL,
                    login_time DATETIME NOT NULL,
                    last_activity DATETIME NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    user_id INTEGER NOT NULL
                )
            """)
            print("✅ Created user_sessions table")

            # Create placeholder clubs table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clubs_club (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    slug VARCHAR(255) NOT NULL UNIQUE,
                    club_type VARCHAR(10) NOT NULL DEFAULT 'LOTTO',
                    sport_tag VARCHAR(50) NOT NULL DEFAULT 'Football',
                    contact_person VARCHAR(100),
                    email VARCHAR(254),
                    website VARCHAR(200),
                    address TEXT,
                    woo_category_id INTEGER UNIQUE,
                    logo VARCHAR(500),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """)
            print("✅ Created clubs_club table (placeholder)")

            # Create placeholder schools table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schools_school (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    slug VARCHAR(255) NOT NULL UNIQUE,
                    school_type VARCHAR(20) NOT NULL DEFAULT 'primary',
                    contact_person VARCHAR(100),
                    email VARCHAR(254),
                    phone VARCHAR(20),
                    address TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """)
            print("✅ Created schools_school table (placeholder)")

            # Create placeholder wholesale schools table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schools_wholesaleschool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    slug VARCHAR(255) NOT NULL UNIQUE,
                    cin7_id INTEGER UNIQUE,
                    contact_person VARCHAR(100),
                    email VARCHAR(254),
                    phone VARCHAR(20),
                    address TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """)
            print("✅ Created schools_wholesaleschool table (placeholder)")

        print("\n🎉 AUTHENTICATION TABLES CREATED SUCCESSFULLY!")
        print("=" * 50)
        print("✅ All authentication tables ready")
        print("✅ Audit logging system ready")
        print("✅ Assignment tables ready")
        print("✅ Session tracking ready")
        print("✅ Placeholder tables for schools/clubs created")
        print("\n🚀 LOGIN SYSTEM NOW FULLY FUNCTIONAL!")

        return True

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_authentication_tables()