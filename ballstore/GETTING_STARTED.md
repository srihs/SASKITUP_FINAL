# BallStore UI - Getting Started Guide

Quick guide to start using the BallStore UI integration.

## 🚀 Quick Start (3 Steps)

### Step 1: Sync BallStore Data
Before using the UI, you need to sync products and categories from WooCommerce:

```bash
# Activate virtual environment
source env/bin/activate

# Run the sync command
python manage.py sync_ballstore

# Or sync specific store
python manage.py sync_ballstore --store-type LOTTO
python manage.py sync_ballstore --store-type SAS
```

**Expected Output:**
```
Starting BallStore sync...
Syncing categories...
✓ Synced 12 categories
Syncing products...
✓ Synced 150 products
✓ Synced 45 variations
✓ Synced 200 images
Sync completed in 45 seconds
```

### Step 2: Start Development Server
```bash
python manage.py runserver
```

### Step 3: Access BallStore
Open your browser and navigate to:
- **Category Browser**: http://localhost:8000/ballstore/
- **Or use the navigation**: Dashboard → Sidebar → Equipments → Ball Store

---

## 📖 How to Use

### Browsing Categories
1. Click "Ball Store" in the sidebar menu (under Equipments)
2. View all available sport categories (Soccer, Basketball, etc.)
3. Each category shows:
   - Sport icon
   - Category name
   - Number of products
   - Description (if available)
4. Click "View Products" on any category

### Viewing Products
1. Browse products in the selected category
2. Use the search box to find specific items
3. Apply filters:
   - **Stock Status**: Show only in-stock or out-of-stock items
   - **Product Type**: Filter by simple or variable products
   - **Sale Items**: Show only discounted products
4. Click "View on Store" to see the product on WooCommerce

### Product Information
Each product card displays:
- **Image**: Featured product image
- **Name**: Product title
- **Price**: Current price (with sale price if applicable)
- **Stock Status**: Color-coded badge
  - 🟢 Green = In Stock
  - 🔴 Red = Out of Stock
  - 🟡 Yellow = Backorder
- **SKU**: Product code
- **Variations**: Badge showing number of options (for variable products)
- **Sale Badge**: Red "SALE" indicator for discounted items

---

## 🔍 Search & Filter Examples

### Search Products
```
Search: "soccer ball"     → Shows all soccer balls
Search: "size 5"          → Shows all size 5 products
Search: "SB-001"          → Finds product by SKU
```

### Use Filters
- **In Stock Only**: Select "In Stock" from stock filter
- **Sale Items**: Select "On Sale" from sale filter
- **Variable Products**: Select "Variable" from type filter
- **Combine Filters**: Use multiple filters together
- **Clear All**: Click "Clear" button to reset

### Example URLs
```
/ballstore/soccer/                         # All soccer products
/ballstore/soccer/?q=ball                  # Search for "ball"
/ballstore/soccer/?stock=instock           # Only in-stock items
/ballstore/soccer/?sale=true               # Only sale items
/ballstore/soccer/?stock=instock&sale=true # In-stock sale items
```

---

## 🎨 Features Overview

### Category Browser
- ✅ Visual grid of all sport categories
- ✅ Product count per category
- ✅ Sport-specific colors and icons
- ✅ Responsive design (mobile-friendly)
- ✅ Hover effects

### Product Listing
- ✅ Product cards with images
- ✅ Price display (regular and sale)
- ✅ Stock indicators
- ✅ Search functionality
- ✅ Multiple filters
- ✅ Variable product badges
- ✅ Sale badges
- ✅ External store links

### Navigation
- ✅ Breadcrumb trail
- ✅ Subcategory navigation
- ✅ Clear filter options
- ✅ Back to categories link

---

## 🔧 Configuration

### Environment Variables
Make sure these are set in your `.env` file:

```bash
# WooCommerce API credentials
WOOCOMMERCE_API_URL=https://your-store.com/wp-json/wc/v3/
WOOCOMMERCE_API_CONSUMER_KEY=ck_your_key_here
WOOCOMMERCE_API_SECRET=cs_your_secret_here
```

