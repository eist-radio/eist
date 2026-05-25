#!/usr/bin/env python3
"""
Generate show cache for éist radio website.

DEMO BRANCH: API-CALLS-ONLY
Shows are sourced directly from Mixcloud/SoundCloud APIs.
Artists are associated via explicit tags on RadioCult artist profiles:

  MC-USERNAME_X       — artist is credited as host on eistcork uploads;
                        their shows appear in X's own Mixcloud upload feed
  HOST-MC-PLAYLIST_P  — artist's shows are in Mixcloud playlist P
                        (on artist's own account if MC-USERNAME_ is set,
                        on eistcork account if MC-USERNAME_ is absent)
  SC-USERNAME_X       — artist has their own SoundCloud account X
  HOST-SC-PLAYLIST_P  — artist's shows are in SoundCloud playlist P on their account

No title parsing. No fuzzy matching. No heuristics.

RadioCult is used for:
- Artist metadata (name, image, bio, tags including username mappings)
- Upcoming schedule

Usage:
    python3 generate-show-cache.py [--full]
"""

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import requests

from soundcloud_api import (
    SoundCloudAuthError,
    SoundCloudAPIError,
    fetch_soundcloud_tracks_api,
    fetch_soundcloud_tracks_api_incremental,
    fetch_soundcloud_playlist,
)

# Configuration
RADIOCULT_BASE_URL = "https://api.radiocult.fm/api/station/eist-radio"
MIXCLOUD_GRAPHQL_URL = "https://app.mixcloud.com/graphql"
MIXCLOUD_USER = "eistcork"
DATA_DIR = Path("data")
SHOWS_FILE = DATA_DIR / "shows.json"
UPCOMING_SCHEDULE_FILE = DATA_DIR / "upcoming_schedule.json"
MC_ARTIST_CACHE_FILE = DATA_DIR / "mixcloud-artist-cache.json"
SC_ARTIST_CACHE_FILE = DATA_DIR / "soundcloud-artist-cache.json"
CACHE_META_FILE = DATA_DIR / "cache-meta.json"
API_SHOWS_CACHE_FILE = DATA_DIR / "api-shows-cache.json"

REQUEST_DELAY = 0.5

ARTIST_SLUG_OVERRIDES = {
    "CHɅCHØU": "chachou",
}

# Archive start date — exclude shows before this date
ARCHIVE_START_DATE = '2025-02-01'

TEST_BROADCAST_TITLES = [
    'box test',
    'box test 2',
    'playlisting test',
    'mensajito_eist_test',
    'mystery test broadcast',
    'stay tuned...',
]


def load_api_keys():
    """Load API keys from .env file or environment variables."""
    keys = {}
    env_file = Path(".env")

    if env_file.exists():
        for line in env_file.read_text().strip().split('\n'):
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                name, value = line.split('=', 1)
                keys[name.strip()] = value.strip()

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
    if name in ARTIST_SLUG_OVERRIDES:
        return ARTIST_SLUG_OVERRIDES[name]
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def generate_slug(title, date_str):
    """Generate URL slug from title and date."""
    slug = normalize_to_slug(title)
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            slug = f"{slug}-{dt.strftime('%Y-%m-%d')}"
        except Exception:
            pass
    return slug


def is_repeat_broadcast(title):
    """Check if show title indicates a repeat broadcast."""
    if not title:
        return False
    title_lower = title.lower()
    patterns = [
        'éist arís', 'eist aris', 'rebroadcast', 'replay', 'repeat', 'from the archives',
    ]
    return any(p in title_lower for p in patterns)


def should_exclude_show(show):
    """Check if a show should be excluded from the archive."""
    title = show.get('title', '')
    if is_repeat_broadcast(title):
        return True
    if title.lower() in TEST_BROADCAST_TITLES:
        return True
    start = show.get('start', '')
    if start and start[:10] < ARCHIVE_START_DATE:
        return True
    return False


# ---------------------------------------------------------------------------
# Tag index
# ---------------------------------------------------------------------------

