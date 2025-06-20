// Updates the schedule
// Running locally, you need to source .env && export API_KEY
document.addEventListener("turbo:load", initializeSchedule);

function initializeSchedule() {
    console.log("Initializing schedule...");
    const container = document.getElementById('schedule-output');
    if (!container || container.dataset.loaded) return;
    container.dataset.loaded = "true";

    var apiKey = radiocultApiKey;
    var stationId = 'eist-radio';
    var timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    function formatDate(date, time = '06:00:59Z') {
        return date.toISOString().split('T')[0] + `T${time}`;
    }

    function convertToLocalTime(utcDate) {
        return new Date(utcDate).toLocaleString('en-US', {
            timeZone: timeZone,
        });
    }

    async function fetchSchedule(localStartDate, endDate) {
        const scheduleUrl = `https://api.radiocult.fm/api/station/${stationId}/schedule?startDate=${localStartDate}&endDate=${endDate}`;
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

            const scheduleData = await response.json();
            console.log('Fetched schedule:', scheduleData.schedules.map(s => s.startDateUtc));
            return scheduleData;
        } catch (error) {
            console.error('Error fetching schedule:', error);
            throw error;
        }
    }

    async function renderSchedule(schedules) {
        container.innerHTML = '';

        const groupedSchedules = schedules.reduce((acc, item) => {
            const localStartDate = new Date(item.startDateUtc);
            let broadcastDate = localStartDate.toISOString().split('T')[0];

            if (localStartDate.getUTCHours() === 0 && localStartDate.getUTCMinutes() === 0) {
                const prevDate = new Date(localStartDate);
                prevDate.setUTCDate(prevDate.getUTCDate() - 1);
                broadcastDate = prevDate.toISOString().split('T')[0];
            }

            acc[broadcastDate] = acc[broadcastDate] || [];
            acc[broadcastDate].push(item);
            return acc;
        }, {});

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
            <th>Show</th>
            `;
            table.appendChild(headerRow);

            const rows = await Promise.all(
                items.map(async (item) => {
                    const localStartDate = new Date(item.startDateUtc);
                    const friendlyTime = localStartDate.toLocaleString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                        timeZone: timeZone,
                    });

                    const row = document.createElement('tr');
                    row.innerHTML = `
                    <td>${friendlyTime}</td>
                    <td>${item.title}</td>
                    `;
                    return row;
                })
            );

            rows.forEach((row) => table.appendChild(row));
            container.appendChild(table);
        }
    }

    async function updateSchedule() {
        const startDate = '2025-06-21T00:00:00Z';
        const endDate = '2025-06-23T00:00:00Z';

        try {
            const data = await fetchSchedule(startDate, endDate);
            console.log('Fetched schedule UTC startDates:', data.schedules.map(s => s.startDateUtc));

            const filteredSchedules = data.schedules.filter((item) => {
                const utcDate = item.startDateUtc.split('T')[0];
                return utcDate === '2025-06-21' || utcDate === '2025-06-22';
            });

            await renderSchedule(filteredSchedules);
        } catch (err) {
            console.error('Schedule update failed:', err);
        }
    }

    updateSchedule();
}
