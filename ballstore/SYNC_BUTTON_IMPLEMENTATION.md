# BallStore Sync Button Implementation

## Overview
Added a sync button functionality to the BallStore application to allow admin/staff users to trigger product syncs from the UI.

## Implementation Summary

### 1. Views (`ballstore/views.py`)

**Added imports:**
- `redirect` from django.shortcuts
- `messages` from django.contrib
- `user_passes_test` from django.contrib.auth.decorators
- `call_command` from django.core.management
- `threading` for background execution
- `logging` for error tracking
- `BallStoreSyncLog` from models

**New functions:**

#### `is_staff_user(user)`
Helper function to check if user is staff/admin:
```python
def is_staff_user(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and user.is_staff
```

#### `run_sync_in_background(sync_log)`
Executes the sync command in a background thread:
- Marks sync as running
- Calls `sync_ballstore` management command
- Handles errors and updates sync log status
- Logs all activities

#### `trigger_sync(request)`
View function to trigger sync (staff only):
- Protected by `@user_passes_test(is_staff_user)` decorator
- Checks for existing running syncs
- Creates new `BallStoreSyncLog` entry
- Starts background thread for sync execution
- Shows success/warning/error messages
- Redirects back to category list

**Key Features:**
- ✅ Runs sync in background (non-blocking)
- ✅ Prevents multiple concurrent syncs
- ✅ Shows user-friendly messages
- ✅ Requires staff/admin permissions
- ✅ Comprehensive error handling
- ✅ Logging for debugging

### 2. URLs (`ballstore/urls.py`)

Added new URL route:
```python
path('sync/', views.trigger_sync, name='trigger-sync'),
```

**URL:** `/ballstore/sync/`
**Name:** `ballstore:trigger-sync`
**Method:** GET (staff only)

### 3. Template (`ballstore/templates/ballstore/category_list.html`)

#### Header Section
Added a flex container with sync button (staff only):
```html
<div class="d-flex justify-content-between align-items-center mb-4">
    <h4 class="card-title mb-0">Browse Categories</h4>
    {% if user.is_staff %}
    <button type="button" class="btn btn-primary" id="syncButton" onclick="confirmSync()">
        <i class="uil-sync me-1"></i> Sync Products
    </button>
    {% endif %}
</div>
```

#### JavaScript Functions

**`confirmSync()`**
Shows SweetAlert confirmation dialog:
- Asks user to confirm sync operation
- Explains sync will run in background (5-10 minutes)
- Shows loading spinner on confirmation
- Redirects to sync URL

**Message Display**
Automatically displays Django messages using SweetAlert:
- Success messages (green, auto-dismiss after 5 seconds)
- Warning messages (yellow, requires dismiss)
- Error messages (red, requires dismiss)
- Info messages (blue, requires dismiss)

**Features:**
- ✅ Beautiful confirmation modal
- ✅ Loading state while redirecting
- ✅ Professional message notifications
- ✅ Only visible to staff users
- ✅ Bootstrap/Unicons styling

## Usage

### For Administrators

1. **Navigate to BallStore Categories:**
   - Go to `/ballstore/` in your browser
   - You'll see the "Sync Products" button in the top-right corner (staff only)

2. **Trigger Sync:**
   - Click the "Sync Products" button
   - Confirm in the modal dialog
   - Wait for success message
   - Continue browsing (sync runs in background)

3. **Monitor Sync:**
   - Check `BallStoreSyncLog` in Django admin
   - Review sync statistics and errors
   - View sync duration and status

### For Developers

**Test the sync button:**
```bash
# 1. Ensure you're logged in as staff/admin
# 2. Visit http://localhost:8000/ballstore/
# 3. Click "Sync Products" button
# 4. Confirm the dialog
# 5. Check logs: tail -f logs/django.log
```

