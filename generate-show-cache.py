#!/usr/bin/env python3
"""
Generate show cache for éist radio website.

Fetches schedule data from RadioCult API and matches archives (Mixcloud + SoundCloud)
to RadioCult shows. Each archive matches to exactly one show (1:1 mapping).

Usage:
    python3 generate-show-cache.py [--full]

Options:
    --full    Force full refresh of all data (default: incremental)
"""

import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Import SoundCloud API client (replaces yt-dlp scraping)
from soundcloud_api import (
    SoundCloudClient,
    SoundCloudAuthError,
    SoundCloudAPIError,
    fetch_soundcloud_tracks_api,
    fetch_soundcloud_tracks_api_incremental,
)

# Import matching logic from dedicated module
from match_mcsc_to_rc import (
    match_archives_to_shows,
    normalize_text,
    extract_date_from_title,
    MATCH_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
)

# Configuration
RADIOCULT_BASE_URL = "https://api.radiocult.fm/api/station/eist-radio"
MIXCLOUD_BASE_URL = "https://api.mixcloud.com"
MIXCLOUD_USER = "eistcork"
SOUNDCLOUD_USER = "eistcork"
DATA_DIR = Path("data")
SHOWS_FILE = DATA_DIR / "shows.json"
UPCOMING_SCHEDULE_FILE = DATA_DIR / "upcoming_schedule.json"
MIXCLOUD_CACHE_FILE = DATA_DIR / "mixcloud-cache.json"
SOUNDCLOUD_CACHE_FILE = DATA_DIR / "soundcloud-cache.json"
CACHE_META_FILE = DATA_DIR / "cache-meta.json"
REVIEW_QUEUE_FILE = DATA_DIR / "review-queue.json"

# Rate limiting
REQUEST_DELAY = 0.5  # Seconds between API requests


def load_api_keys():
    """Load API keys from .env file or environment variables.

    .env format (key=value, one per line):
        API_KEY=your_radiocult_key
        SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id
        SOUNDCLOUD_CLIENT_SECRET=your_soundcloud_client_secret
    """
    keys = {}
    env_file = Path(".env")

    if env_file.exists():
        for line in env_file.read_text().strip().split('\n'):
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                name, value = line.split('=', 1)
                keys[name.strip()] = value.strip()

    # Environment variables override file
    for key_name in ['API_KEY', 'SOUNDCLOUD_CLIENT_ID', 'SOUNDCLOUD_CLIENT_SECRET']:
        env_val = os.environ.get(key_name)
        if env_val:
            keys[key_name] = env_val

    return keys


def get_api_key():
    """Get RadioCult API key."""
    keys = load_api_keys()
    if 'API_KEY' in keys:
        return keys['API_KEY']

    print("Error: No API key found. Create .env file with API_KEY or set API_KEY env var.")
    sys.exit(1)


def normalize_to_slug(name):
    """Normalize name to URL slug, matching generate-artist-pages.sh behavior."""
    if not name:
        return ""
    # Normalize unicode and remove accents
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric with hyphens (like tr -cs 'a-zA-Z0-9' '-')
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Remove leading/trailing hyphens and collapse multiple hyphens
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def generate_slug(title, date_str):
    """Generate URL slug from title and date."""
    # Normalize title
    slug = normalize_text(title)
    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Trim hyphens
    slug = slug.strip('-')
    # Add date
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            slug = f"{slug}-{dt.strftime('%Y-%m-%d')}"
        except:
            pass
    return slug


def is_repeat_broadcast(title):
    """Check if show title indicates a repeat broadcast."""
    if not title:
        return False
    title_lower = title.lower()
    patterns = [
        'éist arís',
        'eist aris',
        'rebroadcast',
        'replay',
        'repeat',
        'from the archives'
    ]
    return any(p in title_lower for p in patterns)


# Archive start date - exclude shows before this date
ARCHIVE_START_DATE = '2025-02-01'

# Test broadcast titles to exclude
TEST_BROADCAST_TITLES = [
    'box test',
    'box test 2',
    'playlisting test',
    'mensajito_eist_test',
    'mystery test broadcast',
    'stay tuned...',
]


