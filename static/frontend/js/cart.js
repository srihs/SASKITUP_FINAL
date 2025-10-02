/**
 * SASKITUP Shopping Cart JavaScript
 * Comprehensive cart management with school-specific features
 */

class SaskitupCart {
    constructor() {
        this.cart = this.loadCart();
        this.schools = new Map();
        this.bulkPricingTiers = this.loadBulkPricingTiers();
        this.promoCodesList = this.loadPromoCodes();
        this.currentPromoCodes = [];

        this.initializeEventListeners();
        this.initializeCart();
        this.updateCartDisplay();
    }

    /**
     * Initialize event listeners for cart functionality
     */
    initializeEventListeners() {
        // Quantity controls
        document.addEventListener('click', (e) => {
            if (e.target.matches('.qty-decrease, .qty-decrease *')) {
                e.preventDefault();
                const button = e.target.closest('.qty-decrease');
                this.updateQuantity(button, 'decrease');
            }

            if (e.target.matches('.qty-increase, .qty-increase *')) {
                e.preventDefault();
                const button = e.target.closest('.qty-increase');
                this.updateQuantity(button, 'increase');
            }
        });

        // Quantity input changes
        document.addEventListener('change', (e) => {
            if (e.target.matches('.qty-input')) {
                this.updateQuantityFromInput(e.target);
            }
        });

        // Item actions
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-edit, .btn-edit *')) {
                e.preventDefault();
                const button = e.target.closest('.btn-edit');
                this.editItem(button);
            }

            if (e.target.matches('.btn-save-later, .btn-save-later *')) {
                e.preventDefault();
                const button = e.target.closest('.btn-save-later');
                this.saveForLater(button);
            }

