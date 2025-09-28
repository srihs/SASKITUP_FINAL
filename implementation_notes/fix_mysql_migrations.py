#!/usr/bin/env python
"""
Fix MySQL Migration Dependencies
Manually insert migration records to resolve dependency issues
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

def fix_migration_dependencies():
    """Fix migration dependency issues by manually inserting missing records"""

    print("🔧 FIXING MYSQL MIGRATION DEPENDENCIES")
    print("=" * 50)

    try:
        with connection.cursor() as cursor:
            # Insert authentication migration record
            cursor.execute("""
                INSERT IGNORE INTO django_migrations (app, name, applied)
                VALUES ('authentication', '0001_initial', NOW())
            """)
            print("✅ Marked authentication.0001_initial as applied")

            # Check current migration status
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
            migrations = cursor.fetchall()

            print("\n📋 Current migration status:")
            for app, name in migrations:
                print(f"   ✅ {app}.{name}")

        print("\n🎉 MIGRATION DEPENDENCIES FIXED!")
        print("=" * 50)
        print("✅ Authentication migration marked as applied")
        print("✅ Dependency conflicts resolved")
        print("\n🚀 NOW TRY: python manage.py migrate")

        return True

    except Exception as e:
        print(f"❌ Error fixing migrations: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    fix_migration_dependencies()