def should_exclude_show(show):
    """
    Check if a show should be excluded from the archive.

    Excludes:
    - Shows before ARCHIVE_START_DATE (Feb 1, 2025)
    - Test broadcasts
    - Repeat broadcasts (éist arís, etc.)
    """
    title = show.get('title', '')

    # Check for repeat broadcasts
    if is_repeat_broadcast(title):
        return True

    # Check for test broadcasts
    if title.lower() in TEST_BROADCAST_TITLES:
        return True

    # Check date cutoff
    start = show.get('start', '')
    if start:
        show_date = start[:10]  # Extract YYYY-MM-DD
        if show_date < ARCHIVE_START_DATE:
            return True

    return False


def fetch_radiocult_schedule(api_key, start_date, end_date):
    """Fetch schedule from RadioCult API."""
    url = f"{RADIOCULT_BASE_URL}/schedule"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    params = {
        "startDate": start_date.isoformat() + "Z",
        "endDate": end_date.isoformat() + "Z"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching RadioCult schedule: {e}")
        return None


def fetch_radiocult_artists(api_key):
    """Fetch all artists from RadioCult API."""
    url = f"{RADIOCULT_BASE_URL}/artists"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return {a['id']: a for a in data.get('artists', [])}
    except requests.RequestException as e:
        print(f"Error fetching RadioCult artists: {e}")
        return {}


def fetch_mixcloud_cloudcasts_incremental(existing_cache=None, fetch_descriptions=True):
    """
    Fetch cloudcasts from eistcork Mixcloud account incrementally.

    Only fetches new items that aren't already in the cache.
    Stops fetching as soon as we encounter a known item (since API returns newest first).

    Args:
        existing_cache: List of existing cached cloudcasts (newest first)
        fetch_descriptions: Whether to fetch descriptions for new items

    Returns:
        Tuple of (merged_cloudcasts, new_count) where merged_cloudcasts is the
        complete list with new items prepended, and new_count is how many were new.
    """
    # Build set of known slugs for O(1) lookup
    known_slugs = set()
    if existing_cache:
        known_slugs = {cc.get('slug') for cc in existing_cache if cc.get('slug')}
        print(f"  Loaded {len(known_slugs)} known Mixcloud slugs from cache")

    new_cloudcasts = []
    url = f"{MIXCLOUD_BASE_URL}/{MIXCLOUD_USER}/cloudcasts/"
    found_known = False
    pages_fetched = 0

    while url and not found_known:
        try:
            time.sleep(REQUEST_DELAY)
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            pages_fetched += 1

            items_this_page = data.get('data', [])
            new_this_page = 0

            for item in items_this_page:
                slug = item.get('slug')

                # Check if we've seen this item before
                if slug in known_slugs:
                    # Found known content - stop fetching
                    found_known = True
                    print(f"  Reached known content at slug: {slug[:50]}...")
                    break

                # New item - add to list
                new_cloudcasts.append({
                    'slug': slug,
                    'name': item.get('name'),
                    'url': item.get('url'),
                    'created_time': item.get('created_time'),
                    'pictures': item.get('pictures', {}),
                    'audio_length': item.get('audio_length'),
                    'description': ''  # Will be fetched separately
                })
                new_this_page += 1

            if found_known:
                break

            print(f"  Page {pages_fetched}: {new_this_page} new items")

            # Get next page
            paging = data.get('paging', {})
            url = paging.get('next')

            # Safety limit - if we've fetched 50 pages without finding known content,
            # something is wrong (or this is effectively a full refresh)
            if pages_fetched >= 50:
                print("  Warning: Fetched 50 pages without finding known content")
                print("  Consider running with --full for a complete refresh")
                break

        except requests.RequestException as e:
            print(f"Error fetching Mixcloud cloudcasts: {e}")
            break

    print(f"  Fetched {len(new_cloudcasts)} new Mixcloud cloudcasts ({pages_fetched} API calls)")

    # Fetch descriptions only for NEW items
    if fetch_descriptions and new_cloudcasts:
        print(f"  Fetching descriptions for {len(new_cloudcasts)} new items...")
        for i, cc in enumerate(new_cloudcasts):
            if (i + 1) % 10 == 0:
                print(f"    Progress: {i + 1}/{len(new_cloudcasts)}")
            try:
                time.sleep(REQUEST_DELAY)
                detail_url = f"{MIXCLOUD_BASE_URL}/{MIXCLOUD_USER}/{cc['slug']}/"
                response = requests.get(detail_url, timeout=30)
                response.raise_for_status()
                detail = response.json()
                cc['description'] = detail.get('description', '')
            except requests.RequestException:
                pass  # Keep empty description on error

        with_desc = sum(1 for cc in new_cloudcasts if cc.get('description'))
        print(f"    New cloudcasts with descriptions: {with_desc}/{len(new_cloudcasts)}")

    # Merge: new items first (they're newest), then existing cache
    if existing_cache:
        merged = new_cloudcasts + existing_cache
    else:
        merged = new_cloudcasts

    return merged, len(new_cloudcasts)


def fetch_mixcloud_cloudcasts_full(fetch_descriptions=True):
    """
    Fetch ALL cloudcasts from eistcork Mixcloud account (full refresh).

    Use this for initial setup or when cache might be corrupted.
    """
    cloudcasts = []
    url = f"{MIXCLOUD_BASE_URL}/{MIXCLOUD_USER}/cloudcasts/"
    pages_fetched = 0

    while url:
        try:
            time.sleep(REQUEST_DELAY)
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            pages_fetched += 1

            for item in data.get('data', []):
                cloudcasts.append({
                    'slug': item.get('slug'),
                    'name': item.get('name'),
                    'url': item.get('url'),
                    'created_time': item.get('created_time'),
                    'pictures': item.get('pictures', {}),
                    'audio_length': item.get('audio_length'),
                    'description': ''  # Will be fetched separately
                })

            if pages_fetched % 5 == 0:
                print(f"  Page {pages_fetched}: {len(cloudcasts)} items so far...")

            # Get next page
            paging = data.get('paging', {})
            url = paging.get('next')

        except requests.RequestException as e:
            print(f"Error fetching Mixcloud cloudcasts: {e}")
            break

    print(f"  Fetched {len(cloudcasts)} Mixcloud cloudcasts ({pages_fetched} API calls)")

    # Fetch descriptions for each cloudcast (requires individual API calls)
    if fetch_descriptions:
        print(f"  Fetching descriptions for {len(cloudcasts)} cloudcasts...")
        for i, cc in enumerate(cloudcasts):
            if (i + 1) % 50 == 0:
                print(f"    Progress: {i + 1}/{len(cloudcasts)}")
            try:
                time.sleep(REQUEST_DELAY)
                detail_url = f"{MIXCLOUD_BASE_URL}/{MIXCLOUD_USER}/{cc['slug']}/"
                response = requests.get(detail_url, timeout=30)
                response.raise_for_status()
                detail = response.json()
                cc['description'] = detail.get('description', '')
            except requests.RequestException:
                pass  # Keep empty description on error

        with_desc = sum(1 for cc in cloudcasts if cc.get('description'))
        print(f"    Cloudcasts with descriptions: {with_desc}/{len(cloudcasts)}")

    return cloudcasts


def fetch_soundcloud_tracks_incremental(existing_cache=None):
    """
    Fetch SoundCloud tracks incrementally using the official API.

    Uses OAuth 2.0 Client Credentials flow with cursor-based pagination.
    Stops when we encounter a track ID that's already in the cache.

    Args:
        existing_cache: List of existing cached tracks (newest first)

    Returns:
        Tuple of (merged_tracks, new_count) where merged_tracks is the
        complete list with new items prepended, and new_count is how many were new.
    """
    if existing_cache:
        print(f"  Loaded {len(existing_cache)} known SoundCloud tracks from cache")

    try:
        merged, new_count = fetch_soundcloud_tracks_api_incremental(
            username=SOUNDCLOUD_USER,
            existing_cache=existing_cache
        )

        if new_count > 0:
            print(f"  Found {new_count} new tracks via SoundCloud API")
        else:
            print("  No new tracks found")

        return merged, new_count

    except SoundCloudAuthError as e:
        print(f"  Authentication error: {e}")
        return existing_cache or [], 0
    except SoundCloudAPIError as e:
        print(f"  API error: {e}")
        return existing_cache or [], 0
    except Exception as e:
        print(f"  Unexpected error: {e}")
        return existing_cache or [], 0


def fetch_soundcloud_tracks_full():
    """
    Fetch ALL SoundCloud tracks (full refresh) using the official API.

    Uses OAuth 2.0 Client Credentials flow with cursor-based pagination.
    Fetches all tracks in a single pass.

    Returns:
        List of all tracks with full metadata.
    """
    print("  Fetching all SoundCloud tracks via API (full refresh)...")

    try:
        tracks = fetch_soundcloud_tracks_api(username=SOUNDCLOUD_USER)
        print(f"  Fetched {len(tracks)} SoundCloud tracks via API")
        return tracks

    except SoundCloudAuthError as e:
        print(f"  Authentication error: {e}")
        return []
    except SoundCloudAPIError as e:
        print(f"  API error: {e}")
        return []
    except Exception as e:
        print(f"  Unexpected error: {e}")
        return []


def generate_artist_slug(name):
    """Generate URL-friendly slug from artist name."""
    if not name:
        return ""
    # Normalize unicode
    slug = unicodedata.normalize('NFKD', name)
    # Remove accents
    slug = ''.join(c for c in slug if not unicodedata.combining(c))
    # Lowercase
    slug = slug.lower()
    # Replace special characters with hyphen
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    return slug


def extract_episode_info(archive_title, show_title):
    """
    Extract episode number/info from archive title.

    Patterns matched:
    - #9, #10, #1 - hashtag followed by number
    - ep7, ep.5, ep3, EP 7 - "ep" with optional dot/space followed by number
    - Episode 7, episode 10 - word "Episode" followed by number
    - vol.1, vol 2 - volume numbers
    - Show Name 8 - standalone number after show title (if show title doesn't already have a number)

    Returns the episode suffix to append (e.g., "#9", "Ep. 7") or None if not found.
    """
    if not archive_title:
        return None

    # Skip if RadioCult title already has an episode indicator
    if show_title:
        show_lower = show_title.lower()
        # Check for existing episode patterns in RadioCult title
        if re.search(r'#\d+', show_title):
            return None
        if re.search(r'\bep\.?\s*\d+', show_lower):
            return None
        if re.search(r'\bepisode\s+\d+', show_lower):
            return None
        if re.search(r'\bvol\.?\s*\d+', show_lower):
            return None

    # Normalize for matching
    title_lower = archive_title.lower()

    # Pattern 1: #N or # N (hashtag episode)
    match = re.search(r'#\s*(\d+)', archive_title)
    if match:
        return f"#{match.group(1)}"

    # Pattern 2: ep/EP followed by number (ep7, ep.5, ep 3, EP7)
    match = re.search(r'\bep\.?\s*(\d+)', title_lower)
    if match:
        return f"Ep. {match.group(1)}"

    # Pattern 3: "Episode N"
    match = re.search(r'\bepisode\s+(\d+)', title_lower)
    if match:
        return f"Ep. {match.group(1)}"

    # Pattern 4: vol/volume followed by number
    match = re.search(r'\bvol\.?\s*(\d+)', title_lower)
    if match:
        return f"Vol. {match.group(1)}"

    # Pattern 5: Show title followed by standalone number
    # Only if the RadioCult title doesn't already end with a number
    if show_title and not re.search(r'\d+\s*$', show_title):
        # Look for the show title in the archive title, then a number after it
        show_title_normalized = normalize_text(show_title)
        archive_normalized = normalize_text(archive_title)

        if show_title_normalized in archive_normalized:
            # Find position after show title and look for a number
            idx = archive_normalized.find(show_title_normalized)
            after_title = archive_normalized[idx + len(show_title_normalized):]
            # Look for a standalone number (not part of a date)
            # Exclude: digits followed by ordinal suffixes (st/nd/rd/th) which indicate dates
            # Also exclude numbers followed by date separators (/, -, .)
            match = re.search(r'^\s*(\d{1,2})(?!\d|/|-|\.|st|nd|rd|th)', after_title)
            if match:
                return f"#{match.group(1)}"

    return None


def normalize_title(title):
    """
    Normalize show titles to fix common typos and inconsistencies.

    Fixes:
    - "éist arís" typo variants (ésit, éís, éis, éíst, etc.)
    """
    if not title:
        return title

    # Fix "éist arís" typo variants
    # Pattern matches various misspellings in parentheses
    typo_patterns = [
        (r'\(ésit arís\)', '(éist arís)'),      # ésit -> éist
        (r'\(éís arís\)', '(éist arís)'),       # éís -> éist
        (r'\(éis arís\)', '(éist arís)'),       # éis -> éist
        (r'\(éíst arís\)', '(éist arís)'),      # éíst -> éist
        (r'\(eíst arís\)', '(éist arís)'),      # eíst -> éist (accent on wrong letter)
        (r'\(eist arís\)', '(éist arís)'),      # eist -> éist (missing fada)
        (r'\(éist aris\)', '(éist arís)'),      # aris -> arís (missing fada)
        (r'\(éist áris\)', '(éist arís)'),      # áris -> arís (accent on wrong letter)
        (r'\(eist aris\)', '(éist arís)'),      # both missing fadas
    ]

    for pattern, replacement in typo_patterns:
        title = re.sub(pattern, replacement, title, flags=re.IGNORECASE)

    return title


def build_show_output(shows, show_matches, artists):
    """Build final show output with archive matches."""
    output = []
    matched_count = 0

    # Build artist lookup
    artist_names = {aid: a.get('name', '') for aid, a in artists.items()}

    for show in shows:
        if should_exclude_show(show):
            continue

        show_id = show.get('id')
        slug = generate_slug(show.get('title', ''), show.get('start', ''))

        # Get first artist name and slug
        artist_ids = show.get('artistIds', [])
        artist_name = ""
        artist_slug = ""
        if artist_ids and artist_ids[0] in artist_names:
            artist_name = artist_names[artist_ids[0]]
            artist_slug = generate_artist_slug(artist_name)

        show_data = {
            'id': show_id,
            'title': normalize_title(show.get('title')),
            'slug': slug,
            'start': show.get('start'),
            'end': show.get('end'),
            'artistIds': artist_ids,
            'artistName': artist_name,
            'artistSlug': artist_slug,
            'description': show.get('description'),
            'mixcloud_match': None,
            'soundcloud_match': None,
            'match_score': 0
        }

        # Add matches if found
        episode_info = None
        if show_id in show_matches:
            matches = show_matches[show_id]
            if matches.get('mixcloud'):
                show_data['mixcloud_match'] = matches['mixcloud']
                show_data['match_score'] = max(show_data['match_score'], matches['mixcloud'].get('score', 0))
                # Try to extract episode info from Mixcloud title
                if not episode_info:
                    episode_info = extract_episode_info(matches['mixcloud'].get('name', ''), show.get('title', ''))
            if matches.get('soundcloud'):
                show_data['soundcloud_match'] = matches['soundcloud']
                show_data['match_score'] = max(show_data['match_score'], matches['soundcloud'].get('score', 0))
                # Try to extract episode info from SoundCloud title if not found yet
                if not episode_info:
                    episode_info = extract_episode_info(matches['soundcloud'].get('title', ''), show.get('title', ''))
            matched_count += 1

        # Store episode info if found
        show_data['episode_info'] = episode_info

        output.append(show_data)

    return output, matched_count


def load_cache_meta():
    """Load cache metadata."""
    if CACHE_META_FILE.exists():
        return json.loads(CACHE_META_FILE.read_text())
    return {}


def save_cache_meta(meta):
    """Save cache metadata."""
    CACHE_META_FILE.write_text(json.dumps(meta, indent=2))


def fetch_radiocult_data(api_key, full_refresh, existing_shows):
    """
    Fetch all RadioCult data: artists, past schedule, and upcoming schedule.

    Returns:
        Tuple of (artists, all_shows, upcoming_schedule_raw)
    """
    # Fetch artists
    print("[RadioCult] Fetching artists...")
    artists = fetch_radiocult_artists(api_key)
    print(f"[RadioCult] Fetched {len(artists)} artists")

    # Fetch schedule
    print("[RadioCult] Fetching schedule...")
    now = datetime.now()
    current_month_start = datetime(now.year, now.month, 1)

    if full_refresh or not existing_shows:
        print("[RadioCult]   Full refresh - fetching all months...")
        start_date = datetime(2025, 1, 1)
        end_date = now + timedelta(days=1)

        all_shows = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=31), end_date)
            time.sleep(REQUEST_DELAY)
            schedule = fetch_radiocult_schedule(api_key, current_start, current_end)

            if schedule and 'schedules' in schedule:
                shows = schedule['schedules']
                now_iso = now.isoformat()
                past_shows = [s for s in shows if s.get('end', '') < now_iso]
                all_shows.extend(past_shows)

            current_start = current_end

        print(f"[RadioCult]   Fetched {len(all_shows)} past shows")
    else:
        fetch_start = current_month_start - timedelta(days=7)

        cached_shows_before_current = []
        for show_data in existing_shows.values():
            show_start = show_data.get('start', '')
            if show_start and show_start < fetch_start.isoformat():
                cached_shows_before_current.append({
                    'id': show_data.get('id'),
                    'title': show_data.get('title'),
                    'start': show_data.get('start'),
                    'end': show_data.get('end'),
                    'artistIds': show_data.get('artistIds', []),
                    'description': show_data.get('description'),
                })

        print(f"[RadioCult]   Using {len(cached_shows_before_current)} cached shows")

        end_date = now + timedelta(days=1)
        time.sleep(REQUEST_DELAY)
        schedule = fetch_radiocult_schedule(api_key, fetch_start, end_date)

        current_month_shows = []
        if schedule and 'schedules' in schedule:
            shows = schedule['schedules']
            now_iso = now.isoformat()
            current_month_shows = [s for s in shows if s.get('end', '') < now_iso]

        print(f"[RadioCult]   Fetched {len(current_month_shows)} from current month")

        all_shows = cached_shows_before_current + current_month_shows

    # Fetch upcoming schedule
    print("[RadioCult] Fetching upcoming schedule...")
    upcoming_start = now
    upcoming_end = now + timedelta(days=30)
    time.sleep(REQUEST_DELAY)
    upcoming_schedule = fetch_radiocult_schedule(api_key, upcoming_start, upcoming_end)

    return artists, all_shows, upcoming_schedule


