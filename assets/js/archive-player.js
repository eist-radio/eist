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

        // Pause live stream if playing
        pauseLiveStream();

        // Update state
        archiveState.isActive = true;
        archiveState.platform = track.platform;
        archiveState.trackId = track.id;

        // Stop and hide the other platform's iframe
        if (track.platform === 'mixcloud') {
            // Switching to Mixcloud - stop SoundCloud
            if (elements.soundcloudIframe) {
                elements.soundcloudIframe.src = '';  // Clear src to stop playback
                elements.soundcloudIframe.classList.add('hidden');
            }
            if (elements.mixcloudIframe) {
                elements.mixcloudIframe.classList.remove('hidden');
            }
            loadMixcloudWidget(track.id);
        } else if (track.platform === 'soundcloud') {
            // Switching to SoundCloud - stop Mixcloud
            if (elements.mixcloudIframe) {
                elements.mixcloudIframe.src = '';  // Clear src to stop playback
                elements.mixcloudIframe.classList.add('hidden');
            }
            if (elements.soundcloudIframe) {
                elements.soundcloudIframe.classList.remove('hidden');
            }
            loadSoundCloudWidget(track.id);
        }

        // Show the player bar
        showArchivePlayer();

        // Save state
        saveState();
    }

    /**
     * Load native Mixcloud widget and trigger playback via Widget API
     */
    function loadMixcloudWidget(slug) {
        // Use Mixcloud's standard embed URL with default styling
        const params = new URLSearchParams({
            feed: `/eistcork/${slug}/`,
            hide_cover: '1',
            mini: '1',
            autoplay: '1'
        });

        elements.mixcloudIframe.src = `https://www.mixcloud.com/widget/iframe/?${params}`;

        // Use Mixcloud Widget API to ensure playback starts
        // The autoplay=1 param often fails due to browser restrictions,
        // but calling play() via the API works because user clicked the button
        if (typeof Mixcloud !== 'undefined' && Mixcloud.PlayerWidget) {
            // Wait for iframe to load, then use Widget API
            elements.mixcloudIframe.addEventListener('load', function onLoad() {
                elements.mixcloudIframe.removeEventListener('load', onLoad);
                try {
                    const widget = Mixcloud.PlayerWidget(elements.mixcloudIframe);
                    widget.ready.then(function() {
                        widget.play();
                        console.log('Mixcloud: play() called via Widget API');
                    }).catch(function(err) {
                        console.warn('Mixcloud widget ready failed:', err);
                    });
                } catch (err) {
                    console.warn('Mixcloud Widget API error:', err);
                }
            }, { once: true });
        }
    }

    /**
     * Load native SoundCloud widget
     */
    function loadSoundCloudWidget(trackId) {
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

        elements.soundcloudIframe.src = `https://w.soundcloud.com/player/?${params}`;
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

        // Hide player
        hideArchivePlayer();

        // Clear iframes
        if (elements.mixcloudIframe) elements.mixcloudIframe.src = '';
        if (elements.soundcloudIframe) elements.soundcloudIframe.src = '';

        // Clear saved state
        sessionStorage.removeItem('archivePlayerState');
    }

    // UI updates
    function showArchivePlayer() {
        elements.container?.classList.add('active');
        document.body.classList.add('archive-playing');
        // Add soundcloud-active class for larger padding if SoundCloud
        if (archiveState.platform === 'soundcloud') {
            document.body.classList.add('soundcloud-active');
        } else {
            document.body.classList.remove('soundcloud-active');
        }
    }

    function hideArchivePlayer() {
        elements.container?.classList.remove('active');
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
