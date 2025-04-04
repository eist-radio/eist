// Update the front page on page load
// Running locally, you need to source .env && export API_KEY
// Restart the hugo server when you make changes
document.addEventListener("turbo:load", initializeFrontPage);
document.addEventListener("turbo:render", initializeFrontPage);

function initializeFrontPage() {
    const apiKey = radiocultApiKey;
    const stationId = 'eist-radio';
    const apiUrl = `https://api.radiocult.fm/api/station/${stationId}`;
    const defaultOfflineImage = '/eist_offline.png';
    const defaultOnlineImage = '/eist_online.png';
    const defaultText = ' ';

    // Global State
    let frontPageArtistDetails = {
        name: defaultText,
        bio: defaultText,
        image: defaultOfflineImage
    };

    // Fetch and update the currently playing show details
    async function updateFrontPageDetails() {
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
            const { status, content, metadata } = data.result;

            // If nothing is playing, use offline image and default text
            if (status !== "schedule") {
                frontPageArtistDetails = {
                    name: defaultText,
                    bio: defaultText,
                    image: defaultOfflineImage
                };
                updateFrontPage({ showDesc: ' ', showTitle: ' ', frontPageArtistDetails });
                return;
            }

            const artistId = content.artistIds?.[0] || defaultText;
            let showDesc = (content.description?.content || [])
            .map(block => {
                if (!Array.isArray(block.content)) return '';
                return block.content.map(child => {
                    if (child.type === 'text') return child.text;
                    if (child.type === 'hardBreak') return '<br>';
                    return '';
                }).join('');
            })
            .join('<br><br>') || defaultText;
            const showTitle = content.title || defaultText;

            // Fetch artist details
            frontPageArtistDetails = await getArtistDetails(artistId);

            // Append the current song title if the media type is "playlist"
            if (content.media?.type === "playlist" && metadata?.title) {
                showDesc += `\n\nNow playing: ${metadata.title}`;
            }

            // Update the DOM with live show details
            updateFrontPage({ showDesc, showTitle, frontPageArtistDetails });

        } catch (error) {
            console.error('Error fetching show details:', error);
            // Fallback to offline when error occurs
            frontPageArtistDetails = {
                name: defaultText,
                bio: defaultText,
                image: defaultOfflineImage
            };
            updateFrontPage({ showDesc: ' ', showTitle: ' ', frontPageArtistDetails });
        }
    }

    // Fetch artist details
    async function getArtistDetails(artistId) {
        if (!artistId) return { name: defaultText, bio: defaultText, image: defaultOnlineImage };

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
                image: artist.logo?.['512x512'] || defaultOnlineImage
            };

        } catch (error) {
            console.error('Error fetching artist details:', error);
            return { name: defaultText, bio: defaultText, image: defaultOnlineImage };
        }
    }

    // Update the front page with show and artist details
    function updateFrontPage({ showDesc, showTitle, frontPageArtistDetails }) {
        const artistNameElement = document.getElementById('dj-name');
        const showDescElement = document.getElementById('player-metadata-show-desc');
        const showTitleElementFrontPage = document.getElementById('player-metadata-show-title-front-page');
        const artistImageElement = document.getElementById('dj-image-front-page');

        if (artistNameElement) artistNameElement.textContent = frontPageArtistDetails.name;
        if (showDescElement) showDescElement.innerHTML = showDesc;
        if (showTitleElementFrontPage) showTitleElementFrontPage.textContent = showTitle;

        if (artistImageElement) artistImageElement.src = frontPageArtistDetails.image || defaultOfflineImage;
    }

    updateFrontPageDetails();
};
