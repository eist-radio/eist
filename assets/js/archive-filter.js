/**
 * Archive Page Filtering & Interactions
 * Handles month/artist/genre filtering, toggle switches, and smooth scrolling
 */


/**
 * Custom Dropdown Component
 * Replaces native select elements with styled, accessible dropdowns
 * Supports optional search/filter functionality
 */
function createCustomDropdown(selectElement, options = {}) {
    if (!selectElement) return null;

    const { searchable = false } = options;

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-dropdown' + (searchable ? ' searchable' : '');

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'custom-dropdown-btn';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');

    const selectedText = document.createElement('span');
    selectedText.className = 'custom-dropdown-selected';
    selectedText.textContent = selectElement.options[selectElement.selectedIndex]?.text || 'Select...';

    const arrow = document.createElement('span');
    arrow.className = 'custom-dropdown-arrow';
    arrow.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>';

    button.appendChild(selectedText);
    button.appendChild(arrow);

    // Search input (optional)
    let searchInput = null;
    let searchWrapper = null;
    if (searchable) {
        searchWrapper = document.createElement('div');
        searchWrapper.className = 'custom-dropdown-search';
        searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'custom-dropdown-search-input';
        searchInput.placeholder = 'Type to filter...';
        searchInput.autocomplete = 'off';
        searchWrapper.appendChild(searchInput);
    }

    const listbox = document.createElement('ul');
    listbox.className = 'custom-dropdown-list';
    listbox.setAttribute('role', 'listbox');
    listbox.setAttribute('tabindex', '-1');

    // Populate options
    Array.from(selectElement.options).forEach((option, index) => {
        const li = document.createElement('li');
        li.className = 'custom-dropdown-option';
        li.setAttribute('role', 'option');
        li.setAttribute('data-value', option.value);
        li.setAttribute('data-text', option.text.toLowerCase());
        li.textContent = option.text;

        if (option.selected) {
            li.classList.add('selected');
            li.setAttribute('aria-selected', 'true');
        }

        li.addEventListener('click', () => {
            // Update native select
            selectElement.value = option.value;
            selectElement.dispatchEvent(new Event('change', { bubbles: true }));

            // Update custom dropdown
            selectedText.textContent = option.text;
            listbox.querySelectorAll('.custom-dropdown-option').forEach(o => {
                o.classList.remove('selected');
                o.setAttribute('aria-selected', 'false');
            });
            li.classList.add('selected');
            li.setAttribute('aria-selected', 'true');

            // Close dropdown and clear search
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
            if (searchInput) {
                searchInput.value = '';
                filterOptions('');
            }
        });

        listbox.appendChild(li);
    });

    wrapper.appendChild(button);
    if (searchWrapper) {
        wrapper.appendChild(searchWrapper);
    }
    wrapper.appendChild(listbox);

    // Filter options based on search term
    function filterOptions(term) {
        const normalizedTerm = term.toLowerCase().trim();
        listbox.querySelectorAll('.custom-dropdown-option').forEach(li => {
            const text = li.getAttribute('data-text') || '';
            const matches = !normalizedTerm || text.includes(normalizedTerm);
            li.classList.toggle('search-hidden', !matches);
        });
    }

    // Search input events
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterOptions(e.target.value);
        });

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                filterOptions('');
                wrapper.classList.remove('open');
                button.setAttribute('aria-expanded', 'false');
                button.focus();
            }
        });
    }

    // Toggle dropdown
    button.addEventListener('click', (e) => {
        e.preventDefault();
        const isOpen = wrapper.classList.contains('open');

        // Close all other dropdowns
        document.querySelectorAll('.custom-dropdown.open').forEach(d => {
            d.classList.remove('open');
            d.querySelector('.custom-dropdown-btn')?.setAttribute('aria-expanded', 'false');
            const si = d.querySelector('.custom-dropdown-search-input');
            if (si) {
                si.value = '';
                d.querySelectorAll('.custom-dropdown-option').forEach(o => o.classList.remove('search-hidden'));
            }
        });

        if (!isOpen) {
            wrapper.classList.add('open');
            button.setAttribute('aria-expanded', 'true');
            if (searchInput) {
                setTimeout(() => searchInput.focus(), 50);
            }
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
            if (searchInput) {
                searchInput.value = '';
                filterOptions('');
            }
        }
    });

    // Keyboard navigation
    wrapper.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
            if (searchInput) {
                searchInput.value = '';
                filterOptions('');
            }
            button.focus();
        }
    });

    // Hide original select and insert custom dropdown
    selectElement.style.display = 'none';
    selectElement.parentNode.insertBefore(wrapper, selectElement);

    return {
        wrapper,
        update: (value) => {
            const option = Array.from(selectElement.options).find(o => o.value === value);
            if (option) {
                selectedText.textContent = option.text;
                listbox.querySelectorAll('.custom-dropdown-option').forEach(o => {
                    o.classList.toggle('selected', o.dataset.value === value);
                });
            }
        }
    };
}

