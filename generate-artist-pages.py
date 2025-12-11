#!/usr/bin/env python3
"""
Generate markdown files for artists from the RadioCult API.

Usage:
    python3 generate-artist-pages.py

Requires:
    - API_KEY environment variable or RADIOCULT_API_KEY file
    - requests library (usually pre-installed)
"""

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

# Configuration
STATION_ID = "eist-radio"
ARTISTS_URL = f"https://api.radiocult.fm/api/station/{STATION_ID}/artists"
OUTPUT_DIR = Path("content/artists")
OUTPUT_FILE = Path("content/artists.md")
HERO_FOCUS_FILE = Path("data/hero-focus.json")
DEFAULT_IMAGE = "/eist_online.png"


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


def normalize_filename(name):
    """
    Normalize name to URL-safe slug.
    Equivalent to the bash function using iconv and sed.
    """
    if not name:
        return ""

    # Replace specific characters that iconv handles specially
    text = name
    for char in 'ɅØøæÆ':
        text = text.replace(char, '-')

    # Normalize unicode and remove accents (like iconv -t ASCII//TRANSLIT)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    # Replace non-alphanumeric with hyphens (like tr -cs 'a-zA-Z0-9' '-')
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text)

    # Remove leading/trailing hyphens and collapse multiple hyphens
    text = re.sub(r'^-+|-+$', '', text)
    text = re.sub(r'-+', '-', text)

    # Lowercase
    return text.lower()


def extract_tag_value(tags, prefix):
    """Extract value from tags with given prefix (e.g., MC-USERNAME_xxx -> xxx)."""
    if not tags:
        return ""
    for tag in tags:
        if tag.startswith(prefix):
            return tag[len(prefix):].lower()
    return ""


def extract_bio(description):
    """
    Extract bio text from RadioCult description structure.
    Handles nested content with text and hardBreak nodes.
    """
    if not description or not isinstance(description, dict):
        return ""

    content = description.get('content', [])
    if not content:
        return ""

    paragraphs = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_content = block.get('content', [])
        if not block_content:
            continue

        parts = []
        for node in block_content:
            if not isinstance(node, dict):
                continue
            if node.get('type') == 'text':
                parts.append(node.get('text', ''))
            elif node.get('type') == 'hardBreak':
                parts.append('\n')

        if parts:
            paragraphs.append(''.join(parts))

    return '\n\n'.join(paragraphs)


def build_social_url(key, value):
    """Build full URL for a social media value."""
    if not value:
        return ""

    if key == 'instagramHandle':
        return f"https://www.instagram.com/{value}"

    # For soundcloud, mixcloud, site - check if already a URL
    if value.startswith('http://') or value.startswith('https://'):
        return value

    if key == 'soundcloud':
        return f"https://www.soundcloud.com/{value}"
    elif key == 'mixcloud':
        return f"https://www.mixcloud.com/{value}"
    elif key == 'site':
        return value  # Site might not need a prefix

    return value


def generate_artist_page(artist, hero_focus_data):
    """Generate markdown content for a single artist."""
    name = artist.get('name', '')
    if not name:
        return None, None

    slug = normalize_filename(name)
    tags = artist.get('tags', [])
    socials = artist.get('socials', {}) or {}

    # Get image URL
    logo = artist.get('logo', {}) or {}
    image_url = logo.get('1024x1024', '') or DEFAULT_IMAGE

    # Extract tag values
    mc_username = extract_tag_value(tags, 'MC-USERNAME_')
    sc_username = extract_tag_value(tags, 'SC-USERNAME_')
    host_sc_playlist = extract_tag_value(tags, 'HOST-SC-PLAYLIST_')
    host_mc_playlist = extract_tag_value(tags, 'HOST-MC-PLAYLIST_')
    eist_mc_playlist = extract_tag_value(tags, 'EIST-MC-PLAYLIST_')

    # Extract genres
    genres = ', '.join(artist.get('genres', []) or [])

    # Get hero focus
    hero_focus = hero_focus_data.get(slug, '')

    # Build social URLs
    soundcloud_url = build_social_url('soundcloud', socials.get('soundcloud', ''))
    mixcloud_url = build_social_url('mixcloud', socials.get('mixcloud', ''))
    instagram_handle = socials.get('instagramHandle', '')
    instagram_url = f"https://www.instagram.com/{instagram_handle}" if instagram_handle else ""
    website_url = socials.get('site', '')

    # Extract bio
    bio = extract_bio(artist.get('description'))

    # Build front matter
    date_str = datetime.now().strftime('%Y-%m-%d')

    content = f'''+++
description = "{name}"
date = {date_str}
draft = false
noindex = false
image = "{image_url}"
hero_focus = "{hero_focus}"
genres = "{genres}"
soundcloud = "{soundcloud_url}"
mixcloud = "{mixcloud_url}"
instagram = "{instagram_url}"
website = "{website_url}"
mc_username = "{mc_username}"
sc_username = "{sc_username}"
host_sc_playlist = "{host_sc_playlist}"
host_mc_playlist = "{host_mc_playlist}"
eist_mc_playlist = "{eist_mc_playlist}"
+++

{bio}

'''

    return slug, content


def main():
    # Get API key
    api_key = get_api_key()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create section index
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    index_content = f'''+++
title = "Artists"
date = {now_utc}
draft = false
noindex = false
+++
'''
    (OUTPUT_DIR / "_index.md").write_text(index_content)

    # Fetch artists from API
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(ARTISTS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Error fetching artists: {e}")
        sys.exit(1)

    artists = data.get('artists', [])
    if not artists:
        print("Error: No artists found.")
        sys.exit(1)

    # Load hero focus data
    hero_focus_data = {}
    if HERO_FOCUS_FILE.exists():
        try:
            hero_focus_data = json.loads(HERO_FOCUS_FILE.read_text())
        except:
            pass

    # Generate artist pages
    artist_links = []

    for artist in artists:
        slug, content = generate_artist_page(artist, hero_focus_data)
        if not slug:
            continue

        # Write artist file
        file_path = OUTPUT_DIR / f"{slug}.md"
        file_path.write_text(content)

        # Collect link for index
        name = artist.get('name', '')
        artist_links.append(f"[{name}](/artists/{slug})")

    print(f"Generated {len(artist_links)} artist pages")

    # Generate artists index file
    index_content = f'''+++
title = "Artists"
date = {now_utc}
draft = false
noindex = false
+++
'''
    index_content += ' / '.join(artist_links)
    OUTPUT_FILE.write_text(index_content)

    print(f"Generated {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
