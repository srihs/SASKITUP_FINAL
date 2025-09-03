/**
 * Clubs App JavaScript Functions
 * Enhanced functionality for the clubs management system
 */

class ClubsManager {
    constructor() {
        this.searchTimeout = null;
        this.init();
    }

    init() {
        this.initializeTooltips();
        this.initializeSearch();
        this.initializeFilters();
        this.initializeCardInteractions();
        this.initializeAjaxSearch();
    }

    /**
     * Initialize Bootstrap tooltips
     */
    initializeTooltips() {
        const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltips.forEach(tooltip => {
            new bootstrap.Tooltip(tooltip, {
                trigger: 'hover',
                placement: 'top'
            });
        });
    }

    /**
     * Initialize search functionality with debouncing
     */
    initializeSearch() {
        const searchInputs = document.querySelectorAll('#searchInput, .club-search');
        
        searchInputs.forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.applyFilters();
                }
            });

            // Debounced search
            input.addEventListener('input', (e) => {
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    if (e.target.value.length > 2 || e.target.value.length === 0) {
                        this.performSearch(e.target.value);
                    }
                }, 500);
            });
        });
    }

    /**
     * Initialize filter functionality
     */
    initializeFilters() {
        const filterSelects = document.querySelectorAll('.filter-select');
        
        filterSelects.forEach(select => {
            select.addEventListener('change', () => {
                this.applyFilters();
            });
        });

        // Filter buttons
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                this.applyFilters();
            });
        });
    }

    /**
     * Initialize card interactions and animations
     */
    initializeCardInteractions() {
        const clubCards = document.querySelectorAll('.club-card, .lotto-club-card, .sas-club-card, .product-card');
        
        clubCards.forEach(card => {
            // Add hover effects
            card.addEventListener('mouseenter', () => {
                this.animateCard(card, 'enter');
            });

            card.addEventListener('mouseleave', () => {
                this.animateCard(card, 'leave');
            });

            // Add click tracking
            const links = card.querySelectorAll('a[href*="club-detail"], a[href*="category-detail"]');
            links.forEach(link => {
                link.addEventListener('click', (e) => {
                    this.trackClubInteraction(e.target);
                });
            });
        });
    }

    /**
     * Initialize AJAX search with suggestions
     */
    initializeAjaxSearch() {
        const searchInput = document.getElementById('searchInput');
        if (!searchInput) return;

        const createSuggestionDropdown = () => {
            const dropdown = document.createElement('div');
            dropdown.className = 'search-suggestions';
            dropdown.style.cssText = `
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: white;
                border: 1px solid #ddd;
                border-top: none;
                border-radius: 0 0 6px 6px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                max-height: 300px;
                overflow-y: auto;
                z-index: 1000;
                display: none;
            `;
            return dropdown;
        };

        const suggestionDropdown = createSuggestionDropdown();
        searchInput.parentElement.style.position = 'relative';
        searchInput.parentElement.appendChild(suggestionDropdown);

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            
            if (query.length < 2) {
                suggestionDropdown.style.display = 'none';
                return;
            }

            // AJAX search request
            fetch(`/clubs/ajax/search/?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    this.displaySearchSuggestions(suggestionDropdown, data.results);
                })
                .catch(error => {
                    console.error('Search error:', error);
                });
        });

        // Hide suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!searchInput.parentElement.contains(e.target)) {
                suggestionDropdown.style.display = 'none';
            }
        });
    }

    /**
     * Display search suggestions
     */
    displaySearchSuggestions(dropdown, results) {
        dropdown.innerHTML = '';

        if (results.length === 0) {
            dropdown.innerHTML = '<div class="p-3 text-muted">No clubs found</div>';
            dropdown.style.display = 'block';
            return;
        }

        results.forEach(club => {
            const suggestion = document.createElement('div');
            suggestion.className = 'search-suggestion-item';
            suggestion.style.cssText = `
                padding: 12px 16px;
                cursor: pointer;
                border-bottom: 1px solid #f1f1f1;
                transition: background-color 0.2s;
            `;
            
            suggestion.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="me-3">
                        <span class="badge ${club.club_type === 'LOTTO' ? 'bg-info' : 'bg-warning'} font-size-10">
                            ${club.club_type}
                        </span>
                    </div>
                    <div class="flex-grow-1">
                        <div class="font-weight-semibold">${club.name}</div>
                        <small class="text-muted">${club.sport_tag}</small>
                    </div>
                </div>
            `;

            suggestion.addEventListener('mouseenter', () => {
                suggestion.style.backgroundColor = '#f8f9fa';
            });

            suggestion.addEventListener('mouseleave', () => {
                suggestion.style.backgroundColor = 'transparent';
            });

            suggestion.addEventListener('click', () => {
                if (club.slug) {
                    window.location.href = `/clubs/club/${club.slug}/`;
                } else {
                    console.error('Club slug not found:', club);
                    // Fallback to search with the club name instead of redirecting to ID
                    const searchInput = document.getElementById('searchInput');
                    if (searchInput) {
                        searchInput.value = club.name;
                        window.clubsManager.applyFilters();
                    }
                }
            });

            dropdown.appendChild(suggestion);
        });

        dropdown.style.display = 'block';
    }

    /**
     * Apply current filters and redirect
     */
    applyFilters() {
        const searchInput = document.getElementById('searchInput');
        const clubTypeFilter = document.getElementById('clubTypeFilter');
        const sportFilter = document.getElementById('sportFilter');
        
        const params = new URLSearchParams();
        
        if (searchInput && searchInput.value.trim()) {
            params.set('search', searchInput.value.trim());
        }
        
        if (clubTypeFilter && clubTypeFilter.value) {
            params.set('type', clubTypeFilter.value);
        }
        
        if (sportFilter && sportFilter.value) {
            params.set('sport', sportFilter.value);
        }

        const newUrl = `${window.location.pathname}?${params.toString()}`;
        window.location.href = newUrl;
    }

    /**
     * Clear all filters
     */
    clearFilters() {
        const inputs = document.querySelectorAll('#searchInput, #clubTypeFilter, #sportFilter');
        inputs.forEach(input => {
            input.value = '';
        });
        
        window.location.href = window.location.pathname;
    }

    /**
     * Perform search with loading state
     */
    performSearch(query) {
        const searchButton = document.querySelector('.btn-primary');
        if (searchButton) {
            const originalText = searchButton.innerHTML;
            searchButton.innerHTML = '<i class="spinner-border spinner-border-sm me-1"></i> Searching...';
            searchButton.disabled = true;
            
            setTimeout(() => {
                searchButton.innerHTML = originalText;
                searchButton.disabled = false;
            }, 1000);
        }
    }

    /**
     * Animate card on hover
     */
    animateCard(card, state) {
        if (state === 'enter') {
            card.style.transform = 'translateY(-8px)';
            card.style.boxShadow = '0 15px 35px rgba(0,0,0,0.15)';
        } else {
            card.style.transform = 'translateY(0)';
            card.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        }
    }

    /**
     * Track club interactions for analytics
     */
    trackClubInteraction(element) {
        const clubName = element.closest('.card').querySelector('h5')?.textContent?.trim();
        const clubType = element.closest('.card').querySelector('.badge')?.textContent?.trim();
        
        if (clubName) {
            // Send to analytics (Google Analytics, Mixpanel, etc.)
            console.log('Club interaction:', { clubName, clubType, timestamp: new Date() });
            
            // Example Google Analytics event
            if (typeof gtag !== 'undefined') {
                gtag('event', 'club_click', {
                    'event_category': 'clubs',
                    'event_label': clubName,
                    'custom_parameter_1': clubType
                });
            }
        }
    }

    /**
     * Show loading state for cards
     */
    showLoadingState() {
        const cardGrid = document.getElementById('clubGrid');
        if (!cardGrid) return;

        cardGrid.innerHTML = Array(6).fill(0).map(() => `
            <div class="col-lg-4 col-md-6 mb-4">
                <div class="card">
                    <div class="card-body">
                        <div class="d-flex align-items-center mb-3">
                            <div class="avatar-md me-3 loading-skeleton rounded"></div>
                            <div class="flex-grow-1">
                                <div class="loading-skeleton" style="height: 20px; width: 60%; margin-bottom: 8px;"></div>
                                <div class="loading-skeleton" style="height: 16px; width: 40%;"></div>
                            </div>
                        </div>
                        <div class="loading-skeleton" style="height: 60px; margin-bottom: 16px;"></div>
                        <div class="loading-skeleton" style="height: 36px;"></div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    /**
     * Handle responsive behavior
     */
    handleResponsive() {
        const handleResize = () => {
            const isMobile = window.innerWidth < 768;
            const cards = document.querySelectorAll('.club-card, .lotto-club-card, .sas-club-card');
            
            cards.forEach(card => {
                if (isMobile) {
                    card.style.transform = 'none';
                    card.addEventListener('touchstart', () => {
                        card.style.backgroundColor = '#f8f9fa';
                    });
                    card.addEventListener('touchend', () => {
                        setTimeout(() => {
                            card.style.backgroundColor = '';
                        }, 150);
                    });
                }
            });
        };

        window.addEventListener('resize', handleResize);
        handleResize(); // Initial call
    }
}

/**
 * Utility functions
 */
const ClubsUtils = {
    /**
     * Format currency
     */
    formatCurrency(amount) {
        return new Intl.NumberFormat('en-ZA', {
            style: 'currency',
            currency: 'ZAR'
        }).format(amount);
    },

    /**
     * Format date
     */
    formatDate(date) {
        return new Intl.DateTimeFormat('en-ZA', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        }).format(new Date(date));
    },

    /**
     * Truncate text
     */
    truncateText(text, maxLength = 50) {
        if (text.length <= maxLength) return text;
        return text.substr(0, maxLength) + '...';
    },

    /**
     * Show toast notification
     */
    showToast(message, type = 'success') {
        // Implementation depends on your toast library
        console.log(`Toast (${type}): ${message}`);
    }
};

/**
 * Global functions for template usage
 */
window.applyFilters = function() {
    if (window.clubsManager) {
        window.clubsManager.applyFilters();
    }
};

window.clearFilters = function() {
    if (window.clubsManager) {
        window.clubsManager.clearFilters();
    }
};

/**
 * Initialize when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function() {
    window.clubsManager = new ClubsManager();
    
    // Handle responsive behavior
    window.clubsManager.handleResponsive();
    
    // Initialize any additional features
    console.log('Clubs management system initialized');
});