# Visual Guide - Quotation Edit History UI

## 📸 Component Previews

This guide shows what each component looks like and where they appear in the application.

---

## 1. Edit Note Modal

### When It Appears
- Triggered when user clicks "Update Quotation" for edited quotations
- Only shows for quotations being edited, not new ones

### Visual Structure
```
┌─────────────────────────────────────────────────────┐
│  📝 Save Changes to Quotation                    × │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ ℹ️  Quotation: QT-2024-001                   │  │
│  │    Status: [Draft]                           │  │
│  │    Items Changed: [5 items]                  │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  Describe your changes *                            │
│  ┌──────────────────────────────────────────────┐  │
│  │ Example: Updated pricing for all items,      │  │
│  │ changed quantities based on client request...│  │
│  │                                               │  │
│  │                                               │  │
│  └──────────────────────────────────────────────┘  │
│  0 / 500 characters (minimum 10 required)          │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ ⚠️  This note will be added to the quotation │  │
│  │    history for tracking purposes.            │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│                          [Cancel] [Save Quotation] │
└─────────────────────────────────────────────────────┘
```

### Design Details
- **Header**: Info icon + title, close button (×)
- **Info Box**: Blue background, shows quotation context
- **Text Area**: 4 rows, character counter below
- **Help Text**: Warning box with yellow background
- **Buttons**: Secondary (Cancel), Success (Save)

---

## 2. History Button

### A. Detail Page Version (Full Button)
```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  [🕐 History (3)]  [✏️ Edit]  [🖨️]  [📥 Download PDF]   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Button Styling**:
- Background: Gradient blue (#50a5f1 → #4c9ae8)
- Icon: Clock/history (uil-history)
- Text: "History" (hidden on mobile)
- Badge: White with number of edits

### B. List/Table Version (Icon Only)
```
┌─────────────────────────────────────────────────────────┐
│ Actions                                                 │
├─────────────────────────────────────────────────────────┤
│  👁️  🕐  ✏️  📥                                          │
│ View History Edit PDF                                   │
└─────────────────────────────────────────────────────────┘
```

**Icon Styling**:
- Color: Info blue (#50a5f1)
- Size: 18px
- Hover: Darker blue, scale 1.1

### Display Logic
```
IF quotation.version > 1 THEN
    SHOW history button
    badge_count = version - 1
ELSE
    HIDE button (no edits yet)
