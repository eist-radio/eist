// Update the player on page load
// Running locally - source .env && export API_KEY. Restart the hugo server when you make changes

var apiKey = radiocultApiKey;
var stationId = 'eist-radio';
var apiUrl = `https://api.radiocult.fm/api/station/${stationId}`;
var streamUrl = 'https://eist-radio.radiocult.fm/stream';
var defaultOfflineImage = 'eist_offline.png';
var defaultOnlineImage = 'eist_online.png';
var defaultText = ' ';

// Global State
let currentAudio = null;
let artistDetails = {
    name: defaultText,
    bio: defaultText,
    image: defaultOfflineImage
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
        updateDOM({ broadcastStatus: status, showDesc, showTitle, artistDetails });

    } catch (error) {
        console.error('Error fetching show details:', error);
    }
}

async function getArtistDetails(artistId) {
    if (!artistId) return { name: defaultText, bio: defaultText, image: defaultOnlineImage };

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
            image: artist.logo?.['256x256'] || defaultOnlineImage
        };

    } catch (error) {
        console.error('Error fetching artist details:', error);
        return { name: defaultText, bio: defaultText, image: defaultOnlineImage };
    }
}

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
        artistImageElement.src = artistDetails.image || DefaultOnlineImage; //'eist_online.png';
    } else {
        broadcastStatusElement.textContent = "off air";
        artistImageElement.src = defaultOfflineImage;
    }
}

function toggleAudio() {
    const playButtonImg = document.querySelector('#player-button img');

    if (!currentAudio) {
        currentAudio = new Audio(streamUrl);
        currentAudio.preload = 'auto';
        currentAudio.setAttribute('playsinline', '');
        currentAudio.setAttribute('muted', 'false');
        currentAudio.play();
        playButtonImg.src = 'pause-alt.svg';
    } else if (currentAudio.paused) {
        currentAudio.play();
        playButtonImg.src = 'pause-alt.svg';
    } else {
        currentAudio.pause();
        playButtonImg.src = 'play-alt.svg';
    }

    setMediaSession(defaultText);
    return false; // Prevent default link behavior
}

function setMediaSession(showDesc) {
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
        navigator.mediaSession.setActionHandler('stop', () => currentAudio.pause());
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
