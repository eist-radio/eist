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
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Try to import thefuzz for fuzzy matching, fall back to basic matching if not available
try:
    from thefuzz import fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    print("Warning: thefuzz not installed. Using basic string matching.")
    print("Install with: pip3 install thefuzz python-Levenshtein")

# Configuration
RADIOCULT_BASE_URL = "https://api.radiocult.fm/api/station/eist-radio"
MIXCLOUD_BASE_URL = "https://api.mixcloud.com"
MIXCLOUD_USER = "eistcork"
SOUNDCLOUD_USER = "eistcork"
SOUNDCLOUD_TRACKS_URL = f"https://soundcloud.com/{SOUNDCLOUD_USER}/tracks"
DATA_DIR = Path("data")
SHOWS_FILE = DATA_DIR / "shows.json"
MIXCLOUD_CACHE_FILE = DATA_DIR / "mixcloud-cache.json"
SOUNDCLOUD_CACHE_FILE = DATA_DIR / "soundcloud-cache.json"
CACHE_META_FILE = DATA_DIR / "cache-meta.json"
REVIEW_QUEUE_FILE = DATA_DIR / "review-queue.json"

# Matching thresholds
MATCH_THRESHOLD = 60  # Minimum score to accept a match
HIGH_CONFIDENCE_THRESHOLD = 80  # Score for high confidence matches

# Rate limiting
REQUEST_DELAY = 0.5  # Seconds between API requests


def get_api_key():
    """Read RadioCult API key from file."""
    key_file = Path("RADIOCULT_API_KEY")
    if key_file.exists():
        return key_file.read_text().strip()

    # Try environment variable
    key = os.environ.get("API_KEY") or os.environ.get("RADIOCULT_API_KEY")
    if key:
        return key

    print("Error: No API key found. Create RADIOCULT_API_KEY file or set API_KEY env var.")
    sys.exit(1)


def normalize_text(text):
    """Normalize text for comparison: lowercase, remove accents, simplify."""
    if not text:
        return ""
    # Normalize unicode
    text = unicodedata.normalize('NFKD', text)
    # Remove accents
    text = ''.join(c for c in text if not unicodedata.combining(c))
    # Lowercase
    text = text.lower()
    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    # Collapse whitespace
    text = ' '.join(text.split())
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


