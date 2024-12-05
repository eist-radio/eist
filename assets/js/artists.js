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
            artistDiv.classList.add('artist');

            // Artist Name as an h1
            const artistName = document.createElement('h2');
            artistName.textContent = artist.name;
            artistDiv.appendChild(artistName);

            // Artist Description
            const artistDescription = document.createElement('p');
            artistDescription.innerHTML = extractTextFromDescription(artist.description);

            // Add social media links at the end of the description
            const socialLink = getSocialLink(artist.socials);
            if (socialLink) {
                artistDescription.innerHTML += `<br><a href="${socialLink.url}" target="_blank">${socialLink.label}</a>`;
            }

            artistDiv.appendChild(artistDescription);

            // Artist Image
            if (artist.logo && artist.logo.default) {
                const artistImage = document.createElement('img');
                artistImage.src = artist.logo.default;
                artistImage.alt = `${artist.name} Logo`;
                artistImage.classList.add('artist-image');
                artistDiv.appendChild(artistImage);
            }

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

    // Add more platforms as needed
    return null; // Fallback if no recognized key is found
}

// Update the artists when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    updateArtists();
});
