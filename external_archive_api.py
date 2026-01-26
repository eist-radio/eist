"""
Fetch metadata from external Mixcloud/SoundCloud URLs.

This module handles fetching archive metadata from URLs that point to accounts
other than the main eistcork account. Artists can add these URLs to their
RadioCult show descriptions to manually link their archives.

Mixcloud: Uses public API (no auth required)
SoundCloud: Uses /resolve endpoint via existing SoundCloudClient
"""

import time
import requests
from typing import Optional

# Reuse existing SoundCloud client
from soundcloud_api import SoundCloudClient, SoundCloudAPIError, SoundCloudAuthError

# Rate limiting
REQUEST_DELAY = 0.3


def fetch_mixcloud_metadata(user: str, slug: str) -> Optional[dict]:
    """
    Fetch metadata from Mixcloud public API.

    GET https://api.mixcloud.com/{user}/{slug}/

    Args:
        user: Mixcloud username
        slug: Cloudcast slug

    Returns:
        Normalized archive dict or None if not found/error
    """
    url = f"https://api.mixcloud.com/{user}/{slug}/"

    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, timeout=30)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        # Check for error response
        if data.get('error'):
            return None

        return {
            'slug': data.get('slug', slug),
            'name': data.get('name', ''),
            'url': data.get('url', f'https://www.mixcloud.com/{user}/{slug}/'),
            'created_time': data.get('created_time', ''),
            'pictures': data.get('pictures', {}),
            'audio_length': data.get('audio_length'),
            'description': data.get('description', ''),
            'external': True,
            'external_user': user
        }

    except requests.RequestException as e:
        print(f"    Warning: Failed to fetch Mixcloud {user}/{slug}: {e}")
        return None


def fetch_soundcloud_metadata(user: str, track: str) -> Optional[dict]:
    """
    Fetch metadata from SoundCloud using /resolve endpoint.

    Uses the existing SoundCloudClient to resolve the URL.

    Args:
        user: SoundCloud username
        track: Track slug

    Returns:
        Normalized archive dict or None if not found/error
    """
    track_url = f"https://soundcloud.com/{user}/{track}"

    try:
        client = SoundCloudClient()
        time.sleep(REQUEST_DELAY)

        # Use /resolve to get track data
        data = client._api_request('/resolve', {'url': track_url})

        if not data or data.get('kind') != 'track':
            return None

        # Normalize to cache format (same as soundcloud_api.normalize_track_data)
        created_at = data.get('created_at', '')
        upload_date = ''
        timestamp = 0

        if created_at:
            try:
                from datetime import datetime
                dt = datetime.strptime(created_at, '%Y/%m/%d %H:%M:%S %z')
                upload_date = dt.strftime('%Y%m%d')
                timestamp = int(dt.timestamp())
            except ValueError:
                pass

        duration_ms = data.get('duration', 0)
        duration_s = duration_ms / 1000.0 if duration_ms else 0

        artwork_url = data.get('artwork_url', '')
        if artwork_url:
            artwork_url = artwork_url.replace('-large.', '-original.')

        return {
            'id': str(data.get('id', '')),
            'title': data.get('title', ''),
            'url': data.get('permalink_url', track_url),
            'upload_date': upload_date,
            'timestamp': timestamp,
            'duration': duration_s,
            'thumbnail': artwork_url,
            'description': data.get('description', ''),
            'external': True,
            'external_user': user
        }

    except (SoundCloudAPIError, SoundCloudAuthError) as e:
        print(f"    Warning: Failed to fetch SoundCloud {user}/{track}: {e}")
        return None
    except Exception as e:
        print(f"    Warning: Unexpected error fetching SoundCloud {user}/{track}: {e}")
        return None


def fetch_external_archive(platform: str, url_info: dict) -> Optional[dict]:
    """
    Unified interface to fetch external archive metadata.

    Args:
        platform: 'mixcloud' or 'soundcloud'
        url_info: Dict with URL components from extract_archive_urls()
            - mixcloud: {'url': ..., 'user': ..., 'slug': ...}
            - soundcloud: {'url': ..., 'user': ..., 'track': ...}

    Returns:
        Normalized archive dict or None if not found/error
    """
    if platform == 'mixcloud':
        return fetch_mixcloud_metadata(url_info['user'], url_info['slug'])
    elif platform == 'soundcloud':
        return fetch_soundcloud_metadata(url_info['user'], url_info['track'])
    else:
        return None
