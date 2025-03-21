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
        // Handle audio errors
        audio.addEventListener("error", function() {
            console.error("Audio error, retrying...");
            setTimeout(() => audio.load(), 5000);
        });

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
            // If we have an ongoing play operation, wait for it to complete before pausing
            if (playPromise !== null) {
                console.log("Waiting for play promise to resolve before pausing");
                playPromise
                    .then(() => {
                        console.log("Play promise resolved, now pausing");
                        audio.pause();
                        audio.currentTime = 0;
                        playPauseBtn.src = '/play.svg';
                        isPlaying = false;
                        updateMediaSession(false);
                    })
                    .catch(() => {
                        console.log("Play promise rejected, updating UI only");
                        playPauseBtn.src = '/play.svg';
                        isPlaying = false;
                        updateMediaSession(false);
                    });
            } else {
                // No ongoing play operation, pause directly
                console.log("Pausing directly");
                audio.pause();
                audio.currentTime = 0;
                playPauseBtn.src = '/play.svg';
                isPlaying = false;
                updateMediaSession(false);
            }
        } else {
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

            return {
                name: artist.name || defaultText,
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

        if (artistNameElement) artistNameElement.textContent = artistDetails.name;
        if (showTitleElement) showTitleElement.textContent = showTitle;

        if (broadcastStatusElement) {
            broadcastStatusElement.textContent = broadcastStatus === "schedule" ? "we are live" : "off air";
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
            navigator.mediaSession.setActionHandler('play', () => {
                togglePlay();
            });
            navigator.mediaSession.setActionHandler('pause', () => {
                togglePlay();
            });
        }
    }

    function setMediaSessionMetadata(showTitle, artistDetails) {
        const isOffline = !showTitle || showTitle === defaultText;

        if ('mediaSession' in navigator) {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: isOffline ? "éist · offline" : showTitle,
                artist: isOffline ? "" : `${artistDetails.name} · live on éist`,
                album: 'eist.radio',
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
    
    // Ensure we have defaults before the API call
    updatePlayer({ 
        broadcastStatus: 'initializing', 
        showTitle: defaultText, 
        artistDetails: { name: defaultText, image: defaultImage } 
    });

    nowPlaying();
    updateMediaSession(isPlaying);
    
    console.log("Player initialization complete");
}