// Pull a list of artists on page load.
// Running locally - source .env && export API_KEY. Restart the hugo server when you make changes

var apiKey = radiocultApiKey;
var stationId = 'eist-radio';
var artistsURL = `https://api.radiocult.fm/api/station/${stationId}/artists`;

// Normalize artist names into filenames
function normalizeFilename(name) {
    return name
        .normalize('NFD') // Normalize to decomposed Unicode (e.g., é → e + ´)
        .replace(/[\u0300-\u036f]/g, '') // Remove diacritics (combining accents)
        .replace(/[^a-zA-Z0-9\s]/g, '-') // Replace ALL non-alphabetic characters (except spaces) with hyphens
        .replace(/\s+/g, '-') // Replace spaces with hyphens
        .replace(/-+/g, '-') // Replace multiple hyphens with a single hyphen
        .replace(/^-|-$/g, '') // Remove leading or trailing hyphens
        .toLowerCase(); // Convert to lowercase
}

// Fetch all artist data from the API
async function fetchAllArtists() {
    try {
        const response = await fetch(artistsURL, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch artists: ${response.statusText}`);
        }

        const data = await response.json();
        return data.artists || [];
    } catch (error) {
        console.error('Error fetching artists:', error);
        throw error;
    }
}

// Render the list of artists as HTML links to their pages
function renderArtists(artists) {
    const container = document.getElementById('artists-output');
    if (!container) return;

    // Sort artists alphabetically by name
    const sortedArtists = artists.sort((a, b) => a.name.localeCompare(b.name));

    const artistLinks = sortedArtists.map(artist => {
        const pageName = normalizeFilename(artist.name); // Normalize the artist name for the URL
        return `<a href="${pageName}" id="host-link">${artist.name}</a>`;
    }).join('  /  ');

    container.innerHTML = `<p>${artistLinks}</p>`;
}

// Main function to fetch and render artists
async function updateArtists() {
    try {
        const artists = await fetchAllArtists();
        renderArtists(artists);
    } catch (error) {
        console.error('Error updating artists:', error);
        document.getElementById('artists-output').innerHTML = '<p>Error fetching artists.</p>';
    }
}

// Update the artists when the page is loaded
document.addEventListener('DOMContentLoaded', updateArtists);