/**
 * Persistent Archive Player for éist Radio
 *
 * Uses native Mixcloud/SoundCloud widget embeds shown in a fixed bottom bar.
 * Maintains playback state across Turbo navigations.
 *
 * Usage:
 *   window.archivePlayer.play({
 *       platform: 'mixcloud' | 'soundcloud',
 *       id: 'track-slug-or-id',
 *       title: 'Show Title',
 *       artist: 'Artist Name'
 *   });
 */

(function() {
    'use strict';

    // State
    let archiveState = {
        isActive: false,
        platform: null, // 'mixcloud' or 'soundcloud'
        trackId: null
    };

    // DOM elements (cached after init)
    let elements = {};

    // Track initialization state
    let isInitialized = false;

    /**
     * Initialize the archive player
     * Called on each Turbo load to ensure elements are bound
     */
    function initArchivePlayer() {
        // Cache DOM elements
        elements = {
            container: document.getElementById('archive-player'),
            mixcloudIframe: document.getElementById('mixcloud-widget'),
            soundcloudIframe: document.getElementById('soundcloud-widget'),
            closeBtn: document.getElementById('archive-close')
        };

        if (!elements.container) {
            console.warn('Archive player container not found');
            return;
        }

        // Only bind event listeners once
        if (!isInitialized) {
            elements.closeBtn?.addEventListener('click', closeArchivePlayer);
            isInitialized = true;
            console.log('Archive player initialized (native widgets)');
        }

        // Check session storage first - if player was explicitly closed, ensure it stays closed
        const savedState = sessionStorage.getItem('archivePlayerState');
        if (!savedState) {
            // No saved state means player was closed - ensure UI reflects this
            hideArchivePlayer();
            if (elements.mixcloudIframe) elements.mixcloudIframe.src = 'about:blank';
            if (elements.soundcloudIframe) elements.soundcloudIframe.src = 'about:blank';
            archiveState.isActive = false;
            console.log('Archive player: no saved state, ensuring closed');
            return;
        }

        // Check if iframes still have content (preserved by Turbo)
        if (elements.mixcloudIframe?.src || elements.soundcloudIframe?.src) {
            const hasMixcloud = elements.mixcloudIframe?.src && elements.mixcloudIframe.src !== 'about:blank' && elements.mixcloudIframe.src !== '';
            const hasSoundcloud = elements.soundcloudIframe?.src && elements.soundcloudIframe.src !== 'about:blank' && elements.soundcloudIframe.src !== '';

            if (hasMixcloud || hasSoundcloud) {
                archiveState.isActive = true;
                archiveState.platform = hasSoundcloud ? 'soundcloud' : 'mixcloud';
                showArchivePlayer();
                console.log('Archive player preserved across navigation');
                return;
            }
        }

        // Restore state from session storage
        restoreState();
    }

    /**
     * Play an archive track
     * @param {Object} track - Track info { platform, id, title, artist }
     */
    function playArchive(track) {
        console.log('Playing archive:', track);

        // Validate required fields
        if (!track.platform || !track.id) {
            console.error('Missing required track info: platform and id are required');
            return;
        }

        // Query DOM directly to ensure we have current elements
        const mixcloudIframe = document.getElementById('mixcloud-widget');
        const soundcloudIframe = document.getElementById('soundcloud-widget');

        // Pause live stream if playing
        pauseLiveStream();

        // Update state
        archiveState.isActive = true;
        archiveState.platform = track.platform;
        archiveState.trackId = track.id;

        // Stop and hide the other platform's iframe
        if (track.platform === 'mixcloud') {
            // Switching to Mixcloud - stop SoundCloud
            if (soundcloudIframe) {
                soundcloudIframe.src = 'about:blank';  // Clear src to stop playback
                soundcloudIframe.classList.add('hidden');
            }
            if (mixcloudIframe) {
                mixcloudIframe.classList.remove('hidden');
            }
            loadMixcloudWidget(track.id, track.url);
        } else if (track.platform === 'soundcloud') {
            // Switching to SoundCloud - stop Mixcloud
            if (mixcloudIframe) {
                mixcloudIframe.src = 'about:blank';  // Clear src to stop playback
                mixcloudIframe.classList.add('hidden');
            }
            if (soundcloudIframe) {
                soundcloudIframe.classList.remove('hidden');
            }
            loadSoundCloudWidget(track.id);
        }

        // Show the player bar
        showArchivePlayer();

        // Save state
        saveState();
    }

    /**
     * Load native Mixcloud widget
     * @param {string} slug - Mixcloud slug (for eistcork) or full path (for external)
     * @param {string} url - Optional full Mixcloud URL (used for external archives)
     */
    function loadMixcloudWidget(slug, url) {
        const mixcloudIframe = document.getElementById('mixcloud-widget');
        if (!mixcloudIframe) {
            console.error('Mixcloud iframe not found');
            return;
        }

        // Extract feed path from URL if provided (supports external archives)
        // Otherwise fall back to eistcork account
        let feedPath = `/eistcork/${slug}/`;
        if (url) {
            try {
                const urlObj = new URL(url);
                feedPath = urlObj.pathname;
            } catch (e) {
                console.warn('Could not parse Mixcloud URL, using default path');
            }
        }

        // Use Mixcloud's standard embed URL
        const params = new URLSearchParams({
            feed: feedPath,
            hide_cover: '1',
            mini: '1',
            autoplay: '1'
        });

        mixcloudIframe.src = `https://www.mixcloud.com/widget/iframe/?${params}`;
    }

    /**
     * Load native SoundCloud widget
     */
    function loadSoundCloudWidget(trackId) {
        // Query DOM directly to ensure we have current element
        const soundcloudIframe = document.getElementById('soundcloud-widget');
        if (!soundcloudIframe) {
            console.error('SoundCloud iframe not found');
            return;
        }

        // Use SoundCloud's standard embed URL with éist brand color
        const params = new URLSearchParams({
            url: `https://api.soundcloud.com/tracks/${trackId}`,
            color: '%23affc41',  // éist lime green accent
            auto_play: 'true',
            hide_related: 'true',
            show_comments: 'false',
            show_user: 'true',
            show_reposts: 'false',
            visual: 'false'
        });

        soundcloudIframe.src = `https://w.soundcloud.com/player/?${params}`;
        console.log('SoundCloud: loading widget for track:', trackId);
    }

    /**
     * Close archive player and return to live mode
     */
    function closeArchivePlayer() {
        // Reset state
        archiveState = {
            isActive: false,
            platform: null,
            trackId: null
        };

        // Query DOM directly to ensure we have current elements (not stale after Turbo navigation)
        const container = document.getElementById('archive-player');
        const mixcloudIframe = document.getElementById('mixcloud-widget');
        const soundcloudIframe = document.getElementById('soundcloud-widget');

        // Hide player container
        if (container) {
            container.classList.remove('active');
        }

        // Remove body classes
        document.body.classList.remove('archive-playing');
        document.body.classList.remove('soundcloud-active');

        // Clear iframes to stop playback - use about:blank to force full unload
        if (mixcloudIframe) mixcloudIframe.src = 'about:blank';
        if (soundcloudIframe) soundcloudIframe.src = 'about:blank';

        // Also update cached elements if they exist
        if (elements.mixcloudIframe) elements.mixcloudIframe.src = 'about:blank';
        if (elements.soundcloudIframe) elements.soundcloudIframe.src = 'about:blank';

        // Clear saved state
        sessionStorage.removeItem('archivePlayerState');

        console.log('Archive player closed and cleaned up');
    }

    // UI updates
    function showArchivePlayer() {
        // Query DOM directly to ensure we have current element
        const container = document.getElementById('archive-player');
        if (container) {
            container.classList.add('active');
        }
        document.body.classList.add('archive-playing');
        // Add soundcloud-active class for larger padding if SoundCloud
        if (archiveState.platform === 'soundcloud') {
            document.body.classList.add('soundcloud-active');
        } else {
            document.body.classList.remove('soundcloud-active');
        }
    }

    function hideArchivePlayer() {
        // Query DOM directly to ensure we have current element
        const container = document.getElementById('archive-player');
        if (container) {
            container.classList.remove('active');
        }
        document.body.classList.remove('archive-playing');
        document.body.classList.remove('soundcloud-active');
    }

    // State persistence
    function saveState() {
        try {
            sessionStorage.setItem('archivePlayerState', JSON.stringify(archiveState));
        } catch (e) {
            console.warn('Failed to save archive state:', e);
        }
    }

    function restoreState() {
        try {
            const saved = sessionStorage.getItem('archivePlayerState');
            if (saved) {
                const state = JSON.parse(saved);
                if (state.isActive && state.trackId && state.platform) {
                    archiveState = state;

                    // Re-show the player if it was active
                    if (elements.mixcloudIframe) {
                        elements.mixcloudIframe.classList.toggle('hidden', state.platform !== 'mixcloud');
                    }
                    if (elements.soundcloudIframe) {
                        elements.soundcloudIframe.classList.toggle('hidden', state.platform !== 'soundcloud');
                    }

                    showArchivePlayer();
                    console.log('Archive state restored');
                }
            }
        } catch (e) {
            console.error('Failed to restore archive state:', e);
        }
    }

    /**
     * Pause the live stream if it's playing
     */
    function pauseLiveStream() {
        const liveAudio = document.getElementById('audio');
        const playPauseBtn = document.getElementById('playPauseBtn');

        if (liveAudio && !liveAudio.paused) {
            liveAudio.pause();
            liveAudio.currentTime = 0;
            if (playPauseBtn) {
                playPauseBtn.src = '/play.svg';
            }
            console.log('Live stream paused for archive playback');
        }
    }

    // Export for use in templates
    window.archivePlayer = {
        play: playArchive,
        close: closeArchivePlayer,
        getState: () => ({ ...archiveState })
    };

    /**
     * Mobile breakpoint for external link behavior.
     * Matches the smallest mobile breakpoint in _player.scss (768px).
     */
    const MOBILE_BREAKPOINT = 768;

    /**
     * Event delegation handler for archive play buttons
     * Handles clicks on any element with [data-archive-play] attribute
     *
     * On mobile (<=768px): opens external platform URL directly
     * On desktop: loads embedded widget player
     */
    function handleArchivePlayClick(event) {
        const btn = event.target.closest('[data-archive-play]');
        if (!btn) return;

        const { platform, trackId, title, artist, artwork, platformUrl } = btn.dataset;

        // On mobile, open external URL instead of loading embed widget
        if (window.innerWidth <= MOBILE_BREAKPOINT && platformUrl) {
            // Allow default navigation for anchor elements, or navigate programmatically
            if (btn.tagName === 'A') {
                // Let the link work naturally - don't prevent default
                return;
            }
            // For button elements, navigate programmatically
            window.open(platformUrl, '_blank', 'noopener');
            event.preventDefault();
            return;
        }

        event.preventDefault();

        if (platform && trackId) {
            playArchive({
                platform: platform,
                id: trackId,
                title: title || '',
                artist: artist || '',
                artwork: artwork || '',
                url: platformUrl || ''
            });
        }
    }

    // Initialize on Turbo load
    document.addEventListener('turbo:load', initArchivePlayer);

    // Use event delegation on document for archive play buttons
    document.addEventListener('click', handleArchivePlayClick);

    // Also init immediately if DOM is ready (for non-Turbo loads)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initArchivePlayer);
    } else {
        initArchivePlayer();
    }

})();
