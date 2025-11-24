#!/bin/bash
# Script to clear all Django migrations and reset database
# WARNING: This will DELETE all migration files and database data!
# Use this only for development/testing environments

echo "=========================================="
echo "Django Migrations Reset Script"
echo "=========================================="
echo ""
echo "WARNING: This will:"
echo "  1. Delete all migration files (except __init__.py)"
echo "  2. You will need to drop and recreate the database"
echo "  3. Create fresh initial migrations"
echo "  4. Run migrations again"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Step 1: Removing migration files..."
echo "=========================================="

# Find and remove all migration files except __init__.py
apps=("authentication" "clubs" "quotations" "schools" "ballstore" "bespoke")

for app in "${apps[@]}"; do
    echo "Clearing migrations for: $app"
    find "./$app/migrations" -type f -name "*.py" -not -name "__init__.py" -delete
done

echo ""
echo "✅ Migration files removed!"
echo ""
echo "=========================================="
echo "Next Steps (MANUAL):"
echo "=========================================="
echo ""
echo "1. Drop the database:"
echo "   mysql -u root -p"
echo "   DROP DATABASE cpq_kitup;"
echo "   CREATE DATABASE cpq_kitup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
echo "   EXIT;"
echo ""
echo "2. Create fresh migrations:"
echo "   python manage.py makemigrations"
echo ""
echo "3. Run migrations:"
echo "   python manage.py migrate"
echo ""
echo "4. Create superuser:"
echo "   python manage.py createsuperuser"
echo ""
echo "5. (Optional) Load data from backup:"
echo "   python manage.py loaddata backup.json"
echo ""
echo "=========================================="
echo "Migration cleanup complete!"
echo "=========================================="
