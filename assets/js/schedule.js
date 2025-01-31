// Update the schedule on page load. Use localStorage to reduce subsequent page load times.
// Running locally - source .env && export API_KEY. Restart the hugo server when you make changes

var apiKey = radiocultApiKey;
var stationId = 'eist-radio';
var cacheKey = 'artistCache';
var timeZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;

// Initialize artist cache from localStorage or create a new Map
const artistCache = new Map(JSON.parse(localStorage.getItem(cacheKey)) || []);

// Save artist cache to localStorage
function saveArtistCache() {
    localStorage.setItem(cacheKey, JSON.stringify([...artistCache]));
}

// Format date to API-compatible string
function formatDate(date, time = '06:00:59Z') {
    return date.toISOString().split('T')[0] + `T${time}`;
}

// Fetch artist name using artist ID with caching
async function fetchArtistName(artistId) {
    if (artistCache.has(artistId)) {
        return artistCache.get(artistId);
    }

    try {
        const response = await fetch(`https://api.radiocult.fm/api/station/${stationId}/artists/${artistId}`, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json',
            },
        });

        if (response.ok) {
            const data = await response.json();
            const artistName = data.artist?.name || 'Unknown Host';
            artistCache.set(artistId, artistName); // Cache the result
            saveArtistCache(); // Persist cache
            return artistName;
        } else {
            console.warn(`Failed to fetch artist: ${response.statusText}`);
            return 'Unknown Host';
        }
    } catch (error) {
        console.error(`Error fetching artist name for ID ${artistId}:`, error);
        return 'Unknown Host';
    }
}

// Fetch schedule data from the API
async function fetchSchedule(startDate, endDate) {
    const scheduleUrl = `https://api.radiocult.fm/api/station/${stationId}/schedule?startDate=${startDate}&endDate=${endDate}&timeZone=${timeZone}`;

    try {
        const response = await fetch(scheduleUrl, {
            method: 'GET',
            headers: {
                'x-api-key': apiKey,
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch schedule: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Error fetching schedule:', error);
        throw error;
    }
}

// Render the schedule into the DOM
async function renderSchedule(schedules) {
    const container = document.getElementById('schedule-output');
    container.innerHTML = ''; // Clear existing content

    if (!schedules || schedules.length === 0) {
        container.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center;"><a href="/schedule">No shows scheduled today - check the weekly schedule.</a></td>
            </tr>
        `;
        return;
    }

    // Group schedules by day
    const groupedSchedules = schedules.reduce((acc, item) => {
        const date = new Date(item.startDateUtc).toISOString().split('T')[0];
        acc[date] = acc[date] || [];
        acc[date].push(item);
        return acc;
    }, {});

    // Generate tables for each day
    for (const [date, items] of Object.entries(groupedSchedules)) {
        const dayHeader = new Date(date).toLocaleString('en-US', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            timeZone: 'UTC',
        });

        const table = document.createElement('table');
        table.style.marginBottom = '20px';

        const caption = document.createElement('caption');
        caption.textContent = dayHeader;
        caption.classList.add('table-day-caption-header');
        table.appendChild(caption);

        const headerRow = document.createElement('tr');
        headerRow.innerHTML = `
            <th>Start</th>
            <th>Host</th>
            <th>Show</th>
        `;
        table.appendChild(headerRow);

        // Fetch and render each schedule row
        const rows = await Promise.all(
            items.map(async (item) => {
                const startDate = new Date(item.startDateUtc);
                const friendlyTime = startDate.toLocaleString('en-US', {
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true,
                    timeZone: 'UTC',
                });
                // Don't render links on the /listen page (numDays=0)
                const artistName = item.artistIds?.length
                    ? await fetchArtistName(item.artistIds[0])
                    : 'Unknown Host';

                const artistLink = (numDays !== 0 && item.artistIds?.length)
                    ? `<a href="/artists/${artistName.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, '-').toLowerCase()}">${artistName}</a>`
                    : artistName;

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${friendlyTime}</td>
                    <td>${artistLink}</td>
                    <td>${item.title}</td>
                `;
                return row;
            })
        );

        rows.forEach((row) => table.appendChild(row));
        container.appendChild(table);
    }
}

// Main function to update the schedule
async function updateSchedule() {
    const today = new Date();
    const endDate = new Date(today);
    endDate.setDate(today.getDate() + numDays); // numDays from the parent page

    const startDateFormatted = formatDate(today, '06:00:59Z');
    const endDateFormatted = formatDate(endDate, '23:59:59Z');

    try {
        const scheduleData = await fetchSchedule(startDateFormatted, endDateFormatted);
        await renderSchedule(scheduleData.schedules);
    } catch (error) {
        console.error('Error updating schedule:', error);
        document.getElementById('schedule-output').innerHTML = '<p>Error fetching schedule.</p>';
    }
}

// Update the schedule when the page is loaded
document.addEventListener('DOMContentLoaded', updateSchedule);