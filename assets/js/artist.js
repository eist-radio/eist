var apiKey = radiocultApiKey;
var stationId = 'eist-radio';
var artistsURL = `https://api.radiocult.fm/api/station/${stationId}/artists`;
var defaultImage = '/no-artist.png'; // Fallback image
let allArtists = [];

// Get the artist name from JSON-LD script tag
// Didn't want to render the Artist name in a h tag cos it looks a bit bum.
target="application/ld+json";
function getArtistNameFromJsonLd() {
    const scriptTag = document.querySelector('script[type="application/ld+json"]');
    if (scriptTag) {
        try {
            const jsonData = JSON.parse(scriptTag.textContent);
            return jsonData.description.trim();
        } catch (error) {
            console.error('Error parsing JSON-LD:', error);
        }
    }
    return '';
}

// Fetch all artists from the API
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
        allArtists = data.artists || [];
    } catch (error) {
        console.error('Error fetching artists:', error);
    }
}

// Find artist by name in the fetched list
function findArtistByName(artistName) {
    return allArtists.find(artist => artist.name.toLowerCase() === artistName.toLowerCase()) || null;
}

// Extract text from the description field
function extractTextFromDescription(description) {
    if (!description || !description.content) {
        return '';
    }
    return description.content.map(paragraph => {
        if (paragraph.content) {
            return paragraph.content.map(contentItem => contentItem.text || '').join('');
        }
        return '';
    }).join('<br>');
}

// Get the first social media link
function getSocialLink(socials) {
    if (!socials || Object.keys(socials).length === 0) {
        return null;
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

// Render a single artist
function renderArtist(artist) {
    const container = document.getElementById('artists-output');
    container.innerHTML = '';

    if (!artist) {
        container.innerHTML = '<p>Artist not found.</p>';
        return;
    }

    const artistDiv = document.createElement('div');
    artistDiv.classList.add('artist');

    const imageDiv = document.createElement('div');
    imageDiv.classList.add('artist-image-container');

    const artistImage = document.createElement('img');
    artistImage.src = artist.logo?.default || defaultImage;
    artistImage.alt = `${artist.name} Logo`;
    artistImage.classList.add('artist-image');

    imageDiv.appendChild(artistImage);
    artistDiv.appendChild(imageDiv);

    const contentDiv = document.createElement('div');
    contentDiv.classList.add('artist-content');

    const artistName = document.createElement('h3');
    artistName.textContent = artist.name;
    contentDiv.appendChild(artistName);

    const artistDescription = document.createElement('p');
    artistDescription.classList.add('artist-desc');
    artistDescription.innerHTML = extractTextFromDescription(artist.description);

    const socialLink = getSocialLink(artist.socials);
    if (socialLink) {
        artistDescription.innerHTML += `<br><a href="${socialLink.url}" target="_blank">${socialLink.label}</a>`;
    }

    contentDiv.appendChild(artistDescription);
    artistDiv.appendChild(contentDiv);

    container.appendChild(artistDiv);
}

// Initialize artist display on page load
document.addEventListener('DOMContentLoaded', async () => {
    await fetchAllArtists();
    const artistName = getArtistNameFromJsonLd();
    if (artistName) {
        const artist = findArtistByName(artistName);
        renderArtist(artist);
    }
});
