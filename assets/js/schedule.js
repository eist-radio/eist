// Update 7 day schedule on page load
// Running locally
// source .env && export API_KEY
// Note: need to restart the hugo server when you make changes
// Timezone calculation is not great :/

apiKey = radiocultApiKey;
stationId = 'eist-radio';

// Get numDays from the parent page
numSchedDays = numDays;

// Get the system timezone
let timeZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;

// Calculate start and end dates
let today = new Date();
let endDate = new Date(today);
endDate.setDate(today.getDate() + numSchedDays); // x days from today

// Format the start and end dates
let startDate = today.toISOString().split('T')[0] + 'T06:00:59Z';
let endDateFormatted = endDate.toISOString().split('T')[0] + 'T23:59:59Z';

// Build the schedule API URL
let scheduleUrl = `https://api.radiocult.fm/api/station/${stationId}/schedule?startDate=${startDate}&endDate=${endDateFormatted}&timezone=${timeZone}`;

// Cache artist names to minimize redundant API calls
const artistCache = new Map();

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

// Process and render the schedule
async function updateSchedule() {
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

        const data = await response.json();

        // Group schedules by day
        const groupedSchedules = data.schedules.reduce((acc, item) => {
            const date = new Date(item.startDateUtc).toISOString().split('T')[0];
            if (!acc[date]) {
                acc[date] = [];
            }
            acc[date].push(item);
            return acc;
        }, {});

        // Get the container element
        const container = document.getElementById('schedule-output');

        // Clear any existing content
        container.innerHTML = '';

        // Generate tables for each day
        for (const [date, schedules] of Object.entries(groupedSchedules)) {
            // Format the day header
            const dayHeader = new Date(date).toLocaleString('en-US', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                timeZone: 'UTC',
            });

            // Create a table and add a header
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
                schedules.map(async (item) => {
                    const startDate = new Date(item.startDateUtc);
                    const friendlyTime = startDate.toLocaleString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                        timeZone: 'UTC',
                    });

                    const hostName = item.artistIds?.length
                        ? await fetchArtistName(item.artistIds[0])
                        : 'Unknown Host';

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${friendlyTime}</td>
                        <td>${hostName}</td>
                        <td>${item.title}</td>
                    `;
                    return row;
                })
            );

            // Append rows to the table
            rows.forEach((row) => table.appendChild(row));

            // Append the table to the container
            container.appendChild(table);
        }
    } catch (error) {
        console.error('Error updating schedule:', error);
        document.getElementById('schedule-output').innerHTML = '<p>Error fetching schedule.</p>';
    }
}

// Update the schedule when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    updateSchedule();
});