def extract_date_from_title(title):
    """Extract broadcast date from Mixcloud title.

    Handles various formats:
    - DD/MM/YY or DD/MM/YYYY (e.g., '30/11/25', '30/11/2025')
    - MM/DD/YYYY (US format, e.g., '11/30/2025')
    - YYYYMMDD (e.g., '20251018')
    - DDMMYYYY (e.g., '28112025')
    - Month DD[st/nd/rd/th] YY (e.g., 'OCT 22ND 25')
    - Nov'25, November 2025
    """
    if not title:
        return None

    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    current_year = datetime.now().year

    def fix_year_typo(year):
        """Fix common year typos (e.g., 2028 -> 2025)."""
        # If year is in the future beyond next year, assume typo
        if year > current_year + 1:
            # Common typo: wrong last digit (28 instead of 25)
            return current_year
        return year

    # Pattern 1: YYYY-MM-DD (ISO format) - check FIRST before DD/MM/YY
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', title)
    if match:
        year, month, day = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 2: DD/MM/YY or DD/MM/YYYY or DD-MM-YY or DD.MM.YYYY (but NOT YYYY-MM-DD which was handled above)
    match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', title)
    if match:
        a, b, year = match.groups()
        if len(year) == 2:
            year = '20' + year
        year = fix_year_typo(int(year))
        a, b = int(a), int(b)
        # Try DD/MM/YYYY first (European)
        try:
            return datetime(year, b, a)
        except ValueError:
            pass
        # Try MM/DD/YYYY (US)
        try:
            return datetime(year, a, b)
        except ValueError:
            pass

    # Pattern 3: YYMMDD (e.g., '251018' for 2025-10-18) - 6 digits starting with 2
    match = re.search(r'(?<!\d)(2[0-9])(\d{2})(\d{2})(?!\d)', title)
    if match:
        year, month, day = match.groups()
        year = int('20' + year)
        year = fix_year_typo(year)
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 4: YYYYMMDD (e.g., '20251018')
    match = re.search(r'(\d{4})(\d{2})(\d{2})', title)
    if match:
        year, month, day = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 5: DDMMYYYY (no separators, e.g., '28112025')
    match = re.search(r'(\d{2})(\d{2})(\d{4})', title)
    if match:
        day, month, year = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 6: DDMMYY (6 digits ending in 25, e.g., '140925' for 14-09-25)
    match = re.search(r'(?<!\d)(\d{2})(\d{2})(2[0-9])(?!\d)', title)
    if match:
        day, month, year = match.groups()
        year = int('20' + year)
        year = fix_year_typo(year)
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 7: DD MM YYYY with spaces (e.g., '06 11 2025')
    match = re.search(r'(?<!\d)(\d{2})\s+(\d{2})\s+(\d{4})(?!\d)', title)
    if match:
        day, month, year = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 8: Month DD[st/nd/rd/th] YY (e.g., 'OCT 22ND 25', 'Nov 5th 2025')
    match = re.search(r'([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{2,4})', title, re.I)
    if match:
        month_str, day, year = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            if len(year) == 2:
                year = '20' + year
            year = fix_year_typo(int(year))
            try:
                return datetime(year, months[month_key], int(day))
            except ValueError:
                pass

    # Pattern 9: DD Month (no year) - e.g., '22 March' - assumes current year
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3,9})(?!\s*\d)', title)
    if match:
        day, month_str = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            try:
                return datetime(current_year, months[month_key], int(day))
            except ValueError:
                pass

    # Pattern 10: Month abbreviation + year only (Nov'25, Nov 25, November 2025)
    match = re.search(r"([A-Za-z]{3,9})[\s']*(\d{2,4})(?!\d)", title)
    if match:
        month_str, year = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            if len(year) == 2:
                year = '20' + year
            year = fix_year_typo(int(year))
            try:
                # Return first day of month for approximate matching
                return datetime(year, months[month_key], 1)
            except ValueError:
                pass

    return None


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
    Fetch SoundCloud tracks incrementally using yt-dlp hybrid approach.

    Uses a two-phase approach:
    1. Fast scan with --flat-playlist to get list of track IDs (~4s for all)
    2. Stop when we find a known ID from cache
    3. Fetch full metadata only for new tracks (~1.8s each)

    Args:
        existing_cache: List of existing cached tracks (newest first)

    Returns:
        Tuple of (merged_tracks, new_count) where merged_tracks is the
        complete list with new items prepended, and new_count is how many were new.
    """
    # Build set of known IDs for O(1) lookup
    known_ids = set()
    if existing_cache:
        known_ids = {str(t.get('id')) for t in existing_cache if t.get('id')}
        print(f"  Loaded {len(known_ids)} known SoundCloud IDs from cache")

    # Phase 1: Fast scan to find new track IDs
    print("  Phase 1: Scanning for new tracks...")
    new_ids = []

    try:
        result = subprocess.run(
            ['yt-dlp', '--flat-playlist', '-j', SOUNDCLOUD_TRACKS_URL],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"  Error running yt-dlp: {result.stderr[:200]}")
            return existing_cache or [], 0

        # Parse each line of JSON output
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                item = json.loads(line)
                track_id = str(item.get('id', ''))

                if track_id in known_ids:
                    # Found known content - stop scanning
                    print(f"  Reached known content at ID: {track_id}")
                    break

                new_ids.append({
                    'id': track_id,
                    'url': item.get('url', '')
                })
            except json.JSONDecodeError:
                continue

    except subprocess.TimeoutExpired:
        print("  Error: yt-dlp scan timed out")
        return existing_cache or [], 0
    except FileNotFoundError:
        print("  Error: yt-dlp not installed. Install with: pip3 install yt-dlp")
        return existing_cache or [], 0

    print(f"  Found {len(new_ids)} new tracks")

    if not new_ids:
        return existing_cache or [], 0

    # Phase 2: Fetch full metadata for new tracks only
    print(f"  Phase 2: Fetching full metadata for {len(new_ids)} new tracks...")
    new_tracks = []

    for i, item in enumerate(new_ids):
        if (i + 1) % 5 == 0:
            print(f"    Progress: {i + 1}/{len(new_ids)}")

        try:
            result = subprocess.run(
                ['yt-dlp', '-j', '--no-download', item['url']],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                continue

            data = json.loads(result.stdout)

            new_tracks.append({
                'id': str(data.get('id', item['id'])),
                'title': data.get('title', ''),
                'url': data.get('webpage_url', item['url']),
                'upload_date': data.get('upload_date', ''),
                'timestamp': data.get('timestamp', 0),
                'duration': data.get('duration', 0),
                'thumbnail': data.get('thumbnail', ''),
                'description': data.get('description', '')
            })

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            continue

    print(f"  Fetched metadata for {len(new_tracks)} new tracks")

    # Merge: new items first (they're newest), then existing cache
    if existing_cache:
        merged = new_tracks + existing_cache
    else:
        merged = new_tracks

    return merged, len(new_tracks)


def fetch_soundcloud_tracks_full():
    """
    Fetch ALL SoundCloud tracks (full refresh).

    Uses yt-dlp without --flat-playlist to get complete metadata for all tracks.
    This is slower but gets everything in one pass.

    Returns:
        List of all tracks with full metadata.
    """
    print("  Fetching all SoundCloud tracks (full refresh)...")

    tracks = []

    try:
        result = subprocess.run(
            ['yt-dlp', '-j', '--no-download', SOUNDCLOUD_TRACKS_URL],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes for full fetch
        )

        if result.returncode != 0:
            print(f"  Error running yt-dlp: {result.stderr[:200]}")
            return tracks

        # Parse each line of JSON output
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)

                tracks.append({
                    'id': str(data.get('id', '')),
                    'title': data.get('title', ''),
                    'url': data.get('webpage_url', ''),
                    'upload_date': data.get('upload_date', ''),
                    'timestamp': data.get('timestamp', 0),
                    'duration': data.get('duration', 0),
                    'thumbnail': data.get('thumbnail', ''),
                    'description': data.get('description', '')
                })
            except json.JSONDecodeError:
                continue

        print(f"  Fetched {len(tracks)} SoundCloud tracks")

    except subprocess.TimeoutExpired:
        print("  Error: yt-dlp full fetch timed out")
    except FileNotFoundError:
        print("  Error: yt-dlp not installed. Install with: pip3 install yt-dlp")

    return tracks


def calculate_match_score(show, cloudcast, artist_name=None, artist_mc_username=None):
    """
    Calculate confidence score for a show-to-cloudcast match.

    Scoring:
    - Host username match: +40 points
    - Artist name in cloudcast title: +25 points
    - Title similarity: +0-35 points (fuzzy match)
    - Exact date match: +25 points
    - Same month match: +10 points
    - Show title appears as substring: +15 points bonus
    """
    score = 0

    show_title = show.get('title', '')
    cloudcast_name = cloudcast.get('name', '')
    show_date = show.get('start', '')

    norm_show = normalize_text(show_title)
    norm_cloud = normalize_text(cloudcast_name)

    # Host username match (from MC-USERNAME tag)
    if artist_mc_username:
        # Check if the cloudcast URL contains the host username
        cloudcast_url = cloudcast.get('url', '').lower()
        if artist_mc_username.lower() in cloudcast_url:
            score += 40

    # Artist name appears in cloudcast title
    if artist_name:
        norm_artist = normalize_text(artist_name)
        if norm_artist and len(norm_artist) > 2 and norm_artist in norm_cloud:
            score += 25

    # Title similarity
    if HAS_FUZZ and show_title and cloudcast_name:
        # Use token set ratio for better matching with reordered words
        similarity = fuzz.token_set_ratio(norm_show, norm_cloud)
        # Scale to 0-35 points
        score += int(similarity * 0.35)

        # Bonus: if show title appears as a substring in cloudcast name
        if len(norm_show) > 3 and norm_show in norm_cloud:
            score += 15
    elif show_title and cloudcast_name:
        # Basic matching without fuzz
        if norm_show in norm_cloud or norm_cloud in norm_show:
            score += 25

    # Date match in Mixcloud title
    if show_date:
        try:
            show_dt = datetime.fromisoformat(show_date.replace('Z', '+00:00'))
            mc_date = extract_date_from_title(cloudcast_name)
            if mc_date:
                if mc_date.date() == show_dt.date():
                    # Exact date match
                    score += 25
                elif mc_date.year == show_dt.year and mc_date.month == show_dt.month:
                    # Same month (for "Nov'25" style dates)
                    score += 10
        except:
            pass

    return score


def match_archives_to_shows(shows, mixcloud_archives, soundcloud_archives, artists):
    """
    Match archives (Mixcloud + SoundCloud) to RadioCult shows.

    FLIPPED DIRECTION: Each archive finds its best matching show.
    This ensures 1:1 mapping - each archive can only match one show.
    Shows can have both Mixcloud AND SoundCloud matches.
    """
    # Build show lookup by date for faster matching
    shows_by_date = {}
    for show in shows:
        if should_exclude_show(show):
            continue
        start = show.get('start', '')
        if start:
            date_key = start[:10]  # YYYY-MM-DD
            if date_key not in shows_by_date:
                shows_by_date[date_key] = []
            shows_by_date[date_key].append(show)

    # Build artist lookup
    artist_names = {aid: a.get('name', '') for aid, a in artists.items()}
    artist_mc_usernames = {}
    for artist_id, artist in artists.items():
        for tag in artist.get('tags', []):
            if tag.startswith('MC-USERNAME_'):
                artist_mc_usernames[artist_id] = tag.replace('MC-USERNAME_', '').lower()
                break

    # Track which shows have been matched to archives
    show_matches = {}  # show_id -> {mixcloud: {...}, soundcloud: {...}}
    archive_review_queue = []

    def find_best_show_for_archive(archive_title, archive_date, archive_source):
        """Find the best matching RadioCult show for an archive."""
        best_show = None
        best_score = 0

        # Parse date from archive
        archive_dt = None
        if archive_date:
            try:
                if len(archive_date) == 8:  # YYYYMMDD
                    archive_dt = datetime.strptime(archive_date, '%Y%m%d')
                else:
                    archive_dt = datetime.fromisoformat(archive_date.replace('Z', '+00:00'))
            except:
                pass

        # Also try to extract date from title - THIS IS THE KEY SIGNAL
        title_date = extract_date_from_title(archive_title)
        title_date_is_specific = title_date and title_date.day != 1  # Not a month-only date

        # PRIORITY: If we have a specific date in the title, check for exact match first
        # This handles cases like "Aus der Ferne #8 (2025-10-19)" definitively
        if title_date_is_specific:
            norm_archive = normalize_text(archive_title)

            # Try both the extracted date AND the swapped day/month version
            # This handles DD/MM vs MM/DD ambiguity (e.g., 05/09 could be May 9 or Sep 5)
            dates_to_try = [title_date]
            if title_date.day <= 12 and title_date.month <= 12 and title_date.day != title_date.month:
                # Day and month are both valid as either, so try swapped version too
                try:
                    swapped = title_date.replace(day=title_date.month, month=title_date.day)
                    dates_to_try.append(swapped)
                except ValueError:
                    pass

            for try_date in dates_to_try:
                exact_date_key = try_date.strftime('%Y-%m-%d')
                exact_date_shows = shows_by_date.get(exact_date_key, [])

                for show in exact_date_shows:
                    show_title = show.get('title', '')
                    norm_show = normalize_text(show_title)

                    # Check if show title appears in archive title (e.g., "Aus der Ferne" in "John O'Callaghan - Aus der Ferne #8")
                    if len(norm_show) > 3 and norm_show in norm_archive:
                        # Definitive match: exact date + title match
                        # Return immediately with very high score
                        return show, 200

                    # Also check fuzzy match for edge cases
                    if HAS_FUZZ:
                        similarity = fuzz.token_set_ratio(norm_show, norm_archive)
                        if similarity >= 80:
                            return show, 200

        # Determine which dates to search for fallback matching
        search_dates = set()
        if archive_dt:
            # Search archive upload date and nearby days (uploads often delayed)
            # Extended to 45 days before (archives often uploaded weeks later)
            for delta in range(-45, 2):
                d = archive_dt + timedelta(days=delta)
                search_dates.add(d.strftime('%Y-%m-%d'))
        if title_date:
            # If it's a month-only date (day=1), search the entire month
            if title_date.day == 1:
                # Add all days of that month
                for day in range(1, 32):
                    try:
                        d = title_date.replace(day=day)
                        search_dates.add(d.strftime('%Y-%m-%d'))
                    except ValueError:
                        break  # Invalid day for this month
            else:
                search_dates.add(title_date.strftime('%Y-%m-%d'))

        # If no date info, search all shows (slower but necessary)
        if not search_dates:
            candidate_shows = [s for shows_list in shows_by_date.values() for s in shows_list]
        else:
            candidate_shows = []
            for date_key in search_dates:
                candidate_shows.extend(shows_by_date.get(date_key, []))

        for show in candidate_shows:
            # Get artist info
            artist_ids = show.get('artistIds', [])
            artist_name = None
            mc_username = None
            for aid in artist_ids:
                if aid in artist_names:
                    artist_name = artist_names[aid]
                if aid in artist_mc_usernames:
                    mc_username = artist_mc_usernames[aid]

            # Calculate score (reuse existing function but swap args conceptually)
            # We're scoring how well this show matches the archive
            score = 0
            show_title = show.get('title', '')
            show_date = show.get('start', '')

            norm_show = normalize_text(show_title)
            norm_archive = normalize_text(archive_title)

            # Artist name in archive title
            if artist_name:
                norm_artist = normalize_text(artist_name)
                if norm_artist and len(norm_artist) > 2 and norm_artist in norm_archive:
                    score += 25

            # Title similarity
            if HAS_FUZZ and show_title and archive_title:
                similarity = fuzz.token_set_ratio(norm_show, norm_archive)
                score += int(similarity * 0.35)

                # Bonus: show title appears in archive name (common for "Show Name Episode X" patterns)
                if len(norm_show) > 3 and norm_show in norm_archive:
                    score += 25

                # Extra bonus: exact title match (after normalization)
                if norm_show == norm_archive:
                    score += 15
            elif show_title and archive_title:
                if norm_show in norm_archive or norm_archive in norm_show:
                    score += 25

            # Date match - THIS IS THE PRIORITY SIGNAL
            # An exact date match combined with title similarity is a definitive match
            if show_date and title_date:
                try:
                    show_dt = datetime.fromisoformat(show_date.replace('Z', '+00:00'))
                    if title_date.date() == show_dt.date():
                        # Exact date match is very strong - boost significantly
                        score += 50
                    elif title_date.year == show_dt.year and title_date.month == show_dt.month:
                        # Same month is a moderate signal
                        score += 15
                except:
                    pass

            if score > best_score:
                best_score = score
                best_show = show

        return best_show, best_score

    # Match Mixcloud archives
    print(f"  Matching {len(mixcloud_archives)} Mixcloud archives...")
    mixcloud_matched = 0
    for archive in mixcloud_archives:
        title = archive.get('name', '')
        created = archive.get('created_time', '')

        show, score = find_best_show_for_archive(title, created, 'mixcloud')

        if show and score >= MATCH_THRESHOLD:
            show_id = show.get('id')
            if show_id not in show_matches:
                show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

            # Only overwrite existing match if new score is higher
            existing_match = show_matches[show_id].get('mixcloud')
            if existing_match is None or score > existing_match.get('score', 0):
                show_matches[show_id]['mixcloud'] = {
                    'slug': archive.get('slug'),
                    'name': title,
                    'url': archive.get('url'),
                    'pictures': archive.get('pictures', {}),
                    'description': archive.get('description', ''),
                    'score': score
                }
                mixcloud_matched += 1
        elif show and score > 0:
            archive_review_queue.append({
                'source': 'mixcloud',
                'archive_title': title,
                'candidate_show': show.get('title'),
                'candidate_date': show.get('start', '')[:10],
                'score': score
            })

    # Match SoundCloud archives
    print(f"  Matching {len(soundcloud_archives)} SoundCloud archives...")
    soundcloud_matched = 0
    for archive in soundcloud_archives:
        title = archive.get('title', '')
        upload_date = archive.get('upload_date', '')  # YYYYMMDD format

        show, score = find_best_show_for_archive(title, upload_date, 'soundcloud')

        if show and score >= MATCH_THRESHOLD:
            show_id = show.get('id')
            if show_id not in show_matches:
                show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

            # Only overwrite existing match if new score is higher
            existing_match = show_matches[show_id].get('soundcloud')
            if existing_match is None or score > existing_match.get('score', 0):
                show_matches[show_id]['soundcloud'] = {
                    'id': archive.get('id'),
                    'title': title,
                    'url': archive.get('url'),
                    'thumbnail': archive.get('thumbnail'),
                    'description': archive.get('description', ''),
                    'score': score
                }
                soundcloud_matched += 1
        elif show and score > 0:
            archive_review_queue.append({
                'source': 'soundcloud',
                'archive_title': title,
                'candidate_show': show.get('title') if show else None,
                'candidate_date': show.get('start', '')[:10] if show else None,
                'score': score
            })

    print(f"  Mixcloud matched: {mixcloud_matched}/{len(mixcloud_archives)}")
    print(f"  SoundCloud matched: {soundcloud_matched}/{len(soundcloud_archives)}")

    return show_matches, archive_review_queue


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
            match = re.search(r'^\s*(\d{1,2})(?!\d|/|-|\.)', after_title)
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

    # Fetch artists
    print("\nFetching artists from RadioCult...")
    artists = fetch_radiocult_artists(api_key)
    print(f"Fetched {len(artists)} artists")

    # Fetch schedule - incremental approach
    print("\nFetching schedule from RadioCult...")
    now = datetime.now()
    current_month_start = datetime(now.year, now.month, 1)

    if full_refresh or not existing_shows:
        # Full refresh: fetch everything from Jan 2025
        print("  Full refresh - fetching all months...")
        start_date = datetime(2025, 1, 1)
        end_date = now + timedelta(days=1)

        all_shows = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=31), end_date)
            print(f"  Fetching {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}...")

            time.sleep(REQUEST_DELAY)
            schedule = fetch_radiocult_schedule(api_key, current_start, current_end)

            if schedule and 'schedules' in schedule:
                shows = schedule['schedules']
                now_iso = now.isoformat()
                past_shows = [s for s in shows if s.get('end', '') < now_iso]
                all_shows.extend(past_shows)

            current_start = current_end

        print(f"  Fetched {len(all_shows)} past shows from RadioCult")
    else:
        # Incremental: use cached shows for old months, fetch current month + 7 day buffer
        # The 7 day buffer catches shows that may have been missed at month boundaries
        fetch_start = current_month_start - timedelta(days=7)

        # Extract raw show data from existing cache (before matching was applied)
        cached_shows_before_current = []
        for show_data in existing_shows.values():
            show_start = show_data.get('start', '')
            if show_start and show_start < fetch_start.isoformat():
                # Reconstruct raw show format from cached data
                cached_shows_before_current.append({
                    'id': show_data.get('id'),
                    'title': show_data.get('title'),
                    'start': show_data.get('start'),
                    'end': show_data.get('end'),
                    'artistIds': show_data.get('artistIds', []),
                    'description': show_data.get('description'),
                })

        print(f"  Using {len(cached_shows_before_current)} cached shows before {fetch_start.strftime('%Y-%m-%d')}")

        # Fetch from fetch_start (7 days before month start) to now
        end_date = now + timedelta(days=1)
        print(f"  Fetching {fetch_start.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")

        time.sleep(REQUEST_DELAY)
        schedule = fetch_radiocult_schedule(api_key, fetch_start, end_date)

        current_month_shows = []
        if schedule and 'schedules' in schedule:
            shows = schedule['schedules']
            now_iso = now.isoformat()
            current_month_shows = [s for s in shows if s.get('end', '') < now_iso]

        print(f"  Fetched {len(current_month_shows)} shows from current month")

        all_shows = cached_shows_before_current + current_month_shows
        print(f"  Total: {len(all_shows)} past shows")

    # Filter out excluded shows (repeats, tests, pre-archive-start-date)
    original_shows = [s for s in all_shows if not should_exclude_show(s)]
    print(f"After filtering excluded shows: {len(original_shows)} original broadcasts")

    # Fetch Mixcloud cloudcasts
    print("\nLoading Mixcloud archives...")
    mixcloud_cache = []
    new_mixcloud_count = 0

    if full_refresh:
        # Full refresh: fetch everything from scratch
        print("  Full refresh requested - fetching all Mixcloud cloudcasts...")
        mixcloud_cache = fetch_mixcloud_cloudcasts_full()
        new_mixcloud_count = len(mixcloud_cache)
        MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
    elif MIXCLOUD_CACHE_FILE.exists():
        # Incremental: load existing cache and fetch only new items
        try:
            existing_cache = json.loads(MIXCLOUD_CACHE_FILE.read_text())
            print(f"  Loaded {len(existing_cache)} cached Mixcloud cloudcasts")
            mixcloud_cache, new_mixcloud_count = fetch_mixcloud_cloudcasts_incremental(existing_cache)
            if new_mixcloud_count > 0:
                MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
                print(f"  Updated cache with {new_mixcloud_count} new items")
            else:
                print("  Cache is up to date")
        except Exception as e:
            print(f"  Error loading cache: {e}")
            print("  Falling back to full fetch...")
            mixcloud_cache = fetch_mixcloud_cloudcasts_full()
            new_mixcloud_count = len(mixcloud_cache)
            MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))
    else:
        # No cache exists - do full fetch
        print("  No cache found - fetching all Mixcloud cloudcasts...")
        mixcloud_cache = fetch_mixcloud_cloudcasts_full()
        new_mixcloud_count = len(mixcloud_cache)
        MIXCLOUD_CACHE_FILE.write_text(json.dumps(mixcloud_cache, indent=2))

    # Fetch SoundCloud tracks
    print("\nLoading SoundCloud archives...")
    soundcloud_cache = []
    new_soundcloud_count = 0

    if full_refresh:
        # Full refresh: fetch everything from scratch
        print("  Full refresh requested - fetching all SoundCloud tracks...")
        soundcloud_cache = fetch_soundcloud_tracks_full()
        new_soundcloud_count = len(soundcloud_cache)
        if soundcloud_cache:
            SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
    elif SOUNDCLOUD_CACHE_FILE.exists():
        # Incremental: load existing cache and fetch only new items
        try:
            existing_cache = json.loads(SOUNDCLOUD_CACHE_FILE.read_text())
            print(f"  Loaded {len(existing_cache)} cached SoundCloud tracks")
            soundcloud_cache, new_soundcloud_count = fetch_soundcloud_tracks_incremental(existing_cache)
            if new_soundcloud_count > 0:
                SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
                print(f"  Updated cache with {new_soundcloud_count} new items")
            else:
                print("  Cache is up to date")
        except Exception as e:
            print(f"  Error loading cache: {e}")
            print("  Falling back to full fetch...")
            soundcloud_cache = fetch_soundcloud_tracks_full()
            new_soundcloud_count = len(soundcloud_cache)
            if soundcloud_cache:
                SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))
    else:
        # No cache exists - do full fetch
        print("  No cache found - fetching all SoundCloud tracks...")
        soundcloud_cache = fetch_soundcloud_tracks_full()
        new_soundcloud_count = len(soundcloud_cache)
        if soundcloud_cache:
            SOUNDCLOUD_CACHE_FILE.write_text(json.dumps(soundcloud_cache, indent=2))

    # Match archives to shows (FLIPPED DIRECTION)
    print("\nMatching archives to RadioCult shows...")
    show_matches, review_queue = match_archives_to_shows(
        original_shows, mixcloud_cache, soundcloud_cache, artists
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