**Check sync status:**
```python
from ballstore.models import BallStoreSyncLog

# Get latest sync
latest_sync = BallStoreSyncLog.objects.order_by('-started_at').first()

print(f"Status: {latest_sync.status}")
print(f"Type: {latest_sync.sync_type}")
print(f"Products: {latest_sync.products_synced}")
print(f"Duration: {latest_sync.duration_seconds}s")
```

## Technical Details

### Permission System
- Only staff users (`user.is_staff`) can see the sync button
- Only authenticated staff can trigger syncs
- Non-staff users are redirected to login page

### Background Execution
- Sync runs in daemon thread
- Uses `threading.Thread` with `daemon=True`
- Non-blocking - user can continue browsing
- Sync log tracks progress and status

### Error Handling
- Checks for existing running syncs (prevents duplicates)
- Catches and logs all exceptions
- Shows user-friendly error messages
- Updates sync log status on failure

### Messages Framework
- Uses Django's messages framework
- Displays via SweetAlert for better UX
- Different styles for different message types
- Auto-dismiss for success messages

## Files Modified

1. `/Users/sas/Repos/SASKITUP/ballstore/views.py` - Added sync views and logic
2. `/Users/sas/Repos/SASKITUP/ballstore/urls.py` - Added sync URL route
3. `/Users/sas/Repos/SASKITUP/ballstore/templates/ballstore/category_list.html` - Added sync button and UI

## Dependencies

**Backend:**
- Django's `call_command` for running management commands
- Django's `messages` framework for user notifications
- Python's `threading` for background execution
- Django's `user_passes_test` for permission checking

**Frontend:**
- SweetAlert2 (for confirmation dialogs and messages)
- Bootstrap 5 (for button styling)
- Unicons (for icons)
- jQuery (for DOM manipulation)

## Security Considerations

- ✅ Staff-only access enforced at view level
- ✅ User authentication required
- ✅ No CSRF vulnerabilities (uses Django's protection)
- ✅ Input validation (no user input required)
- ✅ Proper error handling and logging

## Future Enhancements (Optional)

1. **Sync Status Page:**
   - Show recent sync history
   - Display sync statistics
   - Real-time progress tracking

2. **AJAX Polling:**
   - Check sync status without page refresh
   - Show progress bar
   - Display live updates

3. **Sync Options:**
   - Choose sync type (full/incremental/categories-only)
   - Schedule syncs for later
   - Email notifications on completion

4. **Advanced Permissions:**
   - Custom permission for sync triggering
   - Group-based access control
   - Audit logging for sync triggers

## Testing Checklist

- [ ] Staff user can see sync button
- [ ] Non-staff user cannot see sync button
- [ ] Clicking sync shows confirmation dialog
- [ ] Confirming starts sync and shows success message
- [ ] Canceling dialog does not start sync
- [ ] Cannot start sync when one is already running
- [ ] Sync runs in background (page is responsive)
- [ ] Error messages display correctly
- [ ] Sync log is created and updated
- [ ] Permissions work correctly (redirects to login)

## Troubleshooting

**Issue:** Sync button not visible
**Solution:** Ensure user is logged in as staff (`user.is_staff = True`)

**Issue:** Sync fails immediately
**Solution:** Check WooCommerce credentials in settings (BS_WOO_URL, BS_WOO_KEY, BS_WOO_SECRET)

**Issue:** Multiple syncs running
**Solution:** Clear stuck syncs by updating BallStoreSyncLog status to 'failed' or 'completed'

**Issue:** No success message
**Solution:** Check browser console for JavaScript errors, ensure SweetAlert2 is loaded

## Related Files

- `ballstore/management/commands/sync_ballstore.py` - The sync command
- `ballstore/models.py` - BallStoreSyncLog model
- `base.html` - Base template (should include SweetAlert2 and Bootstrap)

## Notes

- Sync typically takes 5-10 minutes depending on product count
- Users can browse while sync runs (non-blocking)
- Sync status is tracked in BallStoreSyncLog model
- Multiple concurrent syncs are prevented
- All sync activities are logged for debugging
