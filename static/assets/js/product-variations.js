/**
 * Product Variations Manager
 * 
 * A comprehensive JavaScript library for managing dynamic product variations
 * with real-time stock checking and brand-specific styling.
 * 
 * Supports both LOTTO and SAS product systems with:
 * - Color swatches (clickable color boxes)
 * - Size buttons (clickable size options)  
 * - Age group buttons (Adult/Kids toggle)
 * - Stock status indicators
 * - Loading states during API calls
 * - Responsive design for mobile/desktop
 * 
 * @author Claude Code
 * @version 1.0.0
 */

class ProductVariationManager {
    constructor(productId, productType = 'lotto', options = {}) {
        this.productId = productId;
        this.productType = productType.toLowerCase();
        this.selectedVariations = {};
        this.variations = {};
        this.groupedVariations = {};
        this.basePrice = 0;
        this.currentPrice = 0;
        this.isLoading = false;
        
        // Configuration options
        this.options = {
            enableStockCheck: true,
            enablePriceUpdates: true,
            enableLoadingStates: true,
            debounceDelay: 300,
            animationDuration: 200,
            ...options
        };
        
        // Brand themes
        this.themes = {
            lotto: {
                primary: '#C9485B',
                secondary: '#E89DA2',
                disabled: '#6c757d',
                success: '#28a745',
                warning: '#ffc107',
                danger: '#dc3545'
            },
            sas: {
                primary: '#205295',
                secondary: '#2C74B3',
                disabled: '#6c757d',
                success: '#28a745',
                warning: '#ffc107',
                danger: '#dc3545'
            }
        };
        
        this.theme = this.themes[this.productType] || this.themes.lotto;
        
        // DOM elements cache
        this.elements = {};
        
        this.init();
    }
    
    /**
     * Initialize the variation manager
     */
    async init() {
        this.cacheElements();
        this.bindEvents();
        await this.loadVariations();
        this.setupInitialState();
        this.applyBrandStyling();
    }
    
    /**
     * Cache frequently used DOM elements
     */
    cacheElements() {
        this.elements = {
            container: document.querySelector('.variation-section, #productVariations'),
            colorOptions: document.querySelector('.color-options'),
            sizeOptions: document.querySelector('.size-options'),
            ageGroupOptions: document.querySelector('.age-group-options'),
            priceDisplay: document.querySelector('.current-price, #productPrice'),
            stockStatus: document.querySelector('.stock-status'),
            addToCartBtn: document.querySelector('.add-to-cart-btn, .btn-add-to-cart'),
            loadingOverlay: null, // Will be created dynamically
            initialLoadingMessage: document.querySelector('.variation-loading') // Template loading message
        };
        
        // Track initial stock visibility state
        this.stockStatusVisible = false;
        this.hasUserInteraction = false;
        
        // Store the initial price from the page
        if (this.elements.priceDisplay) {
            const priceText = this.elements.priceDisplay.textContent || this.elements.priceDisplay.innerText;
            const priceMatch = priceText.match(/\$([0-9.]+)/);
            if (priceMatch) {
                this.basePrice = parseFloat(priceMatch[1]);
                this.currentPrice = this.basePrice;
            }
        }
    }
    
    /**
     * Bind event listeners
     */
    bindEvents() {
        document.addEventListener('click', this.handleVariationClick.bind(this));
        document.addEventListener('keydown', this.handleKeyboardNavigation.bind(this));
        
        // Debounced stock checking
        this.debouncedStockCheck = this.debounce(this.checkStock.bind(this), this.options.debounceDelay);
    }
    
    /**
     * Load product variations from API
     */
    async loadVariations() {
        try {
            this.showLoading();
            
            const response = await fetch(`/clubs/api/${this.productType}/product/${this.productId}/variations/`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.variations = data.variations || [];
                this.groupedVariations = data.grouped_variations || {};
                this.basePrice = data.base_price || 0;
                this.currentPrice = this.basePrice;
                
                
                this.renderVariations();
            } else {
                console.error('API returned error:', data.error);
                this.showError(data.error || 'Failed to load product variations');
            }
        } catch (error) {
            console.error('Error loading variations:', error);
            this.showError('Unable to load product variations. Please refresh the page.');
        } finally {
            this.hideLoading();
        }
    }
    
    /**
     * Render variation selectors in the DOM
     */
    renderVariations() {
        // Re-cache the loading message in case it wasn't found initially
        if (!this.elements.initialLoadingMessage) {
            this.elements.initialLoadingMessage = document.querySelector('.variation-loading');
        }
        
        // Remove template's loading message when starting to render variations
        if (this.elements.initialLoadingMessage && this.elements.initialLoadingMessage.parentNode) {
            this.elements.initialLoadingMessage.parentNode.removeChild(this.elements.initialLoadingMessage);
            this.elements.initialLoadingMessage = null; // Clear reference after removal
        }
        
        // Clear existing variation containers to ensure proper ordering
        if (this.elements.container) {
            const existingGroups = this.elements.container.querySelectorAll('.variation-group');
            existingGroups.forEach(group => group.remove());
            
            // Clear cached element references to force creation of new containers
            this.elements.colorOptions = null;
            this.elements.sizeOptions = null;
            this.elements.ageGroupOptions = null;
        }
        
        // Render in specific order for SAS products: Age Group (Main Category) → Size (filtered) → Color
        // This matches the original site behavior and ensures proper DOM order
        if (this.productType === 'sas') {
            this.renderAgeGroupOptions(); // Main Category FIRST
            this.renderSizeOptions(); // Size filtering will be applied based on age group selection
            this.renderColorSwatches();
        } else {
            // Original order for LOTTO products
            this.renderColorSwatches();
            this.renderSizeOptions();
            this.renderAgeGroupOptions();
        }
        
        this.renderOtherVariations();
        
        // Initialize color image gallery after rendering variations
        setTimeout(() => {
            this.initializeColorImageGallery();
        }, 100);
    }
    
    /**
     * Render color swatches
     */
    renderColorSwatches() {
        if (!this.groupedVariations || !this.groupedVariations.color) {
            console.log('No color variations available');
            return;
        }
        
        const colors = this.groupedVariations.color || [];
        if (colors.length === 0) return;
        
        const container = this.elements.colorOptions || this.createVariationContainer('color', 'Color');
        container.innerHTML = '<div class="variation-title">Color:</div><div class="color-swatches"></div>';
        
        const swatchContainer = container.querySelector('.color-swatches');
        
        // Enhance color data with images from detailed variations
        const enhancedColors = colors.map(colorGroup => {
            // Find a variation with this color to get the image
            const variationWithImage = this.variations.find(v => 
                v.attributes && v.attributes.color === colorGroup.value
            );
            
            return {
                ...colorGroup,
                image: variationWithImage ? variationWithImage.image : null
            };
        });
        
        enhancedColors.forEach(variation => {
            const swatch = this.createColorSwatch(variation);
            swatchContainer.appendChild(swatch);
        });
    }
    
    /**
     * Create a color swatch element
     */
    createColorSwatch(variation) {
        const swatch = document.createElement('div');
        swatch.className = 'color-swatch';
        swatch.dataset.variationType = 'color';
        swatch.dataset.variationValue = variation.value;
        swatch.dataset.variationId = variation.id;
        swatch.dataset.available = variation.is_available;
        swatch.setAttribute('role', 'button');
        swatch.setAttribute('tabindex', '0');
        swatch.setAttribute('aria-label', `Select color ${variation.value}`);
        swatch.title = variation.value;
        
        // Store image URL for later use
        if (variation.image) {
            swatch.dataset.imageUrl = variation.image;
        }
        
        // Check if variation has an image URL
        if (variation.image) {
            // Create image element for color swatch
            const img = document.createElement('img');
            // Use the proxy URL for external images
            const imageUrl = variation.image.startsWith('http') ? 
                `/clubs/proxy-image/?url=${encodeURIComponent(variation.image)}` : 
                variation.image;
            img.src = imageUrl;
            img.alt = variation.value;
            img.className = 'color-swatch-image';
            img.loading = 'lazy';
            
            // Handle image load errors - fallback to color
            img.onerror = () => {
                img.style.display = 'none';
                const colorHex = this.getColorHex(variation.value);
                swatch.style.backgroundColor = colorHex;
                
                // Add border for white/light colors
                if (this.isLightColor(colorHex)) {
                    swatch.style.border = '2px solid #dee2e6';
                }
            };
            
            swatch.appendChild(img);
        } else {
            // Fallback to color-based swatch if no image
            const colorHex = this.getColorHex(variation.value);
            swatch.style.backgroundColor = colorHex;
            
            // Add border for white/light colors
            if (this.isLightColor(colorHex)) {
                swatch.style.border = '2px solid #dee2e6';
            }
        }
        
        // Add availability indicator
        if (!variation.is_available) {
            swatch.classList.add('disabled');
            const overlay = document.createElement('div');
            overlay.className = 'unavailable-overlay';
            overlay.innerHTML = '✕';
            swatch.appendChild(overlay);
        }
        
        return swatch;
    }
    
