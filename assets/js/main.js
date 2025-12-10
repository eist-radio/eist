// Clean reload on first visit
document.addEventListener("DOMContentLoaded", function () {
    if (!sessionStorage.getItem("visited")) {
        console.log("First visit detected");
        sessionStorage.setItem("visited", "true");
        // Reload using Turbo
        setTimeout(() => {
            Turbo.visit(window.location.href, { action: "replace" });
        }, 100);
    }
});

// Scroll to top on Turbo Frame navigation (but not on back/forward)
// This is needed because turbo-frame doesn't auto-scroll like turbo-drive
document.addEventListener("turbo:before-render", (event) => {
    // Only scroll to top for "advance" actions (new navigation), not "restore" (back/forward)
    if (event.detail.renderMethod === "replace" || !event.detail.isPreview) {
        window.scrollTo(0, 0);
    }
});

// Force Turbo to reload the correct state when swiping back/forward on mobile
window.addEventListener("popstate", (event) => {
    Turbo.visit(window.location.href, { action: "replace" });
});

document.addEventListener("turbo:load", () => {
    // Throttle
    //
    const throttle = (callback, limit) => {
        let timeoutHandler = null;
        return () => {
            if (timeoutHandler == null) {
                timeoutHandler = setTimeout(() => {
                    callback();
                    timeoutHandler = null;
                }, limit);
            }
        };
    };

    // addEventListener Helper
    //
    const listen = (ele, e, callback) => {
        if (document.querySelector(ele) !== null) {
            document.querySelector(ele).addEventListener(e, callback);
        }
    }

    /**
     * Functions
     */

    // Auto Hide Header
    //
    let header = document.getElementById('site-header');
    let lastScrollPosition = window.pageYOffset;

    const autoHideHeader = () => {
        let currentScrollPosition = Math.max(window.pageYOffset, 0);
        if (currentScrollPosition > lastScrollPosition) {
            header.classList.remove('slideInUp');
            header.classList.add('slideOutDown');
        } else {
            header.classList.remove('slideOutDown');
            header.classList.add('slideInUp');
        }
        lastScrollPosition = currentScrollPosition;
    }

    // Mobile Menu Toggle
    //
    let mobileMenuVisible = false;

    const toggleMobileMenu = () => {
        let mobileMenu = document.getElementById('mobile-menu');
        if (mobileMenuVisible == false) {
            mobileMenu.style.animationName = 'bounceInRight';
            mobileMenu.style.webkitAnimationName = 'bounceInRight';
            mobileMenu.style.display = 'block';
            mobileMenuVisible = true;
        } else {
            mobileMenu.style.animationName = 'bounceOutRight';
            mobileMenu.style.webkitAnimationName = 'bounceOutRight';
            mobileMenu.style.display = 'none';
            mobileMenuVisible = false;
        }
    }

    // Priority Navigation (Progressive Collapse)
    // Hides nav items right-to-left as space shrinks
    //
    const initPriorityNav = () => {
        const nav = document.getElementById('priority-nav');
        const navVisible = nav?.querySelector('.nav-visible');
        const overflowBtn = document.getElementById('nav-overflow-btn');
        const overflowDropdown = document.getElementById('nav-overflow-dropdown');

        if (!nav || !navVisible || !overflowBtn) return;

        const navItems = navVisible.querySelectorAll('.nav-item');
        if (navItems.length === 0) return;

        // Overflow button width (measured once, includes padding)
        const overflowBtnWidth = 48;

        const updateNav = () => {
            // === STEP 1: Reset to clean state ===
            // Remove ALL hidden classes and overflow state first
            navItems.forEach(item => item.classList.remove('nav-hidden'));
            overflowBtn.classList.remove('has-overflow');

            // === STEP 2: Force synchronous layout reflow ===
            void navVisible.offsetWidth;

            // === STEP 3: Get container boundary ===
            // Use the PARENT container (.hdr-left) as the stable boundary reference
            // This is stable and won't change based on nav content
            const hdrLeft = nav.closest('.hdr-left');
            const containerRight = hdrLeft ? hdrLeft.getBoundingClientRect().right : navVisible.getBoundingClientRect().right;

            // === STEP 4: Check if last item overflows (needs hamburger) ===
            const lastItem = navItems[navItems.length - 1];
            const lastItemRect = lastItem.getBoundingClientRect();

            // If last item fits within container, all items fit - done
            if (lastItemRect.right <= containerRight) {
                return;
            }

            // === STEP 5: Some items overflow - need hamburger ===
            // Calculate boundary accounting for overflow button
            const boundaryWithBtn = containerRight - overflowBtnWidth;

            // === STEP 6: Find which items fit by checking their actual position ===
            let lastVisibleIndex = -1;
            for (let i = 0; i < navItems.length; i++) {
                const itemRect = navItems[i].getBoundingClientRect();
                // Item fits if its right edge is within the boundary
                if (itemRect.right <= boundaryWithBtn) {
                    lastVisibleIndex = i;
                } else {
                    break;
                }
            }

            // === STEP 7: Apply visibility ===
            navItems.forEach((item, i) => {
                if (i > lastVisibleIndex) {
                    item.classList.add('nav-hidden');
                }
            });

            // === STEP 8: Show overflow button ===
            overflowBtn.classList.add('has-overflow');
        };

        // Toggle dropdown
        overflowBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = overflowDropdown.classList.contains('show');
            overflowDropdown.classList.toggle('show');
            overflowBtn.setAttribute('aria-expanded', !isOpen);
        });

        // Close dropdown on outside click
        document.addEventListener('click', (e) => {
            if (!nav.contains(e.target)) {
                overflowDropdown.classList.remove('show');
                overflowBtn.setAttribute('aria-expanded', 'false');
            }
        });

        // Close dropdown on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                overflowDropdown.classList.remove('show');
                overflowBtn.setAttribute('aria-expanded', 'false');
            }
        });

        // Mark priority nav as active (hides old menu button via CSS)
        document.getElementById('site-header')?.classList.add('priority-nav-active');

        // Initial update
        updateNav();

        // Update on resize (use window resize for viewport-based calculation)
        window.addEventListener('resize', throttle(updateNav, 100));
    };

    initPriorityNav();

    // Social Share Toggle
    //
    let shareMenuVisible = false;
    const shareMobileMenu = () => {
        let shareMenu = document.getElementById('share-links');
        if (shareMenuVisible == false) {
            shareMenu.style.animationName = 'bounceInRight';
            shareMenu.style.webkitAnimationName = 'bounceInRight';
            shareMenu.style.display = 'block';
            shareMenuVisible = true;
        } else {
            shareMenu.style.animationName = 'bounceOutRight';
            shareMenu.style.webkitAnimationName = 'bounceOutRight';
            shareMenu.style.display = 'none';
            shareMenuVisible = false;
        }
    }

    // Featured Image Toggle
    //
    const showImg = () => {
        document.querySelector('.bg-img').classList.add('show-bg-img');
    }

    const hideImg = () => {
        document.querySelector('.bg-img').classList.remove('show-bg-img');
    }

    // ToC Toggle
    //
    const toggleToc = () => {
        document.getElementById('toc').classList.toggle('show-toc');
    }


    if (header !== null) {
        listen('#menu-btn', "click", toggleMobileMenu);
        listen('#share-btn', "click", shareMobileMenu);
        listen('#toc-btn', "click", toggleToc);
        listen('#img-btn', "click", showImg);
        listen('.bg-img', "click", hideImg);

        document.querySelectorAll('.post-year').forEach((ele) => {
            ele.addEventListener('click', () => {
                window.location.hash = '#' + ele.id;
            });
        });

        window.addEventListener('scroll', throttle(() => {
            autoHideHeader();

            if (mobileMenuVisible == true) {
                toggleMobileMenu();
            }
            if (shareMenuVisible == true) {
                shareMobileMenu();
            }
        }, 250));
    }

    // Artist page: Show more/less toggle for show history
    const showsToggleBtn = document.getElementById('shows-toggle');
    if (showsToggleBtn) {
        const grid = document.getElementById('shows-grid');
        const hiddenCards = grid?.querySelectorAll('.show-hidden') || [];
        const extraCount = showsToggleBtn.dataset.extra;
        let expanded = false;

        showsToggleBtn.addEventListener('click', function() {
            expanded = !expanded;

            hiddenCards.forEach((card, index) => {
                if (expanded) {
                    card.style.display = '';
                    card.style.animation = `showCardReveal 0.4s ease-out ${index * 0.05}s forwards`;
                } else {
                    card.style.animation = '';
                    card.style.display = 'none';
                }
            });

            showsToggleBtn.classList.toggle('expanded', expanded);
            const toggleText = showsToggleBtn.querySelector('.toggle-text');
            if (toggleText) {
                toggleText.textContent = expanded ? 'Show less' : `+ ${extraCount} more shows`;
            }
        });
    }
});