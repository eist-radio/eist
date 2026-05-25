#!/usr/bin/env python3
"""
SoundCloud API client for éist radio data pipeline.

Provides authenticated access to the SoundCloud API for fetching track metadata.
Replaces the previous yt-dlp scraping approach with proper OAuth 2.0 API calls.

Authentication:
    Uses OAuth 2.0 Client Credentials flow with client_id and client_secret
    stored in .env file. Tokens are cached and auto-refreshed.

Usage:
    from soundcloud_api import SoundCloudClient

    client = SoundCloudClient()
    tracks = client.get_user_tracks('eistcork')  # Full fetch
    tracks = client.get_user_tracks_incremental('eistcork', existing_ids)  # Incremental
"""

import base64
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


# API configuration
SOUNDCLOUD_API_BASE = "https://api.soundcloud.com"
SOUNDCLOUD_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"

# Rate limiting - conservative to avoid hitting limits
# Token rate limits: 50 tokens per 12h per app, 30 tokens per 1h per IP
REQUEST_DELAY = 0.3  # Seconds between API requests


class SoundCloudAuthError(Exception):
    """Raised when authentication fails."""
    pass


class SoundCloudAPIError(Exception):
    """Raised when API request fails."""
    pass


class SoundCloudClient:
    """
    SoundCloud API client with OAuth 2.0 authentication.

    Handles token acquisition, caching, refresh, and API requests.
    """

    def __init__(self, client_id: str = None, client_secret: str = None):
        """
        Initialize the SoundCloud client.

        Args:
            client_id: OAuth client ID (defaults to env/file)
            client_secret: OAuth client secret (defaults to env/file)
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._user_cache: dict = {}  # username -> user_id cache

        # Load credentials if not provided
        if not self._client_id or not self._client_secret:
            self._load_credentials()

    def _load_credentials(self):
        """Load OAuth credentials from environment or .env file."""
        # Try environment first
        self._client_id = os.environ.get('SOUNDCLOUD_CLIENT_ID')
        self._client_secret = os.environ.get('SOUNDCLOUD_CLIENT_SECRET')

        # Fall back to .env file
        if not self._client_id or not self._client_secret:
            env_file = Path('.env')
            if env_file.exists():
                for line in env_file.read_text().strip().split('\n'):
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        name, value = line.split('=', 1)
                        name = name.strip()
                        value = value.strip()
                        if name == 'SOUNDCLOUD_CLIENT_ID':
                            self._client_id = value
                        elif name == 'SOUNDCLOUD_CLIENT_SECRET':
                            self._client_secret = value

        if not self._client_id or not self._client_secret:
            raise SoundCloudAuthError(
                "Missing SOUNDCLOUD_CLIENT_ID or SOUNDCLOUD_CLIENT_SECRET. "
                "Set in .env file or environment variables."
            )

    def _get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if needed.

        Uses OAuth 2.0 Client Credentials flow.
        Token lifetime is approximately 1 hour.
        """
        # Return cached token if still valid (with 60s buffer)
        if self._access_token and time.time() < (self._token_expires_at - 60):
            return self._access_token

        # Request new token using Client Credentials flow
        credentials = f"{self._client_id}:{self._client_secret}"
        basic_auth = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json; charset=utf-8"
        }

        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(
                SOUNDCLOUD_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=30
            )

            if response.status_code == 401:
                raise SoundCloudAuthError(
                    "Invalid client credentials. Check SOUNDCLOUD_CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET."
                )

            if response.status_code == 429:
                raise SoundCloudAuthError(
                    "Rate limited. Token requests: 50/12h per app, 30/1h per IP."
                )

            response.raise_for_status()
            token_data = response.json()

            self._access_token = token_data.get('access_token')
            # Token typically expires in ~3600s, use 'expires_in' if provided
            expires_in = token_data.get('expires_in', 3600)
            self._token_expires_at = time.time() + expires_in

            return self._access_token

        except requests.RequestException as e:
            raise SoundCloudAuthError(f"Failed to get access token: {e}")

    def _api_request(self, endpoint: str, params: dict = None) -> dict:
        """
        Make an authenticated API request.

        Args:
            endpoint: API endpoint (e.g., '/users/123/tracks')
            params: Query parameters

        Returns:
            JSON response data
        """
        token = self._get_access_token()

        headers = {
            "Authorization": f"OAuth {token}",
            "Accept": "application/json; charset=utf-8"
        }

        url = endpoint if endpoint.startswith('http') else f"{SOUNDCLOUD_API_BASE}{endpoint}"

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 401:
                # Token may have expired, try refreshing
                self._access_token = None
                token = self._get_access_token()
                headers["Authorization"] = f"OAuth {token}"
                response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 404:
                raise SoundCloudAPIError(f"Resource not found: {endpoint}")

            if response.status_code == 429:
                raise SoundCloudAPIError("Rate limited. Please wait before retrying.")

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise SoundCloudAPIError(f"API request failed: {e}")

    def resolve_user(self, username: str) -> dict:
        """
        Resolve a SoundCloud username to user data.

        Args:
            username: SoundCloud username (e.g., 'eistcork')

        Returns:
            User data dict with id, username, track_count, etc.
        """
        if username in self._user_cache:
            return self._user_cache[username]

        user_url = f"https://soundcloud.com/{username}"
        data = self._api_request('/resolve', {'url': user_url})
        self._user_cache[username] = data
        return data

    def get_user_tracks(self, username: str, page_size: int = 200) -> list:
        """
        Fetch all tracks for a SoundCloud user.

        Args:
            username: SoundCloud username
            page_size: Number of tracks per page (max 200)

        Returns:
            List of track dicts in upload order (newest first)
        """
        user = self.resolve_user(username)
        user_id = user.get('id')

        if not user_id:
            raise SoundCloudAPIError(f"Could not resolve user: {username}")

        all_tracks = []
        url = f"/users/{user_id}/tracks"
        params = {'limit': page_size, 'linked_partitioning': 1}

        while url:
            time.sleep(REQUEST_DELAY)

            # For first request, use params; subsequent requests use next_href URL
            if url.startswith('http'):
                data = self._api_request(url)
            else:
                data = self._api_request(url, params)

            if isinstance(data, dict) and 'collection' in data:
                tracks = data['collection']
                all_tracks.extend(tracks)
                url = data.get('next_href')
            elif isinstance(data, list):
                # Handle case where response is a plain list
                all_tracks.extend(data)
                break
            else:
                break

        return all_tracks

    def get_user_playlist(self, username: str, playlist_slug: str) -> list:
        """
        Fetch tracks from a SoundCloud playlist.

        Args:
            username: SoundCloud username who owns the playlist
            playlist_slug: Playlist slug (e.g. 'aus-der-ferne')

        Returns:
            List of track dicts from the playlist (may be partial if playlist is large)
        """
        playlist_url = f"https://soundcloud.com/{username}/sets/{playlist_slug}"
        data = self._api_request('/resolve', {'url': playlist_url})
        return data.get('tracks', [])

    def get_user_tracks_incremental(
        self,
        username: str,
        known_ids: set,
        page_size: int = 200
    ) -> tuple:
        """
        Fetch only new tracks for a SoundCloud user (incremental update).

        Stops fetching when we encounter a track ID that's already in the cache.
        Since tracks are returned newest-first, this efficiently fetches only new content.

        Args:
            username: SoundCloud username
            known_ids: Set of track IDs already in cache
            page_size: Number of tracks per page

        Returns:
            Tuple of (new_tracks, found_known) where:
            - new_tracks: List of new tracks (newest first)
            - found_known: Whether we hit a known track (True) or fetched everything (False)
        """
        user = self.resolve_user(username)
        user_id = user.get('id')

        if not user_id:
            raise SoundCloudAPIError(f"Could not resolve user: {username}")

        new_tracks = []
        found_known = False
        url = f"/users/{user_id}/tracks"
        params = {'limit': page_size, 'linked_partitioning': 1}

        while url and not found_known:
            time.sleep(REQUEST_DELAY)

            if url.startswith('http'):
                data = self._api_request(url)
            else:
                data = self._api_request(url, params)

            if isinstance(data, dict) and 'collection' in data:
                tracks = data['collection']

                for track in tracks:
                    track_id = str(track.get('id', ''))
                    if track_id in known_ids:
                        # Found existing content - stop here
                        found_known = True
                        break
                    new_tracks.append(track)

                if not found_known:
                    url = data.get('next_href')
            else:
                break

        return new_tracks, found_known


