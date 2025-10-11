/**
 * Mini Cart Dropdown Interactions
 *
 * Handles mini cart dropdown behavior and interactions
 */

(function ($) {
    'use strict';

    $(document).ready(function() {
        // Initialize mini cart dropdown
        initMiniCart();
    });

    /**
     * Initialize mini cart functionality
     */
    function initMiniCart() {
        var $cartDropdown = $('#page-header-cart-dropdown');
        var $dropdownMenu = $cartDropdown.next('.dropdown-menu');

        // Close button functionality
        $dropdownMenu.on('click', '.mini-cart-close', function(e) {
            e.preventDefault();
            e.stopPropagation();
            $cartDropdown.dropdown('hide');
        });

        // Prevent dropdown from closing when clicking inside (except on links and close button)
        $dropdownMenu.on('click', function(e) {
            // Close button is handled separately above
            if ($(e.target).hasClass('mini-cart-close') || $(e.target).closest('.mini-cart-close').length) {
                return;
            }
            // Allow links to work normally
            if (!$(e.target).is('a') && !$(e.target).closest('a').length) {
                e.stopPropagation();
            }
        });

        // Add smooth hover effects to cart items
        $dropdownMenu.on('mouseenter', '.mini-cart-item', function() {
            $(this).addClass('hover');
        }).on('mouseleave', '.mini-cart-item', function() {
            $(this).removeClass('hover');
        });

        // Track dropdown open/close events
        $cartDropdown.on('show.bs.dropdown', function() {
            // Add active state to button
            $(this).addClass('show');

            // Optional: Track analytics
            if (typeof gtag !== 'undefined') {
                gtag('event', 'mini_cart_opened', {
                    'event_category': 'Cart',
                    'event_label': 'Mini Cart Dropdown'
                });
            }
        });

        $cartDropdown.on('hide.bs.dropdown', function() {
            // Remove active state from button
            $(this).removeClass('show');
        });

        // Initialize SimpleBar for scrollable area with custom options
        initializeScrollbar($dropdownMenu);

        // Add keyboard navigation support
        enableKeyboardNavigation($cartDropdown, $dropdownMenu);

        // Add click outside to close functionality
        $(document).on('click', function(e) {
            if (!$cartDropdown.is(e.target) &&
                $cartDropdown.has(e.target).length === 0 &&
                !$dropdownMenu.is(e.target) &&
                $dropdownMenu.has(e.target).length === 0) {
                if ($dropdownMenu.hasClass('show')) {
                    $cartDropdown.dropdown('hide');
                }
            }
        });
    }

    /**
     * Initialize SimpleBar scrollbar
     * @param {jQuery} $dropdownMenu - Dropdown menu element
     */
    function initializeScrollbar($dropdownMenu) {
        if (typeof SimpleBar !== 'undefined') {
            var scrollableArea = $dropdownMenu.find('[data-simplebar]');
            if (scrollableArea.length && !scrollableArea.hasClass('simplebar-initialized')) {
                new SimpleBar(scrollableArea[0], {
                    autoHide: false,
                    scrollbarMinSize: 50,
                    classNames: {
                        contentEl: 'simplebar-content',
                        scrollContent: 'simplebar-scroll-content',
                        scrollbar: 'simplebar-scrollbar',
                        track: 'simplebar-track'
                    }
                });
            }
        }
    }

    /**
     * Enable keyboard navigation for accessibility
     * @param {jQuery} $cartDropdown - Dropdown button
     * @param {jQuery} $dropdownMenu - Dropdown menu
     */
    function enableKeyboardNavigation($cartDropdown, $dropdownMenu) {
        // Handle Escape key to close dropdown
        $(document).on('keydown', function(e) {
            if (e.key === 'Escape' && $dropdownMenu.hasClass('show')) {
                $cartDropdown.dropdown('hide');
                $cartDropdown.focus();
            }
        });

        // Handle Tab key to navigate through cart items
        $dropdownMenu.on('keydown', 'a', function(e) {
            if (e.key === 'Tab') {
                var $items = $dropdownMenu.find('a');
                var currentIndex = $items.index(this);

                if (e.shiftKey) {
                    // Shift+Tab - move backwards
                    if (currentIndex === 0) {
                        e.preventDefault();
                        $cartDropdown.focus();
                    }
                } else {
                    // Tab - move forwards
                    if (currentIndex === $items.length - 1) {
                        e.preventDefault();
                        $cartDropdown.dropdown('hide');
                        $cartDropdown.focus();
                    }
                }
            }
        });
    }

    /**
     * Update mini cart badge count (for future AJAX updates)
     * @param {number} count - New item count
     */
    window.updateMiniCartCount = function(count) {
        var $badge = $('#page-header-cart-dropdown .badge');

        if (count > 0) {
            if ($badge.length) {
                // Animate count change
                $badge.addClass('scale-animation');
                setTimeout(function() {
                    $badge.text(count).removeClass('scale-animation');
                }, 200);
            } else {
                // Add new badge with animation
                var $newBadge = $('<span class="badge bg-danger rounded-pill">' + count + '</span>');
                $('#page-header-cart-dropdown i').after($newBadge);
                setTimeout(function() {
                    $newBadge.addClass('scale-in');
                }, 10);
            }
        } else {
            // Remove badge with fade out
            if ($badge.length) {
                $badge.fadeOut(200, function() {
                    $(this).remove();
                });
            }
        }
    };

    /**
     * Update mini cart header text
     * @param {number} count - Item count
     */
    window.updateMiniCartHeader = function(count) {
        var $header = $('.dropdown-menu .p-3.border-bottom h6');
        var $badge = $('.dropdown-menu .p-3.border-bottom .badge');

        if ($badge.length) {
            var pluralText = count === 1 ? 'product' : 'products';
            $badge.text(count + ' ' + pluralText);
        }
    };

    /**
     * Refresh mini cart content (for future AJAX updates)
     * @param {string} url - URL to fetch cart data (optional)
     */
    window.refreshMiniCart = function(url) {
        var $dropdownMenu = $('#page-header-cart-dropdown').next('.dropdown-menu');

        // Add loading state
        $dropdownMenu.addClass('mini-cart-loading');

        if (url) {
            // Future: AJAX call to fetch updated cart data
            $.get(url, function(data) {
                // Update cart content
                $dropdownMenu.html(data);
                $dropdownMenu.removeClass('mini-cart-loading');

                // Re-initialize SimpleBar
                initializeScrollbar($dropdownMenu);
            }).fail(function() {
                console.error('Failed to refresh mini cart');
                $dropdownMenu.removeClass('mini-cart-loading');
            });
        } else {
            // Fallback: reload page
            location.reload();
        }
    };

    /**
     * Add notification/toast when item added to cart
     * @param {string} message - Message to display
     */
    window.showCartNotification = function(message) {
        // You can integrate with your notification system here
        if (typeof toastr !== 'undefined') {
            toastr.success(message, 'Cart Updated');
        } else {
            console.log('Cart notification:', message);
        }
    };

})(jQuery);
