/**
 * SASKITUP Quotation System
 * JavaScript functionality for quotation workflow
 * Bootstrap 4 compatible (uses data-toggle, not data-bs-toggle)
 */

// Global cart state
let cartItems = [];
let cartTotal = 0;

/**
 * Initialize quotation system
 */
$(document).ready(function() {
	// Load cart from session storage if available
	loadCartFromStorage();
});

/**
 * Add product to quotation cart
 * @param {number} productId - Product ID to add
 */
function addToQuotation(productId) {
	const quantity = parseInt($('#qty-' + productId).val()) || 1;

	// Validate quantity
	if (quantity < 1 || quantity > 100) {
		showToast('Quantity must be between 1 and 100', 'error');
		return;
	}

	// Show loading state
	const $btn = $(`button[onclick="addToQuotation(${productId})"]`);
	const originalText = $btn.html();
	$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Adding...');

	// AJAX request to add to cart
	$.ajax({
		url: '/quotations/add/',
		method: 'POST',
		data: {
			product_id: productId,
			quantity: quantity,
			institution_type: window.quotationContext?.institutionType || '',
			institution_id: window.quotationContext?.institutionId || '',
			csrfmiddlewaretoken: getCsrfToken()
		},
		success: function(response) {
			if (response.success) {
				showToast('Product added to quotation!', 'success');
				updateCartCount(response.cart_count);

				// Reset quantity input
				$('#qty-' + productId).val(1);

				// Add animation effect
				$btn.addClass('btn-success').html('<i class="fa fa-check"></i> Added!');
				setTimeout(function() {
					$btn.removeClass('btn-success').html(originalText).prop('disabled', false);
				}, 2000);
			} else {
				showToast(response.message || 'Failed to add product', 'error');
				$btn.html(originalText).prop('disabled', false);
			}
		},
		error: function(xhr) {
			const errorMsg = xhr.responseJSON?.message || 'An error occurred';
			showToast(errorMsg, 'error');
			$btn.html(originalText).prop('disabled', false);
		}
	});
}

/**
 * Update cart item quantity
 * @param {number} productId - Product ID
 * @param {number} change - Quantity change (+1 or -1)
 */
function updateCartQuantity(productId, change) {
	const $display = $('#qty-display-' + productId);
	const currentQty = parseInt($display.text()) || 1;
	const newQty = currentQty + change;

	// Validate new quantity
	if (newQty < 1 || newQty > 100) {
		showToast('Quantity must be between 1 and 100', 'warning');
		return;
	}

	// AJAX request to update quantity
	$.ajax({
		url: '/quotations/update/',
		method: 'POST',
		data: {
			product_id: productId,
			quantity: newQty,
			csrfmiddlewaretoken: getCsrfToken()
		},
		success: function(response) {
			if (response.success) {
				$display.text(newQty);
				updateCartSummary(response.cart_summary);
				showToast('Quantity updated', 'success');
			} else {
				showToast(response.message || 'Failed to update quantity', 'error');
			}
		},
		error: function(xhr) {
			const errorMsg = xhr.responseJSON?.message || 'An error occurred';
			showToast(errorMsg, 'error');
		}
	});
}

/**
 * Remove item from cart
 * @param {number} productId - Product ID to remove
 */
function removeFromCart(productId) {
	if (!confirm('Remove this item from your cart?')) {
		return;
	}

	// AJAX request to remove item
	$.ajax({
		url: '/quotations/remove/',
		method: 'POST',
		data: {
			product_id: productId,
			csrfmiddlewaretoken: getCsrfToken()
		},
		success: function(response) {
			if (response.success) {
				// Remove item from DOM with animation
				$('#cart-item-' + productId).fadeOut(300, function() {
					$(this).remove();

					// Check if cart is empty
					if ($('.cart-item').length === 0) {
						location.reload(); // Reload to show empty state
					}
				});

				updateCartCount(response.cart_count);
				updateCartSummary(response.cart_summary);
				showToast('Item removed from cart', 'success');
			} else {
				showToast(response.message || 'Failed to remove item', 'error');
			}
		},
		error: function(xhr) {
			const errorMsg = xhr.responseJSON?.message || 'An error occurred';
			showToast(errorMsg, 'error');
		}
	});
}

/**
 * Clear entire quotation cart
 */
