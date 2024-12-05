// Pull the list of artists on page load
// Running locally
// source .env && export API_KEY
// Note: need to restart the hugo server when you make changes

let apiKey = radiocultApiKey;
let stationId = 'eist-radio';
let artistsURL = `https://api.radiocult.fm/api/station/${stationId}/artists`;

async function updateArtists() {
    try {
        // Fetch the artist data
        const response = await fetch(artistsURL, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch artists: ${response.statusText}`);
        }

        const data = await response.json();

        // Extract artist details
        const artists = data.artists || [];
        if (artists.length === 0) {
            console.warn('No artists found.');
            return;
        }

        // Get the container element
        const container = document.getElementById('artists-output');

        // Clear any existing content
        container.innerHTML = '';

        // Generate div for each artist
        artists.forEach(artist => {
            const artistDiv = document.createElement('div');
            artistDiv.classList.add('artist'); // Main container for an artist

            // Create and append the image container
            if (artist.logo && artist.logo.default) {
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

            // Append artist div to container
            container.appendChild(artistDiv);
        });
    } catch (error) {
        console.error('Error updating artists:', error);
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

    if (socials.soundcloud) {
        return { url: `https://www.soundcloud.com/${socials.soundcloud}`, label: "SoundCloud" };
    }

    if (socials.instagramHandle) {
        return { url: `https://www.instagram.com/${socials.instagramHandle}`, label: "Instagram" };
    }

    if (socials.facebook) {
        return { url: `https://www.facebook.com/${socials.facebook}`, label: "Facebook" };
    }

    if (socials.mixcloud) {
        return { url: `https://www.mixcloud.com/${socials.mixcloud}`, label: "Mixcloud" };
    }

    if (socials.site) {
        return { url: `${socials.site}`, label: "Website" };
    }

    return null;
}

// Update the artists when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    updateArtists();
});
