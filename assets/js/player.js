// Audio player for de radio like
// Running locally, you need to source .env && export API_KEY
// Restart the hugo server when you make changes

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

    // Global State
    let artistDetails = {
        name: defaultText,
        image: defaultImage
    };

    if (!audio || !playPauseBtn) {
        console.warn("Audio or Play button not found!");
        return;
    }

    // Prevent duplicate event listeners
    if (!playPauseBtn.dataset.listenerAdded) {
        playPauseBtn.addEventListener("click", togglePlay);
        playPauseBtn.dataset.listenerAdded = "true";
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
        const artistNameElement = document.getElementById('dj-name');
        const showTitleElement = document.getElementById('player-metadata-show-title');
        const broadcastStatusElement = document.getElementById('live-text');
        const artistImageElement = document.getElementById('dj-image');

        if (artistNameElement) artistNameElement.textContent = artistDetails.name;
        if (showTitleElement) showTitleElement.textContent = showTitle;

        if (broadcastStatus === "schedule") {
            broadcastStatusElement.textContent = "we are live";
        } else {
            broadcastStatusElement.textContent = "off air";
        }

        if (artistImageElement) {
            artistImageElement.src = artistDetails.image || defaultImage;
        }

        setMediaSessionMetadata(showTitle, artistDetails);
    }

    function togglePlay() {
        if (isPlaying) {
            audio.pause();
            playPauseBtn.src = '/play.svg';
        } else {
            audio.play().then(() => {
                playPauseBtn.src = '/pause.svg';
            }).catch(error => {
                console.error("Playback failed:", error);
                playPauseBtn.src = '/play.svg';
            });
        }
        isPlaying = !isPlaying;
        updateMediaSession(isPlaying);
    }

    function updateMediaSession(isPlaying) {
        if ('mediaSession' in navigator) {
            navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
            navigator.mediaSession.setActionHandler('play', () => audio.play());
            navigator.mediaSession.setActionHandler('pause', () => audio.pause());
            navigator.mediaSession.setActionHandler('stop', () => audio.pause());
        }
    }

    function setMediaSessionMetadata(showTitle, artistDetails) {
        if ('mediaSession' in navigator) {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: showTitle,
                artist: artistDetails.name,
                album: 'éist',
                artwork: [
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

    // Ensure artists are loaded on page load
    document.addEventListener('DOMContentLoaded', async () => {
        nowPlaying();
        initializePage();
    });

    setMediaSessionMetadata(defaultText, artistDetails);
    nowPlaying();
    updateMediaSession(isPlaying);
}