function initArchiveFilters() {
    // Only run on archive page
    const archivePage = document.querySelector('.archive-page');
    if (!archivePage) return;

    // Prevent duplicate initialization on the same page instance
    if (archivePage.dataset.initialized === 'true') return;
    archivePage.dataset.initialized = 'true';

    // DOM Elements
    const monthSelect = document.getElementById('month-select');
    const artistSelect = document.getElementById('artist-select');
    const genreSelect = document.getElementById('genre-select');

    // Create custom dropdowns (artist and genre are searchable)
    const customMonthDropdown = createCustomDropdown(monthSelect);
    const customArtistDropdown = createCustomDropdown(artistSelect, { searchable: true });
    const customGenreDropdown = createCustomDropdown(genreSelect, { searchable: true });
    const includeUnarchivedToggle = document.getElementById('include-unarchived');
    const activeFiltersContainer = document.getElementById('active-filters');
    const activeTagsContainer = document.getElementById('active-tags');
    const clearFiltersBtn = document.getElementById('clear-filters');
    const resetFiltersBtn = document.getElementById('reset-filters');
    const noResultsEl = document.getElementById('no-results');
    const backToTopBtn = document.getElementById('back-to-top');
    const filtersSection = document.querySelector('.archive-filters');

    // All cards and timeline months
    const allCards = document.querySelectorAll('.archive-card');
    const allMonths = document.querySelectorAll('.timeline-month');

    // Current filter state - default to showing only archived shows
    let filters = {
        month: '',
        artist: '',
        includeUnarchived: false,  // false = archived only (default)
        genre: ''  // Single genre filter (changed from genres array)
    };

    /**
     * Apply all current filters and update UI
     */
    function applyFilters() {
        let visibleCount = 0;
        // Active filters shown when any non-default filter is set
        let hasActiveFilters = filters.month || filters.artist || filters.includeUnarchived || filters.genre;

        // Filter cards
        allCards.forEach(card => {
            let visible = true;

            // By default, only show archived. If includeUnarchived is true, show all.
            if (!filters.includeUnarchived && card.dataset.hasArchive !== 'true') {
                visible = false;
            }

            // Artist filter
            if (visible && filters.artist && card.dataset.artist !== filters.artist) {
                visible = false;
            }

            // Genre filter (card must contain the selected genre)
            if (visible && filters.genre) {
                const cardGenres = (card.dataset.genres || '').split(',').map(g => g.trim()).filter(g => g);
                if (!cardGenres.includes(filters.genre)) {
                    visible = false;
                }
            }

            // Apply visibility
            card.classList.toggle('hidden', !visible);
            if (visible) visibleCount++;
        });

        // Handle month sections visibility
        allMonths.forEach(month => {
            const monthKey = month.dataset.month;

            // If month filter is active, hide non-matching months
            if (filters.month && monthKey !== filters.month) {
                month.classList.add('hidden');
                return;
            }

            // Check if this month has any visible cards
            const visibleCardsInMonth = month.querySelectorAll('.archive-card:not(.hidden)');
            month.classList.toggle('hidden', visibleCardsInMonth.length === 0);
        });

        // Show/hide no results message
        noResultsEl.style.display = visibleCount === 0 ? 'block' : 'none';

        // Update active filters display
        updateActiveFiltersDisplay(hasActiveFilters);
    }

    /**
     * Update the active filters UI display
     */
    function updateActiveFiltersDisplay(hasActiveFilters) {
        if (!hasActiveFilters) {
            activeFiltersContainer.style.display = 'none';
            return;
        }

        activeFiltersContainer.style.display = 'flex';
        activeTagsContainer.innerHTML = '';

        // Month tag
        if (filters.month) {
            const date = new Date(filters.month + '-01');
            const monthName = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
            addActiveTag(monthName, () => {
                monthSelect.value = '';
                filters.month = '';
                applyFilters();
            });
        }

        // Artist tag
        if (filters.artist) {
            const artistName = artistSelect.options[artistSelect.selectedIndex].text;
            addActiveTag(artistName, () => {
                artistSelect.value = '';
                filters.artist = '';
                applyFilters();
            });
        }

        // Include unarchived tag (shown when toggle is on)
        if (filters.includeUnarchived) {
            addActiveTag('Including unrecorded', () => {
                includeUnarchivedToggle.checked = false;
                filters.includeUnarchived = false;
                applyFilters();
            });
        }

        // Genre tag
        if (filters.genre) {
            const genreLabel = genreSelect?.options[genreSelect.selectedIndex]?.text || filters.genre.toUpperCase();
            addActiveTag(genreLabel, () => {
                genreSelect.value = '';
                filters.genre = '';
                if (customGenreDropdown) customGenreDropdown.update('');
                applyFilters();
            });
        }
    }

    /**
     * Add an active filter tag to the display
     */
    function addActiveTag(label, onRemove) {
        const tag = document.createElement('span');
        tag.className = 'active-tag';
        tag.innerHTML = `${label} <button aria-label="Remove filter">&times;</button>`;
        tag.querySelector('button').addEventListener('click', onRemove);
        activeTagsContainer.appendChild(tag);
    }

    /**
     * Reset all filters to default state (archived only)
     */
    function resetFilters() {
        if (monthSelect) {
            monthSelect.value = '';
            if (customMonthDropdown) customMonthDropdown.update('');
        }
        if (artistSelect) {
            artistSelect.value = '';
            if (customArtistDropdown) customArtistDropdown.update('');
        }
        if (genreSelect) {
            genreSelect.value = '';
            if (customGenreDropdown) customGenreDropdown.update('');
        }
        if (includeUnarchivedToggle) includeUnarchivedToggle.checked = false;

        filters = {
            month: '',
            artist: '',
            includeUnarchived: false,
            genre: ''
        };

        applyFilters();
    }

    // Event Listeners

    // Month select
    if (monthSelect) {
        monthSelect.addEventListener('change', function() {
            filters.month = this.value;
            applyFilters();

            // Scroll to selected month if exists
            if (this.value) {
                const targetMonth = document.getElementById('month-' + this.value);
                if (targetMonth) {
                    targetMonth.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    }

    // Artist select
    if (artistSelect) {
        artistSelect.addEventListener('change', function() {
            filters.artist = this.value;
            applyFilters();
        });
    }

    // Include unarchived toggle
    if (includeUnarchivedToggle) {
        includeUnarchivedToggle.addEventListener('change', function() {
            filters.includeUnarchived = this.checked;
            applyFilters();
        });
    }

    // Genre select dropdown
    if (genreSelect) {
        genreSelect.addEventListener('change', function() {
            filters.genre = this.value;
            applyFilters();
        });
    }

    // Clear filters button
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', resetFilters);
    }

    // Reset filters button (in no results message)
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', resetFilters);
    }

    // Back to top button
    if (backToTopBtn) {
        backToTopBtn.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // Floating month indicator - tracks visible month section
    const floatingIndicator = document.getElementById('floating-month-indicator');
    const floatingMonthName = document.getElementById('floating-month-name');
    const floatingMonthYear = document.getElementById('floating-month-year');
    const floatingMonthCount = document.getElementById('floating-month-count');
    const timelineMonths = document.querySelectorAll('.timeline-month');

    if (floatingIndicator && timelineMonths.length > 0) {
        // Month name mapping
        const monthNames = {
            '01': 'January', '02': 'February', '03': 'March', '04': 'April',
            '05': 'May', '06': 'June', '07': 'July', '08': 'August',
            '09': 'September', '10': 'October', '11': 'November', '12': 'December'
        };

        let lastVisibleMonth = null;

        function updateFloatingIndicator() {
            const scrollY = window.scrollY;
            const threshold = 300; // Show after scrolling past filters

            if (scrollY < threshold) {
                floatingIndicator.classList.remove('visible');
                return;
            }

            // Find the currently visible month section
            let currentMonth = null;
            const viewportTop = scrollY + 120; // Account for fixed header + player

            for (const monthEl of timelineMonths) {
                // Check if this month section is visible (only visible months, not filtered out)
                if (monthEl.style.display === 'none') continue;

                const rect = monthEl.getBoundingClientRect();
                const monthTop = scrollY + rect.top;
                const monthBottom = monthTop + rect.height;

                // This month is visible if we're within its bounds
                if (viewportTop >= monthTop - 50 && viewportTop < monthBottom) {
                    currentMonth = monthEl;
                    break;
                }
            }

            if (!currentMonth) {
                // Find the last month we passed
                for (let i = timelineMonths.length - 1; i >= 0; i--) {
                    const monthEl = timelineMonths[i];
                    if (monthEl.style.display === 'none') continue;

                    const rect = monthEl.getBoundingClientRect();
                    if (rect.top < 150) {
                        currentMonth = monthEl;
                        break;
                    }
                }
            }

            if (currentMonth) {
                const monthKey = currentMonth.dataset.month; // e.g., "2025-11"
                if (monthKey && monthKey !== lastVisibleMonth) {
                    lastVisibleMonth = monthKey;
                    const [year, month] = monthKey.split('-');
                    const monthHeader = currentMonth.querySelector('.month-header');
                    const showCount = monthHeader?.querySelector('.month-count')?.textContent || '';

                    floatingMonthName.textContent = monthNames[month] || month;
                    floatingMonthYear.textContent = year;
                    floatingMonthCount.textContent = showCount;
                }
                floatingIndicator.classList.add('visible');
            } else {
                floatingIndicator.classList.remove('visible');
            }
        }

        window.addEventListener('scroll', updateFloatingIndicator, { passive: true });
        // Initial check
        updateFloatingIndicator();
    }

    // Apply default filters on page load (archived only by default)
    applyFilters();
}

// Initialize on Turbo navigation (handles both fresh load and Turbo navigations)
document.addEventListener('turbo:load', initArchiveFilters);

// Also initialize immediately if DOM is already ready (handles async script loading)
if (document.readyState !== 'loading') {
    initArchiveFilters();
}
