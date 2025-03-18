// Updates the schedule
// Running locally, you need to source .env && export API_KEY
document.addEventListener("turbo:load", initializeSchedule);

function initializeSchedule() {
    console.log("Initializing schedule...");
    const container = document.getElementById('schedule-output');
    // Prevent multiple executions
    if (!container || container.dataset.loaded) return; 
    // Marks schedule as already loaded
    container.dataset.loaded = "true"; 

    var apiKey = radiocultApiKey;
    var stationId = 'eist-radio';
    var timeZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;

    function formatDate(date, time = '06:00:59Z') {
        return date.toISOString().split('T')[0] + `T${time}`;
    }

    async function fetchArtistName(artistId) {
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
                return data.artist?.name || 'Unknown Host';
            } else {
                console.warn(`Failed to fetch artist: ${response.statusText}`);
                return 'Unknown Host';
            }
        } catch (error) {
            console.error(`Error fetching artist name for ID ${artistId}:`, error);
            return 'Unknown Host';
        }
    }

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

    async function renderSchedule(schedules) {
        container.innerHTML = '';

        const today = new Date().toISOString().split('T')[0];

        // Check if there's anything scheduled for today
        const hasTodaySchedule = schedules.some(item => {
            const startDate = new Date(item.startDateUtc);
            let broadcastDate = startDate.toISOString().split('T')[0];

            if (startDate.getUTCHours() === 0 && startDate.getUTCMinutes() === 0) {
                const prevDate = new Date(startDate);
                prevDate.setUTCDate(prevDate.getUTCDate() - 1);
                broadcastDate = prevDate.toISOString().split('T')[0];
            }

            return broadcastDate === today;
        });

        if (!hasTodaySchedule) {
            container.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center;">
                    <a href="/schedule">No shows scheduled today - check the weekly schedule.</a>
                </td>
            </tr>
            </br>
        `;
        }

        // Group schedules by day, handling 12:00 AM correctly
        const groupedSchedules = schedules.reduce((acc, item) => {
            const startDate = new Date(item.startDateUtc);
            let broadcastDate = startDate.toISOString().split('T')[0];

            if (startDate.getUTCHours() === 0 && startDate.getUTCMinutes() === 0) {
                const prevDate = new Date(startDate);
                prevDate.setUTCDate(prevDate.getUTCDate() - 1);
                broadcastDate = prevDate.toISOString().split('T')[0];
            }

            if (broadcastDate >= today) {
                acc[broadcastDate] = acc[broadcastDate] || [];
                acc[broadcastDate].push(item);
            }

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
            <th>Host</th>
            <th>Show</th>
            `;
            table.appendChild(headerRow);

            const normalizeArtistSlug = (name) => {
                return name
                    .normalize("NFD") // Decompose Unicode characters
                    .replace(/[\u0300-\u036f]/g, "") // Remove diacritics
                    .replace(/[^a-zA-Z0-9]/g, "-") // Replace non-alphanumeric characters with '-'
                    .replace(/--+/g, "-") // Replace multiple dashes with a single dash
                    .replace(/^-+|-+$/g, "") // Remove leading and trailing hyphens
                    .toLowerCase(); // Convert to lowercase
            };

            const rows = await Promise.all(
                items.map(async (item) => {
                    const startDate = new Date(item.startDateUtc);
                    const friendlyTime = startDate.toLocaleString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                        timeZone: 'UTC',
                    });

                    const artistName = item.artistIds?.length? await fetchArtistName(item.artistIds[0]): 'Unknown Host';

                    const artistSlug = normalizeArtistSlug(artistName);
                    const artistLink = (item.artistIds?.length)? `<a href="/artists/${artistSlug}">${artistName}</a>`: artistName;

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

    async function updateSchedule() {
        if (typeof numDays === 'undefined') {
            console.error("Error: numDays is not defined.");
            return;
        }

        const today = new Date();
        const endDate = new Date(today);
        endDate.setDate(today.getDate() + numDays);

        const startDateFormatted = formatDate(today, '00:00:59Z');
        const endDateFormatted = formatDate(endDate, '23:59:59Z');

        const scheduleData = await fetchSchedule(startDateFormatted, endDateFormatted);
        await renderSchedule(scheduleData.schedules);
    }

    updateSchedule(); // Only runs once per page load
};
