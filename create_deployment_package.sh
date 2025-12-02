#!/bin/bash

# SASKITUP Deployment Package Creator
# Creates a clean zip file with only necessary code files for Docker deployment

PACKAGE_NAME="SASKITUP_deployment_$(date +%Y%m%d_%H%M%S).zip"

echo "📦 Creating deployment package: $PACKAGE_NAME"
echo ""

# Create zip excluding unnecessary files
zip -r "$PACKAGE_NAME" . \
  -x "*.git*" \
  -x "env/*" \
  -x "venv/*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x "*/*/__pycache__/*" \
  -x "*/*/*/__pycache__/*" \
  -x "*.pyc" \
  -x "*.pyo" \
  -x "*.log" \
  -x "logs/*" \
  -x "*.sqlite3" \
  -x "*.db" \
  -x ".env" \
  -x ".env.local" \
  -x "media/*" \
  -x "staticfiles/*" \
  -x "temp_uploads/*" \
  -x "*.md" \
  -x "docs/*" \
  -x ".vscode/*" \
  -x ".idea/*" \
  -x "*.swp" \
  -x ".DS_Store" \
  -x "*.zip" \
  -x "implementation_notes/*" \
  -x ".coverage" \
  -x "htmlcov/*" \
  -x "test-results/*" \
  -q

echo ""
echo "✅ Package created: $PACKAGE_NAME"
echo ""
echo "📊 Package contents summary:"
unzip -l "$PACKAGE_NAME" | grep -E "migrations/.*\.py$" | head -20
echo ""
echo "📈 Package size: $(du -h "$PACKAGE_NAME" | cut -f1)"
echo ""
echo "🔍 Verifying migration files..."
MIGRATION_COUNT=$(unzip -l "$PACKAGE_NAME" | grep -E "migrations/0.*\.py$" | wc -l)
echo "   Found $MIGRATION_COUNT migration files"

if [ "$MIGRATION_COUNT" -gt 0 ]; then
  echo "   ✅ Migration files included!"
else
  echo "   ❌ ERROR: No migration files found!"
  exit 1
fi

echo ""
echo "✅ Deployment package ready!"
