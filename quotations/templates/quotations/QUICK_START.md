# Quotation Edit History - Quick Start Guide

## 🚀 5-Minute Integration

### Step 1: Include the Modals (30 seconds)

Add to **quotation_cart.html**, **my_quotations.html**, and **quotation_detail.html**:

```django
<!-- Add before {% endblock %} -->
{% include 'quotations/components/edit_history_modals.html' %}
```

### Step 2: Add History Button (1 minute)

#### For Quotation Detail Page
```django
<!-- In action buttons section -->
{% if quotation.version > 1 %}
<button type="button"
        class="btn btn-info waves-effect waves-light me-1"
        onclick="loadQuotationHistory({{ quotation.id }})">
    <i class="uil uil-history"></i> History
    <span class="badge bg-light text-dark ms-1">{{ quotation.version|add:"-1" }}</span>
</button>
{% endif %}
```

#### For My Quotations List
```django
<!-- In action column -->
{% if quotation.version > 1 %}
<a href="javascript:void(0);"
   onclick="loadQuotationHistory({{ quotation.id }})"
   class="text-info px-3"
   title="View History">
    <i class="uil uil-history font-size-18"></i>
</a>
{% endif %}
```

### Step 3: Modify Save Function (2 minutes)

In **quotation_cart.html**, update the save confirmation:

```javascript
function confirmGenerateQuotation() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('generateQuotationModal'));
    modal.hide();

    const isEditing = {{ is_editing|yesno:"true,false" }};

    if (isEditing) {
        // Show edit note modal
        showEditNoteModal(
            '{{ editing_quotation.quotation_number }}',
            '{{ editing_quotation.get_status_display }}',
            {{ cart_items|length }}
        );
    } else {
        saveQuotation();
    }
}

function saveQuotationWithNote(changeNote) {
    showLoading();

    // Add change note to your existing form data
    const formData = new URLSearchParams();
    // ... your existing form data ...
    formData.append('change_note', changeNote);

    // Your existing AJAX save logic
    fetch('{% url "quotations:save" %}', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrftoken
        },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            toastr.success('Quotation updated successfully!');
            setTimeout(() => {
                window.location.href = data.redirect_url;
            }, 1000);
        } else {
            toastr.error(data.error);
        }
    })
    .catch(error => {
        hideLoading();
        toastr.error('An error occurred');
    });
}
```

### Step 4: Backend Setup (1.5 minutes)

#### Add Model (models.py)
```python
class QuotationHistory(models.Model):
    quotation = models.ForeignKey('Quotation', on_delete=models.CASCADE, related_name='history')
    version = models.PositiveIntegerField()
    modified_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    change_note = models.TextField()

    items_added = models.IntegerField(default=0)
    items_removed = models.IntegerField(default=0)
    items_modified = models.IntegerField(default=0)

    pricing_changed = models.BooleanField(default=False)
    old_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_total = models.DecimalField(max_digits=10, decimal_places=2)
    discount_changed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-version']
        unique_together = ['quotation', 'version']

# Add to Quotation model
class Quotation(models.Model):
    # ... existing fields ...
    version = models.PositiveIntegerField(default=1)
```

