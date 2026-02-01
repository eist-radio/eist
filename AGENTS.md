# éist Radio Website - Technical Reference

This document describes the architecture and structure of the éist radio website for AI coding assistants.

> **IMPORTANT**: Never push to remote without explicit user permission.

## Overview

éist is an internet radio station based in Cork, Ireland. This is a Hugo static site with dynamic client-side features for live radio streaming and schedule display.

**Live site**: https://eist.radio

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Static Site Generator | Hugo 0.137.1 Extended |
| Styling | SCSS (compiled by Hugo) |
| JavaScript | Vanilla ES6+, Turbo Drive |
| Audio | HTML5 `<audio>` element |
| API | RadioCult REST API |
| Hosting | GitHub Pages (production), Netlify (PR previews) |
| CI/CD | GitHub Actions |

## Project Structure

```
/
├── content/                    # Markdown content pages
│   ├── artists/               # Auto-generated artist profile pages
│   └── events/images/         # Event images
├── layouts/                    # Hugo templates
│   ├── _default/              # Base templates (baseof, single, list)
│   ├── partials/              # Reusable components (header, footer, player)
│   └── shortcodes/            # Custom shortcodes (schedule, figure, admonition)
├── assets/
│   ├── js/                    # JavaScript source files
│   └── scss/                  # SCSS stylesheets
├── static/
│   ├── js/                    # Static JavaScript (front-page.js)
│   └── fonts/                 # Nimbus Sans L font files
├── .github/workflows/          # CI/CD pipelines
├── data/                       # JSON data caches (consumed by Hugo)
│   ├── shows.json             # RadioCult shows with archive matches
│   ├── soundcloud-cache.json  # SoundCloud track metadata
│   ├── mixcloud-cache.json    # Mixcloud cloudcast metadata
│   └── review-queue.json      # Low-confidence matches for review
├── hugo.toml                   # Hugo configuration
├── soundcloud_api.py           # SoundCloud OAuth API client
├── generate-show-cache.py      # Main data pipeline script
├── generate-show-pages.py      # Generate Hugo pages for shows
├── generate-artist-pages.py    # Generate Hugo pages from RadioCult API
└── match_mcsc_to_rc.py         # Archive-to-show matching algorithm
```

## Hugo Configuration

Configuration is in `hugo.toml`:

- **Base URL**: `https://eist.radio/`
- **Theme color**: `#4733FF` (éist purple)
- **Unsafe HTML**: Enabled in Goldmark renderer
- **RSS**: Enabled with 10-item limit

### Menu Structure

1. Listen (`/`)
2. About (`/about/`)
3. Schedule (`/schedule/`)
4. App (`/app/`)
5. Support (`/support/`)
6. Get Involved (`/get-involved/`)

## Content Pages

| File | Purpose |
|------|---------|
| `about.md` | About the radio station |
| `app.md` | iOS & Android app download links |
| `schedule.md` | 7-day schedule with dynamic table |
| `support.md` | Donation page with PayPal |
| `get-involved.md` | Show submission information |
| `events.md` | Event announcements |
| `privacy.md` | Privacy policy for mobile apps |
| `newsletter.md` | Newsletter signup (Brevo) |

Artist pages in `content/artists/` are auto-generated - do not edit manually.

## JavaScript Architecture

### Core Files (`assets/js/`)

**player.js**
- Audio playback for stream `https://eist-radio.radiocult.fm/stream`
- Play/pause toggle with promise-based state management
- Fetches current show metadata from RadioCult API
- Updates "Now Playing" display (show title, artist, live status)
- MediaSession API integration for device media controls

**main.js**
- Page initialization and UI interaction
- Auto-hide header on scroll
- Mobile menu toggle with animations
- Turbo navigation integration

**schedule.js**
- Populates 7-day schedule table dynamically
- Fetches from API: `/schedule?startDate=...&endDate=...`
- Converts UTC to user's local timezone
- Generates artist profile links

**copylink.js**
- Share button functionality (copies URL to clipboard)

### Static JS (`static/js/`)

**front-page.js**
- Homepage-specific initialization
- Fetches live show via `/schedule/live` endpoint
- Displays current show with DJ image and bio
- Updates on tab visibility change

**service-worker.js**
- PWA offline caching (network-first strategy)

## RadioCult API Integration

**Base URL**: `https://api.radiocult.fm/api/station/eist-radio/`

| Endpoint | Purpose |
|----------|---------|
| `/schedule/live` | Current playing show + metadata |
| `/schedule?startDate=...&endDate=...` | Schedule for date range |
| `/artists/{id}` | Artist details |
| `/artists` | All artists list |

**Stream URL**: `https://eist-radio.radiocult.fm/stream`

## SCSS Structure

Main stylesheet: `assets/scss/style.scss`