function clearQuotationCart() {
	// AJAX request to clear cart
	$.ajax({
		url: '/quotations/clear/',
		method: 'POST',
		data: {
			csrfmiddlewaretoken: getCsrfToken()
		},
		success: function(response) {
			if (response.success) {
				showToast('Cart cleared successfully', 'success');
				setTimeout(function() {
					location.reload();
				}, 1000);
			} else {
				showToast(response.message || 'Failed to clear cart', 'error');
			}
		},
		error: function(xhr) {
			const errorMsg = xhr.responseJSON?.message || 'An error occurred';
			showToast(errorMsg, 'error');
		}
	});
}

/**
 * Save quotation
 */
function saveQuotation() {
	// Show loading state
	const $btn = $('button[onclick="saveQuotation()"]');
	const originalText = $btn.html();
	$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Saving...');

	// AJAX request to save quotation
	$.ajax({
		url: '/quotations/save/',
		method: 'POST',
		data: {
			csrfmiddlewaretoken: getCsrfToken()
		},
		success: function(response) {
			if (response.success) {
				showToast('Quotation saved successfully!', 'success');
				setTimeout(function() {
					window.location.href = response.redirect_url || '/quotations/my-quotations/';
				}, 1500);
			} else {
				showToast(response.message || 'Failed to save quotation', 'error');
				$btn.html(originalText).prop('disabled', false);
			}
		},
		error: function(xhr) {
			const errorMsg = xhr.responseJSON?.message || 'An error occurred';
			showToast(errorMsg, 'error');
			$btn.html(originalText).prop('disabled', false);
		}
	});
}

/**
 * Update cart count badge
 * @param {number} count - Number of items in cart
 */
function updateCartCount(count) {
	$('#cartCount').text(count || 0);

	// Show/hide badge based on count
	if (count > 0) {
		$('#quotationBadge').fadeIn();
	} else {
		$('#quotationBadge').fadeOut();
	}
}

/**
 * Load cart count from server
 */
function loadCartCount() {
	$.ajax({
		url: '/quotations/cart-count/',
		method: 'GET',
		success: function(response) {
			if (response.success) {
				updateCartCount(response.count);
			}
		},
		error: function() {
			// Silent fail - not critical
		}
	});
}

/**
 * Update cart summary display
 * @param {object} summary - Cart summary data
 */
function updateCartSummary(summary) {
	if (!summary) return;

	$('#subtotal').text('R ' + summary.subtotal);
	$('#discount').text('-R ' + summary.discount);
	$('#tax').text('R ' + summary.tax);
	$('#total').text('R ' + summary.total);
}

/**
 * Load cart from session storage
 */
function loadCartFromStorage() {
	// Get cart count from server on page load
	loadCartCount();
}

/**
 * Get CSRF token from cookies or meta tag
 * @returns {string} CSRF token
 */