def fetch_mixcloud_data(full_refresh):
    """
    Fetch Mixcloud archives (incremental or full).

    Returns:
        Tuple of (mixcloud_cache, new_count)
    """
    print("[Mixcloud] Loading archives...")
    mixcloud_cache = []
    new_count = 0

    if full_refresh:
        print("[Mixcloud]   Full refresh requested...")
        mixcloud_cache = fetch_mixcloud_cloudcasts_full()
        new_count = len(mixcloud_cache)
        MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
    elif MIXCLOUD_CACHE_FILE.exists():
        try:
            existing_cache = json.loads(MIXCLOUD_CACHE_FILE.read_text())
            print(f"[Mixcloud]   Loaded {len(existing_cache)} cached cloudcasts")
            mixcloud_cache, new_count = fetch_mixcloud_cloudcasts_incremental(existing_cache)
            if new_count > 0:
                MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
                print(f"[Mixcloud]   Updated cache with {new_count} new items")
            else:
                print("[Mixcloud]   Cache is up to date")
        except Exception as e:
            print(f"[Mixcloud]   Error loading cache: {e}")
            mixcloud_cache = fetch_mixcloud_cloudcasts_full()
            new_count = len(mixcloud_cache)
            MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
    else:
        print("[Mixcloud]   No cache found - fetching all...")
        mixcloud_cache = fetch_mixcloud_cloudcasts_full()
        new_count = len(mixcloud_cache)
        MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))

    return mixcloud_cache, new_count