def build_artist_tag_index(artists):
    """
    Build per-artist tag index from RadioCult artist data.

    Reads MC-USERNAME_, HOST-MC-PLAYLIST_, SC-USERNAME_, HOST-SC-PLAYLIST_ tags.
    Tags are stripped before matching (some have leading/trailing whitespace in RC).

    Returns:
        Dict of artist_id -> {mc_username, mc_playlist, sc_username, sc_playlist}
        Only includes artists that have at least one recognised tag.
    """
    index = {}
    for artist_id, artist in artists.items():
        tags = artist.get('tags', []) or []
        entry = {
            'mc_username': None,
            'mc_playlist': None,
            'sc_username': None,
            'sc_playlist': None,
        }
        for raw_tag in tags:
            tag = raw_tag.strip()
            if tag.startswith('MC-USERNAME_'):
                entry['mc_username'] = tag[len('MC-USERNAME_'):].lower()
            elif tag.startswith('HOST-MC-PLAYLIST_'):
                entry['mc_playlist'] = unquote(tag[len('HOST-MC-PLAYLIST_'):]).lower()
            elif tag.startswith('SC-USERNAME_'):
                entry['sc_username'] = tag[len('SC-USERNAME_'):].lower()
            elif tag.startswith('HOST-SC-PLAYLIST_'):
                entry['sc_playlist'] = unquote(tag[len('HOST-SC-PLAYLIST_'):]).lower()

        if any(entry.values()):
            index[artist_id] = entry

    return index


# ---------------------------------------------------------------------------
# Mixcloud GraphQL
# ---------------------------------------------------------------------------

def _get_mixcloud_graphql_headers():
    """Headers required for Mixcloud GraphQL API requests."""
    return {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://www.mixcloud.com',
        'Referer': 'https://www.mixcloud.com/',
    }


# Common cloudcast fields used in all Mixcloud GraphQL queries.
# owner.username is included so we can build the correct URL for self-uploaded shows.
_CLOUDCAST_FIELDS = """
  slug
  name
  description
  audioLength
  publishDate
  picture(width: 600, height: 600) { url }
  owner { username }
"""


def _parse_graphql_cloudcast(node):
    """
    Parse a cloudcast node from a GraphQL response into our standard format.

    Works for nodes returned by both the uploads feed and playlist items.
    """
    pictures = {}
    if (node.get('picture') or {}).get('url'):
        pic_url = node['picture']['url']
        pictures = {'medium': pic_url, 'large': pic_url, 'extra_large': pic_url}

    slug = node.get('slug', '')
    # Use the actual owner's username for the URL (may differ from MIXCLOUD_USER
    # when an artist uploads directly to their own account).
    owner = (node.get('owner') or {}).get('username', MIXCLOUD_USER)
    url = f"https://www.mixcloud.com/{owner}/{slug}/" if slug else ''

    return {
        'slug': slug,
        'name': node.get('name', ''),
        'url': url,
        'created_time': node.get('publishDate', ''),
        'pictures': pictures,
        'audio_length': node.get('audioLength', 0),
        'description': node.get('description', '') or '',
    }


