// Update the player on page load

// Running locally
// source .env
// export API_KEY

let apiKey = radiocultApiKey
let stationId = 'eist-radio';
let artistId = 'null' // Get these later
let showDesc = 'null'
let broadcastStatus = 'null'
let artistName = 'null'
let artistBio = 'null'
let artistImage = 'null'
let showTitle ='null'
let url = `https://api.radiocult.fm/api/station/${stationId}/schedule/live`;
let artistUrl=`https://api.radiocult.fm/api/station/${stationId}/artists/${artistId}`

// Fetch and update the currently playing show details
async function updatePlayerDetails() {
    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`API request failed: ${response.status}`);
        }

        const data = await response.json();

        broadcastStatus = data.result.status || 'offAir';

        // Extract artist ID and show description
        // TODO - Created an offline artist in RadioCult. Eeeew. Do this properly! 
        artistId = data.result.content.artistIds?.[0] || '22e7b0ff-538c-4a7f-9d5b-e0ca890d6775';
        artistUrl = `https://api.radiocult.fm/api/station/${stationId}/artists/${artistId}`;
        showDesc = data.result.content.description?.content?.[0]?.content?.[0]?.text ||
            ' ';
        showTitle = data.result.content.title || ' ';

        // Fetch artist details and wait for completion
        const artistDetails = await getArtistDetails(artistId);

        // Update the HTML with both show and artist details
        document.getElementById('player-metadata-show-desc').textContent = showDesc;

        const artistNameElement = document.getElementById('dj-name');
        if (artistNameElement) {
            artistNameElement.textContent = artistDetails.artistName || 'offline';
        }

        const showDescElement = document.getElementById('player-metadata-show-desc');
        if (showDescElement) {
            showDescElement.textContent = showDesc || 'Unknown Desc';
        }

        const showTitleElement = document.getElementById('player-metadata-show-title');
        if (showTitleElement) {
            showTitleElement.textContent = showTitle || 'Unknown Title';
        }

        const artistImageElement = document.getElementById('dj-image');
        if (artistImageElement) {
            artistImageElement.src = artistDetails.artistImage || 'null';
        } else {
           // this not actually needed
           artistImageElement.src = 'offline.png'; 
        }

        const broadcastStatusElement = document.getElementById('live-text');
        const broadcastStatusIndicatorElement = document.getElementsByClassName('broadcast-status-indicator');
        if (broadcastStatus == "schedule") {
            broadcastStatusElement.textContent = "we are live" || 'null';
        } else {
            broadcastStatusElement.textContent = "offline" || 'null';
        }

    } catch (error) {
        console.error('Error fetching show details:', error);
    }
}

// Fetch and update the currently playing artist details
async function getArtistDetails(artistId) {
    try {
        const response = await fetch(artistUrl, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`API request failed with status: ${response.status}`);
        }

        const data = await response.json();

        artistName = data.artist?.name || 'Unknown artist name';
        artistBio =
            data.artist?.description?.content?.[0]?.content?.[0]?.text ||
            'No bio available';
        artistImage = data.artist?.logo?.['256x256'] || 'offline.png';

        return { artistName, artistBio, artistImage };

    } catch (error) {
        console.error('Error fetching artist details:', error);
        return {
            artistName: 'offline',
            artistBio: 'offline',
            artistImage: 'offline'
        };
    }
}

// Handle playing audio and updating the play button controls
function toggleAudio() {
    const playButtonImg = document.querySelector('#player-button img');

    if (!window.currentAudio) {
        window.currentAudio = new Audio('https://eist-radio.radiocult.fm/stream');
        window.currentAudio.play();
        playButtonImg.src = 'pause.svg';
    } else if (window.currentAudio.paused) {
        window.currentAudio.play();
        playButtonImg.src = 'pause.svg';
    } else {
        window.currentAudio.pause();
        playButtonImg.src = 'play.svg';
    }
    setMediaSession();
    return false // Prevent the default link behavior
}

function setMediaSession() {
    if ('mediaSession' in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: 'Éist',
            artist: artistName, // Replace with dynamic data if needed
            album: showDesc, // Replace with dynamic data if needed
            artwork: [
                { src: '/gradient-96x96.png', sizes: '96x96', type: 'image/png' },
                { src: '/gradient-128x128.png', sizes: '128x128', type: 'image/png' },
                { src: '/gradient-192x192.png', sizes: '192x192', type: 'image/png' },
                { src: '/gradient-256x256.png', sizes: '256x256', type: 'image/png' },
                { src: '/gradient-384x384.png', sizes: '384x384', type: 'image/png' },
                { src: '/gradient-512x512.png', sizes: '512x512', type: 'image/png' },
            ]
        });

        navigator.mediaSession.playbackState = window.currentAudio.paused ? 'paused' : 'playing';

        // Optionally handle media session actions
        navigator.mediaSession.setActionHandler('play', () => {
            window.currentAudio.play();
        });
        navigator.mediaSession.setActionHandler('pause', () => {
            window.currentAudio.pause();
        });
    }
}


// Update the player when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    const playerControl = document.getElementById('player-control');
    if (playerControl) {
        playerControl.addEventListener('click', (event) => {
            event.preventDefault(); // Prevent default link behavior
            toggleAudio();
        });
    };
    updatePlayerDetails()
});
