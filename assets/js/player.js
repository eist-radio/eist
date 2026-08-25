// Audio player for de radio like
// Running locally, you need to source .env && export API_KEY
// Restart the hugo server when you make changes
// If you want to hack the audio stream, update the player src in partials/player.html

document.addEventListener("turbo:load", initializePage);

// Initialize the page
function initializePage() {
    console.log("Initializing player...");
    const audio = document.getElementById('audio');
    const playPauseBtn = document.getElementById('playPauseBtn');
    let isPlaying = !audio.paused;
    const defaultText = ' ';
    const apiKey = radiocultApiKey;
    const stationId = 'eist-radio';
    const apiUrl = `https://api.radiocult.fm/api/station/${stationId}`;
    const defaultImage = '/eist_online.png';

    // Track play promises
    let playPromise = null;

    // ---- Stream recovery ------------------------------------------------
    // A severed connection does NOT fire `error` in Chromium — it fires
    // `waiting` then `stalled` and then nothing, leaving the element frozen with
    // paused === false and the button still showing "pause". The old handler
    // listened only for `error`, so it never ran; and it called load() without
    // play(), so even when it did run the stream stayed stopped. Measured: one
    // severed connection left the page silent for the rest of a 6-minute run.
    //
    // `waiting` also fires during ordinary rebuffering, so a stall ARMS a timer
    // rather than reconnecting. If playback resumes, the timer is cancelled.
    // Only a stall that outlives the grace period triggers a reconnect.
    const STALL_GRACE_MS = 4000;
    // First attempt is immediate: by the time the grace period has elapsed the
    // listener is already hearing silence, so an extra delay before the first
    // try is pure added outage. Backoff applies only to repeated failures.
    const RECONNECT_BACKOFF_MS = [0, 1000, 2000, 5000, 10000, 20000];

    // Resolve the stream URL at reconnect time, not at init: the element's src
    // can legitimately have been changed since the page loaded, and each
    // reconnect appends its own cache-buster which must not accumulate.
    function streamBaseUrl() {
        const current = audio.getAttribute('src') || '';
        return current.replace(/[?&]_r=\d+/g, '');
    }

    let userWantsPlayback = false;   // survives stalls; only togglePlay changes it
    let stallTimer = null;
    let reconnectTimer = null;
    let reconnectAttempt = 0;
    let lastPlayheadTime = -1;
    let playheadFrozenSince = null;

    function clearStallTimer() {
        if (stallTimer) { clearTimeout(stallTimer); stallTimer = null; }
    }

    function cancelRecovery() {
        clearStallTimer();
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        playheadFrozenSince = null;
        reconnectAttempt = 0;
    }

    // Arm a reconnect unless playback recovers on its own first.
    function noteStalled(why) {
        if (!userWantsPlayback || stallTimer || reconnectTimer) return;
        console.log(`Stream stalled (${why}), waiting ${STALL_GRACE_MS}ms for recovery`);
        stallTimer = setTimeout(() => {
            stallTimer = null;
            if (!userWantsPlayback) return;
            reconnect(why);
        }, STALL_GRACE_MS);
    }

    // Playback is healthy again — stand down.
    function noteProgress() {
        clearStallTimer();
        playheadFrozenSince = null;
        reconnectAttempt = 0;
    }

    function reconnect(why) {
        if (!userWantsPlayback || reconnectTimer) return;

        const delay = RECONNECT_BACKOFF_MS[Math.min(reconnectAttempt, RECONNECT_BACKOFF_MS.length - 1)];
        reconnectAttempt += 1;
        console.warn(`Reconnecting to stream (${why}), attempt ${reconnectAttempt} in ${delay}ms`);

        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            if (!userWantsPlayback) return;

            // A fresh URL forces a new connection rather than resuming the dead
            // one. Icecast ignores unknown query params (its own Safari redirect
            // appends `_ic2`).
            const base = streamBaseUrl();
            const sep = base.includes('?') ? '&' : '?';
            audio.src = `${base}${sep}_r=${Date.now()}`;
            audio.load();

            // load() alone leaves it stopped; the old code's missing half.
            audio.play()
                .then(() => {
                    console.log('Reconnected to stream');
                    playPauseBtn.src = '/pause.svg';
                    isPlaying = true;
                    updateMediaSession(true);
                })
                .catch((error) => {
                    console.error('Reconnect failed:', error);
                    if (userWantsPlayback) reconnect('reconnect-failed');
                });
        }, delay);
    }

    // Catches the silent freeze: the playhead stops advancing while the element
    // still reports playing, and no event fires at all.
    //
    // Registered once. initializePage() re-runs on every turbo:load, but
    // #global-player is data-turbo-permanent so the element — and the closure
    // that owns the stall listeners below — persists. Without this guard each
    // navigation would leak another interval.
    const startWatchdog = () => setInterval(() => {
        if (!userWantsPlayback || audio.paused) { playheadFrozenSince = null; return; }
        if (audio.currentTime === lastPlayheadTime) {
            playheadFrozenSince = playheadFrozenSince ?? Date.now();
            if (Date.now() - playheadFrozenSince >= STALL_GRACE_MS) {
                playheadFrozenSince = null;
                reconnect('playhead-frozen');
            }
        } else {
            noteProgress();
        }
        lastPlayheadTime = audio.currentTime;
    }, 1000);

    // Global State
    let artistDetails = {
        name: defaultText,
        image: defaultImage
    };

    // Prevent duplicate event listeners
    if (!playPauseBtn.dataset.listenerAdded) {
        playPauseBtn.addEventListener("click", togglePlay);
        playPauseBtn.dataset.listenerAdded = "true";
    }

    // Setup audio listeners if not already set
    if (!audio.dataset.listenersAdded) {
        // React to the events that actually fire on a broken stream. `error` is
        // kept, but Chromium never fires it on an abrupt close — `stalled` and
        // `waiting` are the ones that do.
        audio.addEventListener("error", function() {
            console.error("Audio error:", audio.error && audio.error.message);
            if (userWantsPlayback) reconnect('error');
        });

        audio.addEventListener("stalled", () => noteStalled('stalled'));
        audio.addEventListener("waiting", () => noteStalled('waiting'));

        startWatchdog();

        // Recovery signals — stand the reconnect down.
        audio.addEventListener("playing", noteProgress);
        audio.addEventListener("canplay", noteProgress);

        // Update play state
        audio.addEventListener("play", function() {
            isPlaying = true;
            playPauseBtn.src = '/pause.svg';
            console.log("Audio play event fired");
        });

        // Update pause state
        audio.addEventListener("pause", function() {
            isPlaying = false;
            playPauseBtn.src = '/play.svg';
            console.log("Audio pause event fired");
        });

        audio.dataset.listenersAdded = "true";
    }

    // Toggle play/pause with promise handling
    function togglePlay() {
        console.log("Toggle play called, current state:", isPlaying);

        if (isPlaying) {
            // The user is stopping: drop the intent flag first so no in-flight
            // stall timer can reconnect behind them.
            userWantsPlayback = false;

            // If we have an ongoing play operation, wait for it to complete before pausing
            if (playPromise !== null) {
                console.log("Waiting for play promise to resolve before pausing");
                playPromise
                    .then(() => {
                        console.log("Play promise resolved, now pausing");
                        cancelRecovery();
                        audio.pause();
                        audio.currentTime = 0;
                        playPauseBtn.src = '/play.svg';
                        isPlaying = false;
                        updateMediaSession(false);
                    })
                    .catch(() => {
                        console.log("Play promise rejected, updating UI only");
                        cancelRecovery();
                        playPauseBtn.src = '/play.svg';
                        isPlaying = false;
                        updateMediaSession(false);
                    });
            } else {
                // No ongoing play operation, pause directly
                console.log("Pausing directly");
                cancelRecovery();
                audio.pause();
                audio.currentTime = 0;
                playPauseBtn.src = '/play.svg';
                isPlaying = false;
                updateMediaSession(false);
            }
        } else {
            // Stop archive player if it's playing
            if (window.archivePlayer && typeof window.archivePlayer.close === 'function') {
                window.archivePlayer.close();
                console.log("Archive player stopped for live stream playback");
            }

            // The user is starting: recovery is armed from here until they stop.
            userWantsPlayback = true;
            reconnectAttempt = 0;

            // Reload the stream before playing
            audio.load();

            // Store the play promise
            console.log("Starting playback");
            playPromise = audio.play();

            playPromise
                .then(() => {
                    console.log("Playback started successfully");
                    playPauseBtn.src = '/pause.svg';
                    isPlaying = true;
                    updateMediaSession(true);
                    // Clear the promise reference after it's resolved
                    playPromise = null;
                })
                .catch(error => {
                    console.error("Playback failed:", error);
                    playPauseBtn.src = '/play.svg';
                    isPlaying = false;
                    updateMediaSession(false);
                    // Clear the promise reference after it's rejected
                    playPromise = null;
                });
        }
    }

    // Fetch artist details
    async function getArtistDetails(artistId) {
        if (!artistId) return { name: defaultText, bio: defaultText, image: defaultImage };

        try {
            const response = await fetch(`${apiUrl}/artists/${artistId}`, {
                method: 'GET',
                headers: {
                    'x-api-key': apiKey,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error(`API request failed: ${response.status}`);

            const data = await response.json();
            const artist = data.artist || {};

            // Generate slug from name for artist page URL
            const artistName = artist.name || defaultText;
            const slug = artistName.toLowerCase()
                .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // Remove accents
                .replace(/[^a-z0-9\s-]/g, '') // Remove special chars
                .replace(/\s+/g, '-') // Spaces to hyphens
                .replace(/-+/g, '-'); // Collapse multiple hyphens

            return {
                name: artistName,
                slug: slug,
                bio: artist.description?.content?.[0]?.content?.[0]?.text || 'No bio available',
                image: artist.logo?.['256x256'] || defaultImage
            };

        } catch (error) {
            console.error('Error fetching artist details:', error);
            return { name: defaultText, bio: defaultText, image: defaultImage };
        }
    }

    async function nowPlaying() {
        try {
            const response = await fetch(`${apiUrl}/schedule/live`, {
                method: 'GET',
                headers: {
                    'x-api-key': apiKey,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error(`API request failed: ${response.status}`);

            const data = await response.json();
            const { status, content } = data.result;

            const artistId = content.artistIds?.[0] || null;
            const showTitle = content.title || defaultText;

            if (status !== "schedule") {
                artistDetails = { name: defaultText, image: defaultImage };
                updatePlayer({ broadcastStatus: status, showTitle, artistDetails });
                return;
            }

            // Fetch artist details by ID
            artistDetails = await getArtistDetails(artistId);
            updatePlayer({ broadcastStatus: status, showTitle, artistDetails });

        } catch (error) {
            console.error('Error fetching show details:', error);
            artistDetails = { name: defaultText, image: defaultImage };
            updatePlayer({ broadcastStatus: 'off air', showTitle: ' ', artistDetails });
        }
    }

    function updatePlayer({ broadcastStatus, showTitle, artistDetails }) {
        console.log("Updating player UI with:", { broadcastStatus, showTitle, artistName: artistDetails.name });

        const artistNameElement = document.getElementById('dj-name');
        const showTitleElement = document.getElementById('player-metadata-show-title');
        const broadcastStatusElement = document.getElementById('live-text');
        const artistImageElement = document.getElementById('dj-image');
        const liveIndicator = document.getElementById('live-indicator');
        const broadcastStatusContainer = document.querySelector('.broadcast-status');

        if (artistNameElement) artistNameElement.textContent = artistDetails.name;
        if (showTitleElement) showTitleElement.textContent = showTitle;

        // Show the status area now that we have data
        if (broadcastStatusContainer) {
            broadcastStatusContainer.classList.add('loaded');
        }

        const isLive = broadcastStatus === "schedule";

        // Update live indicator state
        if (liveIndicator) {
            if (isLive) {
                liveIndicator.classList.remove('off-air');
            } else {
                liveIndicator.classList.add('off-air');
            }
        }

        // Update broadcast status text with styled spans
        if (broadcastStatusElement) {
            if (isLive && artistDetails.slug) {
                broadcastStatusElement.innerHTML =
                    `<span class="dj-prefix">w/</span> <a href="/artists/${artistDetails.slug}/" class="dj-name">${artistDetails.name}</a>`;
            } else if (isLive) {
                broadcastStatusElement.innerHTML =
                    `<span class="dj-prefix">w/</span> <span class="dj-name">${artistDetails.name}</span>`;
            } else {
                broadcastStatusElement.innerHTML =
                    `<span class="dj-prefix">off air</span>`;
            }
        }

        if (artistImageElement) {
            artistImageElement.src = artistDetails.image || defaultImage;
        }

        setMediaSessionMetadata(showTitle, artistDetails);
        console.log("Player UI update complete");
    }

    function updateMediaSession(isPlaying) {
        if ('mediaSession' in navigator) {
            navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';

            navigator.mediaSession.setActionHandler('play', async () => {
                if (audio.paused) {
                    // Stop archive player if it's playing
                    if (window.archivePlayer && typeof window.archivePlayer.close === 'function') {
                        window.archivePlayer.close();
                    }
                    try {
                        // Lock-screen / headset play must arm recovery too,
                        // otherwise a stall started this way is never repaired.
                        userWantsPlayback = true;
                        reconnectAttempt = 0;
                        await audio.play();
                        isPlaying = true;
                        playPauseBtn.src = '/pause.svg';
                        navigator.mediaSession.playbackState = "playing";
                    } catch (error) {
                        console.error("Error resuming playback:", error);
                    }
                }
            });

            navigator.mediaSession.setActionHandler('pause', () => {
                if (!audio.paused) {
                    // Deliberate pause: stand recovery down.
                    userWantsPlayback = false;
                    cancelRecovery();
                    audio.pause();
                    isPlaying = false;
                    playPauseBtn.src = '/play.svg';
                    navigator.mediaSession.playbackState = "paused";
                }
            });
        }
    }


    function setMediaSessionMetadata(showTitle, artistDetails) {
        const isOffline = !showTitle || showTitle === defaultText;

        if ('mediaSession' in navigator) {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: isOffline ? "éist · off air" : showTitle,
                artist: isOffline ? "" : `${artistDetails.name} · live on éist`,
                album: '',
                artwork: isOffline ? [] : [
                    { src: artistDetails.image, sizes: '96x96', type: 'image/png' },
                    { src: artistDetails.image, sizes: '128x128', type: 'image/png' },
                    { src: artistDetails.image, sizes: '192x192', type: 'image/png' },
                    { src: artistDetails.image, sizes: '256x256', type: 'image/png' },
                    { src: artistDetails.image, sizes: '384x384', type: 'image/png' },
                    { src: artistDetails.image, sizes: '512x512', type: 'image/png' }
                ]
            });
        }
    }

    // Handle visibility changes
    document.addEventListener("visibilitychange", function() {
        if (document.visibilityState === 'visible') {
            console.log("Page became visible");
            nowPlaying();
        }
    });

    // Initialize with default metadata
    setMediaSessionMetadata(defaultText, artistDetails);

    // Start fetching now playing information
    console.log("Starting initial nowPlaying fetch");

    // Don't show anything until we have real data from the API
    nowPlaying();
    updateMediaSession(isPlaying);

    // Initialize scroll-driven player morph
    initPlayerMorph();

    console.log("Player initialization complete");
}

// ===========================================
// UNIFIED HEADER SCROLL
// Simple class toggle - CSS handles all transitions
// ===========================================
function initPlayerMorph() {
    const header = document.getElementById('site-header');

    if (!header) {
        console.log("Header scroll: missing header element");
        return;
    }

    // Prevent duplicate initialization
    if (header.dataset.scrollInitialized) return;
    header.dataset.scrollInitialized = "true";

    const SCROLL_THRESHOLD = 50; // Scroll distance to trigger compact mode
    let isScrolled = false;
    let ticking = false;

    function updateScrollState() {
        const scrollY = window.scrollY || window.pageYOffset;
        const shouldBeScrolled = scrollY > SCROLL_THRESHOLD;

        if (shouldBeScrolled !== isScrolled) {
            isScrolled = shouldBeScrolled;
            header.classList.toggle('header-scrolled', isScrolled);
            document.body.classList.toggle('header-scrolled', isScrolled);
        }

        ticking = false;
    }

    function onScroll() {
        if (!ticking) {
            requestAnimationFrame(updateScrollState);
            ticking = true;
        }
    }

    // Listen for scroll
    window.addEventListener('scroll', onScroll, { passive: true });

    // Also re-check on resize (content reflow can change scroll position)
    window.addEventListener('resize', onScroll, { passive: true });

    // Initial state check
    updateScrollState();

    console.log("Header scroll initialized");
}