END IF
```

---

## 3. History Timeline Modal

### When It Appears
- Triggered by clicking history button
- Shows loading spinner initially
- Displays timeline when data loaded

### Visual Structure
```
┌────────────────────────────────────────────────────────────┐
│  🕐 Quotation History                                   × │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ●═══════════════════════════════════════════════════════ │
│  ║                                                         │
│  ║  ┌──────────────────────────────────────────────────┐  │
│  ║  │ [Version 3] [LATEST]          2 hours ago        │  │
│  ║  │ 👤 John Smith                                     │  │
│  ║  │                                                   │  │
│  ║  │ 📝 Change Note                                    │  │
│  ║  │ Updated pricing based on supplier changes        │  │
│  ║  │                                                   │  │
│  ║  │ 📋 Changes Summary [2 items] ▼                   │  │
│  ║  └──────────────────────────────────────────────────┘  │
│  ║                                                         │
│  ○─────────────────────────────────────────────────────── │
│  ║                                                         │
│  ║  ┌──────────────────────────────────────────────────┐  │
│  ║  │ [Version 2]                   3 days ago         │  │
│  ║  │ 👤 Jane Doe                                       │  │
│  ║  │                                                   │  │
│  ║  │ 📝 Change Note                                    │  │
│  ║  │ Added 3 new items per client request             │  │
│  ║  │                                                   │  │
│  ║  │ 📋 Changes Summary [5 items] ▶                   │  │
│  ║  │ ┌────────────────────────────────────────────┐   │  │
│  ║  │ │ Items Added: +3                            │   │  │
│  ║  │ │ Items Modified: 2                          │   │  │
│  ║  │ │ Total Price: $1,234.00 → $1,567.00        │   │  │
│  ║  │ └────────────────────────────────────────────┘   │  │
│  ║  └──────────────────────────────────────────────────┘  │
│  ║                                                         │
│  ○─────────────────────────────────────────────────────── │
│  ║                                                         │
│  ║  ┌──────────────────────────────────────────────────┐  │
│  ║  │ [Version 1]                   1 week ago         │  │
│  ║  │ 👤 John Smith                                     │  │
│  ║  │                                                   │  │
│  ║  │ 📝 Change Note                                    │  │
│  ║  │ Initial quotation created                        │  │
│  ║  └──────────────────────────────────────────────────┘  │
│                                                            │
│                                              [Close]       │
└────────────────────────────────────────────────────────────┘
```

### Timeline Elements

#### Vertical Line
- Color: Gradient from primary (#556ee6) to light (#e9ecef)
- Width: 2px
- Position: Left side

#### Timeline Markers
- Shape: Circle (18px diameter)
- Border: 3px solid primary
- Latest version: Filled with primary color
- Other versions: White with primary border

#### Timeline Cards
- Background: Light gray (#f8f9fa)
- Border-left: 3px solid primary
- Hover: Darker background, shift right 5px, shadow
- Padding: 1.25rem

#### Version Badge
- Background: Gradient primary
- Color: White
- Border-radius: 20px
- Font: 0.75rem, bold

#### Latest Badge
- Background: Gradient success (#34c38f)
- Color: White
- Border-radius: 20px
- Font: 0.75rem, bold

#### Change Note Box
- Background: White
- Border-left: 2px solid success (#34c38f)
- Padding: 0.75rem

#### Changes Toggle
- Background: White
- Border: 1px solid #dee2e6
- Cursor: Pointer
- Hover: Light background, primary border
- Collapse icon: Rotates 180° when expanded

#### Changes Details
- Items Added: Green text (+3)
- Items Removed: Red text (-2)
- Items Modified: Blue text (5)
- Price change: Old → New with arrow

---

## 4. Loading & Error States

### Loading State
```
┌────────────────────────────────────────────┐
│                                            │
│              ⟳                             │
│        Loading history...                  │
│                                            │
└────────────────────────────────────────────┘
```
- Spinner: Bootstrap primary color
- Text: Muted gray

### Error State
```
┌────────────────────────────────────────────┐
│  ⚠️  Failed to load history.               │
│     Please try again.                      │
└────────────────────────────────────────────┘
```
- Background: Danger red (#f46a6a)
- Icon: Warning triangle
- Text: White

### Empty State
```
┌────────────────────────────────────────────┐
│                                            │
│              🕐                            │
│      No History Available                  │
│                                            │
│  This quotation has no edit history yet.  │
│                                            │
└────────────────────────────────────────────┘
```
- Icon: Large history icon, light gray
- Text: Muted gray

---

## 5. Responsive Layouts

### Desktop (≥992px)
```
┌─────────────────────────────────────────────┐
│  [🕐 History (3)]  [✏️ Edit]  [🖨️]  [📥]   │
└─────────────────────────────────────────────┘
```
- Full button text visible
- Horizontal layout
- Badges visible

### Tablet (768px - 991px)
```
┌────────────────────────────────┐
│  [🕐 History]  [✏️]  [🖨️]  [📥] │
└────────────────────────────────┘
```
- Shortened text
- Icons with minimal text
- Compact spacing

### Mobile (<768px)
```
┌──────────────┐
│  🕐  ✏️  🖨️   │
│  📥  ←       │
└──────────────┘
```
- Icon-only buttons
- Stacked when needed
- Full-width modals

### Timeline Responsive
- Desktop: Left-aligned with 30px padding
- Mobile: Reduced padding (20px), smaller markers
- Cards: Full width on all devices
- Text: Scales down on mobile

---

## 6. Color Palette

### Primary Colors
```
Primary:  ██████ #556ee6 (Buttons, badges, timeline)
Success:  ██████ #34c38f (Success actions, latest badge)
Info:     ██████ #50a5f1 (History button, info messages)
Warning:  ██████ #f1b44c (Warning messages)
Danger:   ██████ #f46a6a (Error states, removed items)
```

### Neutral Colors
```
Dark:     ██████ #495057 (Primary text)
Muted:    ██████ #6c757d (Secondary text)
Light:    ██████ #f8f9fa (Backgrounds)
Border:   ██████ #dee2e6 (Borders)
```

### Gradients
```
Primary Button:   #556ee6 → #4c63d2
Success Button:   #34c38f → #2ca87f
Info Button:      #50a5f1 → #4c9ae8
Timeline Line:    #556ee6 → #e9ecef
```

---

## 7. Typography

### Headings
```
Modal Title:     1.25rem, semi-bold
Version Badge:   1.1rem, bold
Section Headers: 0.875rem, uppercase, bold
```

### Body Text
```
Primary Text:    0.9rem, regular
Secondary Text:  0.875rem, regular
Small Text:      0.75rem, regular
```

### Special Elements
```
Character Count: 0.875rem, muted
Timestamps:      0.875rem, muted
Change Labels:   0.875rem, bold
Change Values:   0.875rem, regular
```

---

## 8. Icons Reference

### Used Icons (Unicons)
```
uil-edit-alt        ✏️  Edit note
uil-history         🕐  History
uil-info-circle     ℹ️  Information
uil-exclamation-triangle ⚠️  Warning
uil-user            👤  User
uil-clock           🕐  Time
uil-comment-notes   📝  Note
uil-list-ul         📋  List
uil-angle-down      ▼  Collapse arrow
uil-arrow-right     →  Change arrow
uil-times           ×  Close
uil-check-circle    ✓  Success
```

### Icon Sizes
- Small: 14px (inline icons)
- Medium: 18px (action buttons)
- Large: 20px (modal headers)
- Extra Large: 4rem (empty states)

---

## 9. Spacing System

### Padding
```
Card:           1.25rem (20px)
Modal:          1.5rem (24px)
Change Note:    0.75rem (12px)
Button:         0.47rem 0.75rem
Badge:          0.25rem 0.5rem
```

### Margin
```
Section Spacing:    1.5rem (24px)
Element Spacing:    0.75rem (12px)
Compact Spacing:    0.5rem (8px)
Timeline Item:      2rem (32px) bottom
```

### Border Radius
```
Modal:          0.375rem (6px)
Card:           0.375rem (6px)
Button:         0.25rem (4px)
Badge:          20px (pill shape)
```

---

## 10. Animation & Transitions

### Hover Effects
```
Button Hover:
  - Transform: translateY(-2px)
  - Shadow: 0 4px 12px rgba(primary, 0.3)
  - Duration: 0.3s ease