### App Settings
Verify in `kitup/settings.py`:

```python
INSTALLED_APPS = [
    ...
    'ballstore',  # Should be present
    ...
]
```

---

## 📱 Mobile Access

The UI is fully responsive and works on:
- 📱 Mobile phones (iOS & Android)
- 📱 Tablets
- 💻 Desktop computers
- 💻 Large displays

**Layout automatically adjusts:**
- Mobile: 1 column
- Tablet: 2 columns
- Desktop: 3-4 columns

---

## ❓ Troubleshooting

### No Categories Showing
**Problem**: Category list is empty

**Solution**:
```bash
# Sync categories from WooCommerce
python manage.py sync_ballstore
```

### No Products in Category
**Problem**: Category shows "No Products Found"

**Solutions**:
1. Check if products are synced: `python manage.py sync_ballstore`
2. Verify products are active in WooCommerce
3. Check if category is properly assigned to products
4. Clear any active filters

### Images Not Loading
**Problem**: Product images don't display

**Solutions**:
1. Check WooCommerce product has featured image
2. Verify image URL is accessible
3. Check browser console for errors
4. Re-sync products: `python manage.py sync_ballstore`

### Search Not Working
**Problem**: Search returns no results

**Solutions**:
1. Check search term spelling
2. Try partial search (e.g., "ball" instead of "basketball")
3. Clear other filters
4. Verify products are synced

### URL Not Found (404 Error)
**Problem**: `/ballstore/` gives 404 error

**Solution**:
```bash
# Verify URLs are configured
python manage.py check

# Check URL configuration
grep -r "ballstore.urls" kitup/urls.py
```

---

## 🔄 Keeping Data Fresh

### Manual Sync
Run whenever you add/update products in WooCommerce:
```bash
python manage.py sync_ballstore
```

### Automated Sync (Future)
Set up a cron job or scheduled task:
```bash
# Example: Daily sync at 2 AM
0 2 * * * /path/to/env/bin/python /path/to/manage.py sync_ballstore
```

---

## 📊 Admin Panel

### View Synced Data
Access Django admin panel:
1. Navigate to: http://localhost:8000/admin/
2. Login with admin credentials
3. Click "BallStore" section
4. View:
   - Categories
   - Products
   - Product Variations
   - Sync Logs

### Monitor Sync Operations
1. Go to: Admin → BallStore → Sync Logs
2. View sync history, duration, and errors
3. Check last sync time per category/product

---

## 🎯 Best Practices

### For Users
1. **Use Search**: Quickly find products by name or SKU
2. **Filter Smart**: Combine filters to narrow results
3. **Check Stock**: Use stock filter before viewing products
4. **Mobile Friendly**: Browse on any device

### For Admins
1. **Regular Syncs**: Keep data up-to-date with WooCommerce
2. **Monitor Logs**: Check sync logs for errors
3. **Test Filters**: Verify all filters work correctly
4. **Image Quality**: Ensure WooCommerce images are optimized

---

## 📚 Additional Resources

### Documentation
- **BALLSTORE_UI.md** - Complete UI documentation
- **UI_IMPLEMENTATION_SUMMARY.md** - Implementation details
- **README_SYNC.md** - WooCommerce sync guide

### Support
- Check Django logs: `django.log`
- View sync logs in admin panel
- Verify WooCommerce API connection

---

## ✅ Checklist

Before using BallStore UI:
- [ ] WooCommerce API credentials configured
- [ ] BallStore data synced
- [ ] Development server running
- [ ] Navigate to /ballstore/ URL
- [ ] Categories display correctly
- [ ] Products load in categories
- [ ] Search and filters work
- [ ] External links open WooCommerce pages

---

## 🎉 You're Ready!

The BallStore UI is now ready to use. Start by clicking "Ball Store" in the sidebar menu and explore the available products!

**Need Help?** Check the troubleshooting section above or review the full documentation in BALLSTORE_UI.md.