Imports in order:
1. `predefined.scss` - Mixins and helpers
2. `normalize.scss` - CSS reset
3. `syntax.scss` - Code block styling
4. `scroll.scss` - Scrollbar styling
5. `socialshare.scss` - Social share buttons
6. `custom.scss` - Main éist styling (550+ lines)

### Color Palette

```scss
$eist: #4733FF              // Primary purple
$eist-secondary: #AFFC41    // Lime green accent
$eist-highlight: #96BFE6    // Light blue
```

### Responsive Breakpoints

- Desktop: 1200px max-width
- Large screens (1800px+): Extends to 1600px
- Tablet (1000px): Hide desktop nav, show hamburger
- Mobile (520px): Resize player, adjust layouts

## Templates

### Base Layout (`layouts/_default/baseof.html`)

- Loads compiled SCSS
- Includes partials: header, main content, footer
- Script loading: main.js, copylink.js, player.js, turbo

### Key Partials

| Partial | Purpose |
|---------|---------|
| `header.html` | Navigation, logo, mobile menu |
| `footer.html` | Footer with social links |
| `player.html` | Audio player HTML element |
| `menu.html` | Navigation menu |
| `social-icons.html` | Social media icons |

### Shortcodes

| Shortcode | Usage |
|-----------|-------|
| `schedule` | `{{< schedule numDays=7 >}}` - Renders schedule table |
| `figure` | Image with caption |
| `admonition` | Note/info/warning boxes |

## Build & Deployment

### Local Development

```bash
# Set API key
export API_KEY="your-radiocult-api-key"

# Generate artist pages
python3 generate-artist-pages.py

# Start dev server
hugo server
```

### Production (GitHub Actions)

Triggered on:
- Push to `main`
- Scheduled: Every 6 hours (06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC)
- Manual dispatch

Steps:
1. Generate artist pages from API
2. Build with `hugo --gc --minify`
3. Deploy to GitHub Pages

### PR Previews

Automatically deployed to Netlify on PR open/update.

Pipeline steps:
1. Install Python dependencies (`thefuzz`, `python-Levenshtein`, `requests`)
2. Generate artist pages (`generate-artist-pages.py`)
3. Align artist images for hero sections (`scripts/detect-faces.py`) - skips gracefully if deps unavailable
4. Generate show cache (`generate-show-cache.py`) - fetches from SoundCloud/Mixcloud APIs
5. Generate show pages (`generate-show-pages.py`)
6. Build with Hugo
7. Deploy to Netlify

Preview URL format: `preview-{PR_NUMBER}.{NETLIFY_DOMAIN}`

## Secrets Required

| Secret | Purpose |
|--------|---------|
| `RADIOCULT_API_KEY` | RadioCult API authentication (CI uses this name) |
| `SOUNDCLOUD_CLIENT_ID` | SoundCloud OAuth client ID |
| `SOUNDCLOUD_CLIENT_SECRET` | SoundCloud OAuth client secret |
| `NETLIFY_AUTH_TOKEN` | Netlify deployment |
| `NETLIFY_SITE_ID` | Netlify site ID |

### Local API Keys

For local development, add keys to `.env`:

```
API_KEY=your_radiocult_key
SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id
SOUNDCLOUD_CLIENT_SECRET=your_soundcloud_client_secret
```

Then `source .env && export API_KEY` before running scripts. The Python scripts also read `.env` directly.

## Data Pipeline (Archive Matching)

The site matches RadioCult show schedules with archives uploaded to SoundCloud and Mixcloud.

### Scripts

| Script | Purpose |
|--------|---------|
| `soundcloud_api.py` | OAuth 2.0 API client for SoundCloud (replaces yt-dlp scraping) |
| `generate-show-cache.py` | Main pipeline: fetches from all sources, runs matching, outputs JSON |
| `match_mcsc_to_rc.py` | Matching algorithm: dates, titles, fuzzy matching |
| `generate-show-pages.py` | Creates Hugo markdown pages for matched shows |

### Flow

```
RadioCult API ──┐
                ├──► generate-show-cache.py ──► data/shows.json ──► generate-show-pages.py ──► content/archive/*.md
SoundCloud API ─┤         │
Mixcloud API ───┘         ▼
                   data/soundcloud-cache.json
                   data/mixcloud-cache.json
```

### Running Locally

```bash
source .env && export API_KEY SOUNDCLOUD_CLIENT_ID SOUNDCLOUD_CLIENT_SECRET
python3 generate-show-cache.py        # Incremental update
python3 generate-show-cache.py --full # Full refresh
python3 generate-show-pages.py        # Generate Hugo pages
```

## Key Architectural Notes

1. **Hybrid Rendering**: Static pages at build time, dynamic data (schedule, now playing) fetched client-side

2. **Turbo Navigation**: SPA-like experience with `data-turbo-permanent` on player to preserve audio state

3. **Artist Pages**: Auto-generated from RadioCult API - regenerated every 6 hours via cron