#### Add View (views.py)
```python
@require_http_methods(["GET"])
def quotation_history(request, quotation_id):
    try:
        quotation = Quotation.objects.get(id=quotation_id)
        history_records = QuotationHistory.objects.filter(
            quotation=quotation
        ).select_related('modified_by').order_by('-version')

        history_data = [{
            'version': r.version,
            'date': r.modified_at.isoformat(),
            'user': r.modified_by.get_full_name() or r.modified_by.username,
            'note': r.change_note,
            'changes': {
                'items_added': r.items_added or 0,
                'items_removed': r.items_removed or 0,
                'items_modified': r.items_modified or 0,
                'pricing_changed': r.pricing_changed or False,
                'old_total': str(r.old_total) if r.old_total else None,
                'new_total': str(r.new_total),
                'discount_changed': r.discount_changed or False,
            }
        } for r in history_records]

        return JsonResponse({'success': True, 'history': history_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

#### Add URL (urls.py)
```python
urlpatterns = [
    # ... existing ...
    path('<int:quotation_id>/history/', views.quotation_history, name='quotation-history'),
]
```

#### Update Save View (views.py)
```python
def save_quotation(request):
    if request.method == 'POST':
        is_editing = 'quotation_id' in request.session

        if is_editing:
            quotation = Quotation.objects.get(id=request.session['quotation_id'])
            old_total = quotation.total
            old_items = set(quotation.items.values_list('id', flat=True))

            # Update quotation (your existing logic)
            # ...

            # Track changes
            new_items = set(quotation.items.values_list('id', flat=True))
            QuotationHistory.objects.create(
                quotation=quotation,
                version=quotation.version,
                modified_by=request.user,
                change_note=request.POST.get('change_note', ''),
                items_added=len(new_items - old_items),
                items_removed=len(old_items - new_items),
                items_modified=len(old_items & new_items),
                pricing_changed=(old_total != quotation.total),
                old_total=old_total,
                new_total=quotation.total
            )

            quotation.version += 1
            quotation.save()
        else:
            # New quotation
            quotation.version = 1
            quotation.save()

        return JsonResponse({
            'success': True,
            'redirect_url': reverse('quotations:quotation-detail', args=[quotation.id])
        })
```

### Step 5: Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## ✅ That's It!

You now have:
- ✅ Edit note modal when saving edited quotations
- ✅ History button with edit count badge
- ✅ Timeline modal showing all changes
- ✅ Full change tracking in database

---

## 📖 Component Usage

### Show Edit Note Modal
```javascript
showEditNoteModal(quotationNumber, quotationStatus, itemsCount);
```

### Load History Timeline
```javascript
loadQuotationHistory(quotationId);
```

### Check if Quotation Has History
```django
{% if quotation.version > 1 %}
    <!-- Show history button -->
{% endif %}
```

---

## 🎨 Styling

All styles are included in the components and match your existing design:
- Primary: #556ee6
- Success: #34c38f
- Info: #50a5f1
- Bootstrap 5 compatible
- Responsive mobile-first
- WCAG 2.1 AA compliant

---

## 🧪 Testing

### Test Edit Note Modal
1. Edit an existing quotation
2. Click "Update Quotation"
3. Modal should appear requesting change note
4. Try submitting with <10 characters (should fail)
5. Enter valid note and submit

### Test History Timeline
1. Edit a quotation multiple times
2. Click history button
3. Timeline should show all versions
4. Click to expand change details

---

## 📱 Responsive Behavior

- **Desktop**: Full buttons with text and badges
- **Mobile**: Icon-only buttons, stacked layout
- **Modals**: Scrollable on small screens

---

## 🔧 Customization

### Change Colors
```css
:root {
    --primary-color: #556ee6;
    --info-color: #50a5f1;
    --timeline-gradient-start: #556ee6;
}
```

### Adjust Character Limits
```javascript
// In edit_history_modals.html
minlength="10"
maxlength="500"
```

### Modal Sizes
```html
<!-- Larger modal -->
<div class="modal-dialog modal-xl">

<!-- Smaller modal -->
<div class="modal-dialog modal-sm">
```

---

## 🐛 Troubleshooting

**Modal doesn't open?**
- Check Bootstrap JS is loaded
- Verify function is defined

**Character counter not working?**
- Ensure jQuery is loaded
- Check console for errors

**History not loading?**
- Verify endpoint URL is correct
- Check backend returns correct JSON

**Styles not applying?**
- CSS must be after Bootstrap
- Clear browser cache

---

## 📚 Full Documentation

See `EDIT_HISTORY_README.md` for complete documentation including:
- Detailed feature descriptions
- Accessibility guidelines
- Advanced customization
- Performance optimization
- Testing checklist

---

## 🎯 Next Steps

1. Run migrations
2. Test with a sample quotation
3. Customize colors if needed
4. Review full README for advanced features

**Happy coding!** 🚀