    /**
     * Render size options
     */
    renderSizeOptions() {
        if (!this.groupedVariations || !this.groupedVariations.size) {
            console.log('No size variations available');
            return;
        }
        
        const sizes = this.groupedVariations.size || [];
        if (sizes.length === 0) return;
        
        const container = this.elements.sizeOptions || this.createVariationContainer('size', 'Size');
        container.innerHTML = '<div class="variation-title">Size:</div><div class="size-buttons"></div>';
        
        const buttonContainer = container.querySelector('.size-buttons');
        
        // Apply filtering for SAS products
        let filteredSizes = sizes;
        if (this.productType === 'sas') {
            filteredSizes = this.getFilteredSizes(sizes);
        }
        
        // Sort sizes for better display
        const sortedSizes = this.sortSizes(filteredSizes);
        
        sortedSizes.forEach(variation => {
            const button = this.createSizeButton(variation);
            buttonContainer.appendChild(button);
        });
    }
    
    /**
     * Create a size button element (now as non-interactive label)
     */
    createSizeButton(variation) {
        const button = document.createElement('div');
        button.className = 'size-button';
        button.dataset.variationType = 'size';
        button.dataset.variationValue = variation.value;
        button.dataset.variationId = variation.id;
        button.dataset.available = variation.is_available;
        button.setAttribute('role', 'text');
        button.setAttribute('aria-label', `Size ${variation.value}`);
        button.textContent = variation.value;
        
        if (!variation.is_available) {
            button.classList.add('disabled');
            button.setAttribute('aria-disabled', 'true');
        }
        
        // Make completely non-interactive
        button.style.pointerEvents = 'none';
        button.style.cursor = 'default';
        
        return button;
    }
    
    /**
     * Render age group options
     */
    renderAgeGroupOptions() {
        if (!this.groupedVariations) {
            console.log('No grouped variations available for age groups');
            return;
        }
        
        const ageGroups = this.groupedVariations.age_group || this.groupedVariations.gender || [];
        if (ageGroups.length === 0) return;
        
        // For SAS products, show as "Select Main Category" instead of "Age Group"
        const title = this.productType === 'sas' ? 'Select Main Category' : 'Age Group';
        const container = this.elements.ageGroupOptions || this.createVariationContainer('age_group', title);
        container.innerHTML = `<div class="variation-title">${title}:</div><div class="age-group-buttons"></div>`;
        
        const buttonContainer = container.querySelector('.age-group-buttons');
        
        ageGroups.forEach(variation => {
            const button = this.createAgeGroupButton(variation);
            buttonContainer.appendChild(button);
        });
    }
    
    /**
     * Create an age group button element
     */
    createAgeGroupButton(variation) {
        const button = document.createElement('button');
        button.className = 'age-group-button';
        button.dataset.variationType = variation.type;
        button.dataset.variationValue = variation.value;
        button.dataset.variationId = variation.id;
        button.dataset.available = variation.is_available;
        button.setAttribute('role', 'button');
        button.setAttribute('aria-label', `Select ${variation.value}`);
        button.textContent = variation.value;
        
        if (!variation.is_available) {
            button.disabled = true;
            button.classList.add('disabled');
            button.setAttribute('aria-disabled', 'true');
        }
        
        return button;
    }
    
    /**
     * Render other variation types
     */
    renderOtherVariations() {
        if (!this.groupedVariations) {
            console.log('No grouped variations available for other variations');
            return;
        }
        
        const otherTypes = Object.keys(this.groupedVariations).filter(
            type => !['color', 'size', 'age_group', 'gender'].includes(type)
        );
        
        otherTypes.forEach(type => {
            const variations = this.groupedVariations[type];
            const container = this.createVariationContainer(type, this.formatVariationTitle(type));
            container.innerHTML = `<div class="variation-title">${this.formatVariationTitle(type)}:</div><div class="variation-buttons"></div>`;
            
            const buttonContainer = container.querySelector('.variation-buttons');
            
            variations.forEach(variation => {
                const button = this.createVariationButton(variation);
                buttonContainer.appendChild(button);
            });
        });
    }
    
    /**
     * Create a generic variation button
     */
    createVariationButton(variation) {
        const button = document.createElement('button');
        button.className = 'variation-button';
        button.dataset.variationType = variation.type;
        button.dataset.variationValue = variation.value;
        button.dataset.variationId = variation.id;
        button.dataset.available = variation.is_available;
        button.setAttribute('role', 'button');
        button.setAttribute('aria-label', `Select ${variation.value}`);
        button.textContent = variation.value;
        
        if (!variation.is_available) {
            button.disabled = true;
            button.classList.add('disabled');
            button.setAttribute('aria-disabled', 'true');
        }
        
        return button;
    }
    
    /**
     * Create a variation container
     */
    createVariationContainer(type, title) {
        const container = document.createElement('div');
        container.className = `variation-group variation-group-${type}`;
        container.dataset.variationType = type;
        
        if (this.elements.container) {
            this.elements.container.appendChild(container);
        } else {
            // Create main container if it doesn't exist
            const mainContainer = document.createElement('div');
            mainContainer.className = 'variation-section';
            mainContainer.appendChild(container);
            
            // Insert after product info or at the end of product details
            const insertPoint = document.querySelector('.product-info, .product-description') || document.body;
            insertPoint.parentNode.insertBefore(mainContainer, insertPoint.nextSibling);
            
            this.elements.container = mainContainer;
        }
        
        return container;
    }
    
    /**
     * Handle variation selection clicks
     */
    handleVariationClick(event) {
        const target = event.target.closest('[data-variation-type]');
        if (!target || target.dataset.available === 'false') return;
        
        const variationType = target.dataset.variationType;
        
        // Ignore clicks on size buttons since they're now non-interactive labels
        if (variationType === 'size') {
            return;
        }
        
        const variationValue = target.dataset.variationValue;
        const variationId = target.dataset.variationId;
        
        // Handle color variation image updates
        if (variationType === 'color' && target.dataset.imageUrl) {
            this.updateMainImageForColor(target.dataset.imageUrl);
            this.updateGalleryForColor(variationType, variationValue);
        }
        
        // Always show stock on user interaction
        this.selectVariation(variationType, variationValue, variationId, target, true);
    }
    
