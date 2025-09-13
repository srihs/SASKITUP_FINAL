# Clear Locks Button Functionality Test Guide

This guide provides comprehensive instructions for testing the Clear Locks button functionality in the SASKITUP sync management interface.

## Overview

The Clear Locks button is a crucial feature that allows users to clear stuck sync operations. The button only appears when stale sync jobs (running for more than 2 hours) are detected in the system.

## Test Scenarios

### 🔧 Quick Manual Test (Recommended)

This is the fastest way to see the Clear Locks button in action:

#### Step 1: Create Test Stale Jobs
```bash
cd /Users/sas/Repos/SASKITUP
python create_test_stale_jobs.py
```

This will create 2 stale sync jobs that are 3+ hours old.

#### Step 2: Start Development Server
```bash
python manage.py runserver
```

#### Step 3: Test the Interface
1. Navigate to: http://localhost:8000/clubs/settings/sync-management/
2. Click **"Check Lock Status"** button
3. Wait for the status check to complete (3-5 seconds)
4. The **"Clear Locks"** button should appear with text like "Clear 2 Stale Jobs"
5. Click **"Clear Locks"** button
6. Confirm the action in the dialog that appears
7. Verify success messages appear in the log

#### Step 4: Clean Up
```bash
python create_test_stale_jobs.py --cleanup
```

### 🤖 Automated Browser Test

For comprehensive automated testing using Selenium:

#### Prerequisites
```bash
# Install Selenium
pip install selenium

# Install ChromeDriver (macOS)
brew install chromedriver

# Or download ChromeDriver manually from:
# https://chromedriver.chromium.org/
```

#### Run Automated Test
```bash
# Full automated test with browser UI
python test_clear_locks_functionality.py

# Headless mode (faster, no browser window)
python test_clear_locks_functionality.py --headless

# Custom base URL
python test_clear_locks_functionality.py --base-url http://localhost:8080
```

#### Test Results
The automated test will:
- ✅ Create mock stale sync jobs
- ✅ Navigate to sync management page
- ✅ Test "Check Lock Status" button
- ✅ Verify "Clear Locks" button appears
- ✅ Test button click and confirmation
- ✅ Verify locks are cleared
- ✅ Generate screenshots and logs
- ✅ Clean up test data

### 📊 Status Monitoring Test

Check current sync job status:

```bash
# View current job status
python create_test_stale_jobs.py --status

# Create custom test scenario
python create_test_stale_jobs.py --count 5 --hours 6
```

## Expected Behavior

### When NO Stale Jobs Exist
- ✅ "Check Lock Status" button works normally  
- ✅ Jobs table shows recent jobs
- ❌ "Clear Locks" button remains hidden
- ✅ Status shows "Clear" or "Ready"

### When Stale Jobs Exist (>2 hours old)
- ✅ "Check Lock Status" shows stale jobs in red/warning
- ✅ "Clear Locks" button appears with count (e.g., "Clear 2 Stale Jobs")
- ✅ Status shows "X stale locks" in red
- ✅ Log shows stale job details with warning messages

### After Clicking "Clear Locks"
- ✅ Confirmation dialog appears
- ✅ Stale jobs are marked as "failed" in database
- ✅ Success messages appear in management log
- ✅ "Clear Locks" button disappears
- ✅ Status updates to "Clear" or shows remaining active jobs
- ✅ Jobs table updates to show cleared jobs as "Failed"

## Visual Indicators

### Button States
```
Check Lock Status:
[Checking Status...] → [Check Lock Status]

Clear Locks (when stale jobs found):
[Clear 2 Stale Jobs] → [Clearing...] → (disappears)
```

### Status Indicators
```
System Status:
Ready (green) → Checking... (blue) → X stale locks (red) → Clear (green)
```

### Log Messages
```
✓ Found 2 recent sync jobs (blue/info)
⚠ 2 sync jobs currently running (yellow/warning)  
🔴 LOTTO job running for 3.2h - Progress: 45% (red/error)
🚨 2 stale sync jobs detected (running >2 hours) (red/error)
✓ Successfully cleared 2 stuck sync jobs (green/success)
```

## Troubleshooting

### Clear Locks Button Not Appearing

**Cause**: No stale jobs in database  
**Solution**: 
```bash
# Create test stale jobs
python create_test_stale_jobs.py

# Or check current status
python create_test_stale_jobs.py --status
```

