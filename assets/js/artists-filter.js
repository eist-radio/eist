/**
 * Artists Page Filtering & Interactions
 * Handles name search, genre filtering, and smooth scrolling
 */

// Track escape key listener to prevent accumulation
let artistsEscapeKeyHandler = null;

/**
 * Custom Dropdown Component
 * Replaces native select elements with styled, accessible dropdowns
 */
function createCustomDropdown(selectElement) {
    if (!selectElement) return null;

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-dropdown';

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

            // Close dropdown
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        });

        listbox.appendChild(li);
    });

    wrapper.appendChild(button);
    wrapper.appendChild(listbox);

    // Toggle dropdown
    button.addEventListener('click', (e) => {
        e.preventDefault();
        const isOpen = wrapper.classList.contains('open');

        // Close all other dropdowns
        document.querySelectorAll('.custom-dropdown.open').forEach(d => {
            d.classList.remove('open');
            d.querySelector('.custom-dropdown-btn')?.setAttribute('aria-expanded', 'false');
        });

        if (!isOpen) {
            wrapper.classList.add('open');
            button.setAttribute('aria-expanded', 'true');
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        }
    });

    // Keyboard navigation
    wrapper.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            wrapper.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
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
    const genreTags = document.querySelectorAll('.genre-filter-tag');
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

    // Create custom dropdown for artist jump select
    const customArtistDropdown = createCustomDropdown(artistJumpSelect);

    // Current filter state
    let filters = {
        search: '',
        genres: [],
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

            // Genre filter (card must have at least one of the selected genres)
            if (visible && filters.genres.length > 0) {
                const cardGenres = (card.dataset.genres || '').split(',').map(g => g.trim()).filter(g => g);
                const hasMatchingGenre = filters.genres.some(g => cardGenres.includes(g));
                if (!hasMatchingGenre) {
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
        if (filters.search || filters.genres.length > 0) {
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
        const hasActiveFilters = filters.search || filters.genres.length > 0;

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

        // Genre tags
        filters.genres.forEach(genre => {
            addActiveTag(genre.toUpperCase(), () => {
                filters.genres = filters.genres.filter(g => g !== genre);
                // Update genre tag button state
                genreTags.forEach(tag => {
                    if (tag.dataset.genre === genre) {
                        tag.classList.remove('active');
                    }
                });
                // Also update drawer tags
                const drawerTag = document.querySelector(`.genre-drawer-tag[data-genre="${genre}"]`);
                if (drawerTag) drawerTag.classList.remove('active');
                applyFilters();
            });
        });
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
        searchInput.value = '';
        genreTags.forEach(tag => tag.classList.remove('active'));
        document.querySelectorAll('.genre-drawer-tag').forEach(tag => tag.classList.remove('active'));

        filters = {
            search: '',
            genres: [],
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

        if (genreParam) {
            // Decode and normalize the genre (lowercase, trimmed)
            const genre = decodeURIComponent(genreParam).toLowerCase().trim();

            // Find and activate the matching genre tag in visible row
            let foundInRow = false;
            genreTags.forEach(tag => {
                if (tag.dataset.genre === genre) {
                    tag.classList.add('active');
                    filters.genres.push(genre);
                    foundInRow = true;
                }
            });

            // If not in visible row, check drawer and inject into visible row
            if (!foundInRow) {
                let foundInDrawer = false;
                let genreDisplayName = genre.toUpperCase();

                // Find the genre in drawer to get its proper display name
                drawerTags.forEach(tag => {
                    if (tag.dataset.genre === genre) {
                        foundInDrawer = true;
                        genreDisplayName = tag.textContent.trim();
                        tag.classList.add('active');
                    }
                });

                if (foundInDrawer) {
                    // Inject genre pill into visible row
                    const genreTagsContainer = document.getElementById('genre-tags');
                    const showMoreBtn = document.getElementById('show-more-genres');

                    if (genreTagsContainer) {
                        // Create new pill button with same structure as existing pills
                        const newPill = document.createElement('button');
                        newPill.className = 'genre-filter-tag active';
                        newPill.dataset.genre = genre;
                        newPill.textContent = genreDisplayName;

                        // Add click handler matching existing pills
                        newPill.addEventListener('click', function() {
                            if (this.classList.contains('active')) {
                                this.classList.remove('active');
                                filters.genres = filters.genres.filter(g => g !== genre);
                            } else {
                                this.classList.add('active');
                                filters.genres.push(genre);
                            }
                            syncDrawerTagsWithFilters();
                            applyFilters();
                        });

                        // Find last visible (non-hidden) pill to replace
                        const visiblePills = Array.from(genreTagsContainer.querySelectorAll('.genre-filter-tag:not(.url-hidden)'));
                        if (visiblePills.length > 0) {
                            const lastPill = visiblePills[visiblePills.length - 1];
                            // Hide the last pill instead of removing it
                            lastPill.classList.add('url-hidden');
                            lastPill.style.display = 'none';
                        }

                        // Insert before "+X more" button if it exists, otherwise append
                        if (showMoreBtn) {
                            genreTagsContainer.insertBefore(newPill, showMoreBtn);
                        } else {
                            genreTagsContainer.appendChild(newPill);
                        }

                        filters.genres.push(genre);
                    }
                }
            }

            // Apply filters if genre was found
            if (filters.genres.length > 0) {
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

    // Genre tag buttons (main row)
    genreTags.forEach(tag => {
        tag.addEventListener('click', function() {
            const genre = this.dataset.genre;

            if (this.classList.contains('active')) {
                this.classList.remove('active');
                filters.genres = filters.genres.filter(g => g !== genre);
            } else {
                this.classList.add('active');
                filters.genres.push(genre);
            }

            // Sync drawer tags
            syncDrawerTagsWithFilters();
            applyFilters();
        });
    });

    // Genre Drawer functionality
    const genreDrawer = document.getElementById('genre-drawer');
    const genreDrawerOverlay = document.getElementById('genre-drawer-overlay');
    const showMoreGenresBtn = document.getElementById('show-more-genres');
    const closeDrawerBtn = document.getElementById('close-genre-drawer');
    const genreSearch = document.getElementById('genre-search');
    const genreNoResults = document.getElementById('genre-no-results');
    const selectedGenreCount = document.getElementById('selected-genre-count');
    const clearGenreSelectionBtn = document.getElementById('clear-genre-selection');
    const applyGenreSelectionBtn = document.getElementById('apply-genre-selection');
    const drawerTags = document.querySelectorAll('.genre-drawer-tag');

    // Initialize from URL params (must be after drawerTags is defined)
    initFromUrlParams();

    // Apply default filters (hide inactive artists) on initial load
    applyFilters();

    function openGenreDrawer() {
        if (!genreDrawer) return;
        // Move drawer and overlay to body to escape stacking context
        if (genreDrawer.parentElement !== document.body) {
            document.body.appendChild(genreDrawer);
        }
        if (genreDrawerOverlay && genreDrawerOverlay.parentElement !== document.body) {
            document.body.appendChild(genreDrawerOverlay);
        }
        genreDrawer.classList.add('active');
        genreDrawerOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        syncDrawerTagsWithFilters();
        updateSelectedCount();
        setTimeout(() => genreSearch?.focus(), 100);
    }

    function closeGenreDrawer() {
        if (!genreDrawer) return;
        genreDrawer.classList.remove('active');
        genreDrawerOverlay.classList.remove('active');
        document.body.style.overflow = '';
        if (genreSearch) genreSearch.value = '';
        filterDrawerGenres('');
    }

    function syncDrawerTagsWithFilters() {
        drawerTags.forEach(tag => {
            const genre = tag.dataset.genre;
            tag.classList.toggle('active', filters.genres.includes(genre));
        });
    }

    function syncMainTagsWithFilters() {
        genreTags.forEach(tag => {
            const genre = tag.dataset.genre;
            tag.classList.toggle('active', filters.genres.includes(genre));
        });
    }

    function updateSelectedCount() {
        if (selectedGenreCount) {
            selectedGenreCount.textContent = filters.genres.length;
        }
    }

    function filterDrawerGenres(searchTerm) {
        const term = searchTerm.toLowerCase().trim();
        let visibleCount = 0;

        drawerTags.forEach(tag => {
            const genreName = tag.textContent.toLowerCase();
            const matches = !term || genreName.includes(term);
            tag.classList.toggle('hidden', !matches);
            if (matches) visibleCount++;
        });

        if (genreNoResults) {
            genreNoResults.style.display = visibleCount === 0 ? 'block' : 'none';
        }
    }

    // Drawer event listeners
    if (showMoreGenresBtn) {
        showMoreGenresBtn.addEventListener('click', openGenreDrawer);
    }

    if (closeDrawerBtn) {
        closeDrawerBtn.addEventListener('click', closeGenreDrawer);
    }

    if (genreDrawerOverlay) {
        genreDrawerOverlay.addEventListener('click', closeGenreDrawer);
    }

    if (genreSearch) {
        genreSearch.addEventListener('input', function() {
            filterDrawerGenres(this.value);
        });
    }

    // Drawer tag clicks
    drawerTags.forEach(tag => {
        tag.addEventListener('click', function() {
            const genre = this.dataset.genre;

            if (this.classList.contains('active')) {
                this.classList.remove('active');
                filters.genres = filters.genres.filter(g => g !== genre);
            } else {
                this.classList.add('active');
                filters.genres.push(genre);
            }

            updateSelectedCount();
        });
    });

    // Clear all genre selections in drawer
    if (clearGenreSelectionBtn) {
        clearGenreSelectionBtn.addEventListener('click', function() {
            filters.genres = [];
            drawerTags.forEach(tag => tag.classList.remove('active'));
            updateSelectedCount();
        });
    }

    // Apply genre selections and close drawer
    if (applyGenreSelectionBtn) {
        applyGenreSelectionBtn.addEventListener('click', function() {
            syncMainTagsWithFilters();
            applyFilters();
            closeGenreDrawer();
        });
    }

    // Escape key closes drawer - remove previous listener to prevent accumulation
    if (artistsEscapeKeyHandler) {
        document.removeEventListener('keydown', artistsEscapeKeyHandler);
    }
    artistsEscapeKeyHandler = function(e) {
        if (e.key === 'Escape' && genreDrawer?.classList.contains('active')) {
            closeGenreDrawer();
        }
    };
    document.addEventListener('keydown', artistsEscapeKeyHandler);

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