4. **State**: No framework - vanilla JavaScript with global state objects (`artistDetails`, `frontPageArtistDetails`)

5. **Error Handling**: Graceful fallbacks when API unavailable, offline images for failed loads

## Common Tasks

### Adding a new page
1. Create `content/pagename.md` with front matter
2. Add to menu in `hugo.toml` if needed

### Modifying styles
- Edit `assets/scss/custom.scss` for éist-specific styles
- Other SCSS files for specific components

### Updating player behavior
- Edit `assets/js/player.js` for playback logic
- Edit `layouts/partials/player.html` for HTML structure

### Changing schedule display
- Edit `assets/js/schedule.js` for logic
- Edit `layouts/shortcodes/schedule.html` for markup

## Branch: demo/api-calls-only

The `demo/api-calls-only` branch implements an alternative architecture for sourcing show/episode data. This section documents how it differs from the main branch.

### Main Branch vs Demo Branch Architecture

**Main Branch Flow:**
```
RadioCult Schedule → Shows/Episodes (primary source)
       ↓
Match to MC/SC tracks (for embeds/links)
```

In the main branch:
- Shows are sourced from RadioCult schedule entries
- Each scheduled show is then matched to Mixcloud/SoundCloud archives using fuzzy matching
- RadioCult is the authoritative source for show metadata, timing, and artist associations

**Demo Branch Flow (API-Calls-Only):**
```
MC/SC API → Shows/Episodes (primary source)
       ↓
Match to Artists via username tags from RadioCult
```

In this branch:
- Shows are sourced directly from Mixcloud and SoundCloud APIs
- Each track from MC/SC becomes a show entry
- Artists are associated by matching track titles to RadioCult artist profiles via username tags

### What RadioCult Is Used For (Demo Branch)

RadioCult is still used for:
- **Artist metadata**: name, image, bio, and tags (including username mappings)
- **Upcoming schedule**: Future shows still come from RadioCult
- **NOT used for**: Archive/episode generation (this comes from MC/SC APIs)

### Artist Matching Mechanism

The demo branch matches tracks to artists using tags in RadioCult artist profiles:

| Tag Format | Purpose |
|------------|---------|
| `MC-USERNAME_username` | Maps Mixcloud username to artist |
| `SC-USERNAME_username` | Maps SoundCloud username to artist |
| `HOST-MC-PLAYLIST_` | Maps host's Mixcloud playlist to artist |

**Matching strategies (in priority order):**
1. Extract artist name from track title (e.g., "Artist Name - Track Title")
2. Match extracted name to MC/SC username tags
3. Match to normalized artist names
4. Match to artist slugs
5. Partial/fuzzy matching for longer names

Tracks that cannot be matched to an artist appear with "Unknown Artist".

### New Features in Demo Branch

1. **Platform indicator badges**: Show cards display MC (purple) or SC (orange) badges indicating the source platform

2. **New data file**: `data/api-shows-cache.json` contains metadata about API-sourced shows including generation timestamp and source counts

3. **Platform field in frontmatter**: Show pages include a `platform` field ("mixcloud" or "soundcloud") indicating the source

### Files Changed

| File | Change |
|------|--------|
| `generate-show-cache.py` | Major rewrite: sources shows from MC/SC APIs instead of RadioCult schedule |
| `generate-show-pages.py` | Added `platform` field to frontmatter |
| `layouts/archive/list.html` | Added platform badge display |
| `layouts/archive/single.html` | Added platform badge display |
| `layouts/artists/single.html` | Added platform badge on show cards |
| `assets/scss/_archive.scss` | Platform badge styles (`.archive-platform-badge`) |
| `assets/scss/_artists.scss` | Platform badge styles (`.artist-show-platform-badge`) |
| `assets/scss/_shows.scss` | Platform badge styles (`.show-platform-badge`) |

### Key Differences in generate-show-cache.py

**Main branch:**
- Fetches RadioCult schedule for past shows
- Matches shows to MC/SC archives using date and title matching
- Uses `match_mcsc_to_rc.py` for sophisticated fuzzy matching

**Demo branch:**
- Does NOT fetch RadioCult past schedule
- Fetches all tracks from MC/SC APIs directly
- Uses `build_artist_lookup()` to create username-to-artist mappings
- Uses `match_track_to_artist()` to associate tracks with artists
- Uses `convert_track_to_show()` to convert API tracks to show format

### When to Use Each Approach

**Main branch (RadioCult-primary):**
- Best when RadioCult schedule is the authoritative source
- Handles shows that may not have archives yet
- Better for stations that schedule shows in advance

**Demo branch (API-primary):**
- Best when MC/SC archives are the authoritative source
- Simpler architecture with fewer matching edge cases
- Good for stations that upload archives without formal scheduling
- Shows only appear once they have an actual archive