### Button Appears But Click Doesn't Work

**Check**: Browser console for JavaScript errors  
**Check**: Django logs for backend errors  
**Check**: Network tab for failed AJAX requests

### Database Changes Not Persisting

**Check**: Django database connection  
**Check**: Transaction handling in view  
**Verify**: Job status with:
```python
from clubs.models import SyncJob
SyncJob.objects.filter(status='running').count()  # Should decrease after clearing
```

### Automated Test Failing

**Common Issues**:
- ChromeDriver not installed or in PATH
- Django server not running on expected port
- Browser window size issues (use --headless)
- Timeout waiting for elements (slow system)

**Debug**:
```bash
# Check generated screenshots
ls -la *.png

# Check page source
cat final_page_source.html

# Run with verbose logging
python test_clear_locks_functionality.py --headless
```

## Technical Details

### Database Schema
```python
# SyncJob model fields relevant to stale detection
class SyncJob(models.Model):
    status = models.CharField()  # 'running' jobs can become stale
    started_at = models.DateTimeField()  # Used to calculate age
    created_at = models.DateTimeField()  # Fallback if started_at is None
    
    def is_stale(self, max_age_hours=2):
        # Returns True if job is running and older than max_age_hours
```

### API Endpoints
```python
# Check job status
GET /clubs/sync/jobs/  → Returns job list with stale indicators

# Clear stale locks
POST /clubs/sync/clear-locks/  → Marks stale jobs as failed
```

### JavaScript Logic
```javascript
// Button visibility controlled by:
if (staleCount > 0) {
    clearLocksBtn.style.display = 'inline-block';
    clearLocksBtn.innerHTML = `Clear ${staleCount} Stale Jobs`;
} else {
    clearLocksBtn.style.display = 'none';
}
```

## Test Data Cleanup

### Manual Cleanup
```bash
# Clean up all test jobs
python create_test_stale_jobs.py --cleanup

# Or via Django shell
python manage.py shell
>>> from clubs.models import SyncJob
>>> SyncJob.objects.filter(current_step__contains="Test Job").delete()
```

### Automatic Cleanup
The automated test cleans up after itself, but if it crashes:
```bash
# Emergency cleanup
python -c "
import os, sys, django
sys.path.append('/Users/sas/Repos/SASKITUP')
os.environ['DJANGO_SETTINGS_MODULE'] = 'kitup.settings'
django.setup()
from clubs.models import SyncJob
SyncJob.objects.filter(current_step__contains='STUCK').delete()
"
```

## Success Criteria

A successful test should demonstrate:

1. ✅ **Button Visibility Logic**: Button only appears when stale jobs exist
2. ✅ **Accurate Detection**: Correctly identifies jobs >2 hours old  
3. ✅ **User Confirmation**: Shows confirmation dialog before clearing
4. ✅ **Database Updates**: Actually marks jobs as failed in database
5. ✅ **UI Feedback**: Shows progress and success messages
6. ✅ **State Management**: Button disappears after successful clearing
7. ✅ **Error Handling**: Graceful handling of failures or network issues

## Integration with Real Sync Operations

### Production Considerations
- The feature should work with real sync jobs that genuinely become stuck
- Users should be able to clear locks and retry failed syncs
- Clearing locks should not affect currently active (non-stale) operations
- The 2-hour threshold can be adjusted via the `max_age_hours` parameter

### Monitoring Integration  
- Logs can be integrated with monitoring systems
- Stale job detection can trigger alerts
- Clear locks operations can be audited for security

---

## Quick Reference

### Most Common Test Flow
```bash
# 1. Create test data
python create_test_stale_jobs.py

# 2. Start server  
python manage.py runserver

# 3. Test manually at:
# http://localhost:8000/clubs/settings/sync-management/

# 4. Clean up
python create_test_stale_jobs.py --cleanup
```

### File Locations
- Main test script: `test_clear_locks_functionality.py`
- Quick setup script: `create_test_stale_jobs.py`  
- Sync management page: `template/clubs/sync_management.html`
- Backend views: `clubs/views.py` (lines 694-759)
- URL routing: `clubs/urls.py` (line 27)

This comprehensive test suite ensures the Clear Locks button functionality works correctly in all scenarios and provides users with a reliable way to manage stuck sync operations.