            if (e.target.matches('.btn-remove, .btn-remove *')) {
                e.preventDefault();
                const button = e.target.closest('.btn-remove');
                this.removeItem(button);
            }
        });

        // School actions
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-collapse, .btn-collapse *')) {
                e.preventDefault();
                const button = e.target.closest('.btn-collapse');
                this.toggleSchoolSection(button);
            }

            if (e.target.matches('.btn-contact-coordinator')) {
                e.preventDefault();
                this.contactCoordinator(e.target);
            }

            if (e.target.matches('.btn-change-delivery')) {
                e.preventDefault();
                this.changeDeliveryMethod(e.target);
            }
        });

        // Bulk actions
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-bulk-edit')) {
                e.preventDefault();
                this.openBulkEditModal();
            }

            if (e.target.matches('.btn-apply-promo')) {
                e.preventDefault();
                this.openPromoModal();
            }

            if (e.target.matches('.btn-save-cart')) {
                e.preventDefault();
                this.saveCart();
            }
        });

        // Promo code functionality
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-apply-code')) {
                e.preventDefault();
                this.applyPromoCode();
            }

            if (e.target.matches('.btn-remove-promo')) {
                e.preventDefault();
                this.removePromoCode(e.target);
            }

            if (e.target.matches('.btn-apply-promo-code')) {
                e.preventDefault();
                this.applyPromoCodeFromModal(e.target);
            }
        });

        // Saved items
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-move-to-cart')) {
                e.preventDefault();
                this.moveToCart(e.target);
            }

            if (e.target.matches('.btn-remove-saved')) {
                e.preventDefault();
                this.removeSavedItem(e.target);
            }
        });

        // Recently viewed
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-add-recent')) {
                e.preventDefault();
                this.addRecentToCart(e.target);
            }
        });

        // Checkout
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn-checkout')) {
                e.preventDefault();
                this.proceedToCheckout();
            }
        });

        // Modal functionality
        document.addEventListener('click', (e) => {
            if (e.target.matches('.modal-close, .modal-close *')) {
                e.preventDefault();
                this.closeModal();
            }

            if (e.target.matches('.modal')) {
                if (e.target === e.currentTarget) {
                    this.closeModal();
                }
            }
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });

        // Payment method changes
        document.addEventListener('change', (e) => {
            if (e.target.matches('input[name="payment"]')) {
                this.updatePaymentMethod(e.target.value);
            }
        });

        // Auto-save cart on changes
        document.addEventListener('cartUpdated', () => {
            this.saveCart();
        });
    }

    /**
     * Initialize cart data and display
     */
    initializeCart() {
        // Load cart items from localStorage or API
        this.organizeItemsBySchool();
        this.calculateBulkPricing();
        this.validateGradeLevels();
        this.checkStockAvailability();
    }

    /**
     * Load cart data from localStorage
     */
    loadCart() {
        try {
            const savedCart = localStorage.getItem('saskitup_cart');
            return savedCart ? JSON.parse(savedCart) : {
                items: [],
                savedItems: [],
                promoCode: null,
                notes: '',
                paymentMethod: 'school-account'
            };
        } catch (error) {
            console.error('Error loading cart:', error);
            return {
                items: [],
                savedItems: [],
                promoCode: null,
                notes: '',
                paymentMethod: 'school-account'
            };
        }
    }

    /**
     * Load bulk pricing tiers
     */
    loadBulkPricingTiers() {
        return {
            tier1: { min: 1, max: 9, discount: 0 },
            tier2: { min: 10, max: 24, discount: 0.10 },
            tier3: { min: 25, max: 49, discount: 0.15 },
            tier4: { min: 50, max: 99, discount: 0.20 },
            tier5: { min: 100, max: Infinity, discount: 0.25 }
        };
    }

    /**
     * Load available promo codes
     */
    loadPromoCodes() {
        return [
            {
                code: 'SCHOOL2024',
                description: '$10 off school orders over $50',
                type: 'fixed',
                value: 10,
                minOrder: 50,
                validFor: ['school-account']
            },
            {
                code: 'BULK15',
                description: '15% off bulk orders (20+ items)',
                type: 'percentage',
                value: 15,
                minQuantity: 20
            },
            {
                code: 'NEWSCHOOL',
                description: '20% off first order for new schools',
                type: 'percentage',
                value: 20,
                newSchoolOnly: true
            },
            {
                code: 'CUSTOM5',
                description: '$5 off custom items',
                type: 'fixed',
                value: 5,
                customOnly: true
            }
        ];
    }

    /**
     * Organize cart items by school
     */
    organizeItemsBySchool() {
        this.schools.clear();

        // Get all cart items from DOM
        const cartItems = document.querySelectorAll('.cart-item');

        cartItems.forEach(item => {
            const schoolGroup = item.closest('.school-group');
            const schoolId = schoolGroup.dataset.schoolId;

            if (!this.schools.has(schoolId)) {
                this.schools.set(schoolId, {
                    id: schoolId,
                    name: schoolGroup.querySelector('.school-name').textContent.trim(),
                    items: [],
                    deliveryMethod: this.getDeliveryMethod(schoolGroup),
                    coordinator: this.getCoordinatorInfo(schoolGroup)
                });
            }

            const school = this.schools.get(schoolId);
            school.items.push(this.getItemData(item));
        });
    }

    /**
     * Get item data from DOM element
     */
    getItemData(itemElement) {
        const itemId = itemElement.dataset.itemId;
        const nameElement = itemElement.querySelector('.item-name');
        const priceElement = itemElement.querySelector('.final-price');
        const qtyElement = itemElement.querySelector('.qty-input');
        const customization = this.getCustomizationData(itemElement);

        return {
            id: itemId,
            name: nameElement ? nameElement.textContent.trim() : '',
            basePrice: this.extractPrice(itemElement.querySelector('.base-price')),
            customizationFee: this.extractPrice(itemElement.querySelector('.custom-fee')),
            quantity: parseInt(qtyElement ? qtyElement.value : 1),
            customization: customization,
            requiresApproval: itemElement.querySelector('.approval-status') !== null,
            specs: this.getItemSpecs(itemElement)
        };
    }

    /**
     * Get customization data from item
     */
    getCustomizationData(itemElement) {
        const customDetails = itemElement.querySelector('.customization-details');
        if (!customDetails) return null;

        const customFields = customDetails.querySelectorAll('.custom-field');
        const customization = {};

        customFields.forEach(field => {
            const text = field.textContent.trim();
            const [key, value] = text.split(':').map(s => s.trim());
            if (key && value) {
                customization[key.toLowerCase().replace(/\s+/g, '_')] = value;
            }
        });

        return Object.keys(customization).length > 0 ? customization : null;
    }

    /**
     * Get item specifications
     */
    getItemSpecs(itemElement) {
        const specs = {};
        const specItems = itemElement.querySelectorAll('.spec-item');

        specItems.forEach(spec => {
            const text = spec.textContent.trim();
            const [key, value] = text.split(':').map(s => s.trim());
            if (key && value) {
                specs[key.toLowerCase()] = value;
            }
        });

        return specs;
    }

    /**
     * Extract price from element
     */
    extractPrice(element) {
        if (!element) return 0;
        const text = element.textContent.trim();
        const match = text.match(/\$?([\d,]+\.?\d*)/);
        return match ? parseFloat(match[1].replace(',', '')) : 0;
    }

    /**
     * Get delivery method for school
     */
    getDeliveryMethod(schoolGroup) {
        const deliveryElement = schoolGroup.querySelector('.delivery-method');
        return deliveryElement ? deliveryElement.textContent.trim() : 'School Delivery';
    }

    /**
     * Get coordinator information
     */
    getCoordinatorInfo(schoolGroup) {
        const coordinatorElement = schoolGroup.querySelector('.school-coordinator');
        if (!coordinatorElement) return null;

        const text = coordinatorElement.textContent.trim();
        const emailMatch = text.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
        const nameMatch = text.match(/Coordinator:\s*([^-]+)/);

        return {
            name: nameMatch ? nameMatch[1].trim() : '',
            email: emailMatch ? emailMatch[1] : ''
        };
    }

    /**
     * Update item quantity
     */
    updateQuantity(button, action) {
        const cartItem = button.closest('.cart-item');
        const qtyInput = cartItem.querySelector('.qty-input');
        const currentQty = parseInt(qtyInput.value);

        let newQty;
        if (action === 'increase') {
            newQty = Math.min(currentQty + 1, 100);
        } else {
            newQty = Math.max(currentQty - 1, 1);
        }

        qtyInput.value = newQty;
        this.updateItemTotal(cartItem);
        this.updateSchoolSubtotal(cartItem.closest('.school-group'));
        this.updateCartSummary();
        this.checkBulkPricing();

        // Announce change for accessibility
        this.announceChange(`Quantity updated to ${newQty}`);

        // Dispatch custom event
        document.dispatchEvent(new CustomEvent('cartUpdated', {
            detail: {
                action: 'quantity_changed',
                itemId: cartItem.dataset.itemId,
                newQuantity: newQty,
                message: `Quantity updated to ${newQty}`
            }
        }));
    }

    /**
     * Update quantity from input field
     */
    updateQuantityFromInput(input) {
        const cartItem = input.closest('.cart-item');
        const newQty = Math.max(1, Math.min(100, parseInt(input.value) || 1));

        input.value = newQty;
        this.updateItemTotal(cartItem);
        this.updateSchoolSubtotal(cartItem.closest('.school-group'));
        this.updateCartSummary();
        this.checkBulkPricing();

        document.dispatchEvent(new CustomEvent('cartUpdated', {
            detail: {
                action: 'quantity_changed',
                itemId: cartItem.dataset.itemId,
                newQuantity: newQty,
                message: `Quantity updated to ${newQty}`
            }
        }));
    }

    /**
     * Update individual item total
     */
    updateItemTotal(cartItem) {
        const qtyInput = cartItem.querySelector('.qty-input');
        const finalPriceElement = cartItem.querySelector('.final-price');
        const totalPriceElement = cartItem.querySelector('.total-price');

        const quantity = parseInt(qtyInput.value);
        const unitPrice = this.extractPrice(finalPriceElement);
        const total = quantity * unitPrice;

        if (totalPriceElement) {
            totalPriceElement.textContent = `$${total.toFixed(2)}`;
        }

        // Update bulk pricing indicator
        this.updateBulkPricingIndicator(cartItem);
    }

    /**
     * Update bulk pricing indicator for item
     */
    updateBulkPricingIndicator(cartItem) {
        const schoolGroup = cartItem.closest('.school-group');
        const totalQuantity = this.getTotalSchoolQuantity(schoolGroup);
        const bulkInfo = cartItem.querySelector('.bulk-pricing-info');

        if (bulkInfo) {
            const tier = this.getBulkTier(totalQuantity);
            const nextTier = this.getNextBulkTier(totalQuantity);

            const tierSpan = bulkInfo.querySelector('.bulk-tier');
            const nextTierSpan = bulkInfo.querySelector('.next-tier');

            if (tierSpan) {
                tierSpan.textContent = `Tier ${tier.number}: ${tier.min}+ items (${(tier.discount * 100).toFixed(0)}% off)`;
            }

            if (nextTierSpan && nextTier) {
                const needed = nextTier.min - totalQuantity;
                nextTierSpan.textContent = `${needed} more for Tier ${nextTier.number}`;
            } else if (nextTierSpan) {
                nextTierSpan.textContent = 'Max tier reached!';
            }
        }
    }

    /**
     * Get total quantity for a school
     */
    getTotalSchoolQuantity(schoolGroup) {
        const qtyInputs = schoolGroup.querySelectorAll('.qty-input');
        let total = 0;

        qtyInputs.forEach(input => {
            total += parseInt(input.value) || 0;
        });

        return total;
    }

    /**
     * Get bulk pricing tier
     */
    getBulkTier(quantity) {
        for (const [key, tier] of Object.entries(this.bulkPricingTiers)) {
            if (quantity >= tier.min && quantity <= tier.max) {
                return {
                    ...tier,
                    number: parseInt(key.replace('tier', ''))
                };
            }
        }
        return this.bulkPricingTiers.tier1;
    }

    /**
     * Get next bulk pricing tier
     */
    getNextBulkTier(quantity) {
        for (const [key, tier] of Object.entries(this.bulkPricingTiers)) {
            if (quantity < tier.min) {
                return {
                    ...tier,
                    number: parseInt(key.replace('tier', ''))
                };
            }
        }
        return null;
    }

    /**
     * Update school subtotal
     */
    updateSchoolSubtotal(schoolGroup) {
        const cartItems = schoolGroup.querySelectorAll('.cart-item');
        let subtotal = 0;
        let savings = 0;

        cartItems.forEach(item => {
            const totalPrice = this.extractPrice(item.querySelector('.total-price'));
            const savingsElement = item.querySelector('.savings');
            const itemSavings = savingsElement ? this.extractPrice(savingsElement) : 0;

            subtotal += totalPrice;
            savings += itemSavings;
        });

        const subtotalElement = schoolGroup.querySelector('.subtotal-amount');
        const savingsElement = schoolGroup.querySelector('.savings-amount');

        if (subtotalElement) {
            subtotalElement.textContent = `$${subtotal.toFixed(2)}`;
        }

        if (savingsElement) {
            savingsElement.textContent = `$${savings.toFixed(2)}`;
        }
    }

    /**
     * Calculate and apply bulk pricing
     */
    calculateBulkPricing() {
        this.schools.forEach(school => {
            const schoolGroup = document.querySelector(`[data-school-id="${school.id}"]`);
            if (!schoolGroup) return;

            const totalQuantity = this.getTotalSchoolQuantity(schoolGroup);
            const tier = this.getBulkTier(totalQuantity);

            // Apply bulk discount to applicable items
            const cartItems = schoolGroup.querySelectorAll('.cart-item');
            cartItems.forEach(item => {
                this.applyBulkDiscountToItem(item, tier.discount);
            });
        });
    }

    /**
     * Apply bulk discount to individual item
     */
    applyBulkDiscountToItem(cartItem, discountRate) {
        const basePriceElement = cartItem.querySelector('.base-price');
        const bulkDiscountElement = cartItem.querySelector('.bulk-discount');
        const finalPriceElement = cartItem.querySelector('.final-price');

        if (!basePriceElement || !finalPriceElement) return;

        const basePrice = this.extractPrice(basePriceElement);
        const customFee = this.extractPrice(cartItem.querySelector('.custom-fee')) || 0;
        const bulkDiscount = basePrice * discountRate;
        const finalPrice = basePrice - bulkDiscount + customFee;

        if (bulkDiscountElement) {
            bulkDiscountElement.textContent = `-$${bulkDiscount.toFixed(2)}`;
        }

        finalPriceElement.textContent = `$${finalPrice.toFixed(2)}`;

        // Update item total
        this.updateItemTotal(cartItem);
    }

    /**
     * Check bulk pricing across all schools
     */
    checkBulkPricing() {
        this.calculateBulkPricing();
        this.updateCartSummary();
    }

    /**
     * Update main cart summary
     */
    updateCartSummary() {
        let itemsSubtotal = 0;
        let totalSavings = 0;
        let customizationFees = 0;
        let shipping = 0;
        let itemCount = 0;
        let schoolCount = 0;

        // Calculate totals from all schools
        document.querySelectorAll('.school-group').forEach(schoolGroup => {
            schoolCount++;

            const subtotal = this.extractPrice(schoolGroup.querySelector('.subtotal-amount'));
            const savings = this.extractPrice(schoolGroup.querySelector('.savings-amount'));
            const shippingCost = this.extractPrice(schoolGroup.querySelector('.shipping-amount')) || 0;

            itemsSubtotal += subtotal;
            totalSavings += savings;
            shipping += shippingCost;

            // Count items and customization fees
            schoolGroup.querySelectorAll('.cart-item').forEach(item => {
                const qty = parseInt(item.querySelector('.qty-input').value);
                itemCount += qty;

                const customFee = this.extractPrice(item.querySelector('.custom-fee')) || 0;
                customizationFees += customFee * qty;
            });
        });

        // Apply promo code discounts
        const promoDiscount = this.calculatePromoDiscount(itemsSubtotal, itemCount);

        // Calculate tax (8.25% in this example)
        const taxableAmount = itemsSubtotal + customizationFees + shipping - promoDiscount;
        const tax = taxableAmount * 0.0825;

        const total = taxableAmount + tax;

        // Update summary display
        this.updateSummaryDisplay({
            itemsSubtotal,
            totalSavings,
            customizationFees,
            shipping,
            promoDiscount,
            tax,
            total,
            itemCount,
            schoolCount
        });

        // Update header badges
        this.updateHeaderBadges(schoolCount, itemCount, totalSavings);
    }

    /**
     * Update summary display elements
     */
    updateSummaryDisplay(totals) {
        const elements = {
            itemsSubtotal: document.querySelector('.breakdown-item:nth-child(1) span:last-child'),
            bulkDiscounts: document.querySelector('.breakdown-item:nth-child(2) span:last-child'),
            schoolDiscounts: document.querySelector('.breakdown-item:nth-child(3) span:last-child'),
            customizationFees: document.querySelector('.breakdown-item:nth-child(4) span:last-child'),
            shipping: document.querySelector('.breakdown-item:nth-child(5) span:last-child'),
            tax: document.querySelector('.breakdown-item:nth-child(6) span:last-child'),
            total: document.querySelector('.total-line strong'),
            savings: document.querySelector('.total-savings')
        };

        if (elements.itemsSubtotal) {
            elements.itemsSubtotal.textContent = `$${totals.itemsSubtotal.toFixed(2)}`;
            // Update item count in label
            const label = elements.itemsSubtotal.closest('.breakdown-item').querySelector('span:first-child');
            if (label) {
                label.textContent = `Items Subtotal (${totals.itemCount} items):`;
            }
        }

        if (elements.bulkDiscounts) {
            elements.bulkDiscounts.textContent = `-$${(totals.totalSavings * 0.6).toFixed(2)}`;
        }

        if (elements.schoolDiscounts) {
            elements.schoolDiscounts.textContent = `-$${(totals.totalSavings * 0.4).toFixed(2)}`;
        }

        if (elements.customizationFees) {
            elements.customizationFees.textContent = `$${totals.customizationFees.toFixed(2)}`;
        }

        if (elements.shipping) {
            elements.shipping.textContent = `$${totals.shipping.toFixed(2)}`;
        }

        if (elements.tax) {
            elements.tax.textContent = `$${totals.tax.toFixed(2)}`;
        }

        if (elements.total) {
            elements.total.textContent = `Total: $${totals.total.toFixed(2)}`;
        }

        if (elements.savings) {
            const totalSavingsAmount = totals.totalSavings + totals.promoDiscount;
            elements.savings.textContent = `You saved $${totalSavingsAmount.toFixed(2)}!`;
        }
    }

    /**
     * Update header badges
     */
    updateHeaderBadges(schoolCount, itemCount, savings) {
        const schoolsBadge = document.getElementById('schoolsBadge');
        const itemsBadge = document.getElementById('itemsBadge');
        const savingsBadge = document.getElementById('savingsBadge');

        if (schoolsBadge) {
            schoolsBadge.textContent = `${schoolCount} School${schoolCount !== 1 ? 's' : ''}`;
        }

        if (itemsBadge) {
            itemsBadge.textContent = `${itemCount} Item${itemCount !== 1 ? 's' : ''}`;
        }

        if (savingsBadge) {
            savingsBadge.textContent = `$${savings.toFixed(2)} Saved`;
        }

        // Update cart count in header
        const cartCount = document.getElementById('cartCount');
        if (cartCount) {
            cartCount.textContent = itemCount;
        }
    }

    /**
     * Calculate promo code discount
     */
    calculatePromoDiscount(subtotal, itemCount) {
        let totalDiscount = 0;

        this.currentPromoCodes.forEach(promoCode => {
            const promo = this.promoCodesList.find(p => p.code === promoCode);
            if (!promo) return;

            // Check if promo code is applicable
            if (promo.minOrder && subtotal < promo.minOrder) return;
            if (promo.minQuantity && itemCount < promo.minQuantity) return;

            // Calculate discount
            if (promo.type === 'fixed') {
                totalDiscount += promo.value;
            } else if (promo.type === 'percentage') {
                totalDiscount += subtotal * (promo.value / 100);
            }
        });

        return totalDiscount;
    }

    /**
     * Validate grade levels for items
     */
    validateGradeLevels() {
        document.querySelectorAll('.cart-item').forEach(item => {
            const gradeValidation = item.querySelector('.grade-validation');
            if (gradeValidation) {
                // This would typically validate against the student's actual grade
                // For now, we'll assume all items are valid
                const icon = gradeValidation.querySelector('i');
                const text = gradeValidation.querySelector('span');

                if (icon && text) {
                    icon.className = 'fas fa-check-circle text-success';
                    text.textContent = 'Grade level verified';
                }
            }
        });
    }

    /**
     * Check stock availability
     */
    checkStockAvailability() {
        document.querySelectorAll('.cart-item').forEach(item => {
            const stockInfo = item.querySelector('.stock-info');
            if (stockInfo) {
                // This would typically check against real inventory
                // For demo purposes, we'll show random stock levels
                const stockLevel = Math.floor(Math.random() * 50) + 10;
                const stockStatus = stockInfo.querySelector('.stock-status');

                if (stockStatus) {
                    if (stockLevel > 20) {
                        stockStatus.textContent = `${stockLevel} in stock`;
                        stockStatus.className = 'stock-status text-success';
                    } else if (stockLevel > 5) {
                        stockStatus.textContent = `${stockLevel} in stock`;
                        stockStatus.className = 'stock-status text-warning';
                    } else {
                        stockStatus.textContent = `Only ${stockLevel} left!`;
                        stockStatus.className = 'stock-status text-error';
                    }
                }
            }
        });
    }

    /**
     * Edit item functionality
     */
    editItem(button) {
        const cartItem = button.closest('.cart-item');
        const itemData = this.getItemData(cartItem);

        // For demo purposes, we'll show an alert
        // In a real implementation, this would open an edit modal
        alert(`Edit functionality for ${itemData.name} would open here.\n\nFeatures:\n- Size/color modifications\n- Customization changes\n- Quantity adjustments\n- Special requests`);
    }

    /**
     * Save item for later
     */
    saveForLater(button) {
        const cartItem = button.closest('.cart-item');
        const itemData = this.getItemData(cartItem);

        // Add to saved items
        this.addToSavedItems(itemData);

        // Remove from cart with animation
        this.removeItemFromCart(cartItem, 'Moved to saved items');

        this.announceChange(`${itemData.name} moved to saved items`);
    }

    /**
     * Add item to saved items list
     */
    addToSavedItems(itemData) {
        if (!this.cart.savedItems) {
            this.cart.savedItems = [];
        }

        this.cart.savedItems.push(itemData);
        this.updateSavedItemsDisplay();
    }

    /**
     * Update saved items display
     */
    updateSavedItemsDisplay() {
        const savedTitle = document.querySelector('.saved-title');
        if (savedTitle) {
            savedTitle.innerHTML = `
                <i class="fas fa-bookmark"></i>
                Saved for Later (${this.cart.savedItems.length} items)
            `;
        }
    }

    /**
     * Remove item from cart
     */
    removeItem(button) {
        const cartItem = button.closest('.cart-item');
        const itemData = this.getItemData(cartItem);

        if (confirm(`Remove ${itemData.name} from your cart?`)) {
            this.removeItemFromCart(cartItem, 'Item removed from cart');
        }
    }

    /**
     * Remove item from cart with animation
     */
    removeItemFromCart(cartItem, message) {
        const schoolGroup = cartItem.closest('.school-group');

        // Add remove animation
        cartItem.style.transition = 'all 0.3s ease';
        cartItem.style.transform = 'translateX(-100%)';
        cartItem.style.opacity = '0';

        setTimeout(() => {
            cartItem.remove();

            // Check if school group is now empty
            const remainingItems = schoolGroup.querySelectorAll('.cart-item');
            if (remainingItems.length === 0) {
                schoolGroup.style.transition = 'all 0.3s ease';
                schoolGroup.style.transform = 'scale(0.9)';
                schoolGroup.style.opacity = '0';

                setTimeout(() => {
                    schoolGroup.remove();
                    this.updateCartSummary();
                }, 300);
            } else {
                this.updateSchoolSubtotal(schoolGroup);
                this.updateCartSummary();
            }

            this.checkBulkPricing();
            this.announceChange(message);

            document.dispatchEvent(new CustomEvent('cartUpdated', {
                detail: {
                    action: 'item_removed',
                    message: message
                }
            }));
        }, 300);
    }

    /**
     * Toggle school section collapse
     */
    toggleSchoolSection(button) {
        const target = button.dataset.target;
        const section = document.getElementById(target);
        const icon = button.querySelector('i');

        if (section) {
            if (section.style.display === 'none') {
                section.style.display = 'block';
                icon.className = 'fas fa-chevron-up';
                this.announceChange('School section expanded');
            } else {
                section.style.display = 'none';
                icon.className = 'fas fa-chevron-down';
                this.announceChange('School section collapsed');
            }
        }
    }

    /**
     * Contact coordinator
     */
    contactCoordinator(button) {
        const schoolGroup = button.closest('.school-group');
        const coordinator = this.getCoordinatorInfo(schoolGroup);

        if (coordinator && coordinator.email) {
            const subject = encodeURIComponent('SASKITUP Order Inquiry');
            const body = encodeURIComponent(`Hello ${coordinator.name},\n\nI have a question about my upcoming order.\n\nBest regards`);

            window.location.href = `mailto:${coordinator.email}?subject=${subject}&body=${body}`;
        } else {
            alert('Coordinator contact information not available. Please contact customer service.');
        }
    }

    /**
     * Change delivery method
     */
    changeDeliveryMethod(button) {
        const schoolGroup = button.closest('.school-group');
        const currentMethod = schoolGroup.querySelector('.delivery-method').textContent.trim();

        const newMethod = currentMethod === 'Individual Shipping' ? 'School Delivery' : 'Individual Shipping';

        if (confirm(`Change delivery method to "${newMethod}"?`)) {
            schoolGroup.querySelector('.delivery-method').textContent = newMethod;

            // Update shipping costs
            this.updateShippingCosts(schoolGroup, newMethod);
            this.updateCartSummary();

            this.announceChange(`Delivery method changed to ${newMethod}`);
        }
    }

    /**
     * Update shipping costs based on delivery method
     */
    updateShippingCosts(schoolGroup, deliveryMethod) {
        const shippingElement = schoolGroup.querySelector('.shipping-amount');
        const warningElement = schoolGroup.querySelector('.delivery-warning');

        if (deliveryMethod === 'School Delivery') {
            if (shippingElement) {
                shippingElement.textContent = '$0.00';
            }
            if (warningElement) {
                warningElement.style.display = 'none';
            }
        } else {
            if (shippingElement) {
                shippingElement.textContent = '$8.95';
            }
            if (warningElement) {
                warningElement.style.display = 'flex';
            }
        }
    }

    /**
     * Apply promo code
     */
    applyPromoCode() {
        const input = document.querySelector('.promo-code-input');
        const code = input.value.trim().toUpperCase();

        if (!code) {
            this.showMessage('Please enter a promo code', 'error');
            return;
        }

        const promo = this.promoCodesList.find(p => p.code === code);

        if (!promo) {
            this.showMessage('Invalid promo code', 'error');
            return;
        }

        if (this.currentPromoCodes.includes(code)) {
            this.showMessage('Promo code already applied', 'warning');
            return;
        }

        // Validate promo code conditions
        const totalItems = this.getTotalItemCount();
        const subtotal = this.getCartSubtotal();

        if (promo.minOrder && subtotal < promo.minOrder) {
            this.showMessage(`Minimum order of $${promo.minOrder} required`, 'error');
            return;
        }

        if (promo.minQuantity && totalItems < promo.minQuantity) {
            this.showMessage(`Minimum ${promo.minQuantity} items required`, 'error');
            return;
        }

        // Apply promo code
        this.currentPromoCodes.push(code);
        this.displayActivePromo(promo);
        this.updateCartSummary();

        input.value = '';
        this.showMessage(`Promo code "${code}" applied successfully!`, 'success');

        this.announceChange(`Promo code ${code} applied`);
    }

    /**
     * Display active promo code
     */
    displayActivePromo(promo) {
        const activePromosContainer = document.querySelector('.active-promos');
        if (!activePromosContainer) return;

        const promoElement = document.createElement('div');
        promoElement.className = 'active-promo';
        promoElement.innerHTML = `
            <span class="promo-name">${promo.code}</span>
            <span class="promo-discount">-$${this.calculatePromoValue(promo).toFixed(2)}</span>
            <button class="btn-remove-promo" data-code="${promo.code}">×</button>
        `;

        activePromosContainer.appendChild(promoElement);
    }

    /**
     * Calculate promo code value
     */
    calculatePromoValue(promo) {
        const subtotal = this.getCartSubtotal();

        if (promo.type === 'fixed') {
            return promo.value;
        } else if (promo.type === 'percentage') {
            return subtotal * (promo.value / 100);
        }

        return 0;
    }

    /**
     * Remove promo code
     */
    removePromoCode(button) {
        const code = button.dataset.code;
        const promoElement = button.closest('.active-promo');

        // Remove from active codes
        this.currentPromoCodes = this.currentPromoCodes.filter(c => c !== code);

        // Remove from display
        promoElement.remove();

        // Update totals
        this.updateCartSummary();

        this.showMessage(`Promo code "${code}" removed`, 'info');
        this.announceChange(`Promo code ${code} removed`);
    }

    /**
     * Open promo code modal
     */
    openPromoModal() {
        const modal = document.getElementById('promoModal');
        if (modal) {
            modal.classList.add('show');

            // Populate promo list
            const promoList = modal.querySelector('.promo-list');
            if (promoList) {
                promoList.innerHTML = this.promoCodesList.map(promo => `
                    <div class="promo-item">
                        <div class="promo-code">${promo.code}</div>
                        <div class="promo-description">${promo.description}</div>
                        <button class="btn-apply-promo-code" data-code="${promo.code}">Apply</button>
                    </div>
                `).join('');
            }
        }
    }

    /**
     * Apply promo code from modal
     */
    applyPromoCodeFromModal(button) {
        const code = button.dataset.code;
        const input = document.querySelector('.promo-code-input');

        if (input) {
            input.value = code;
            this.applyPromoCode();
        }

        this.closeModal();
    }

    /**
     * Close modal
     */
    closeModal() {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.classList.remove('show');
        });
    }

    /**
     * Move saved item to cart
     */
    moveToCart(button) {
        const savedItem = button.closest('.saved-item');
        const itemName = savedItem.querySelector('h4').textContent.trim();

        // In a real implementation, this would add the item back to the cart
        this.showMessage(`"${itemName}" moved to cart`, 'success');

        // Remove from saved items with animation
        savedItem.style.transition = 'all 0.3s ease';
        savedItem.style.transform = 'translateX(100%)';
        savedItem.style.opacity = '0';

        setTimeout(() => {
            savedItem.remove();
            this.updateSavedItemsDisplay();
        }, 300);

        this.announceChange(`${itemName} moved to cart`);
    }

    /**
     * Remove saved item
     */
    removeSavedItem(button) {
        const savedItem = button.closest('.saved-item');
        const itemName = savedItem.querySelector('h4').textContent.trim();

        if (confirm(`Remove "${itemName}" from saved items?`)) {
            savedItem.style.transition = 'all 0.3s ease';
            savedItem.style.transform = 'scale(0.9)';
            savedItem.style.opacity = '0';

            setTimeout(() => {
                savedItem.remove();
                this.updateSavedItemsDisplay();
            }, 300);

            this.announceChange(`${itemName} removed from saved items`);
        }
    }

    /**
     * Add recent item to cart
     */
    addRecentToCart(button) {
        const recentItem = button.closest('.recent-item');
        const itemName = recentItem.querySelector('.recent-name').textContent.trim();

        // In a real implementation, this would add the item to the cart
        this.showMessage(`"${itemName}" added to cart`, 'success');
        this.announceChange(`${itemName} added to cart`);
    }

    /**
     * Save cart to localStorage
     */
    saveCart() {
        try {
            localStorage.setItem('saskitup_cart', JSON.stringify(this.cart));
        } catch (error) {
            console.error('Error saving cart:', error);
        }
    }

    /**
     * Proceed to checkout
     */
    proceedToCheckout() {
        // Validate cart
        if (this.getTotalItemCount() === 0) {
            this.showMessage('Your cart is empty', 'error');
            return;
        }

        // Check for items requiring approval
        const approvalItems = document.querySelectorAll('.approval-status');
        if (approvalItems.length > 0) {
            const proceed = confirm('Some items require approval. Do you want to proceed to checkout?');
            if (!proceed) return;
        }

        // Show loading
        this.showLoading(true);

        // Simulate checkout process
        setTimeout(() => {
            this.showLoading(false);
            // In a real implementation, this would redirect to checkout page
            alert('Redirecting to secure checkout...');
        }, 2000);
    }

    /**
     * Update payment method
     */
    updatePaymentMethod(method) {
        this.cart.paymentMethod = method;
        this.announceChange(`Payment method changed to ${method.replace('-', ' ')}`);
    }

    /**
     * Get total item count
     */
    getTotalItemCount() {
        let total = 0;
        document.querySelectorAll('.qty-input').forEach(input => {
            total += parseInt(input.value) || 0;
        });
        return total;
    }

    /**
     * Get cart subtotal
     */
    getCartSubtotal() {
        let total = 0;
        document.querySelectorAll('.subtotal-amount').forEach(element => {
            total += this.extractPrice(element);
        });
        return total;
    }

    /**
     * Show loading overlay
     */
    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            if (show) {
                overlay.classList.add('show');
            } else {
                overlay.classList.remove('show');
            }
        }
    }

    /**
     * Show message to user
     */
    showMessage(message, type = 'info') {
        // Create temporary message element
        const messageElement = document.createElement('div');
        messageElement.className = `message message-${type}`;
        messageElement.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            z-index: 1000;
            transform: translateX(100%);
            transition: transform 0.3s ease;
        `;
        messageElement.textContent = message;

        document.body.appendChild(messageElement);

        // Animate in
        setTimeout(() => {
            messageElement.style.transform = 'translateX(0)';
        }, 100);

        // Remove after 3 seconds
        setTimeout(() => {
            messageElement.style.transform = 'translateX(100%)';
            setTimeout(() => {
                document.body.removeChild(messageElement);
            }, 300);
        }, 3000);
    }

    /**
     * Announce change for screen readers
     */
    announceChange(message) {
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = message;

        document.body.appendChild(announcement);

        setTimeout(() => {
            document.body.removeChild(announcement);
        }, 1000);
    }

    /**
     * Update cart display
     */
    updateCartDisplay() {
        this.updateCartSummary();
        this.checkBulkPricing();
        this.validateGradeLevels();
        this.checkStockAvailability();
    }
}

// Initialize cart when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.saskitupCart = new SaskitupCart();
});

// Additional utility functions

/**
 * Format currency
 */
function formatCurrency(amount) {
    return `$${parseFloat(amount).toFixed(2)}`;
}

/**
 * Debounce function for performance
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
 * Animate element
 */
function animateElement(element, animation, duration = 300) {
    element.style.transition = `all ${duration}ms ease`;
    element.style.transform = animation;

    setTimeout(() => {
        element.style.transform = '';
    }, duration);
}

// Export for module usage if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SaskitupCart;
}