def _mixcloud_post(payload):
    """Make a single Mixcloud GraphQL POST, raising on HTTP or GraphQL errors."""
    response = requests.post(
        MIXCLOUD_GRAPHQL_URL,
        json=payload,
        headers=_get_mixcloud_graphql_headers(),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if 'errors' in data:
        fatal = [e for e in data['errors'] if 'picture url' not in e.get('message', '').lower()]
        if fatal:
            raise requests.RequestException(f"GraphQL error: {fatal[0].get('message', 'Unknown')}")

    return data


def fetch_mixcloud_artist_playlist(account_username, playlist_slug):
    """
    Fetch all cloudcasts from a named Mixcloud playlist on an account.

    Mixcloud's GraphQL exposes playlists via:
      userLookup → playlists → [Playlist] → items → [PlaylistItem] → cloudcast

    We list all playlists for the account and find the one matching playlist_slug.

    Args:
        account_username: Mixcloud account that owns the playlist (artist or eistcork)
        playlist_slug: Playlist slug (lowercase, URL-decoded, e.g. 'aus-der-ferne')

    Returns:
        List of cloudcast dicts, or [] if not found / error.
    """
    query = """
    query UserPlaylists($lookup: UserLookup!, $first: Int!, $after: String) {
      userLookup(lookup: $lookup) {
        playlists(first: $first, after: $after) {
          edges {
            node {
              slug
              name
              items(first: 500) {
                edges {
                  node {
                    cloudcast {
                      """ + _CLOUDCAST_FIELDS + """
                    }
                  }
                }
                pageInfo { hasNextPage }
              }
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """

    playlists_cursor = None

    while True:
        try:
            time.sleep(REQUEST_DELAY)
            variables = {'lookup': {'username': account_username}, 'first': 20}
            if playlists_cursor:
                variables['after'] = playlists_cursor

            data = _mixcloud_post({'query': query, 'variables': variables})

            playlists_conn = (data.get('data', {}).get('userLookup') or {}).get('playlists', {})
            if not playlists_conn:
                print(f"[Mixcloud] User not found: {account_username}")
                return []

            for edge in playlists_conn.get('edges', []):
                node = edge.get('node') or {}
                if node.get('slug') == playlist_slug:
                    items_conn = node.get('items', {})
                    if items_conn.get('pageInfo', {}).get('hasNextPage'):
                        print(f"[Mixcloud] Warning: playlist '{playlist_slug}' has >500 items; "
                              f"only first 500 fetched")
                    cloudcasts = [
                        _parse_graphql_cloudcast(ie['node']['cloudcast'])
                        for ie in items_conn.get('edges', [])
                        if ie.get('node') and ie['node'].get('cloudcast')
                    ]
                    print(f"[Mixcloud] Playlist '{playlist_slug}' on {account_username}: "
                          f"{len(cloudcasts)} cloudcasts")
                    return cloudcasts

            if not playlists_conn.get('pageInfo', {}).get('hasNextPage'):
                print(f"[Mixcloud] Playlist '{playlist_slug}' not found on {account_username}")
                return []

            playlists_cursor = playlists_conn['pageInfo']['endCursor']

        except requests.RequestException as e:
            print(f"[Mixcloud] Error fetching playlists for {account_username}: {e}")
            return []


def _fetch_mixcloud_uploads_page(username, first=100, after=None):
    """
    Fetch one page of cloudcasts from a Mixcloud user's upload feed.

    Returns:
        Tuple of (cloudcasts, has_next_page, end_cursor)
    """
    query = """
    query UserUploads($lookup: UserLookup!, $first: Int!, $after: String) {
      userLookup(lookup: $lookup) {
        uploads(first: $first, after: $after) {
          edges {
            node {
              """ + _CLOUDCAST_FIELDS + """
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """
    variables = {'lookup': {'username': username}, 'first': first}
    if after:
        variables['after'] = after

    data = _mixcloud_post({'query': query, 'variables': variables})

    user_data = (data.get('data', {}).get('userLookup')) or {}
    uploads = user_data.get('uploads', {})
    edges = uploads.get('edges', [])
    page_info = uploads.get('pageInfo', {})

    cloudcasts = [_parse_graphql_cloudcast(e['node']) for e in edges if e.get('node')]
    return cloudcasts, page_info.get('hasNextPage', False), page_info.get('endCursor')


def fetch_mixcloud_artist_uploads(username, existing_cache=None, full_refresh=False):
    """
    Fetch cloudcasts from an artist's Mixcloud upload feed (incremental or full).

    The artist's feed contains all uploads credited to them, including eistcork-uploaded
    shows where the artist was set as host. Stops incremental fetch when a known slug
    is found (API returns newest first).

    Returns:
        Tuple of (cloudcasts, new_count)
    """
    known_slugs = set()
    if existing_cache and not full_refresh:
        known_slugs = {cc.get('slug') for cc in existing_cache if cc.get('slug')}

    new_cloudcasts = []
    cursor = None
    found_known = False
    pages_fetched = 0

    while not found_known:
        try:
            time.sleep(REQUEST_DELAY)
            cloudcasts, has_next_page, cursor = _fetch_mixcloud_uploads_page(
                username, first=100, after=cursor
            )
            pages_fetched += 1

            for cc in cloudcasts:
                slug = cc.get('slug')
                if slug and slug in known_slugs:
                    found_known = True
                    break
                new_cloudcasts.append(cc)

            if found_known or not has_next_page:
                break

            if pages_fetched >= 20:
                print(f"[Mixcloud] Warning: fetched 20 pages for '{username}' without hitting cache")
                break

        except requests.RequestException as e:
            print(f"[Mixcloud] Error fetching uploads for '{username}': {e}")
            break

    merged = new_cloudcasts + (existing_cache or [])
    return merged, len(new_cloudcasts)


def fetch_mixcloud_for_artist(mc_username, mc_playlist, existing_tracks, full_refresh):
    """
    Fetch Mixcloud cloudcasts for one artist using the correct strategy:

    - mc_username + mc_playlist: fetch playlist from artist's own MC account
    - mc_username only:          fetch all uploads from artist's MC account (incremental)
    - mc_playlist only:          fetch playlist from the eistcork account

    Returns:
        List of cloudcast dicts (new + existing merged for uploads; fresh for playlists)
    """
    if mc_playlist:
        account = mc_username if mc_username else MIXCLOUD_USER
        return fetch_mixcloud_artist_playlist(account, mc_playlist), 0

    if mc_username:
        merged, new_count = fetch_mixcloud_artist_uploads(mc_username, existing_tracks, full_refresh)
        return merged, new_count

    return [], 0


# ---------------------------------------------------------------------------
# SoundCloud per-artist fetch (with per-artist cache)
# ---------------------------------------------------------------------------

def load_sc_artist_cache():
    """Load per-artist SoundCloud cache. Returns {username: [tracks]}."""
    if SC_ARTIST_CACHE_FILE.exists():
        try:
            return json.loads(SC_ARTIST_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_sc_artist_cache(cache):
    SC_ARTIST_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def load_mc_artist_cache():
    """Load per-artist Mixcloud cache. Returns {username: [cloudcasts]}."""
    if MC_ARTIST_CACHE_FILE.exists():
        try:
            return json.loads(MC_ARTIST_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_mc_artist_cache(cache):
    MC_ARTIST_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def fetch_soundcloud_for_artist(username, playlist_slug, existing_tracks, full_refresh):
    """
    Fetch SoundCloud tracks for a single artist.

    If playlist_slug is set, fetches that playlist from the artist's account (fresh).
    Otherwise fetches all tracks from the artist's account (incremental when cached).

    Returns:
        List of track dicts in cache format.
    """
    if playlist_slug:
        print(f"[SoundCloud]   '{username}': fetching playlist '{playlist_slug}'...")
        try:
            time.sleep(REQUEST_DELAY)
            tracks = fetch_soundcloud_playlist(username, playlist_slug)
            print(f"[SoundCloud]   Got {len(tracks)} tracks from playlist")
            return tracks
        except (SoundCloudAuthError, SoundCloudAPIError) as e:
            print(f"[SoundCloud]   Playlist fetch failed: {e}")
            return existing_tracks or []

    if full_refresh or not existing_tracks:
        print(f"[SoundCloud]   '{username}': full fetch...")
        try:
            tracks = fetch_soundcloud_tracks_api(username)
            print(f"[SoundCloud]   Got {len(tracks)} tracks")
            return tracks
        except (SoundCloudAuthError, SoundCloudAPIError) as e:
            print(f"[SoundCloud]   Fetch failed: {e}")
            return []
    else:
        print(f"[SoundCloud]   '{username}': incremental ({len(existing_tracks)} cached)...")
        try:
            merged, new_count = fetch_soundcloud_tracks_api_incremental(username, existing_tracks)
            print(f"[SoundCloud]   {new_count} new tracks")
            return merged
        except (SoundCloudAuthError, SoundCloudAPIError) as e:
            print(f"[SoundCloud]   Fetch failed: {e}")
            return existing_tracks


# ---------------------------------------------------------------------------
# RadioCult
# ---------------------------------------------------------------------------

def fetch_radiocult_schedule(api_key, start_date, end_date):
    """Fetch schedule from RadioCult API."""
    url = f"{RADIOCULT_BASE_URL}/schedule"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    params = {
        "startDate": start_date.isoformat() + "Z",
        "endDate": end_date.isoformat() + "Z",
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching RadioCult schedule: {e}")
        return None


def fetch_radiocult_artists(api_key):
    """Fetch all artists from RadioCult API. Returns {artist_id: artist}."""
    url = f"{RADIOCULT_BASE_URL}/artists"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return {a['id']: a for a in data.get('artists', [])}
    except requests.RequestException as e:
        print(f"Error fetching RadioCult artists: {e}")
        return {}


def fetch_radiocult_artists_only(api_key):
    print("[RadioCult] Fetching artists...")
    artists = fetch_radiocult_artists(api_key)
    print(f"[RadioCult] Fetched {len(artists)} artists")
    return artists


def fetch_radiocult_upcoming_only(api_key):
    print("[RadioCult] Fetching upcoming schedule...")
    now = datetime.now()
    time.sleep(REQUEST_DELAY)
    return fetch_radiocult_schedule(api_key, now, now + timedelta(days=30))


# ---------------------------------------------------------------------------
# Show conversion
# ---------------------------------------------------------------------------

def convert_track_to_show(track, artist, platform='mixcloud'):
    """
    Convert an API track to show format.

    Args:
        track: Track dict from Mixcloud or SoundCloud
        artist: Dict with 'id', 'name', 'slug' — always a valid artist
        platform: 'mixcloud' or 'soundcloud'

    Returns:
        Show dict compatible with generate-show-pages.py
    """
    artist_id = artist['id']
    artist_name = artist['name']
    artist_slug = artist['slug']

    if platform == 'mixcloud':
        slug = track.get('slug', '')
        name = track.get('name', '')
        url = track.get('url', '')
        created_time = track.get('created_time', '')
        pictures = track.get('pictures', {})
        duration = track.get('audio_length', 0)
        description = track.get('description', '')

        return {
            'id': f"mc-{slug}",
            'title': name,
            'slug': generate_slug(name, created_time),
            'start': created_time,
            'end': created_time,
            'artistIds': [artist_id],
            'artistName': artist_name,
            'artistSlug': artist_slug,
            'description': _make_description(description),
            'mixcloud_match': {
                'slug': slug,
                'name': name,
                'url': url,
                'audio_length': duration,
                'pictures': pictures,
            },
            'soundcloud_match': None,
            'match_score': 600,
            'episode_info': None,
            'platform': 'mixcloud',
        }

    # SoundCloud
    track_id = str(track.get('id', ''))
    title = track.get('title', '')
    url = track.get('url', '')
    thumbnail = track.get('thumbnail', '')
    duration = track.get('duration', 0)
    description = track.get('description', '')

    timestamp = track.get('timestamp', 0)
    upload_date = track.get('upload_date', '')
    if timestamp:
        created_time = datetime.fromtimestamp(timestamp).isoformat()
    elif upload_date and len(upload_date) == 8:
        try:
            created_time = datetime.strptime(upload_date, '%Y%m%d').isoformat()
        except ValueError:
            created_time = ''
    else:
        created_time = ''

    return {
        'id': f"sc-{track_id}",
        'title': title,
        'slug': generate_slug(title, created_time),
        'start': created_time,
        'end': created_time,
        'artistIds': [artist_id],
        'artistName': artist_name,
        'artistSlug': artist_slug,
        'description': _make_description(description),
        'mixcloud_match': None,
        'soundcloud_match': {
            'id': track_id,
            'title': title,
            'url': url,
            'duration': duration,
            'thumbnail': thumbnail,
        },
        'match_score': 600,
        'episode_info': None,
        'platform': 'soundcloud',
    }


def _make_description(text):
    """Wrap plain text in RadioCult doc structure, or return None if empty."""
    if not text:
        return None
    return {
        'type': 'doc',
        'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}],
    }


# ---------------------------------------------------------------------------
# Cache metadata
# ---------------------------------------------------------------------------

def load_cache_meta():
    if CACHE_META_FILE.exists():
        return json.loads(CACHE_META_FILE.read_text())
    return {}


def save_cache_meta(meta):
    CACHE_META_FILE.write_text(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """
    Main — tag-driven show sourcing.

    Step 1: Fetch RC artists and upcoming schedule.
    Step 2: Build artist tag index.
    Step 3: For each tagged artist, fetch their Mixcloud shows (playlist or uploads).
    Step 4: For each tagged artist with SC tags, fetch their SoundCloud shows.
    Step 5: Convert tracks to shows, deduplicate, filter, sort.
    Step 6: Process upcoming schedule.
    Step 7: Write output files.
    """
    full_refresh = '--full' in sys.argv

    print("=" * 60)
    print("éist Radio Show Cache Generator")
    print("DEMO: API-CALLS-ONLY (Tag-driven, no title heuristics)")
    print("=" * 60)

    DATA_DIR.mkdir(exist_ok=True)
    api_key = get_api_key()

    # Step 1: Fetch RadioCult data
    artists = fetch_radiocult_artists_only(api_key)
    upcoming_schedule = fetch_radiocult_upcoming_only(api_key)

    # Step 2: Build artist tag index
    print("\n[Tags] Building artist tag index...")
    artist_tags = build_artist_tag_index(artists)
    print(f"  {len(artist_tags)} artists have MC/SC tags")
    for artist_id, tags in artist_tags.items():
        name = artists.get(artist_id, {}).get('name', artist_id)
        parts = [f"{k}={v}" for k, v in tags.items() if v]
        print(f"    {name}: {', '.join(parts)}")

    # Step 3: Fetch Mixcloud per artist
    print("\n[Mixcloud] Fetching per-artist cloudcasts...")
    mc_artist_cache = {} if full_refresh else load_mc_artist_cache()
    mc_artist_tracks = {}  # username_or_key -> [cloudcasts]
    mc_total_new = 0

    for artist_id, tags in artist_tags.items():
        mc_username = tags.get('mc_username')
        mc_playlist = tags.get('mc_playlist')
        if not mc_username and not mc_playlist:
            continue

        artist_name = artists.get(artist_id, {}).get('name', artist_id)
        cache_key = f"{mc_username or 'eistcork'}:{mc_playlist or 'uploads'}"
        existing = mc_artist_cache.get(cache_key, [])

        print(f"  [{artist_name}] mc_username={mc_username!r} mc_playlist={mc_playlist!r}")

        tracks, new_count = fetch_mixcloud_for_artist(mc_username, mc_playlist, existing, full_refresh)
        mc_artist_tracks[artist_id] = tracks
        mc_total_new += new_count

        # Only cache uploads (playlists are always fetched fresh)
        if mc_username and not mc_playlist:
            mc_artist_cache[cache_key] = tracks

    if any(not tags.get('mc_playlist') for tags in artist_tags.values() if tags.get('mc_username')):
        save_mc_artist_cache(mc_artist_cache)

    print(f"[Mixcloud] {sum(len(t) for t in mc_artist_tracks.values())} total cloudcasts "
          f"({mc_total_new} new)")

    # Step 4: Fetch SoundCloud per artist
    print("\n[SoundCloud] Fetching per-artist tracks...")
    sc_artist_cache = {} if full_refresh else load_sc_artist_cache()
    sc_artist_tracks = {}  # username -> [tracks]

    for artist_id, tags in artist_tags.items():
        sc_username = tags.get('sc_username')
        if not sc_username:
            continue
        sc_playlist = tags.get('sc_playlist')
        existing = sc_artist_cache.get(sc_username, []) if not sc_playlist else []

        tracks = fetch_soundcloud_for_artist(sc_username, sc_playlist, existing, full_refresh)
        sc_artist_tracks[sc_username] = tracks
        if not sc_playlist:
            sc_artist_cache[sc_username] = tracks

    if sc_artist_tracks:
        save_sc_artist_cache(sc_artist_cache)
        total_sc = sum(len(t) for t in sc_artist_tracks.values())
        print(f"[SoundCloud] {total_sc} total tracks across {len(sc_artist_tracks)} artists")

    # Step 5: Build shows per artist
    print("\n[Shows] Converting tracks to shows...")
    all_shows = []
    seen_slugs = set()

    for artist_id, tags in artist_tags.items():
        artist = artists.get(artist_id, {})
        artist_name = artist.get('name', '')
        if not artist_name:
            continue

        artist_info = {
            'id': artist_id,
            'name': artist_name,
            'slug': normalize_to_slug(artist_name),
        }

        # Mixcloud
        for track in mc_artist_tracks.get(artist_id, []):
            show = convert_track_to_show(track, artist_info, 'mixcloud')
            if show['slug'] not in seen_slugs and not should_exclude_show(show):
                seen_slugs.add(show['slug'])
                all_shows.append(show)

        # SoundCloud
        sc_username = tags.get('sc_username')
        if sc_username:
            for track in sc_artist_tracks.get(sc_username, []):
                show = convert_track_to_show(track, artist_info, 'soundcloud')
                if show['slug'] not in seen_slugs and not should_exclude_show(show):
                    seen_slugs.add(show['slug'])
                    all_shows.append(show)

    all_shows.sort(key=lambda x: x.get('start', ''), reverse=True)

    mc_count = sum(1 for s in all_shows if s.get('platform') == 'mixcloud')
    sc_count = sum(1 for s in all_shows if s.get('platform') == 'soundcloud')
    print(f"  Total: {len(all_shows)} shows ({mc_count} Mixcloud, {sc_count} SoundCloud)")

    # Step 6: Process upcoming schedule
    now = datetime.now()
    if upcoming_schedule and 'schedules' in upcoming_schedule:
        future_shows = [s for s in upcoming_schedule['schedules'] if s.get('start', '') > now.isoformat()]
        upcoming_data = []
        for show in future_shows:
            artist_ids = show.get('artistIds', [])
            artist_name = None
            artist_slug = None
            if artist_ids:
                info = artists.get(artist_ids[0], {})
                artist_name = info.get('name')
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

    # Step 7: Write output files
    SHOWS_FILE.write_text(json.dumps(all_shows, indent=2))

    total_mc_tracks = sum(len(t) for t in mc_artist_tracks.values())
    total_sc_tracks = sum(len(t) for t in sc_artist_tracks.values())

    API_SHOWS_CACHE_FILE.write_text(json.dumps({
        'shows': all_shows,
        'generated_at': datetime.now().isoformat(),
        'source': 'api-calls-only',
        'mixcloud_tracks': total_mc_tracks,
        'soundcloud_tracks': total_sc_tracks,
    }, indent=2))

    save_cache_meta({
        'last_updated': datetime.now().isoformat(),
        'full_refresh': full_refresh,
        'source_mode': 'api-calls-only',
        'total_shows': len(all_shows),
        'mixcloud_shows': mc_count,
        'soundcloud_shows': sc_count,
        'new_mixcloud_this_run': mc_total_new,
        'total_mixcloud_cached': total_mc_tracks,
        'total_soundcloud_cached': total_sc_tracks,
    })

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total shows: {len(all_shows)}")
    print(f"  Mixcloud:    {mc_count}")
    print(f"  SoundCloud:  {sc_count}")
    print(f"\nOutput files:")
    print(f"  {SHOWS_FILE}")
    print(f"  {API_SHOWS_CACHE_FILE}")
    print(f"  {MC_ARTIST_CACHE_FILE}")
    print(f"  {SC_ARTIST_CACHE_FILE}")
    print(f"  {CACHE_META_FILE}")
    print("=" * 60)


if __name__ == '__main__':
    main()
