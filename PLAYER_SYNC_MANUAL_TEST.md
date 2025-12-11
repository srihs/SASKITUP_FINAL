# Manual Testing Guide: Player Detail Synchronization

This document provides step-by-step instructions to manually test the player detail synchronization feature in the quotation system.

## Feature Overview

When editing a quotation with bespoke products that have player details:
- **Increasing quantity**: Automatically adds empty player slots
- **Decreasing quantity**: Prompts user to select which players to keep

## Test Scenario 1: Quantity Increase (Auto-Add Empty Slots)

### Steps:
1. Login to http://127.0.0.1:8000/
2. Navigate to **Quotations** → **New Quotation**
3. Click the **Bespoke** tab
4. Click **View Products** on **Base Garment**
5. Select any product and click **View Details**
6. Configure the product:
   - Select size: **M**
   - Set quantity: **2**
7. Click **Add to Quotation**
8. Go to cart at http://127.0.0.1:8000/quotations/cart/
9. Click **View Player Details** button
10. Add 2 player details:
    - Player 1: Name: "John Doe", Number: "10", Initial: "JD"
    - Player 2: Name: "Jane Smith", Number: "20", Initial: "JS"
11. Click **Save Changes**
12. **Increase quantity from 2 to 5** using the quantity spinner
13. Wait for the update to complete (should NOT show a modal)

### Expected Results:
✅ No player selection modal appears
✅ Quantity successfully updates to 5
✅ Page reloads showing qty = 5

14. Click **View Player Details** button again

### Expected Results:
✅ Modal now shows **5 player slots**
✅ First 2 slots have the data you entered (John Doe, Jane Smith)
✅ Last 3 slots are empty (ready for new player data)

---

## Test Scenario 2: Quantity Decrease (Prompt for Player Selection)

### Prerequisites:
Complete Scenario 1 first (you should have 5 player slots with 2 filled)

### Steps:
1. Fill in the remaining 3 empty player slots:
   - Player 3: Name: "Bob Johnson", Number: "30", Initial: "BJ"
   - Player 4: Name: "Alice Williams", Number: "40", Initial: "AW"
   - Player 5: Name: "Charlie Brown", Number: "50", Initial: "CB"
2. Click **Save Changes**
3. **Decrease quantity from 5 to 3** using the quantity spinner
4. A **Player Selection Modal** should appear immediately

### Expected Results:
✅ Modal title: "Select Players to Keep"
✅ Message shows: "Select 3 player(s) to keep from the current 5 players"
✅ 5 checkboxes are displayed, one for each player
✅ First 3 players are **auto-selected** (John Doe, Jane Smith, Bob Johnson)
✅ Players 4 and 5 are **not selected**

5. Try selecting a 4th player (should trigger warning)

### Expected Results:
✅ Warning appears: "You can only select 3 player(s)"
✅ 4th checkbox is automatically unchecked

6. Uncheck "Bob Johnson" (Player 3)
7. Check "Charlie Brown" (Player 5)
8. Now you should have: John Doe, Jane Smith, Charlie Brown selected
9. Click **Confirm Selection**

### Expected Results:
✅ Modal closes
✅ Success message appears
✅ Page reloads with quantity = 3

10. Click **View Player Details** button

### Expected Results:
✅ Modal now shows **only 3 player slots**
✅ The 3 slots contain the players you selected:
   - Slot 1: John Doe, #10, JD
   - Slot 2: Jane Smith, #20, JS
   - Slot 3: Charlie Brown, #50, CB

---

## Test Scenario 3: Addon Quantity Sync Verification

### Steps:
1. Go back to cart (should still have the bespoke product with qty=3)
2. Edit the product to add an addon (e.g., Heat Transfer)
3. Save the product with addon
4. Increase product quantity from 3 to 6

### Expected Results:
✅ Player selection does NOT appear (3 → 6 is an increase)
✅ After update, product qty = 6
✅ **Addon qty also = 6** (synchronized)
✅ Player details should now have 6 slots (3 filled, 3 empty)

5. Decrease quantity from 6 to 4

### Expected Results:
✅ Player selection modal appears
✅ Shows 6 players, asks you to select 4
✅ After confirmation:
   - Product qty = 4
   - **Addon qty = 4** (synchronized)
   - Player details = 4 slots (only selected players)

---

## Edge Cases to Test

### Edge Case 1: No Player Details Exist
1. Add a new bespoke product without filling player details
2. Increase quantity from 2 to 5

**Expected**: No modal, player slots increase from 2 to 5 (all empty)

### Edge Case 2: Decrease to Same Count as Players
1. Have 3 players, quantity = 3
2. Decrease to 2

**Expected**: Player selection modal appears asking to select 2 from 3

### Edge Case 3: Cancel Player Selection
1. Trigger player selection modal
2. Click "Cancel" or X button

**Expected**:
- Modal closes
- Quantity reverts to previous value
- No changes are saved

---

## Implementation Details

### Backend Changes:
- `quotations/views.py:1715-1763`: Added player sync logic to `UpdateQuotationItemView`
- `quotations/views.py:1882-1960`: New `UpdateQuotationItemWithPlayersView` endpoint
- `quotations/urls.py:49`: Added URL route for player selection endpoint

### Frontend Changes:
- `quotations_cart.html:1859-1886`: Added player selection modal HTML
- `quotations_cart.html:2267-2280`: Modified `updateCartQuantityValue` to handle player selection response
- `quotations_cart.html:3542-3698`: Implemented `PlayerSelectionModal` JavaScript object

### Data Flow:
1. User changes quantity in cart
2. AJAX POST to `/quotations/update/`
3. Backend checks if bespoke product with player details
4. **If quantity increase**: Auto-add empty slots, return success
5. **If quantity decrease**: Return `requires_player_selection: true` with player data
6. Frontend shows modal if player selection required
7. User selects players, clicks confirm
8. AJAX POST to `/quotations/update-with-players/` with selected players
9. Backend updates quantity and player list
10. Page reloads with updated data

---

## Troubleshooting

### Issue: Modal doesn't appear on quantity decrease
**Check**: Browser console for JavaScript errors
**Fix**: Ensure `PlayerSelectionModal.init()` is called on page load

### Issue: Quantity reverts after modal confirmation
**Check**: Network tab for failed AJAX requests
**Fix**: Verify CSRF token is present and URL route is correct

### Issue: Player data lost after quantity change
**Check**: Django logs for session save errors
**Fix**: Ensure `save_quotation_session()` is called after updates

---

## Success Criteria

All scenarios pass when:
- ✅ Quantity increases add empty player slots automatically
- ✅ Quantity decreases show player selection modal
- ✅ Selected players are preserved correctly
- ✅ Addon quantities sync with parent product
- ✅ No data loss during operations
- ✅ User-friendly error messages
- ✅ Smooth UX with loading indicators