def is_valid_track(api_track: dict) -> bool:
    """
    Check if an API response item is a valid track.

    Filters out user objects and other non-track items that might
    appear in the API response.
    """
    # Must have 'kind' field set to 'track'
    if api_track.get('kind') != 'track':
        return False

    # Must have a valid created_at timestamp
    if not api_track.get('created_at'):
        return False

    # Must have a duration > 0
    if not api_track.get('duration'):
        return False

    return True


def normalize_track_data(api_track: dict) -> dict:
    """
    Convert SoundCloud API track data to the cache format used by the pipeline.

    API format:
        {
            "kind": "track",
            "id": 2223981467,
            "title": "Track Title",
            "permalink_url": "https://soundcloud.com/user/track",
            "created_at": "2025/12/04 15:32:42 +0000",
            "duration": 3600118,  (milliseconds)
            "artwork_url": "https://i1.sndcdn.com/artworks-...-large.jpg",
            "description": "..."
        }

    Cache format:
        {
            "id": "2223981467",
            "title": "Track Title",
            "url": "https://soundcloud.com/user/track",
            "upload_date": "20251204",
            "timestamp": 1733326362,
            "duration": 3600.118,  (seconds)
            "thumbnail": "https://i1.sndcdn.com/artworks-...-original.jpg",
            "description": "..."
        }
    """
    # Parse created_at: "2025/12/04 15:32:42 +0000"
    created_at = api_track.get('created_at', '')
    upload_date = ''
    timestamp = 0

    if created_at:
        try:
            # Parse SoundCloud's date format
            dt = datetime.strptime(created_at, '%Y/%m/%d %H:%M:%S %z')
            upload_date = dt.strftime('%Y%m%d')
            timestamp = int(dt.timestamp())
        except ValueError:
            pass

    # Convert duration from milliseconds to seconds
    duration_ms = api_track.get('duration', 0)
    duration_s = duration_ms / 1000.0 if duration_ms else 0

    # Get artwork URL, preferring original quality
    artwork_url = api_track.get('artwork_url', '')
    if artwork_url:
        # SoundCloud returns -large.jpg by default, swap to -original.jpg
        artwork_url = artwork_url.replace('-large.', '-original.')

    return {
        'id': str(api_track.get('id', '')),
        'title': api_track.get('title', ''),
        'url': api_track.get('permalink_url', ''),
        'upload_date': upload_date,
        'timestamp': timestamp,
        'duration': duration_s,
        'thumbnail': artwork_url,
        'description': api_track.get('description', '')
    }


