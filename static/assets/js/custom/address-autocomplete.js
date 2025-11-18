/**
 * Address Autocomplete Module
 *
 * Provides Google Places Autocomplete functionality for address forms
 * Specifically configured for New Zealand addresses
 *
 * Usage:
 *   AddressAutocomplete.init('id_street_address', {
 *       streetField: 'id_street_address',
 *       suburbField: 'id_suburb',
 *       cityField: 'id_city',
 *       postcodeField: 'id_postcode',
 *       regionField: 'id_region'  // Optional hidden field
 *   });
 *
 * @version 1.0.0
 * @requires Google Maps JavaScript API with Places library
 */

const AddressAutocomplete = (function() {
    'use strict';

    /**
     * Configuration defaults
     */
    const defaults = {
        componentRestrictions: { country: 'nz' },
        fields: ['address_components', 'formatted_address'],
        types: ['address'],
        strictBounds: false
    };

    /**
     * Active autocomplete instances
     */
    const instances = {};

    /**
     * Extract address components from Google Places result
     *
     * @param {Object} place - Google Places result object
     * @returns {Object} Extracted address components
     */
    function extractAddressComponents(place) {
        if (!place || !place.address_components) {
            console.warn('AddressAutocomplete: Invalid place object');
            return null;
        }

        const components = {
            street_number: '',
            route: '',
            sublocality_level_1: '',
            locality: '',
            administrative_area_level_2: '',
            postal_code: '',
            administrative_area_level_1: ''
        };

        // Extract all components
        for (const component of place.address_components) {
            const componentType = component.types[0];

            if (components.hasOwnProperty(componentType)) {
                components[componentType] = component.long_name;
            }
        }

        // Build street address (street number + route)
        const streetParts = [components.street_number, components.route].filter(Boolean);
        const streetAddress = streetParts.length > 0
            ? streetParts.join(' ')
            : place.formatted_address.split(',')[0]; // Fallback to first part of formatted address

        // Determine suburb (prefer sublocality_level_1, fallback to locality)
        const suburb = components.sublocality_level_1 || components.locality;

        // Determine city (prefer locality, fallback to administrative_area_level_2)
        const city = components.locality || components.administrative_area_level_2;

        return {
            street_address: streetAddress,
            suburb: suburb,
            city: city,
            postcode: components.postal_code,
            region: components.administrative_area_level_1
        };
    }

    /**
     * Populate form fields with extracted address data
     *
     * @param {Object} addressData - Extracted address components
     * @param {Object} fieldIds - Field ID mappings
     */
    function populateFields(addressData, fieldIds) {
        if (!addressData) return;

        // Populate street address
        if (fieldIds.streetField && addressData.street_address) {
            const streetField = document.getElementById(fieldIds.streetField);
            if (streetField) {
                streetField.value = addressData.street_address;
                // Trigger input event for any listeners
                streetField.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        // Populate suburb
        if (fieldIds.suburbField && addressData.suburb) {
            const suburbField = document.getElementById(fieldIds.suburbField);
            if (suburbField) {
                suburbField.value = addressData.suburb;
                suburbField.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        // Populate city
        if (fieldIds.cityField && addressData.city) {
            const cityField = document.getElementById(fieldIds.cityField);
            if (cityField) {
                cityField.value = addressData.city;
                cityField.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        // Populate postcode
        if (fieldIds.postcodeField && addressData.postcode) {
            const postcodeField = document.getElementById(fieldIds.postcodeField);
            if (postcodeField) {
                postcodeField.value = addressData.postcode;
                postcodeField.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }

        // Populate region (hidden field for shipping calculations)
        if (fieldIds.regionField && addressData.region) {
            let regionField = document.getElementById(fieldIds.regionField);

            // Create hidden field if it doesn't exist
            if (!regionField) {
                regionField = document.createElement('input');
                regionField.type = 'hidden';
                regionField.id = fieldIds.regionField;
                regionField.name = fieldIds.regionField.replace('id_', '');
                document.querySelector('form').appendChild(regionField);
            }

            regionField.value = addressData.region;
        }
    }

    /**
     * Show loading indicator on autocomplete field
     *
     * @param {HTMLElement} field - Input field element
     * @param {boolean} show - Show or hide loading indicator
     */
    function toggleLoadingIndicator(field, show) {
        if (!field) return;

        const indicator = field.parentElement.querySelector('.autocomplete-loading');

        if (show) {
            if (!indicator) {
                const loader = document.createElement('div');
                loader.className = 'autocomplete-loading';
                loader.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i>';
                loader.style.cssText = 'position:absolute;right:10px;top:50%;transform:translateY(-50%);color:#999;';
                field.parentElement.style.position = 'relative';
                field.parentElement.appendChild(loader);
            }
        } else {
            if (indicator) {
                indicator.remove();
            }
        }
    }

    /**
     * Initialize autocomplete on a specific field
     *
     * @param {string} inputFieldId - ID of the input field to attach autocomplete
     * @param {Object} fieldIds - Mapping of field IDs for population
     * @param {Object} options - Additional autocomplete options
     * @returns {Object|null} Autocomplete instance or null if failed
     */
    function init(inputFieldId, fieldIds, options = {}) {
        // Check if Google Maps API is loaded
        if (typeof google === 'undefined' || !google.maps || !google.maps.places) {
            console.error('AddressAutocomplete: Google Maps Places API not loaded');
            return null;
        }

        // Get input field
        const inputField = document.getElementById(inputFieldId);
        if (!inputField) {
            console.error(`AddressAutocomplete: Input field '${inputFieldId}' not found`);
            return null;
        }

        // Merge options with defaults
        const config = Object.assign({}, defaults, options);

        // Create autocomplete instance
        const autocomplete = new google.maps.places.Autocomplete(inputField, config);

        // Add visual indicator
        inputField.setAttribute('placeholder', 'Start typing your address...');
        inputField.setAttribute('autocomplete', 'off');

        // Handle place selection
        autocomplete.addListener('place_changed', function() {
            toggleLoadingIndicator(inputField, true);

            const place = autocomplete.getPlace();

            if (!place || !place.address_components) {
                console.warn('AddressAutocomplete: No address details available');
                toggleLoadingIndicator(inputField, false);
                return;
            }

            // Extract and populate address components
            const addressData = extractAddressComponents(place);
            populateFields(addressData, fieldIds);

            toggleLoadingIndicator(inputField, false);

            // Trigger custom event for external listeners
            const event = new CustomEvent('addressAutocompleted', {
                detail: { addressData: addressData, place: place }
            });
            inputField.dispatchEvent(event);

            // Force hide the dropdown after selection
            // Use multiple strategies to ensure dropdown is hidden

            // Strategy 1: Direct blur to trigger autocomplete's internal hiding
            inputField.blur();

            // Strategy 2: Force hide via display:none with retries
            const hideDropdown = (attempts = 0) => {
                const pacContainers = document.querySelectorAll('.pac-container');
                if (pacContainers.length > 0) {
                    pacContainers.forEach(container => {
                        container.style.display = 'none';
                        container.style.visibility = 'hidden';
                    });
                } else if (attempts < 5) {
                    // Retry if dropdown not yet rendered
                    setTimeout(() => hideDropdown(attempts + 1), 50);
                }
            };

            // Execute immediately and with delays
            hideDropdown();
            setTimeout(hideDropdown, 100);
            setTimeout(hideDropdown, 300);
        });

        // Store instance
        instances[inputFieldId] = autocomplete;

        console.log(`AddressAutocomplete: Initialized on field '${inputFieldId}'`);
        return autocomplete;
    }

    /**
     * Get autocomplete instance by field ID
     *
     * @param {string} inputFieldId - ID of the input field
     * @returns {Object|null} Autocomplete instance or null
     */
    function getInstance(inputFieldId) {
        return instances[inputFieldId] || null;
    }

    /**
     * Destroy autocomplete instance
     *
     * @param {string} inputFieldId - ID of the input field
     */
    function destroy(inputFieldId) {
        if (instances[inputFieldId]) {
            google.maps.event.clearInstanceListeners(instances[inputFieldId]);
            delete instances[inputFieldId];
            console.log(`AddressAutocomplete: Destroyed instance for '${inputFieldId}'`);
        }
    }

    /**
     * Check if Google Maps API is ready
     *
     * @returns {boolean} True if API is loaded
     */
    function isApiReady() {
        return typeof google !== 'undefined' &&
               google.maps &&
               google.maps.places;
    }

    // Public API
    return {
        init: init,
        getInstance: getInstance,
        destroy: destroy,
        isApiReady: isApiReady
    };
})();

// Make globally available
window.AddressAutocomplete = AddressAutocomplete;
