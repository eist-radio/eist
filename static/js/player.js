// Constants
const stationId = 'eist-radio';
const apiUrl = `https://api.radiocult.fm/api/station/${stationId}`;
const streamUrl = 'https://eist-radio.radiocult.fm/stream';
const defaultImage = 'eist_offline.png';
const defaultText = ' ';

// Global State
let currentAudio = null;
let artistDetails = {
    name: defaultText,
    bio: defaultText,
    image: defaultImage
};

// Fetch and update the currently playing show details
async function updatePlayerDetails() {
    try {
        const response = await fetch(`${apiUrl}/schedule/live`, {
            method: 'GET',
            headers: {
                'x-api-key': radiocultApiKey,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) throw new Error(`API request failed: ${response.status}`);

        const data = await response.json();
        const { status, content } = data.result;

        const artistId = content.artistIds?.[0] || defaultText;
        const showDesc = content.description?.content?.[0]?.content?.[0]?.text || defaultText;
        const showTitle = content.title || defaultText;

        // Fetch artist details
        artistDetails = await getArtistDetails(artistId);

        // Update the DOM
        updateDOM({ broadcastStatus: status, showDesc, showTitle, artistDetails });

    } catch (error) {
        console.error('Error fetching show details:', error);
    }
}

// Fetch artist details
async function getArtistDetails(artistId) {
    if (!artistId) return { name: defaultText, bio: defaultText, image: defaultImage };

    try {
        const response = await fetch(`${apiUrl}/artists/${artistId}`, {
            method: 'GET',
            headers: {
                'x-api-key': radiocultApiKey,
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

// Update the DOM with show and artist details
function updateDOM({ broadcastStatus, showDesc, showTitle, artistDetails }) {
    const artistNameElement = document.getElementById('dj-name');
    const showDescElement = document.getElementById('player-metadata-show-desc');
    const showTitleElement = document.getElementById('player-metadata-show-title');
    const artistImageElement = document.getElementById('dj-image');
    const broadcastStatusElement = document.getElementById('live-text');

    if (artistNameElement) artistNameElement.textContent = artistDetails.name;
    if (showDescElement) showDescElement.textContent = showDesc;
    if (showTitleElement) showTitleElement.textContent = showTitle;

    if (broadcastStatus === "schedule") {
        broadcastStatusElement.textContent = "we are live";
        artistImageElement.src = 'eist_online.png';
    } else {
        broadcastStatusElement.textContent = "off air";
        artistImageElement.src = image;
    }
}

// Toggle audio playback
function toggleAudio() {
    const playButtonImg = document.querySelector('#player-button img');

    if (!currentAudio) {
        currentAudio = new Audio(streamUrl);
        currentAudio.play();
        playButtonImg.src = 'pause-alt.svg';
    } else if (currentAudio.paused) {
        currentAudio.play();
        playButtonImg.src = 'pause-alt.svg';
    } else {
        currentAudio.pause();
        playButtonImg.src = 'play-alt.svg';
    }

    setMediaSession();
    updatePlayerDetails();
    return false; // Prevent default link behavior
}

// Set media session metadata
function setMediaSession() {
    if ('mediaSession' in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: 'Éist',
            artist: artistDetails.name,
            album: showDesc,
            artwork: [
                { src: './gradient-96x96.png', sizes: '96x96', type: 'image/png' },
                { src: './gradient-128x128.png', sizes: '128x128', type: 'image/png' },
                { src: './gradient-192x192.png', sizes: '192x192', type: 'image/png' },
                { src: './gradient-256x256.png', sizes: '256x256', type: 'image/png' },
                { src: './gradient-384x384.png', sizes: '384x384', type: 'image/png' },
                { src: './gradient-512x512.png', sizes: '512x512', type: 'image/png' },
            ]
        });

        navigator.mediaSession.playbackState = currentAudio.paused ? 'paused' : 'playing';

        navigator.mediaSession.setActionHandler('play', () => currentAudio.play());
        navigator.mediaSession.setActionHandler('pause', () => currentAudio.pause());
    }
}

// Initialize player on page load
document.addEventListener('DOMContentLoaded', () => {
    const playerControl = document.getElementById('player-control');
    if (playerControl) {
        playerControl.addEventListener('click', (event) => {
            event.preventDefault();
            toggleAudio();
        });
    }
    updatePlayerDetails();
});