Card Hover:
  - Transform: translateX(5px)
  - Background: Darker
  - Duration: 0.3s ease
```

### Icon Rotations
```
Collapse Arrow:
  - Closed: rotate(0deg)
  - Open: rotate(180deg)
  - Duration: 0.3s ease
```

### Modal Animations
```
Open:
  - Fade in background
  - Scale up content
  - Duration: 0.15s

Close:
  - Fade out background
  - Scale down content
  - Duration: 0.15s
```

---

## 11. Accessibility Indicators

### Focus States
```
Visible outline on all focusable elements:
  - Color: Primary
  - Width: 2px
  - Offset: 2px
  - Style: Solid
```

### ARIA Labels
```
Buttons:        aria-label="View quotation history"
Modals:         aria-labelledby, aria-hidden
Collapse:       aria-expanded, aria-controls
Status:         role="status", aria-live="polite"
```

### Keyboard Hints
```
Enter:   Submit forms
Escape:  Close modals
Tab:     Navigate elements
Space:   Activate buttons
```

---

## 12. Integration Points

### Quotation Cart Page
```
Location: Before save confirmation
Trigger:  isEditing === true
Action:   showEditNoteModal()
```

### My Quotations Page
```
Location: Action column (8th column)
Display:  Icon only
Trigger:  onclick="loadQuotationHistory(id)"
```

### Quotation Detail Page
```
Location: Action buttons (top right)
Display:  Full button with badge
Trigger:  onclick="loadQuotationHistory(id)"
```

---

## 13. User Flow

### Creating New Quotation
```
1. Add items to cart
2. Fill recipient info
3. Click "Generate Quotation"
   └─> No edit note modal (new quotation)
4. Quotation created with version 1
5. No history button shown
```

### Editing Existing Quotation
```
1. Click "Edit" on quotation
2. Modify items/details
3. Click "Update Quotation"
   └─> Edit note modal appears
4. Enter change description (10-500 chars)
5. Click "Save Quotation"
   └─> History record created
   └─> Version incremented
6. History button now visible
```

### Viewing History
```
1. See history button (if version > 1)
2. Click history button
   └─> Modal opens with loading spinner
3. History data fetched via AJAX
4. Timeline rendered with all versions
5. Click to expand change details
6. Review modifications
7. Close modal
```

---

## Visual Design Checklist

- [x] Consistent color scheme with existing theme
- [x] Bootstrap 5 compatible
- [x] Responsive on all devices (320px+)
- [x] Accessible (WCAG 2.1 AA)
- [x] Smooth animations and transitions
- [x] Clear visual hierarchy
- [x] Intuitive interaction patterns
- [x] Loading and error states
- [x] Empty state handling
- [x] Professional appearance

---

This visual guide complements the technical documentation and provides a clear understanding of how the components appear and behave in the application.