    /**
     * Handle keyboard navigation
     */
    handleKeyboardNavigation(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            const target = event.target.closest('[data-variation-type]');
            if (target && target.dataset.available !== 'false' && target.dataset.variationType !== 'size') {
                event.preventDefault();
                this.handleVariationClick(event);
            }
        }
    }
    
    /**
     * Select a variation
     */
    selectVariation(type, value, id, element, showStock = true) {
        // Clear previous selection for this type
        this.clearSelectionForType(type);
        
        // Set new selection
        this.selectedVariations[type] = { value, id };
        element.classList.add('selected');
        element.setAttribute('aria-selected', 'true');
        
        // Add visual feedback
        this.addSelectionFeedback(element);
        
        // Mark that user has interacted
        this.hasUserInteraction = true;
        
        // For SAS products, handle size filtering when age group changes
        if (this.productType === 'sas' && (type === 'age_group' || type === 'gender' || type === 'select main category')) {
            this.updateSizeOptionsForAgeGroup(value);
        }
        
        // Update price and check stock
        this.updatePrice();
        if (this.options.enableStockCheck && showStock) {
            this.showStockStatusAfterSelection();
            this.debouncedStockCheck();
        }
        
        // Display color-size stock information when a color is selected
        if (type === 'color') {
            this.displayColorSizeStock(value);
        }
        
        // Trigger custom event
        this.dispatchVariationChangeEvent(type, value, id);
        
        // Log for debugging
        console.log('Variation selected:', { type, value, id, selections: this.selectedVariations, showStock });
    }
    
    /**
     * Clear selection for a specific variation type
     */
    clearSelectionForType(type) {
        const previousSelection = document.querySelector(`[data-variation-type="${type}"].selected`);
        if (previousSelection) {
            previousSelection.classList.remove('selected');
            previousSelection.setAttribute('aria-selected', 'false');
        }
        
        if (this.selectedVariations[type]) {
            delete this.selectedVariations[type];
        }
        
        // If clearing color selection and no color variations remain, restore original gallery for LOTTO
        if (type === 'color' && this.productType === 'lotto' && !this.selectedVariations.color) {
            this.restoreOriginalGallery();
        }
        
        // Update stock display based on remaining selections
        if (Object.keys(this.selectedVariations).length === 0 && this.hasUserInteraction) {
            // All selections cleared - hide stock status completely
            this.hideStockStatusAfterClear();
        } else if (this.options.enableStockCheck && this.stockStatusVisible) {
            // Some selections remain - update stock display
            this.updateStockDisplay();
        }
    }
    
    /**
     * Add visual feedback for selection
     */
    addSelectionFeedback(element) {
        element.style.transform = 'scale(0.95)';
        setTimeout(() => {
            element.style.transform = '';
        }, this.options.animationDuration);
    }
    
    /**
     * Update product price based on selected variations
     */
    updatePrice() {
        if (!this.options.enablePriceUpdates) return;
        
        let totalPriceModifier = 0;
        
        Object.values(this.selectedVariations).forEach(selection => {
            const variation = this.variations.find(v => v.id === selection.id);
            if (variation && variation.price_modifier) {
                totalPriceModifier += variation.price_modifier;
            }
        });
        
        this.currentPrice = this.basePrice + totalPriceModifier;
        this.updatePriceDisplay();
    }
    
    /**
     * Update the price display in the DOM
     */
    updatePriceDisplay() {
        if (this.elements.priceDisplay && this.currentPrice > 0) {
            const formattedPrice = this.productType === 'sas' ? 
                `R${this.currentPrice.toFixed(2)}` : 
                `$${this.currentPrice.toFixed(2)}`;
            
            this.elements.priceDisplay.textContent = formattedPrice;
            
            // Add animation
            this.elements.priceDisplay.style.transform = 'scale(1.05)';
            setTimeout(() => {
                this.elements.priceDisplay.style.transform = '';
            }, this.options.animationDuration);
        }
    }
    
    /**
     * Check stock availability for current selection
     */
    async checkStock() {
        try {
            this.showStockCheckLoading();
            
            // Don't check stock if not visible
            if (!this.stockStatusVisible) {
                return;
            }
            
            // Check if we have any selections
            if (Object.keys(this.selectedVariations).length === 0) {
                // No selections - hide stock status
                this.hideStockStatusAfterClear();
                return;
            }
            
            const variations = {};
            Object.entries(this.selectedVariations).forEach(([type, selection]) => {
                variations[type] = selection.value;
            });
            
            const response = await fetch('/clubs/api/product/check-stock/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    product_id: this.productId,
                    product_type: this.productType,
                    variations: variations
                })
            });
            
            const data = await response.json();
            this.updateStockStatus(data);
            
        } catch (error) {
            console.error('Error checking stock:', error);
            this.showError('Unable to check stock availability');
        } finally {
            this.hideStockCheckLoading();
        }
    }
    
    /**
     * Update stock display based on current selections
     */
    updateStockDisplay() {
        // Don't show stock status unless explicitly made visible
        if (!this.stockStatusVisible) {
            return;
        }
        
        const selections = this.selectedVariations;
        const selectionCount = Object.keys(selections).length;
        
        if (selectionCount === 0) {
            // No selections - show overall product stock
            this.showOverallProductStock();
        } else if (selectionCount === 1) {
            // Single selection - determine what type and show appropriate stock
            const [selectedType, selectedValue] = Object.entries(selections)[0];
            
            if (selectedType === 'size') {
                this.showSizeOnlyStock(selectedValue.value);
            } else if (selectedType === 'color') {
                this.showColorOnlyStock(selectedValue.value);
            } else {
                // Other single selections - use general partial selection method
                this.showPartialSelectionStock(selections);
            }
        } else if (selectionCount === 2) {
            // Two selections - check if it's size and color combination
            const hasSize = selections.size;
            const hasColor = selections.color;
            
            if (hasSize && hasColor) {
                this.showSizeColorCombinationStock(hasSize.value, hasColor.value);
            } else {
                // Other two-attribute combinations - use general method
                this.showCombinationStock(selections);
            }
        } else {
            // Multiple selections - should be handled by API call in checkStock()
            // This is a fallback in case API call fails
            this.showCombinationStock(selections);
        }
    }
    
    /**
     * Show overall product stock (when no variations selected)
     */
    showOverallProductStock() {
        if (!this.variations || this.variations.length === 0) return;
        
        // Calculate total stock quantities across all variations
        const inStockVariations = this.variations.filter(v => v.stock_status === 'instock');
        const backorderVariations = this.variations.filter(v => v.stock_status === 'onbackorder');
        
        let stockStatus, stockData;
        
        if (inStockVariations.length > 0) {
            // Sum up actual stock quantities, handling null values appropriately
            const totalInStock = inStockVariations.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null (status-only products)
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockStatus = 'instock';
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'instock',
                stock_quantity: totalInStock > 0 ? totalInStock : null > 0 ? totalInStock : null
            };
        } else if (backorderVariations.length > 0) {
            const totalOnBackorder = backorderVariations.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockStatus = 'onbackorder';
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'onbackorder',
                stock_quantity: totalOnBackorder > 0 ? totalOnBackorder : null
            };
        } else {
            stockStatus = 'outofstock';
            stockData = {
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            };
        }
        
        this.updateStockStatus(stockData);
    }
    
    /**
     * Show stock for partial selection (e.g., only size selected)
     */
    showPartialSelectionStock(selections) {
        const [selectedType, selectedValue] = Object.entries(selections)[0];
        
        // Find variations that match the selected attribute
        const matchingVariations = this.variations.filter(variation => {
            const attributes = variation.attributes || {};
            return attributes[selectedType] === selectedValue.value;
        });
        
        if (matchingVariations.length === 0) {
            this.updateStockStatus({
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            });
            return;
        }
        
        // Calculate total stock quantities for matching variations
        const inStock = matchingVariations.filter(v => v.stock_status === 'instock');
        const onBackorder = matchingVariations.filter(v => v.stock_status === 'onbackorder');
        
        let stockData;
        if (inStock.length > 0) {
            // Sum up actual stock quantities, handling null values appropriately
            const totalInStock = inStock.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null (status-only products)
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'instock',
                stock_quantity: totalInStock > 0 ? totalInStock : null
            };
        } else if (onBackorder.length > 0) {
            const totalOnBackorder = onBackorder.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'onbackorder',
                stock_quantity: totalOnBackorder > 0 ? totalOnBackorder : null
            };
        } else {
            stockData = {
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            };
        }
        
        this.updateStockStatus(stockData);
    }
    
    /**
     * Show stock for specific combination (fallback method)
     */
    showCombinationStock(selections) {
        // Find exact variation match
        const exactMatch = this.variations.find(variation => {
            const attributes = variation.attributes || {};
            return Object.entries(selections).every(([type, selection]) => 
                attributes[type] === selection.value
            );
        });
        
        if (exactMatch) {
            const stockData = {
                success: true,
                is_available: exactMatch.stock_status !== 'outofstock',
                stock_status: exactMatch.stock_status,
                stock_quantity: exactMatch.stock || 1
            };
            this.updateStockStatus(stockData);
        } else {
            // No exact match found
            this.updateStockStatus({
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            });
        }
    }

    /**
     * Show stock for size-only selection across all colors
     */
    showSizeOnlyStock(sizeValue) {
        const matchingVariations = this.variations.filter(variation => {
            const attributes = variation.attributes || {};
            return attributes.size === sizeValue;
        });
        
        if (matchingVariations.length === 0) {
            this.updateStockStatus({
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            });
            return;
        }
        
        // Calculate total stock across all colors for this size
        const inStock = matchingVariations.filter(v => v.stock_status === 'instock');
        const onBackorder = matchingVariations.filter(v => v.stock_status === 'onbackorder');
        
        let stockData;
        if (inStock.length > 0) {
            const totalInStock = inStock.reduce((sum, v) => sum + (v.stock || 1), 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'instock',
                stock_quantity: totalInStock > 0 ? totalInStock : null
            };
        } else if (onBackorder.length > 0) {
            const totalOnBackorder = onBackorder.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'onbackorder',
                stock_quantity: totalOnBackorder > 0 ? totalOnBackorder : null
            };
        } else {
            stockData = {
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            };
        }
        
        this.updateStockStatus(stockData);
    }

    /**
     * Show stock for color-only selection across all sizes
     */
    showColorOnlyStock(colorValue) {
        const matchingVariations = this.variations.filter(variation => {
            const attributes = variation.attributes || {};
            return attributes.color === colorValue;
        });
        
        if (matchingVariations.length === 0) {
            this.updateStockStatus({
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            });
            return;
        }
        
        // Calculate total stock across all sizes for this color
        const inStock = matchingVariations.filter(v => v.stock_status === 'instock');
        const onBackorder = matchingVariations.filter(v => v.stock_status === 'onbackorder');
        
        let stockData;
        if (inStock.length > 0) {
            const totalInStock = inStock.reduce((sum, v) => sum + (v.stock || 1), 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'instock',
                stock_quantity: totalInStock > 0 ? totalInStock : null
            };
        } else if (onBackorder.length > 0) {
            const totalOnBackorder = onBackorder.reduce((sum, v) => {
                const stock = v.stock;
                if (stock === null || stock === undefined) {
                    return sum; // Don't add to sum if stock is null
                }
                return sum + Math.max(stock, 1);
            }, 0);
            stockData = {
                success: true,
                is_available: true,
                stock_status: 'onbackorder',
                stock_quantity: totalOnBackorder > 0 ? totalOnBackorder : null
            };
        } else {
            stockData = {
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            };
        }
        
        this.updateStockStatus(stockData);
    }

    /**
     * Show stock for specific size and color combination
     */
    showSizeColorCombinationStock(sizeValue, colorValue) {
        const exactMatch = this.variations.find(variation => {
            const attributes = variation.attributes || {};
            return attributes.size === sizeValue && attributes.color === colorValue;
        });
        
        if (exactMatch) {
            const stockData = {
                success: true,
                is_available: exactMatch.stock_status !== 'outofstock',
                stock_status: exactMatch.stock_status,
                stock_quantity: exactMatch.stock || 1
            };
            this.updateStockStatus(stockData);
        } else {
            // No exact match found
            this.updateStockStatus({
                success: true,
                is_available: false,
                stock_status: 'outofstock',
                stock_quantity: 0
            });
        }
    }
    
    /**
     * Update stock status display
     */
    updateStockStatus(stockData) {
        if (!this.elements.stockStatus) return;
        
        const isAvailable = stockData.success && stockData.is_available;
        const stockStatus = stockData.stock_status || 'unknown';
        const stockQuantity = stockData.stock_quantity || 0;
        
        // Remove existing status classes
        this.elements.stockStatus.classList.remove('in-stock', 'out-of-stock', 'on-backorder', 'low-stock');
        
        // Get formatted stock display
        const stockDisplay = this.formatStockDisplay(stockStatus, stockQuantity, isAvailable);
        
        // Add new status class and content
        this.elements.stockStatus.classList.add(stockDisplay.cssClass);
        this.elements.stockStatus.innerHTML = stockDisplay.html;
        
        // Update add to cart button
        this.updateAddToCartButton(isAvailable, stockStatus);
        
        // Also update any legacy stock status elements
        this.updateLegacyStockDisplay(stockStatus, stockQuantity);
    }
    
    /**
     * Format stock display with enhanced quantity information
     */
    formatStockDisplay(stockStatus, stockQuantity, isAvailable) {
        let cssClass, icon, text, displayText;
        
        if (!isAvailable || stockQuantity === 0) {
            cssClass = 'out-of-stock';
            icon = 'uil-times-circle';
            text = 'Out of Stock';
            displayText = text;
        } else if (stockStatus === 'onbackorder') {
            cssClass = 'on-backorder';
            icon = 'uil-clock';
            text = 'Available on Backorder';
            // Only show quantity if it's a valid number, otherwise just show status
            if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity > 0) {
                displayText = `${text} (${stockQuantity} available)`;
            } else {
                displayText = text;
            }
        } else {
            // In stock - determine if low stock
            if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity <= 5 && stockQuantity > 0) {
                cssClass = 'low-stock';
                icon = 'uil-exclamation-triangle';
                text = 'Low Stock';
                displayText = `${text} (${stockQuantity} available)`;
            } else {
                cssClass = 'in-stock';
                icon = 'uil-check-circle';
                text = 'In Stock';
                // Only show quantity if it's a valid number, otherwise just show "In Stock"
                if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity > 0) {
                    displayText = `${text} (${stockQuantity} available)`;
                } else {
                    displayText = text;
                }
            }
        }
        
        return {
            cssClass,
            html: `<i class="${icon}"></i><span>${displayText}</span>`,
            text: displayText,
            quantity: stockQuantity
        };
    }

    /**
     * Update legacy stock display elements (for backward compatibility)
     */
    updateLegacyStockDisplay(stockStatus, stockQuantity = 0) {
        // Call global updateStockStatus function if it exists
        if (typeof window.updateStockStatus === 'function') {
            window.updateStockStatus(stockStatus);
        }
        
        // Update any other stock status elements
        const otherStockElements = document.querySelectorAll('.stock-badge, .product-stock-status');
        otherStockElements.forEach(element => {
            element.classList.remove('bg-success', 'bg-warning', 'bg-danger', 'bg-info');
            
            if (stockStatus === 'instock') {
                if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity <= 5 && stockQuantity > 0) {
                    element.classList.add('bg-warning');
                    element.textContent = `Low Stock (${stockQuantity})`;
                } else {
                    element.classList.add('bg-success');
                    // Only show quantity if it's a valid number, otherwise just show "In Stock"
                    if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity > 0) {
                        element.textContent = `In Stock (${stockQuantity})`;
                    } else {
                        element.textContent = 'In Stock';
                    }
                }
            } else if (stockStatus === 'onbackorder') {
                element.classList.add('bg-info');
                // Only show quantity if it's a valid number, otherwise just show "Backorder"
                if (stockQuantity !== null && stockQuantity !== undefined && stockQuantity > 0) {
                    element.textContent = `Backorder (${stockQuantity})`;
                } else {
                    element.textContent = 'Backorder';
                }
            } else {
                element.classList.add('bg-danger');
                element.textContent = 'Out of Stock';
            }
        });
    }
    
    /**
     * Update add to cart button state
     */
    updateAddToCartButton(isAvailable, stockStatus) {
        if (!this.elements.addToCartBtn) return;
        
        if (isAvailable) {
            this.elements.addToCartBtn.disabled = false;
            this.elements.addToCartBtn.classList.remove('disabled');
            
            if (stockStatus === 'onbackorder') {
                this.elements.addToCartBtn.innerHTML = '<i class="uil-shopping-cart me-2"></i>Add to Cart (Backorder)';
            } else {
                this.elements.addToCartBtn.innerHTML = '<i class="uil-shopping-cart me-2"></i>Add to Cart';
            }
        } else {
            this.elements.addToCartBtn.disabled = true;
            this.elements.addToCartBtn.classList.add('disabled');
            this.elements.addToCartBtn.innerHTML = '<i class="uil-times-circle me-2"></i>Out of Stock';
        }
    }
    
    /**
     * Apply brand-specific styling
     */
    applyBrandStyling() {
        const root = document.documentElement;
        const theme = this.theme;
        
        // Set CSS custom properties for dynamic theming
        root.style.setProperty('--brand-primary', theme.primary);
        root.style.setProperty('--brand-secondary', theme.secondary);
        root.style.setProperty('--brand-disabled', theme.disabled);
        root.style.setProperty('--brand-success', theme.success);
        root.style.setProperty('--brand-warning', theme.warning);
        root.style.setProperty('--brand-danger', theme.danger);
        
        // Add brand-specific CSS if not already present
        if (!document.getElementById('variation-styles')) {
            this.injectBrandStyles();
        }
    }
    
    /**
     * Inject brand-specific CSS styles
     */
    injectBrandStyles() {
        const style = document.createElement('style');
        style.id = 'variation-styles';
        style.textContent = `
            .variation-section {
                margin: 2rem 0;
                padding: 1.5rem;
                background: #fff;
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,0.1);
            }
            
            .variation-title {
                font-weight: 600;
                color: #2c3e50;
                margin-bottom: 1rem;
                font-size: 1.1rem;
            }
            
            .color-swatches {
                display: flex;
                gap: 0.75rem;
                flex-wrap: wrap;
                margin-bottom: 1.5rem;
            }
            
            .color-swatch {
                width: 50px;
                height: 50px;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s ease;
                position: relative;
                border: 3px solid transparent;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            
            .color-swatch-image {
                width: 100%;
                height: 100%;
                object-fit: cover;
                border-radius: 5px;
                transition: transform 0.2s ease;
            }
            
            .color-swatch:hover {
                transform: scale(1.05);
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            }
            
            .color-swatch:hover .color-swatch-image {
                transform: scale(1.1);
            }
            
            .color-swatch.selected {
                border-color: var(--brand-primary);
                transform: scale(1.05);
                box-shadow: 0 0 0 3px var(--brand-primary);
            }
            
            .color-swatch.selected .color-swatch-image {
                transform: scale(1.1);
            }
            
            .color-swatch.disabled {
                opacity: 0.5;
                cursor: not-allowed;
                filter: grayscale(100%);
            }
            
            .unavailable-overlay {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                color: white;
                font-weight: bold;
                text-shadow: 0 0 3px rgba(0,0,0,0.8);
                font-size: 14px;
            }
            
            .size-buttons,
            .age-group-buttons,
            .variation-buttons {
                display: flex;
                gap: 0.5rem;
                flex-wrap: wrap;
                margin-bottom: 1.5rem;
            }
            
            .size-button,
            .age-group-button,
            .variation-button {
                padding: 0.75rem 1.25rem;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                background: #fff;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s ease;
                min-width: 60px;
                text-align: center;
                color: #495057;
            }
            
            .size-button:hover,
            .age-group-button:hover,
            .variation-button:hover {
                border-color: var(--brand-primary);
                background: rgba(var(--brand-primary-rgb), 0.05);
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .size-button.selected,
            .age-group-button.selected,
            .variation-button.selected {
                border-color: var(--brand-primary);
                background: var(--brand-primary);
                color: white;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(var(--brand-primary-rgb), 0.3);
            }
            
            .size-button.disabled,
            .age-group-button.disabled,
            .variation-button.disabled {
                opacity: 0.5;
                cursor: not-allowed;
                background: #f8f9fa;
                color: var(--brand-disabled);
            }
            
            .loading-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(255, 255, 255, 0.9);
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 12px;
                z-index: 10;
            }
            
            .loading-spinner {
                width: 40px;
                height: 40px;
                border: 4px solid #e9ecef;
                border-top: 4px solid var(--brand-primary);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .stock-check-loading {
                opacity: 0.7;
                pointer-events: none;
            }
            
            .error-message {
                background: var(--brand-danger);
                color: white;
                padding: 0.75rem 1rem;
                border-radius: 4px;
                margin: 1rem 0;
                font-size: 0.9rem;
            }
            
            /* Enhanced stock status display */
            .stock-status {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.75rem 1rem;
                border-radius: 8px;
                font-weight: 500;
                margin: 1rem 0;
                transition: all 0.3s ease;
            }
            
            .stock-status-hidden {
                display: none !important;
                opacity: 0;
                transform: translateY(-10px);
            }
            
            .stock-status-visible {
                display: flex !important;
                opacity: 1;
                transform: translateY(0);
            }
            
            .stock-status.in-stock {
                background: rgba(40, 167, 69, 0.1);
                color: #28a745;
                border: 1px solid rgba(40, 167, 69, 0.3);
            }
            
            .stock-status.low-stock {
                background: rgba(255, 193, 7, 0.1);
                color: #ff8c00;
                border: 1px solid rgba(255, 140, 0, 0.3);
            }
            
            .stock-status.out-of-stock {
                background: rgba(220, 53, 69, 0.1);
                color: #dc3545;
                border: 1px solid rgba(220, 53, 69, 0.3);
            }
            
            .stock-status.on-backorder {
                background: rgba(23, 162, 184, 0.1);
                color: #17a2b8;
                border: 1px solid rgba(23, 162, 184, 0.3);
            }
            
            .stock-status i {
                font-size: 1.1rem;
            }
            
            .stock-quantity {
                font-size: 0.9rem;
                opacity: 0.8;
                font-weight: normal;
                margin-left: 0.25rem;
            }
            
            /* Enhanced stock display animations */
            .stock-status {
                position: relative;
                overflow: hidden;
            }
            
            .stock-status::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s;
            }
            
            .stock-status:hover::before {
                left: 100%;
            }
            
            /* Size filtering animation */
            .size-buttons {
                transition: opacity 0.2s ease, transform 0.2s ease;
            }
            
            /* Low stock pulsing animation */
            .stock-status.low-stock {
                animation: lowStockPulse 2s ease-in-out infinite;
            }
            
            @keyframes lowStockPulse {
                0%, 100% {
                    box-shadow: 0 0 5px rgba(255, 140, 0, 0.3);
                }
                50% {
                    box-shadow: 0 0 15px rgba(255, 140, 0, 0.6);
                }
            }
            
            .stock-check-loading {
                opacity: 0.6;
                position: relative;
            }
            
            .stock-check-loading::after {
                content: '';
                position: absolute;
                top: 50%;
                right: 1rem;
                width: 16px;
                height: 16px;
                border: 2px solid transparent;
                border-top: 2px solid currentColor;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            /* Responsive design */
            @media (max-width: 768px) {
                .color-swatches {
                    justify-content: center;
                }
                
                .size-buttons,
                .age-group-buttons,
                .variation-buttons {
                    justify-content: center;
                }
                
                .color-swatch {
                    width: 35px;
                    height: 35px;
                }
                
                .size-button,
                .age-group-button,
                .variation-button {
                    padding: 0.5rem 1rem;
                    font-size: 0.9rem;
                }
            }
            
            @media (max-width: 576px) {
                .variation-section {
                    padding: 1rem;
                }
                
                .color-swatch {
                    width: 30px;
                    height: 30px;
                }
                
                .size-buttons,
                .age-group-buttons,
                .variation-buttons {
                    gap: 0.25rem;
                }
            }
        `;
        
        document.head.appendChild(style);
    }
    
    /**
     * Show loading overlay
     */
    showLoading() {
        if (!this.options.enableLoadingStates) return;
        
        if (!this.elements.loadingOverlay) {
            this.elements.loadingOverlay = document.createElement('div');
            this.elements.loadingOverlay.className = 'loading-overlay';
            this.elements.loadingOverlay.innerHTML = '<div class="loading-spinner"></div>';
        }
        
        if (this.elements.container) {
            this.elements.container.style.position = 'relative';
            this.elements.container.appendChild(this.elements.loadingOverlay);
        }
    }
    
    /**
     * Hide loading overlay
     */
    hideLoading() {
        // Remove dynamic loading overlay
        if (this.elements.loadingOverlay && this.elements.loadingOverlay.parentNode) {
            this.elements.loadingOverlay.parentNode.removeChild(this.elements.loadingOverlay);
        }
        
        // Remove template's initial loading message
        if (this.elements.initialLoadingMessage && this.elements.initialLoadingMessage.parentNode) {
            this.elements.initialLoadingMessage.parentNode.removeChild(this.elements.initialLoadingMessage);
            this.elements.initialLoadingMessage = null; // Clear reference after removal
        }
    }
    
    /**
     * Show stock check loading
     */
    showStockCheckLoading() {
        if (this.elements.stockStatus) {
            this.elements.stockStatus.classList.add('stock-check-loading');
        }
    }
    
    /**
     * Hide stock check loading
     */
    hideStockCheckLoading() {
        if (this.elements.stockStatus) {
            this.elements.stockStatus.classList.remove('stock-check-loading');
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        // Remove template's loading message on error
        if (this.elements.initialLoadingMessage && this.elements.initialLoadingMessage.parentNode) {
            this.elements.initialLoadingMessage.parentNode.removeChild(this.elements.initialLoadingMessage);
            this.elements.initialLoadingMessage = null; // Clear reference after removal
        }
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        
        if (this.elements.container) {
            this.elements.container.appendChild(errorDiv);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.parentNode.removeChild(errorDiv);
                }
            }, 5000);
        }
    }
    
    /**
     * Setup initial state
     */
    setupInitialState() {
        // Hide stock status initially - will be shown only after user interaction
        this.hideStockStatusInitially();
        
        // Ensure price display shows base price initially
        if (this.basePrice > 0) {
            this.currentPrice = this.basePrice;
            this.updatePriceDisplay();
        }
        
        // Auto-select first available variation for each type if only one option
        if (!this.groupedVariations || typeof this.groupedVariations !== 'object') {
            console.warn('No grouped variations available for initial state setup');
            return;
        }
        
        Object.entries(this.groupedVariations).forEach(([type, variations]) => {
            const availableVariations = variations.filter(v => v.is_available);
            if (availableVariations.length === 1) {
                const variation = availableVariations[0];
                const element = document.querySelector(`[data-variation-type="${type}"][data-variation-value="${variation.value}"]`);
                if (element) {
                    // Don't show stock status for auto-selected variations
                    this.selectVariation(type, variation.value, variation.id, element, false);
                }
            }
        });
        
        // Log initial state for debugging
        console.log('Initial state setup complete:', {
            groupedVariations: Object.keys(this.groupedVariations),
            variations: this.variations.length,
            selectedVariations: this.selectedVariations,
            stockStatusVisible: this.stockStatusVisible,
            basePrice: this.basePrice,
            currentPrice: this.currentPrice
        });
    }
    
    /**
     * Dispatch custom variation change event
     */
    dispatchVariationChangeEvent(type, value, id) {
        const event = new CustomEvent('variationChanged', {
            detail: {
                type,
                value,
                id,
                selectedVariations: this.selectedVariations,
                currentPrice: this.currentPrice
            }
        });
        
        document.dispatchEvent(event);
    }
    
    /**
     * Get selected variations
     */
    getSelectedVariations() {
        return { ...this.selectedVariations };
    }
    
    /**
     * Get current price
     */
    getCurrentPrice() {
        return this.currentPrice;
    }
    
    /**
     * Get stock information for specific combination
     */
    getStockForCombination(combinations = {}) {
        // Use provided combinations or current selections
        const targetCombinations = Object.keys(combinations).length > 0 ? combinations : this.selectedVariations;
        
        if (Object.keys(targetCombinations).length === 0) {
            return this.getOverallProductStock();
        }
        
        // Find matching variations based on combinations
        const matchingVariations = this.variations.filter(variation => {
            const attributes = variation.attributes || {};
            return Object.entries(targetCombinations).every(([type, selection]) => {
                const value = selection.value || selection; // Handle both object and string values
                return attributes[type] === value;
            });
        });
        
        if (matchingVariations.length === 0) {
            return {
                available: false,
                stock_status: 'outofstock',
                stock_quantity: 0,
                variations: []
            };
        }
        
        // Analyze stock status
        const inStock = matchingVariations.filter(v => v.stock_status === 'instock');
        const onBackorder = matchingVariations.filter(v => v.stock_status === 'onbackorder');
        
        let overall_status, total_quantity = 0;
        
        if (inStock.length > 0) {
            overall_status = 'instock';
            total_quantity = inStock.reduce((sum, v) => sum + (v.stock || 1), 0);
        } else if (onBackorder.length > 0) {
            overall_status = 'onbackorder';
            total_quantity = onBackorder.reduce((sum, v) => sum + (v.stock || 1), 0);
        } else {
            overall_status = 'outofstock';
            total_quantity = 0;
        }
        
        return {
            available: overall_status !== 'outofstock',
            stock_status: overall_status,
            stock_quantity: total_quantity,
            variations: matchingVariations,
            combination: targetCombinations
        };
    }
    
    /**
     * Get overall product stock information
     */
    getOverallProductStock() {
        if (!this.variations || this.variations.length === 0) {
            return {
                available: false,
                stock_status: 'outofstock',
                stock_quantity: 0,
                variations: []
            };
        }
        
        const inStock = this.variations.filter(v => v.stock_status === 'instock');
        const onBackorder = this.variations.filter(v => v.stock_status === 'onbackorder');
        
        let overall_status, total_quantity = 0;
        
        if (inStock.length > 0) {
            overall_status = 'instock';
            total_quantity = inStock.reduce((sum, v) => sum + (v.stock || 1), 0);
        } else if (onBackorder.length > 0) {
            overall_status = 'onbackorder';
            total_quantity = onBackorder.reduce((sum, v) => sum + (v.stock || 1), 0);
        } else {
            overall_status = 'outofstock';
            total_quantity = 0;
        }
        
        return {
            available: overall_status !== 'outofstock',
            stock_status: overall_status,
            stock_quantity: total_quantity,
            variations: this.variations
        };
    }
    
    /**
     * Check if all required variations are selected
     */
    isSelectionComplete() {
        const requiredTypes = Object.keys(this.groupedVariations);
        return requiredTypes.every(type => this.selectedVariations[type]);
    }
    
    /**
     * Reset all selections
     */
    resetSelections() {
        Object.keys(this.selectedVariations).forEach(type => {
            this.clearSelectionForType(type);
        });
        
        this.currentPrice = this.basePrice;
        this.updatePriceDisplay();
        
        // Hide stock status after reset
        this.hideStockStatusAfterClear();
        
        console.log('All selections reset');
    }
    
    // Utility methods
    
    /**
     * Get color hex code from color name
     */
    getColorHex(colorName) {
        const colorMap = {
            'red': '#dc3545',
            'blue': '#007bff',
            'green': '#28a745',
            'yellow': '#ffc107',
            'black': '#343a40',
            'white': '#ffffff',
            'navy': '#001f3f',
            'grey': '#6c757d',
            'gray': '#6c757d',
            'orange': '#fd7e14',
            'purple': '#6f42c1',
            'pink': '#e83e8c',
            'brown': '#795548',
            'gold': '#ffd700',
            'silver': '#c0c0c0'
        };
        
        return colorMap[colorName.toLowerCase()] || '#6c757d';
    }
    
    /**
     * Check if a color is light
     */
    isLightColor(hex) {
        const rgb = this.hexToRgb(hex);
        if (!rgb) return false;
        
        const brightness = (rgb.r * 299 + rgb.g * 587 + rgb.b * 114) / 1000;
        return brightness > 128;
    }
    
    /**
     * Convert hex to RGB
     */
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : null;
    }
    
    /**
     * Format variation title
     */
    formatVariationTitle(type) {
        return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    /**
     * Debounce function
     */
    debounce(func, wait) {
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
     * Get CSRF token
     */
    getCSRFToken() {
        const cookie = document.cookie.split(';')
            .find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }
    
    /**
     * Hide stock status initially (on page load)
     */
    hideStockStatusInitially() {
        if (this.elements.stockStatus) {
            this.elements.stockStatus.classList.add('stock-status-hidden');
            this.elements.stockStatus.classList.remove('stock-status-visible');
            this.stockStatusVisible = false;
        }
        
        // Also hide add to cart button initially or make it neutral
        if (this.elements.addToCartBtn) {
            this.elements.addToCartBtn.innerHTML = '<i class="uil-shopping-cart me-2"></i>Add to Cart';
            this.elements.addToCartBtn.disabled = false;
            this.elements.addToCartBtn.classList.remove('disabled');
        }
        
        console.log('Stock status hidden initially');
    }
    
    /**
     * Show stock status after user selection
     */
    showStockStatusAfterSelection() {
        if (this.elements.stockStatus) {
            this.elements.stockStatus.classList.remove('stock-status-hidden');
            this.elements.stockStatus.classList.add('stock-status-visible');
            this.stockStatusVisible = true;
        }
        
        console.log('Stock status shown after user selection');
    }
    
    /**
     * Hide stock status after clearing all selections
     */
    hideStockStatusAfterClear() {
        if (this.elements.stockStatus && Object.keys(this.selectedVariations).length === 0) {
            this.elements.stockStatus.classList.add('stock-status-hidden');
            this.elements.stockStatus.classList.remove('stock-status-visible');
            this.stockStatusVisible = false;
            
            // Reset add to cart button to neutral state
            if (this.elements.addToCartBtn) {
                this.elements.addToCartBtn.innerHTML = '<i class="uil-shopping-cart me-2"></i>Add to Cart';
                this.elements.addToCartBtn.disabled = false;
                this.elements.addToCartBtn.classList.remove('disabled');
            }
        }
        
        console.log('Stock status hidden after clearing selections');
    }

    /**
     * Show stock status after clearing selections to display overall stock
     */
    showOverallStockAfterClear() {
        if (this.elements.stockStatus && Object.keys(this.selectedVariations).length === 0) {
            this.elements.stockStatus.classList.remove('stock-status-hidden');
            this.elements.stockStatus.classList.add('stock-status-visible');
            this.stockStatusVisible = true;
            
            // Show overall product stock
            this.showOverallProductStock();
        }
        
        console.log('Showing overall stock after clearing selections');
    }

    /**
     * Manually trigger stock update for current selections
     */
    refreshStockDisplay() {
        if (this.options.enableStockCheck) {
            // Show stock status if not visible and there are selections
            if (!this.stockStatusVisible && Object.keys(this.selectedVariations).length > 0) {
                this.showStockStatusAfterSelection();
            }
            this.updateStockDisplay();
        }
    }

    /**
     * Force show stock status with current overall stock (for external use)
     */
    showOverallStock() {
        this.showStockStatusAfterSelection();
        this.showOverallProductStock();
    }

    /**
     * Get stock information for external use
     */
    getStockInfo() {
        const selections = this.selectedVariations;
        const selectionCount = Object.keys(selections).length;
        
        if (selectionCount === 0) {
            return this.getOverallProductStock();
        } else {
            return this.getStockForCombination(selections);
        }
    }
    
    /**
     * Get debug information about current state
     */
    getDebugInfo() {
        return {
            productId: this.productId,
            productType: this.productType,
            selectedVariations: this.selectedVariations,
            variationsCount: this.variations.length,
            groupedVariationsTypes: Object.keys(this.groupedVariations),
            currentPrice: this.currentPrice,
            basePrice: this.basePrice,
            stockCheckEnabled: this.options.enableStockCheck,
            stockStatusVisible: this.stockStatusVisible,
            hasUserInteraction: this.hasUserInteraction,
            currentStockInfo: this.getStockForCombination()
        };
    }
    
    /**
     * Get filtered sizes based on age group selection for SAS products
     */
    getFilteredSizes(allSizes) {
        if (this.productType !== 'sas') {
            return allSizes;
        }
        
        const selectedAgeGroup = this.selectedVariations.age_group || this.selectedVariations.gender || this.selectedVariations['select main category'];
        
        if (!selectedAgeGroup) {
            // No age group selected, show all sizes
            return allSizes;
        }
        
        const ageGroupValue = selectedAgeGroup.value.toLowerCase();
        
        return allSizes.filter(size => {
            const sizeValue = size.value.toLowerCase();
            
            if (ageGroupValue === 'adults' || ageGroupValue === 'adult') {
                // Adult sizes: XS, S, M, L, XL, 2XL, 3XL, 4XL, 5XL
                return /^(xs|s|m|l|xl|2xl|3xl|4xl|5xl)$/i.test(sizeValue);
            } else if (ageGroupValue === 'kids' || ageGroupValue === 'children' || ageGroupValue === 'child') {
                // Kids sizes: 4k, 6k, 8k, 10k, 12k, 14k, 16k
                return /^(4k|6k|8k|10k|12k|14k|16k)$/i.test(sizeValue);
            }
            
            // Unknown age group, show all sizes
            return true;
        });
    }
    
    /**
     * Sort sizes in logical order
     */
    sortSizes(sizes) {
        return sizes.sort((a, b) => {
            const aValue = a.value.toLowerCase();
            const bValue = b.value.toLowerCase();
            
            // Define sort order for adult sizes
            const adultOrder = ['xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl'];
            
            // Define sort order for kids sizes
            const kidsOrder = ['4k', '6k', '8k', '10k', '12k', '14k', '16k'];
            
            // Check if both are adult sizes
            const aAdultIndex = adultOrder.indexOf(aValue);
            const bAdultIndex = adultOrder.indexOf(bValue);
            
            if (aAdultIndex !== -1 && bAdultIndex !== -1) {
                return aAdultIndex - bAdultIndex;
            }
            
            // Check if both are kids sizes
            const aKidsIndex = kidsOrder.indexOf(aValue);
            const bKidsIndex = kidsOrder.indexOf(bValue);
            
            if (aKidsIndex !== -1 && bKidsIndex !== -1) {
                return aKidsIndex - bKidsIndex;
            }
            
            // Fallback to alphabetical sorting
            return aValue.localeCompare(bValue);
        });
    }
    
    /**
     * Update size options when age group selection changes (SAS products only)
     */
    updateSizeOptionsForAgeGroup(ageGroupValue) {
        if (this.productType !== 'sas' || !this.groupedVariations.size) {
            return;
        }
        
        const sizeContainer = this.elements.sizeOptions;
        if (!sizeContainer) {
            return;
        }
        
        // Clear any existing size selection
        // Clear any existing size selection when age group changes
        this.clearSelectionForType('size');
        
        // Get the size button container
        const buttonContainer = sizeContainer.querySelector('.size-buttons');
        if (!buttonContainer) {
            return;
        }
        
        // Clear existing buttons
        buttonContainer.innerHTML = '';
        
        // Get filtered and sorted sizes
        const allSizes = this.groupedVariations.size || [];
        const filteredSizes = this.getFilteredSizes(allSizes);
        const sortedSizes = this.sortSizes(filteredSizes);
        
        // Render new size buttons
        sortedSizes.forEach(variation => {
            const button = this.createSizeButton(variation);
            buttonContainer.appendChild(button);
        });
        
        // Add animation effect
        buttonContainer.style.opacity = '0.5';
        buttonContainer.style.transform = 'scale(0.95)';
        
        setTimeout(() => {
            buttonContainer.style.opacity = '1';
            buttonContainer.style.transform = 'scale(1)';
        }, 150);
        
        console.log(`Updated size options for age group: ${ageGroupValue}. Showing ${sortedSizes.length} sizes.`);
    }
    
    /**
     * Update main product image when color is selected
     */
    updateMainImageForColor(imageUrl) {
        const mainImage = document.getElementById('mainProductImage');
        if (mainImage && imageUrl) {
            // Use the proxy URL for external images
            const proxiedUrl = imageUrl.startsWith('http') ? 
                `/clubs/proxy-image/?url=${encodeURIComponent(imageUrl)}` : 
                imageUrl;
            
            // Add loading effect
            mainImage.style.opacity = '0.7';
            
            // Update image with error handling
            const newImage = new Image();
            newImage.onload = () => {
                mainImage.src = proxiedUrl;
                mainImage.style.opacity = '1';
            };
            newImage.onerror = () => {
                console.warn('Failed to load color variation image:', imageUrl);
                mainImage.style.opacity = '1';
            };
            newImage.src = proxiedUrl;
        }
    }
    
    /**
     * Update gallery thumbnails to show all color variations
     */
    updateGalleryForColor(variationType, variationValue) {
        if (variationType !== 'color') return;
        
        // Get all color variations with images
        const colorVariations = this.groupedVariations.color || [];
        const variationsWithImages = colorVariations.filter(v => v.image);
        
        if (variationsWithImages.length === 0) return;
        
        // Look for thumbnail sidebar (SAS) or thumbnail gallery (LOTTO)
        let thumbnailContainer = document.querySelector('.thumbnail-sidebar');
        let originalGallery = document.querySelector('.product-thumbnails, #thumbnailGallery');
        
        // If no sidebar exists, try to use the main gallery (LOTTO)
        if (!thumbnailContainer) {
            thumbnailContainer = originalGallery;
        }
        
        if (!thumbnailContainer) return;
        
        // For LOTTO: Show thumbnail sidebar and hide original gallery
        if (this.productType === 'lotto') {
            const thumbnailSidebar = document.querySelector('.thumbnail-sidebar');
            if (thumbnailSidebar && originalGallery) {
                thumbnailSidebar.style.display = 'flex';
                originalGallery.style.display = 'none';
                thumbnailContainer = thumbnailSidebar;
            }
        }
        
        // Clear existing thumbnails
        thumbnailContainer.innerHTML = '';
        
        // Add thumbnails for each color variation
        variationsWithImages.forEach((variation, index) => {
            const thumbnail = document.createElement('img');
            // Use the proxy URL for external images
            const imageUrl = variation.image.startsWith('http') ? 
                `/clubs/proxy-image/?url=${encodeURIComponent(variation.image)}` : 
                variation.image;
            thumbnail.src = imageUrl;
            thumbnail.alt = `${variation.value} color variation`;
            thumbnail.className = 'thumbnail-image';
            thumbnail.dataset.colorValue = variation.value;
            
            // Mark current selection as active
            if (variation.value === variationValue) {
                thumbnail.classList.add('active');
            }
            
            // Add click handler to update main image
            thumbnail.addEventListener('click', () => {
                // Update main image
                this.updateMainImageForColor(variation.image);
                
                // Update active thumbnail
                document.querySelectorAll('.thumbnail-image').forEach(thumb => 
                    thumb.classList.remove('active')
                );
                thumbnail.classList.add('active');
                
                // Update color swatch selection if this color is not already selected
                if (this.selectedVariations.color?.value !== variation.value) {
                    const colorSwatch = document.querySelector(
                        `[data-variation-type="color"][data-variation-value="${variation.value}"]`
                    );
                    if (colorSwatch) {
                        colorSwatch.click();
                    }
                }
            });
            
            // Handle image load errors
            thumbnail.onerror = () => {
                thumbnail.style.display = 'none';
            };
            
            thumbnailContainer.appendChild(thumbnail);
        });
        
        console.log(`Updated gallery with ${variationsWithImages.length} color variation images`);
    }
    
    /**
     * Initialize color image gallery on page load
     */
    initializeColorImageGallery() {
        // Only initialize if we have color variations with images
        const colorVariations = this.groupedVariations.color || [];
        const variationsWithImages = colorVariations.filter(v => v.image);
        
        if (variationsWithImages.length === 0) {
            console.log('No color variations with images found, keeping original gallery');
            // For LOTTO: Ensure original gallery is visible and thumbnail sidebar is hidden
            if (this.productType === 'lotto') {
                const thumbnailSidebar = document.querySelector('.thumbnail-sidebar');
                const originalGallery = document.querySelector('.product-thumbnails, #thumbnailGallery');
                if (thumbnailSidebar) {
                    thumbnailSidebar.style.display = 'none';
                }
                if (originalGallery) {
                    originalGallery.style.display = 'flex';
                }
            }
            return;
        }
        
        console.log(`Initializing color image gallery with ${variationsWithImages.length} color images`);
        
        // Update gallery to show all color variation images
        this.updateGalleryForColor('color', variationsWithImages[0].value);
        
        // Set first color variation image as main image if no color is selected
        if (!this.selectedVariations.color && variationsWithImages[0].image) {
            this.updateMainImageForColor(variationsWithImages[0].image);
        }
    }
    
    /**
     * Restore original gallery when color variations are cleared (LOTTO specific)
     */
    restoreOriginalGallery() {
        if (this.productType !== 'lotto') return;
        
        const thumbnailSidebar = document.querySelector('.thumbnail-sidebar');
        const originalGallery = document.querySelector('.product-thumbnails, #thumbnailGallery');
        
        if (thumbnailSidebar) {
            thumbnailSidebar.style.display = 'none';
        }
        if (originalGallery) {
            originalGallery.style.display = 'flex';
        }
        
        console.log('Restored original gallery for LOTTO product');
    }
    
    /**
     * Display stock information for all sizes in a specific color
     * @param {string} colorValue - The selected color value
     */
    async displayColorSizeStock(colorValue) {
        try {
            // Show loading state
            this.showColorSizeStockLoading();
            
            // Call the API to get stock information
            const response = await fetch('/clubs/api/product/color-size-stock/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    product_id: this.productId,
                    product_type: this.productType,
                    color: colorValue
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success && data.sizes && data.sizes.length > 0) {
                this.showColorSizeStockDisplay(data);
            } else {
                console.log('No stock information available for color:', colorValue);
                this.hideColorSizeStockDisplay();
            }
            
        } catch (error) {
            console.error('Error fetching color size stock:', error);
            this.hideColorSizeStockDisplay();
        }
    }
    
    /**
     * Show loading state for color-size stock display
     */
    showColorSizeStockLoading() {
        const container = this.getOrCreateColorSizeStockContainer();
        if (container) {
            container.style.display = 'block';
            container.innerHTML = `
                <div class="stock-loading d-flex align-items-center mb-3">
                    <div class="spinner-border spinner-border-sm me-2" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <span class="text-muted">Loading stock information...</span>
                </div>
            `;
        }
    }
    
    /**
     * Display the stock information in a formatted way
     * @param {Object} data - The stock data from API
     */
    showColorSizeStockDisplay(data) {
        const container = this.getOrCreateColorSizeStockContainer();
        if (!container || !data.sizes || data.sizes.length === 0) {
            this.hideColorSizeStockDisplay();
            return;
        }
        
        const colorName = data.color;
        const sizes = data.sizes;
        
        let stockHtml = `
            <div class="color-size-stock-header mb-2">
                <h6 class="mb-0 d-flex align-items-center">
                    <i class="fas fa-tshirt me-2 text-${this.productType === 'lotto' ? 'danger' : 'primary'}"></i>
                    <span>Stock Available for <strong>${colorName}</strong></span>
                </h6>
            </div>
            <div class="stock-grid row g-2">
        `;
        
        // Create stock display for each size
        sizes.forEach(sizeInfo => {
            const isAvailable = sizeInfo.is_available;
            const stockQuantity = sizeInfo.stock_quantity;
            const stockStatus = sizeInfo.stock_status;
            const sizeName = sizeInfo.size;
            
            let stockText = '';
            let badgeClass = '';
            
            if (isAvailable && stockQuantity > 0) {
                stockText = `${stockQuantity} available`;
                badgeClass = 'bg-success';
            } else if (stockStatus === 'onbackorder') {
                stockText = 'On backorder';
                badgeClass = 'bg-warning text-dark';
            } else {
                stockText = 'Out of stock';
                badgeClass = 'bg-secondary';
            }
            
            stockHtml += `
                <div class="col-6 col-md-4 col-lg-3">
                    <div class="stock-item p-2 border rounded ${isAvailable ? 'border-success' : 'border-secondary'}">
                        <div class="size-label fw-bold text-center mb-1">Size ${sizeName}</div>
                        <div class="stock-status text-center">
                            <span class="badge ${badgeClass} small">${stockText}</span>
                        </div>
                    </div>
                </div>
            `;
        });
        
        stockHtml += `
            </div>
        `;
        
        container.innerHTML = stockHtml;
        container.style.display = 'block';
    }
    
    /**
     * Get or create the color-size stock display container
     */
    getOrCreateColorSizeStockContainer() {
        let container = document.getElementById('color-size-stock-display');
        
        if (!container) {
            // Find a good location to insert the container
            const variationSection = document.querySelector('.variation-section, .product-variations, #productVariations');
            const stockSection = document.querySelector('.stock-status, .product-stock');
            
            container = document.createElement('div');
            container.id = 'color-size-stock-display';
            container.className = 'color-size-stock-display mt-3 p-3 bg-light rounded';
            container.style.display = 'none';
            
            // Try to insert after the variations section, or before stock section
            if (variationSection) {
                variationSection.insertAdjacentElement('afterend', container);
            } else if (stockSection) {
                stockSection.insertAdjacentElement('beforebegin', container);
            } else {
                // Fallback: try to find the product info section
                const productInfo = document.querySelector('.product-info, .product-details');
                if (productInfo) {
                    productInfo.appendChild(container);
                }
            }
        }
        
        return container;
    }
    
    /**
     * Hide the color-size stock display
     */
    hideColorSizeStockDisplay() {
        const container = document.getElementById('color-size-stock-display');
        if (container) {
            container.style.display = 'none';
        }
    }
    
    /**
     * Get CSRF token for API calls
     */
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
               document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }
}

// Export for global use
window.ProductVariationManager = ProductVariationManager;