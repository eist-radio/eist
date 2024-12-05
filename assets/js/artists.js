// TODO modify this for artists
// Pull artists details from the API on page load

// Running locally
// source .env
// export API_KEY
// Note need to restart the hugo server when you make changes

let apiKey = radiocultApiKey;
let stationId = 'eist-radio';
let url = `https://api.radiocult.fm/api/station/${stationId}/schedule/live`;

// Get the system timezone using the `Intl.DateTimeFormat` API
let timeZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;

// Calculate start and end dates
let today = new Date();
let endDate = new Date(today);

endDate.setDate(today.getDate() + 7); // 7 days from today

// Format the start and end dates as needed
// Start of today in ISO format
let startDate = today.toISOString().split('T')[0] + 'T00:00:00Z';

// End of the 7th day in ISO format
let endDateFormatted = endDate.toISOString().split('T')[0] + 'T23:59:59Z'; 

// Build the API URL
let scheduleUrl = `https://api.radiocult.fm/api/station/${stationId}/schedule?startDate=${startDate}&endDate=${endDateFormatted}&timezone=${timeZone}`;

async function updateSchedule() {
    // Fetch the schedule data
    fetch(scheduleUrl, {
        method: 'GET',
        headers: {
            'x-api-key': apiKey,
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        // Extract and group schedules by day
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

        // Generate a table for each day
        for (const [date, schedules] of Object.entries(groupedSchedules)) {
            // Format the day header
            const dayHeader = new Date(date).toLocaleString('en-US', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                timeZone: 'UTC'
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
                <th>Start time</th>
                <th>Show</th>
            `;
            table.appendChild(headerRow);

            // Add rows for the schedule
            schedules.forEach(item => {
                const startDate = new Date(item.startDateUtc);
                const friendlyTime = startDate.toLocaleString('en-US', {
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true,
                    timeZone: 'UTC'
                });

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${friendlyTime}</td>
                    <td>${item.title}</td>
                `;
                table.appendChild(row);
            });

            // Append the table to the container
            container.appendChild(table);
        }
    })
    .catch(error => {
        console.error('Error fetching schedule:', error);
        document.getElementById('schedule-output').innerHTML = '<p>Error fetching schedule.</p>';
    });
}

// Update the schedule when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
    updateSchedule();
});
