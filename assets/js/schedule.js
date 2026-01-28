// Updates the schedule
// Running locally, you need to source .env && export API_KEY
document.addEventListener("turbo:load", initializeSchedule);
// Fallback for direct page loads (Turbo may not fire turbo:load on initial visit)
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeSchedule);
} else {
    initializeSchedule();
}

function initializeSchedule() {
    console.log("Initializing schedule...");
    const container = document.getElementById('schedule-output');
    // Prevent multiple executions
    if (!container || container.dataset.loaded) return;
    // Marks schedule as already loaded
    container.dataset.loaded = "true";

    var apiKey = radiocultApiKey;
    var stationId = 'eist-radio';
    var timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    // Navigation state
    var currentOffset = 0; // Days offset from today (negative = past, positive = future)
    const canNavigate = typeof allowNavigation !== 'undefined' && allowNavigation;
    const pastDaysLimit = typeof maxPastDays !== 'undefined' ? maxPastDays : 0;

    function formatDate(date, time = '06:00:59Z') {
        return date.toISOString().split('T')[0] + `T${time}`;
    }

    function convertToLocalTime(utcDate) {
        return new Date(utcDate).toLocaleString('en-US', {
            timeZone: timeZone, // Convert to user's local timezone
        });
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

    async function fetchSchedule(localStartDate, endDate) {
        const scheduleUrl = `https://api.radiocult.fm/api/station/${stationId}/schedule?startDate=${localStartDate}&endDate=${endDate}&timeZone=${timeZone}`;

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

    async function renderSchedule(schedules, minDate) {
        container.innerHTML = '';

        const today = new Date().toISOString().split('T')[0];
        const filterDate = minDate || today;

        // Check if there's anything scheduled for today (only show message on home page)
        if (!canNavigate) {
            const hasTodaySchedule = schedules.some(item => {
                const localStartDate = new Date(item.startDateUtc);
                let broadcastDate = localStartDate.toISOString().split('T')[0];

                if (localStartDate.getUTCHours() === 0 && localStartDate.getUTCMinutes() === 0) {
                    const prevDate = new Date(localStartDate);
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
        }

        // Group schedules by day, handling 12:00 AM correctly
        const groupedSchedules = schedules.reduce((acc, item) => {
            const localStartDate = new Date(item.startDateUtc);
            let broadcastDate = localStartDate.toISOString().split('T')[0];

            if (localStartDate.getUTCHours() === 0 && localStartDate.getUTCMinutes() === 0) {
                const prevDate = new Date(localStartDate);
                prevDate.setUTCDate(prevDate.getUTCDate() - 1);
                broadcastDate = prevDate.toISOString().split('T')[0];
            }

            if (broadcastDate >= filterDate) {
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
            <th>Show</th>
            <th>Host</th>
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
                    const localStartDate = new Date(item.startDateUtc);
                    const friendlyTime = localStartDate.toLocaleString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true,
                        timeZone: timeZone, // Use actual timezone
                    });

                    const artistName = item.artistIds?.length? await fetchArtistName(item.artistIds[0]): 'Unknown Host';

                    const artistSlug = normalizeArtistSlug(artistName);
                    const artistLink = (item.artistIds?.length)? `<a href="/artists/${artistSlug}">${artistName}</a>`: artistName;

                    const row = document.createElement('tr');
                    row.innerHTML = `
                    <td>${friendlyTime}</td>
                    <td>${item.title}</td>
                    <td>${artistLink}</td>
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
        const startDate = new Date(today);
        startDate.setDate(today.getDate() + currentOffset);

        const endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + numDays);

        const localStartDateFormatted = formatDate(startDate, '00:00:59Z');
        const endDateFormatted = formatDate(endDate, '23:59:59Z');
        const minDate = startDate.toISOString().split('T')[0];

        const scheduleData = await fetchSchedule(localStartDateFormatted, endDateFormatted);
        await renderSchedule(scheduleData.schedules, minDate);

        // Update navigation UI
        updateNavigationUI(startDate, endDate);
    }

    function updateNavigationUI(startDate, endDate) {
        if (!canNavigate) return;

        const navContainer = document.getElementById('schedule-nav');
        const prevBtn = document.getElementById('schedule-prev');
        const nextBtn = document.getElementById('schedule-next');
        const rangeSpan = document.getElementById('schedule-range');

        if (!navContainer) return;

        navContainer.style.display = 'flex';

        // Format date range display
        const formatShortDate = (date) => date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric'
        });
        rangeSpan.textContent = `${formatShortDate(startDate)} - ${formatShortDate(endDate)}`;

        // Disable prev button if at max past limit
        prevBtn.disabled = currentOffset <= -pastDaysLimit;
        prevBtn.style.opacity = prevBtn.disabled ? '0.5' : '1';
        prevBtn.style.cursor = prevBtn.disabled ? 'not-allowed' : 'pointer';
    }

    function setupNavigation() {
        if (!canNavigate) return;

        const navContainer = document.getElementById('schedule-nav');
        const prevBtn = document.getElementById('schedule-prev');
        const nextBtn = document.getElementById('schedule-next');

        // Show navigation immediately with "Loading..." text
        if (navContainer) {
            navContainer.style.display = 'flex';
        }

        const rangeSpan = document.getElementById('schedule-range');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (currentOffset > -pastDaysLimit) {
                    currentOffset -= numDays;
                    if (currentOffset < -pastDaysLimit) {
                        currentOffset = -pastDaysLimit;
                    }
                    if (rangeSpan) rangeSpan.textContent = 'Loading...';
                    updateSchedule();
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                currentOffset += numDays;
                if (rangeSpan) rangeSpan.textContent = 'Loading...';
                updateSchedule();
            });
        }
    }

    setupNavigation();
    updateSchedule();
};