def fetch_soundcloud_data(full_refresh):
    """
    Fetch SoundCloud archives (incremental or full).

    Returns:
        Tuple of (soundcloud_cache, new_count)
    """
    print("[SoundCloud] Loading archives...")
    soundcloud_cache = []
    new_count = 0

    if full_refresh:
        print("[SoundCloud]   Full refresh requested...")
        soundcloud_cache = fetch_soundcloud_tracks_full()
        new_count = len(soundcloud_cache)
        if soundcloud_cache:
            SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
    elif SOUNDCLOUD_CACHE_FILE.exists():
        try:
            existing_cache = json.loads(SOUNDCLOUD_CACHE_FILE.read_text())
            print(f"[SoundCloud]   Loaded {len(existing_cache)} cached tracks")
            soundcloud_cache, new_count = fetch_soundcloud_tracks_incremental(existing_cache)
            if new_count > 0:
                SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
                print(f"[SoundCloud]   Updated cache with {new_count} new items")
            else:
                print("[SoundCloud]   Cache is up to date")
        except Exception as e:
            print(f"[SoundCloud]   Error loading cache: {e}")
            soundcloud_cache = fetch_soundcloud_tracks_full()
            new_count = len(soundcloud_cache)
            if soundcloud_cache:
                SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
    else:
        print("[SoundCloud]   No cache found - fetching all...")
        soundcloud_cache = fetch_soundcloud_tracks_full()
        new_count = len(soundcloud_cache)
        if soundcloud_cache:
            SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))

    return soundcloud_cache, new_count


