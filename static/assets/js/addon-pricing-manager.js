// Addon Pricing Manager - Inline Editing
// Simple and clean inline price editing for addon pricing tables

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

// Track currently editing cell to prevent multiple edits
let currentlyEditing = null;

// Initialize inline editing when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeInlineEditing();
});

function initializeInlineEditing() {
    // Add click handlers to all editable price values
    const editablePrices = document.querySelectorAll('.price-value.editable');

    editablePrices.forEach(priceElement => {
        priceElement.addEventListener('click', function(e) {
            e.stopPropagation();
            startEditingPrice(this);
        });
    });
}

function startEditingPrice(priceElement) {
    // Prevent multiple edits
    if (currentlyEditing && currentlyEditing !== priceElement) {
        cancelEdit(currentlyEditing);
    }

    currentlyEditing = priceElement;

    // Get current price value
    const priceId = priceElement.dataset.priceId;
    const currentPrice = priceElement.textContent.trim().replace('$', '').replace(',', '');

    // Create input element
    const input = document.createElement('input');
    input.type = 'number';
    input.step = '0.01';
    input.min = '0';
    input.value = currentPrice;
    input.className = 'price-edit-input';

    // Mark price element as editing
    priceElement.classList.add('editing');

    // Insert input after price element
    priceElement.parentNode.insertBefore(input, priceElement.nextSibling);

    // Focus and select the input
    input.focus();
    input.select();

    // Handle save on blur
    input.addEventListener('blur', function() {
        savePrice(priceId, this.value, priceElement, input);
    });

    // Handle save on Enter key
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            savePrice(priceId, this.value, priceElement, input);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelEdit(priceElement, input);
        }
    });
}

function savePrice(priceId, newValue, priceElement, input) {
    // Validate input
    const price = parseFloat(newValue);
    if (isNaN(price) || price < 0) {
        Swal.fire({
            icon: 'error',
            title: 'Invalid Price',
            text: 'Please enter a valid price greater than or equal to 0',
            timer: 2000
        });
        cancelEdit(priceElement, input);
        return;
    }

    // Format price
    const formattedPrice = price.toFixed(2);

    // Send AJAX request to update price
    fetch(`/bespoke/api/pricing/price/${priceId}/edit/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({
            price: formattedPrice,
            reason: 'Inline edit'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update the display
            priceElement.textContent = `$${formattedPrice}`;
            priceElement.classList.remove('editing');

            // Remove input
            if (input && input.parentNode) {
                input.remove();
            }

            currentlyEditing = null;

            // Show success message
            showSuccessToast('Price updated successfully');
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Update Failed',
                text: data.error || 'Failed to update price',
                timer: 3000
            });
            cancelEdit(priceElement, input);
        }
    })
    .catch(error => {
        console.error('Error updating price:', error);
        Swal.fire({
            icon: 'error',
            title: 'Network Error',
            text: 'Failed to update price. Please try again.',
            timer: 3000
        });
        cancelEdit(priceElement, input);
    });
}

function cancelEdit(priceElement, input) {
    if (priceElement) {
        priceElement.classList.remove('editing');
    }

    if (input && input.parentNode) {
        input.remove();
    }

    currentlyEditing = null;
}

function showSuccessToast(message) {
    // Simple toast notification
    const toast = Swal.mixin({
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: 2000,
        timerProgressBar: true,
        didOpen: (toast) => {
            toast.addEventListener('mouseenter', Swal.stopTimer);
            toast.addEventListener('mouseleave', Swal.resumeTimer);
        }
    });

    toast.fire({
        icon: 'success',
        title: message
    });
}

// Close any open edits when clicking outside
document.addEventListener('click', function(e) {
    if (currentlyEditing && !e.target.classList.contains('price-edit-input') && !e.target.classList.contains('price-value')) {
        const input = currentlyEditing.parentNode.querySelector('.price-edit-input');
        if (input) {
            input.blur();
        }
    }
});
