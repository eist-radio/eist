// Pull the list of artists on page load. Use localStorage to reduce subsequent page load times.
// Running locally - source .env && export API_KEY. Restart the hugo server when you make changes

var apiKey = radiocultApiKey;
var stationId = 'eist-radio';
var artistsURL = `https://api.radiocult.fm/api/station/${stationId}/artists`;
var cacheKey = 'artistsCache';

// Initialize artists cache from localStorage or create a new Map
const artistsCache = new Map(JSON.parse(localStorage.getItem(cacheKey)) || []);

// Save artists cache to localStorage
function saveArtistsCache() {
    localStorage.setItem(cacheKey, JSON.stringify([...artistsCache]));
}

// Fetch artist data from the API
async function fetchArtists() {
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

// Helper function to extract text from the description field
function extractTextFromDescription(description) {
    if (!description || !description.content) {
        return '';
    }

    return description.content
        .map(paragraph => {
            if (paragraph.content) {
                return paragraph.content
                    .map(contentItem => contentItem.text || '')
                    .join('');
            }
            return '';
        })
        .join('<br>');
}

// Helper function to generate the first social media link
function getSocialLink(socials) {
    if (!socials || Object.keys(socials).length === 0) {
        return null; // No socials provided
    }

    const socialPlatforms = [
        { key: 'soundcloud', url: `https://www.soundcloud.com/${socials.soundcloud}`, label: 'SoundCloud' },
        { key: 'instagramHandle', url: `https://www.instagram.com/${socials.instagramHandle}`, label: 'Instagram' },
        { key: 'facebook', url: `https://www.facebook.com/${socials.facebook}`, label: 'Facebook' },
        { key: 'mixcloud', url: `https://www.mixcloud.com/${socials.mixcloud}`, label: 'Mixcloud' },
        { key: 'site', url: socials.site, label: 'Website' },
    ];

    for (const platform of socialPlatforms) {
        if (socials[platform.key]) {
            return { url: platform.url, label: platform.label };
        }
    }

    return null;
}

// Render artist data into the DOM
function renderArtists(artists) {
    const container = document.getElementById('artists-output');
    container.innerHTML = ''; // Clear existing content

    if (artists.length === 0) {
        console.warn('No artists found.');
        container.innerHTML = '<p>No artists found.</p>';
        return;
    }

    // Use a document fragment to minimize DOM manipulations
    const fragment = document.createDocumentFragment();

    artists.forEach(artist => {
        const artistDiv = document.createElement('div');
        artistDiv.classList.add('artist'); // Main container for an artist

        // Create and append the image container
        if (artist.logo?.default) {
            const imageDiv = document.createElement('div');
            imageDiv.classList.add('artist-image-container');

            const artistImage = document.createElement('img');
            artistImage.src = artist.logo.default;
            artistImage.alt = `${artist.name} Logo`;
            artistImage.classList.add('artist-image');

            imageDiv.appendChild(artistImage);
            artistDiv.appendChild(imageDiv);
        }

        // Create and append the content container
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('artist-content');

        // Set artist name as a h3
        const artistName = document.createElement('h3');
        artistName.textContent = artist.name;
        contentDiv.appendChild(artistName);

        // Artist Description
        const artistDescription = document.createElement('p');
        artistDescription.classList.add('artist-desc');
        artistDescription.innerHTML = extractTextFromDescription(artist.description);

        // Add social media links at the end of the description
        const socialLink = getSocialLink(artist.socials);
        if (socialLink) {
            artistDescription.innerHTML += `<br><a href="${socialLink.url}" target="_blank">${socialLink.label}</a>`;
        }

        contentDiv.appendChild(artistDescription);
        artistDiv.appendChild(contentDiv);

        // Append artist div to fragment
        fragment.appendChild(artistDiv);
    });

    // Append fragment to container
    container.appendChild(fragment);
}

// Main function to update the artists
async function updateArtists() {
    try {
        const artists = await fetchArtists();
        renderArtists(artists);
    } catch (error) {
        console.error('Error updating artists:', error);
        document.getElementById('artists-output').innerHTML = '<p>Error fetching artists.</p>';
    }
}

// Update the artists when the page is loaded
document.addEventListener('DOMContentLoaded', updateArtists);