def main():
    # Parse arguments
    full_refresh = '--full' in sys.argv

    print("=" * 60)
    print("éist Radio Show Cache Generator")
    print("=" * 60)

    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True)

    # Get API key
    api_key = get_api_key()

    # Load existing cache
    existing_shows = {}
    if SHOWS_FILE.exists() and not full_refresh:
        try:
            existing_shows = {s['id']: s for s in json.loads(SHOWS_FILE.read_text())}
            print(f"Loaded {len(existing_shows)} existing cached shows")
        except:
            pass

    # Fetch all data sources in parallel
    print("\nFetching data from all sources in parallel...")
    artists = {}
    all_shows = []
    upcoming_schedule = None
    mixcloud_cache = []
    new_mixcloud_count = 0
    soundcloud_cache = []
    new_soundcloud_count = 0

    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all fetch tasks
        futures = {
            executor.submit(fetch_radiocult_data, api_key, full_refresh, existing_shows): 'radiocult',
            executor.submit(fetch_mixcloud_data, full_refresh): 'mixcloud',
            executor.submit(fetch_soundcloud_data, full_refresh): 'soundcloud',
        }

        # Collect results as they complete
        for future in as_completed(futures):
            source = futures[future]
            try:
                if source == 'radiocult':
                    artists, all_shows, upcoming_schedule = future.result()
                elif source == 'mixcloud':
                    mixcloud_cache, new_mixcloud_count = future.result()
                elif source == 'soundcloud':
                    soundcloud_cache, new_soundcloud_count = future.result()
            except Exception as e:
                print(f"Error fetching {source}: {e}")

    # Filter out excluded shows (repeats, tests, pre-archive-start-date)
    original_shows = [s for s in all_shows if not should_exclude_show(s)]
    print(f"\nAfter filtering: {len(original_shows)} original broadcasts")

    # Process upcoming schedule (needs artists data)
    now = datetime.now()
    if upcoming_schedule and 'schedules' in upcoming_schedule:
        future_shows = [s for s in upcoming_schedule['schedules'] if s.get('start', '') > now.isoformat()]

        upcoming_data = []
        for show in future_shows:
            artist_ids = show.get('artistIds', [])
            artist_name = None
            artist_slug = None

            if artist_ids:
                artist_id = artist_ids[0]
                artist_info = artists.get(artist_id, {})
                artist_name = artist_info.get('name')
                if artist_name:
                    artist_slug = normalize_to_slug(artist_name)

            upcoming_data.append({
                'id': show.get('id'),
                'title': show.get('title'),
                'start': show.get('start'),
                'end': show.get('end'),
                'artistIds': artist_ids,
                'artistName': artist_name,
                'artistSlug': artist_slug,
            })

        upcoming_data.sort(key=lambda x: x.get('start', ''))
        UPCOMING_SCHEDULE_FILE.write_text(json.dumps(upcoming_data, indent=2))
        print(f"Saved {len(upcoming_data)} upcoming shows")
    else:
        UPCOMING_SCHEDULE_FILE.write_text('[]')

    # Match archives to shows (FLIPPED DIRECTION)
    # Optimization: skip matching if no new archives were added
    if new_mixcloud_count == 0 and new_soundcloud_count == 0 and existing_shows:
        print("\nNo new archives - reusing existing matches...")
        # Build show_matches from existing cached data
        show_matches = {}
        for show_id, show_data in existing_shows.items():
            mc_match = show_data.get('mixcloud_match')
            sc_match = show_data.get('soundcloud_match')
            if mc_match or sc_match:
                show_matches[show_id] = {
                    'mixcloud': mc_match,
                    'soundcloud': sc_match
                }
        print(f"  Restored {len(show_matches)} existing matches")
        # Load existing review queue
        review_queue = []
        if REVIEW_QUEUE_FILE.exists():
            try:
                review_queue = json.loads(REVIEW_QUEUE_FILE.read_text())
            except:
                pass
    else:
        print("\nMatching archives to RadioCult shows...")
        show_matches, review_queue = match_archives_to_shows(
            original_shows, mixcloud_cache, soundcloud_cache, artists,
            should_exclude_fn=should_exclude_show
        )

    # Build final output
    all_show_data, matched_count = build_show_output(original_shows, show_matches, artists)

    # Sort by date (most recent first)
    all_show_data.sort(key=lambda x: x.get('start', ''), reverse=True)

    # Save shows cache
    SHOWS_FILE.write_text(json.dumps(all_show_data, indent=2))

    # Save review queue
    if review_queue:
        REVIEW_QUEUE_FILE.write_text(json.dumps(review_queue, indent=2))

    # Count stats
    mixcloud_count = sum(1 for s in all_show_data if s.get('mixcloud_match'))
    soundcloud_count = sum(1 for s in all_show_data if s.get('soundcloud_match'))
    both_count = sum(1 for s in all_show_data if s.get('mixcloud_match') and s.get('soundcloud_match'))

    # Save metadata
    meta = {
        'last_updated': datetime.now().isoformat(),
        'full_refresh': full_refresh,
        'total_shows': len(all_show_data),
        'shows_with_archives': matched_count,
        'mixcloud_matches': mixcloud_count,
        'soundcloud_matches': soundcloud_count,
        'both_platforms': both_count,
        'review_queue_size': len(review_queue),
        'new_mixcloud_this_run': new_mixcloud_count,
        'total_mixcloud_cached': len(mixcloud_cache)
    }
    save_cache_meta(meta)

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total shows processed: {len(all_show_data)}")
    print(f"Shows with archives:   {matched_count} ({matched_count*100//max(len(all_show_data),1)}%)")
    print(f"  - Mixcloud:          {mixcloud_count}")
    print(f"  - SoundCloud:        {soundcloud_count}")
    print(f"  - Both platforms:    {both_count}")
    print(f"New Mixcloud this run: {new_mixcloud_count}")
    print(f"Review queue:          {len(review_queue)}")
    print(f"\nOutput files:")
    print(f"  {SHOWS_FILE}")
    print(f"  {MIXCLOUD_CACHE_FILE}")
    print(f"  {SOUNDCLOUD_CACHE_FILE}")
    if review_queue:
        print(f"  {REVIEW_QUEUE_FILE}")
    print(f"  {CACHE_META_FILE}")
    print("=" * 60)


if __name__ == '__main__':
    main()
