# Quick Pagination Test Guide

**Time Required:** 5-10 minutes
**Prerequisites:** Logged in as admin user

---

## Quick Test Checklist

### Test 1: Schools Tab - Page 1 (2 min)
1. Navigate to: http://127.0.0.1:8000/quotations/new/?tab=schools
2. Check boxes:
   - [ ] Products are displayed
   - [ ] Count shows "Showing 1 to X of Y products"
   - [ ] Pagination controls visible (if >24 products)
   - [ ] Can see page numbers (1, 2, 3, etc.)

### Test 2: Page Navigation (2 min)
1. Click page "2" button (or "Next")
2. Check boxes:
   - [ ] URL changes to `?tab=schools&page=2`
   - [ ] Different products appear
   - [ ] Count updates to "Showing 25 to X of Y products"
   - [ ] Page 2 is highlighted/active
   - [ ] "Previous" button now enabled

### Test 3: Clubs Tab (1 min)
1. Click "Clubs" tab
2. Check boxes:
   - [ ] URL changes to `?tab=clubs`
   - [ ] Pagination resets (shows page 1)
   - [ ] Different products (club products) displayed

### Test 4: Search + Pagination (2 min)
1. Back to Schools tab
2. Search for "shirt" or any product name
3. Check boxes:
   - [ ] Search results appear
   - [ ] Pagination works with search (if >24 results)
   - [ ] URL includes search parameter: `?tab=schools&search=shirt&page=2`

### Test 5: Edge Case (1 min)
1. Manually type in URL: http://127.0.0.1:8000/quotations/new/?tab=schools&page=9999
2. Check boxes:
   - [ ] Page loads without error (no 404)
   - [ ] Shows valid page (redirects to last page or page 1)

---

## What to Look For

### ✅ Good Signs
- Pagination controls appear when >24 products
- Page numbers work correctly
- URL updates when changing pages
- Product count is accurate
- No visual layout breaking
- Mobile responsive (test on narrow browser window)

### ❌ Issues to Report
- Pagination missing when >24 products exist
- Page navigation broken (404 errors)
- URL doesn't update correctly
- Product count inaccurate
- Layout breaks at bottom of page
- Pagination not working on mobile view

---

## Quick Browser Console Test

Open browser console (F12) and run:

```javascript
// Check if pagination exists
console.log('Pagination found:', !!document.querySelector('.pagination'));

// Count visible products
console.log('Products on page:', document.querySelectorAll('.product-card, .card').length);

// Check current page from URL
const params = new URLSearchParams(window.location.search);
console.log('Current page:', params.get('page') || '1');
console.log('Current tab:', params.get('tab') || 'schools');
```

---

## Screenshot Locations

If you want to save evidence, take screenshots at:
1. Schools page 1: `/Users/sas/Repos/SASKITUP/test_screenshots/schools_p1.png`
2. Schools page 2: `/Users/sas/Repos/SASKITUP/test_screenshots/schools_p2.png`
3. Clubs page 1: `/Users/sas/Repos/SASKITUP/test_screenshots/clubs_p1.png`
4. Search results: `/Users/sas/Repos/SASKITUP/test_screenshots/search_pagination.png`

---

## Report Results

After testing, report:
1. ✅ / ❌ for each checkbox above
2. Total products in database (Schools and Clubs)
3. Any visual or functional issues
4. Browser and OS used for testing

---

**Quick Result Summary Template:**

```
PAGINATION TEST RESULTS
========================
Date: [DATE]
Browser: [Chrome/Firefox/Safari]
User: admin

Schools Tab:
- Products per page: [ ] ≤24
- Pagination visible: [ ] Yes / [ ] No
- Navigation works: [ ] Yes / [ ] No

Clubs Tab:
- Products per page: [ ] ≤24
- Pagination visible: [ ] Yes / [ ] No
- Navigation works: [ ] Yes / [ ] No

Search + Pagination:
- Works correctly: [ ] Yes / [ ] No

Edge Cases:
- Invalid pages handled: [ ] Yes / [ ] No

Overall: [ ] PASS / [ ] FAIL
Issues found: [LIST ANY ISSUES]
```
