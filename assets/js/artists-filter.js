/**
 * Artists Page Filtering & Interactions
 * Handles name search, genre filtering, and smooth scrolling
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

    // Populate options (respecting hidden state)
    Array.from(selectElement.options).forEach((option, index) => {
        const li = document.createElement('li');
        li.className = 'custom-dropdown-option';
        li.setAttribute('role', 'option');
        li.setAttribute('data-value', option.value);
        li.setAttribute('data-text', option.text.toLowerCase());
        li.textContent = option.text;

        // Preserve hidden state from native select
        if (option.hidden) {
            li.classList.add('hidden');
        }

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
        },
        // Sync hidden state with native select options
        syncHiddenState: () => {
            Array.from(selectElement.options).forEach((option, index) => {
                const li = listbox.querySelectorAll('.custom-dropdown-option')[index];
                if (li) {
                    li.classList.toggle('hidden', option.hidden);
                }
            });
        }
    };
}

function initArtistsFilters() {
    // Only run on artists page
    const artistsPage = document.querySelector('.artists-page');
    if (!artistsPage) return;

    // Prevent duplicate initialization
    if (artistsPage.dataset.initialized === 'true') return;
    artistsPage.dataset.initialized = 'true';

    // DOM Elements
    const searchInput = document.getElementById('artist-search');
    const resultsCount = document.getElementById('results-count');
    const genreSelect = document.getElementById('genre-select');
    const activeFiltersContainer = document.getElementById('active-filters');
    const activeTagsContainer = document.getElementById('active-tags');
    const clearFiltersBtn = document.getElementById('clear-filters');
    const resetFiltersBtn = document.getElementById('reset-filters');
    const noResultsEl = document.getElementById('no-results');
    const backToTopBtn = document.getElementById('back-to-top');
    const filtersSection = document.querySelector('.artists-filters');
    const artistsGrid = document.getElementById('artists-grid');

    // All cards
    const allCards = document.querySelectorAll('.artist-card');
    const totalArtists = allCards.length;
    const artistsWithShows = parseInt(artistsGrid?.dataset.artistsWithShows || totalArtists, 10);

    // Include inactive toggle
    const includeInactiveToggle = document.getElementById('include-inactive');
    const artistJumpSelect = document.getElementById('artist-jump-select');

    // Create custom dropdowns (both searchable)
    const customArtistDropdown = createCustomDropdown(artistJumpSelect, { searchable: true });
    const customGenreDropdown = createCustomDropdown(genreSelect, { searchable: true });

    // Current filter state
    let filters = {
        search: '',
        genre: '',  // Single genre filter (changed from genres array)
        includeInactive: false
    };

    /**
     * Apply all current filters and update UI
     */
    function applyFilters() {
        let visibleCount = 0;
        const searchTerm = filters.search.toLowerCase().trim();
        const baseCount = filters.includeInactive ? totalArtists : artistsWithShows;

        allCards.forEach(card => {
            let visible = true;

            // Inactive filter (artists without shows)
            if (!filters.includeInactive && card.dataset.hasShows === 'false') {
                visible = false;
            }

            // Search filter
            if (visible && searchTerm) {
                const name = card.dataset.name || '';
                if (!name.includes(searchTerm)) {
                    visible = false;
                }
            }

            // Genre filter (card must contain the selected genre)
            if (visible && filters.genre) {
                const cardGenres = (card.dataset.genres || '').split(',').map(g => g.trim()).filter(g => g);
                if (!cardGenres.includes(filters.genre)) {
                    visible = false;
                }
            }

            // Apply visibility with animation
            if (visible) {
                card.classList.remove('hidden');
                card.style.animation = 'none';
                card.offsetHeight; // Trigger reflow
                card.style.animation = 'fadeInUp 0.3s ease forwards';
                visibleCount++;
            } else {
                card.classList.add('hidden');
            }
        });

        // Update results count
        if (filters.search || filters.genre) {
            resultsCount.textContent = `Showing ${visibleCount} of ${baseCount} artists`;
        } else {
            resultsCount.textContent = `Showing ${baseCount} artists`;
        }

        // Show/hide no results message
        if (noResultsEl) {
            noResultsEl.style.display = visibleCount === 0 ? 'block' : 'none';
        }
        if (artistsGrid) {
            artistsGrid.style.display = visibleCount === 0 ? 'none' : 'grid';
        }

        // Update active filters display
        updateActiveFiltersDisplay();
    }

    /**
     * Update the active filters UI display
     */
    function updateActiveFiltersDisplay() {
        const hasActiveFilters = filters.search || filters.genre;

        if (!hasActiveFilters) {
            activeFiltersContainer.style.display = 'none';
            return;
        }

        activeFiltersContainer.style.display = 'flex';
        activeTagsContainer.innerHTML = '';

        // Search tag
        if (filters.search) {
            addActiveTag(`"${filters.search}"`, () => {
                searchInput.value = '';
                filters.search = '';
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
     * Reset all filters (except includeInactive toggle)
     */
    function resetFilters() {
        if (searchInput) searchInput.value = '';
        if (genreSelect) {
            genreSelect.value = '';
            if (customGenreDropdown) customGenreDropdown.update('');
        }

        filters = {
            search: '',
            genre: '',
            includeInactive: filters.includeInactive // preserve toggle state
        };

        applyFilters();
    }

    /**
     * Initialize filters from URL parameters
     * Supports ?genre=<slug> for direct linking from artist pages
     */
    function initFromUrlParams() {
        const params = new URLSearchParams(window.location.search);
        const genreParam = params.get('genre');

        if (genreParam && genreSelect) {
            // Decode and normalize the genre (lowercase, trimmed)
            const genre = decodeURIComponent(genreParam).toLowerCase().trim();

            // Find matching option in select
            const matchingOption = Array.from(genreSelect.options).find(
                opt => opt.value === genre
            );

            if (matchingOption) {
                genreSelect.value = genre;
                filters.genre = genre;
                if (customGenreDropdown) customGenreDropdown.update(genre);
                applyFilters();
            }
        }
    }

    // Event Listeners

    // Search input with debounce
    let searchTimeout;
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                filters.search = this.value;
                applyFilters();
            }, 150);
        });

        // Clear on escape
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && this.value) {
                this.value = '';
                filters.search = '';
                applyFilters();
            }
        });
    }

    // Include inactive toggle
    if (includeInactiveToggle) {
        includeInactiveToggle.addEventListener('change', function() {
            filters.includeInactive = this.checked;

            // Update dropdown options visibility
            const dropdownOptions = artistJumpSelect?.querySelectorAll('option[data-has-shows]');
            dropdownOptions?.forEach(option => {
                if (option.dataset.hasShows === 'false') {
                    option.hidden = !filters.includeInactive;
                }
            });

            // Sync custom dropdown hidden state
            if (customArtistDropdown) {
                customArtistDropdown.syncHiddenState();
            }

            applyFilters();
        });
    }

    // Artist jump dropdown - navigate to artist page via turbo-frame navigation (preserves audio)
    if (artistJumpSelect) {
        artistJumpSelect.addEventListener('change', function() {
            if (this.value) {
                // Create link targeting turbo-frame to ensure frame navigation (not Drive)
                // Links outside the frame default to Drive navigation which disrupts iframes
                const link = document.createElement('a');
                link.href = this.value;
                link.dataset.turboFrame = 'main-content';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        });
    }

    // Genre select dropdown
    if (genreSelect) {
        genreSelect.addEventListener('change', function() {
            filters.genre = this.value;
            applyFilters();
        });
    }

    // Initialize from URL params
    initFromUrlParams();

    // Apply default filters (hide inactive artists) on initial load
    applyFilters();

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

    // Sticky filter shadow on scroll + mobile collapse
    const filterExpandBtn = document.getElementById('filter-expand-btn');

    if (filtersSection) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 200) {
                filtersSection.classList.add('scrolled');
                // Remove expanded state when scrolling down
                if (window.scrollY > 300) {
                    filtersSection.classList.remove('expanded');
                }
            } else {
                filtersSection.classList.remove('scrolled');
                filtersSection.classList.remove('expanded');
            }
        }, { passive: true });
    }

    // Mobile filter expand toggle
    if (filterExpandBtn) {
        filterExpandBtn.addEventListener('click', function() {
            filtersSection.classList.toggle('expanded');
        });
    }
}

// Initialize on Turbo navigation
document.addEventListener('turbo:load', initArtistsFilters);

// Also initialize immediately if DOM is ready
if (document.readyState !== 'loading') {
    initArtistsFilters();
}
