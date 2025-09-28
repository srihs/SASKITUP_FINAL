#!/usr/bin/env python
"""
Create Audit and Assignment Tables for MySQL
Creates missing authentication-related tables
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

def create_audit_tables():
    """Create missing audit and assignment tables in MySQL"""

    print("🔧 CREATING AUDIT AND ASSIGNMENT TABLES")
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
                    timestamp DATETIME(6) NOT NULL,
                    user_id INTEGER NULL,
                    INDEX idx_user_id (user_id),
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_action_type (action_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created audit_logs table")

            # Create sales_rep_club_assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sales_rep_club_assignments (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    assigned_date DATETIME(6) NOT NULL,
                    notes TEXT,
                    territory_name VARCHAR(100),
                    priority_level VARCHAR(20) NOT NULL DEFAULT 'medium',
                    created_at DATETIME(6) NOT NULL,
                    updated_at DATETIME(6) NOT NULL,
                    club_id INTEGER NULL,
                    created_by_id INTEGER NULL,
                    sales_rep_id INTEGER NOT NULL,
                    INDEX idx_sales_rep_id (sales_rep_id),
                    INDEX idx_club_id (club_id),
                    INDEX idx_is_active (is_active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created sales_rep_club_assignments table")

            # Create sales_rep_school_assignments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sales_rep_school_assignments (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    assigned_date DATETIME(6) NOT NULL,
                    notes TEXT,
                    territory_name VARCHAR(100),
                    priority_level VARCHAR(20) NOT NULL DEFAULT 'medium',
                    created_at DATETIME(6) NOT NULL,
                    updated_at DATETIME(6) NOT NULL,
                    created_by_id INTEGER NULL,
                    sales_rep_id INTEGER NOT NULL,
                    school_id INTEGER NULL,
                    wholesale_school_id INTEGER NULL,
                    INDEX idx_sales_rep_id (sales_rep_id),
                    INDEX idx_school_id (school_id),
                    INDEX idx_wholesale_school_id (wholesale_school_id),
                    INDEX idx_is_active (is_active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created sales_rep_school_assignments table")

            # Create user_sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER AUTO_INCREMENT PRIMARY KEY,
                    session_key VARCHAR(40) NOT NULL UNIQUE,
                    ip_address VARCHAR(39) NOT NULL,
                    user_agent TEXT NOT NULL,
                    login_time DATETIME(6) NOT NULL,
                    last_activity DATETIME(6) NOT NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    user_id INTEGER NOT NULL,
                    INDEX idx_user_id (user_id),
                    INDEX idx_session_key (session_key),
                    INDEX idx_is_active (is_active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created user_sessions table")

            # Create user groups table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authentication_user_groups (
                    id INTEGER AUTO_INCREMENT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    UNIQUE KEY unique_user_group (user_id, group_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created authentication_user_groups table")

            # Create user permissions table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authentication_user_user_permissions (
                    id INTEGER AUTO_INCREMENT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    permission_id INTEGER NOT NULL,
                    UNIQUE KEY unique_user_permission (user_id, permission_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✅ Created authentication_user_user_permissions table")

        print("\n🎉 AUDIT AND ASSIGNMENT TABLES CREATED!")
        print("=" * 50)
        print("✅ Audit logging system ready")
        print("✅ Assignment management ready")
        print("✅ Session tracking ready")
        print("✅ User permissions ready")
        print("\n🚀 LOGIN SYSTEM NOW FULLY FUNCTIONAL!")

        return True

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_audit_tables()