function getCsrfToken() {
	// Try to get from form input first
	const tokenInput = $('input[name=csrfmiddlewaretoken]').val();
	if (tokenInput) return tokenInput;

	// Try to get from cookie
	const cookieValue = document.cookie
		.split('; ')
		.find(row => row.startsWith('csrftoken='))
		?.split('=')[1];

	return cookieValue || '';
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - Toast type (success, error, warning, info)
 */
function showToast(message, type = 'info') {
	// Remove any existing toasts
	$('.toast-notification').remove();

	// Icon mapping
	const icons = {
		success: 'fa-check-circle',
		error: 'fa-times-circle',
		warning: 'fa-exclamation-triangle',
		info: 'fa-info-circle'
	};

	// Color mapping
	const colors = {
		success: '#388e3c',
		error: '#c62828',
		warning: '#f57c00',
		info: '#1976d2'
	};

	// Create toast element
	const $toast = $(`
		<div class="toast-notification" style="
			position: fixed;
			top: 100px;
			right: 30px;
			background: white;
			padding: 1rem 1.5rem;
			border-radius: 10px;
			box-shadow: 0 5px 20px rgba(0,0,0,0.3);
			z-index: 9999;
			display: flex;
			align-items: center;
			gap: 1rem;
			max-width: 400px;
			border-left: 4px solid ${colors[type]};
			animation: slideInRight 0.3s ease;
		">
			<i class="fa ${icons[type]}" style="color: ${colors[type]}; font-size: 1.5rem;"></i>
			<span style="flex: 1; color: #222831; font-weight: 500;">${message}</span>
			<i class="fa fa-times" style="cursor: pointer; color: #888;" onclick="$(this).closest('.toast-notification').remove()"></i>
		</div>
	`);

	// Add animation styles
	if (!$('#toast-styles').length) {
		$('head').append(`
			<style id="toast-styles">
				@keyframes slideInRight {
					from {
						transform: translateX(400px);
						opacity: 0;
					}
					to {
						transform: translateX(0);
						opacity: 1;
					}
				}
				@keyframes slideOutRight {
					from {
						transform: translateX(0);
						opacity: 1;
					}
					to {
						transform: translateX(400px);
						opacity: 0;
					}
				}
			</style>
		`);
	}

	// Append to body
	$('body').append($toast);

	// Auto-remove after 5 seconds
	setTimeout(function() {
		$toast.css('animation', 'slideOutRight 0.3s ease');
		setTimeout(function() {
			$toast.remove();
		}, 300);
	}, 5000);
}

/**
 * Form validation helper
 * @param {string} formSelector - jQuery selector for form
 * @returns {boolean} Validation result
 */
function validateQuotationForm(formSelector) {
	const $form = $(formSelector);
	let isValid = true;

	// Clear previous error states
	$form.find('.is-invalid').removeClass('is-invalid');
	$form.find('.invalid-feedback').remove();

	// Validate required fields
	$form.find('[required]').each(function() {
		const $field = $(this);
		if (!$field.val() || $field.val().trim() === '') {
			isValid = false;
			$field.addClass('is-invalid');
			$field.after('<div class="invalid-feedback">This field is required</div>');
		}
	});

	// Validate email fields
	$form.find('[type="email"]').each(function() {
		const $field = $(this);
		const email = $field.val();
		const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

		if (email && !emailRegex.test(email)) {
			isValid = false;
			$field.addClass('is-invalid');
			$field.after('<div class="invalid-feedback">Please enter a valid email address</div>');
		}
	});

	// Validate number fields
	$form.find('[type="number"]').each(function() {
		const $field = $(this);
		const value = parseFloat($field.val());
		const min = parseFloat($field.attr('min'));
		const max = parseFloat($field.attr('max'));

		if (!isNaN(min) && value < min) {
			isValid = false;
			$field.addClass('is-invalid');
			$field.after(`<div class="invalid-feedback">Value must be at least ${min}</div>`);
		}

		if (!isNaN(max) && value > max) {
			isValid = false;
			$field.addClass('is-invalid');
			$field.after(`<div class="invalid-feedback">Value must not exceed ${max}</div>`);
		}
	});

	return isValid;
}

/**
 * Debounce function for search/filter inputs
 * @param {function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {function} Debounced function
 */
function debounce(func, wait) {
	let timeout;
	return function executedFunction(...args) {
		const later = () => {
			clearTimeout(timeout);
			func(...args);
		};
		clearTimeout(timeout);
		timeout = setTimeout(later, wait);
	};
}

/**
 * Format currency for display
 * @param {number} amount - Amount to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(amount) {
	return 'R ' + parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

/**
 * Calculate line total
 * @param {number} unitPrice - Unit price
 * @param {number} quantity - Quantity
 * @returns {number} Line total
 */
function calculateLineTotal(unitPrice, quantity) {
	return parseFloat(unitPrice) * parseInt(quantity);
}

/**
 * Calculate cart totals
 * @param {array} items - Cart items
 * @returns {object} Cart totals
 */
function calculateCartTotals(items) {
	let subtotal = 0;

	items.forEach(item => {
		subtotal += calculateLineTotal(item.unit_price, item.quantity);
	});

	const discount = 0; // Implement discount logic if needed
	const taxRate = 0.15; // 15% tax
	const tax = (subtotal - discount) * taxRate;
	const total = subtotal - discount + tax;

	return {
		subtotal: subtotal.toFixed(2),
		discount: discount.toFixed(2),
		tax: tax.toFixed(2),
		total: total.toFixed(2)
	};
}

// Export functions for use in other scripts if needed
window.QuotationJS = {
	addToQuotation,
	updateCartQuantity,
	removeFromCart,
	clearQuotationCart,
	saveQuotation,
	updateCartCount,
	showToast,
	validateQuotationForm,
	formatCurrency,
	calculateCartTotals
};