def fetch_soundcloud_playlist(username: str, playlist_slug: str) -> list:
    """
    Fetch all tracks from a SoundCloud playlist.

    Args:
        username: SoundCloud username who owns the playlist
        playlist_slug: Playlist slug (lowercase, e.g. 'aus-der-ferne')

    Returns:
        List of track dicts in cache format
    """
    client = SoundCloudClient()
    try:
        api_tracks = client.get_user_playlist(username, playlist_slug)
        return [normalize_track_data(t) for t in api_tracks if is_valid_track(t)]
    except SoundCloudAPIError as e:
        print(f"[SoundCloud] Playlist fetch failed for {username}/sets/{playlist_slug}: {e}")
        return []


def fetch_soundcloud_tracks_api(username: str = 'eistcork') -> list:
    """
    Fetch all SoundCloud tracks using the official API.

    This is the full-refresh function that fetches all tracks.

    Args:
        username: SoundCloud username

    Returns:
        List of track dicts in cache format (newest first)
    """
    client = SoundCloudClient()
    api_tracks = client.get_user_tracks(username)
    # Filter to valid tracks only and normalize
    return [normalize_track_data(t) for t in api_tracks if is_valid_track(t)]


def fetch_soundcloud_tracks_api_incremental(
    username: str = 'eistcork',
    existing_cache: list = None
) -> tuple:
    """
    Fetch new SoundCloud tracks incrementally using the official API.

    Stops when we hit a known track ID from the existing cache.

    Args:
        username: SoundCloud username
        existing_cache: List of existing cached tracks (newest first)

    Returns:
        Tuple of (merged_tracks, new_count) where:
        - merged_tracks: Complete list with new tracks prepended
        - new_count: Number of new tracks found
    """
    # Build set of known IDs for O(1) lookup
    known_ids = set()
    if existing_cache:
        known_ids = {str(t.get('id')) for t in existing_cache if t.get('id')}

    if not known_ids:
        # No cache - do full fetch
        tracks = fetch_soundcloud_tracks_api(username)
        return tracks, len(tracks)

    # Incremental fetch
    client = SoundCloudClient()
    new_api_tracks, found_known = client.get_user_tracks_incremental(username, known_ids)

    # Filter to valid tracks and normalize to cache format
    new_tracks = [normalize_track_data(t) for t in new_api_tracks if is_valid_track(t)]

    # Merge: new tracks first, then existing cache
    merged = new_tracks + (existing_cache or [])

    return merged, len(new_tracks)


if __name__ == '__main__':
    # Quick test
    import json

    print("Testing SoundCloud API client...")

    client = SoundCloudClient()

    print("\n1. Resolving user 'eistcork'...")
    user = client.resolve_user('eistcork')
    print(f"   User ID: {user.get('id')}")
    print(f"   Track count: {user.get('track_count')}")

    print("\n2. Fetching first 5 tracks...")
    tracks = client.get_user_tracks('eistcork', page_size=5)
    print(f"   Got {len(tracks)} tracks")
    if tracks:
        normalized = normalize_track_data(tracks[0])
        print(f"   First track (normalized): {json.dumps(normalized, indent=2)}")

    print("\n3. Testing incremental fetch with fake known IDs...")
    # Pretend we know the 3rd track
    if len(tracks) >= 3:
        known = {str(tracks[2]['id'])}
        new_tracks, found = client.get_user_tracks_incremental('eistcork', known, page_size=5)
        print(f"   Found {len(new_tracks)} new tracks before hitting known ID")
        print(f"   Found known: {found}")

    print("\nDone!")
