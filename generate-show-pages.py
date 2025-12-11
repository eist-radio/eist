#!/usr/bin/env python3
"""
Generate show pages from cached show data.

Reads from data/shows.json and creates content/archive/*.md

OPTIMIZATION: This Python version replaces the bash script and is ~10-20x faster
because it processes all shows in a single pass without spawning subprocesses.

The bash version spawned 21 jq processes per show (27,867 total for 1327 shows),
while this version parses the JSON once and generates all files in memory.

This script precomputes related_shows (other shows by same artist) to avoid
O(n^2) lookups in Hugo templates. Each show page includes up to 4 slugs of
other shows by the same artist, sorted newest-first.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

SHOWS_FILE = "data/shows.json"
OUTPUT_DIR = "content/archive"


def extract_description(desc_obj):
    """Extract plain text from RadioCult description JSON structure."""
    if not desc_obj or not isinstance(desc_obj, dict):
        return ""

    content = desc_obj.get("content", [])
    if not content:
        return ""

    paragraphs = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_content = block.get("content", [])
        if not block_content:
            continue

        parts = []
        for item in block_content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")
            if item_type == "text":
                parts.append(item.get("text", ""))
            elif item_type == "hardBreak":
                parts.append("\n")

        if parts:
            paragraphs.append("".join(parts))

    return "\n\n".join(paragraphs)


def escape_toml_string(s):
    """Escape double quotes for TOML strings."""
    if s is None:
        return ""
    return str(s).replace('"', '\\"')


def format_date(iso_string):
    """Convert ISO date string to YYYY-MM-DD format."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return ""


def build_artist_shows_mapping(shows):
    """
    Build a mapping of artist_slug -> [show_slugs] sorted by date descending.
    Only includes shows that have an archive (mixcloud or soundcloud match).
    """
    artist_shows = defaultdict(list)

    # Sort shows by start date descending (newest first)
    sorted_shows = sorted(
        shows,
        key=lambda x: x.get("start", "") or "",
        reverse=True
    )

    for show in sorted_shows:
        artist_slug = show.get("artistSlug")
        slug = show.get("slug")

        if not artist_slug or not slug:
            continue

        # Only include shows with archives
        if show.get("mixcloud_match") or show.get("soundcloud_match"):
            artist_shows[artist_slug].append(slug)

    return artist_shows


def get_related_shows(artist_slug, current_slug, artist_shows, limit=4):
    """Get up to `limit` related shows by the same artist, excluding current show."""
    if not artist_slug or artist_slug not in artist_shows:
        return []

    related = []
    for slug in artist_shows[artist_slug]:
        if slug == current_slug:
            continue
        related.append(slug)
        if len(related) >= limit:
            break

    return related


def generate_show_page(show, artist_shows):
    """Generate the markdown content for a single show page."""
    slug = show.get("slug")
    if not slug:
        return None, None

    # Basic fields
    title = show.get("title", "Untitled")
    episode_info = show.get("episode_info")
    if episode_info:
        title = f"{title} {episode_info}"

    start = show.get("start", "")
    end = show.get("end", "")
    show_date = format_date(start)

    # Artist info
    artist_ids = show.get("artistIds", [])
    first_artist_id = artist_ids[0] if artist_ids else ""
    artist_name = show.get("artistName", "")
    artist_slug = show.get("artistSlug", "")

    # Mixcloud data
    mc_match = show.get("mixcloud_match") or {}
    mc_slug = mc_match.get("slug", "")
    mc_url = mc_match.get("url", "")
    mc_pictures = mc_match.get("pictures") or {}
    mc_image = mc_pictures.get("large") or mc_pictures.get("medium") or ""
    mc_desc = mc_match.get("description", "")

    # SoundCloud data
    sc_match = show.get("soundcloud_match") or {}
    sc_id = str(sc_match.get("id", "")) if sc_match.get("id") else ""
    sc_url = sc_match.get("url", "")
    sc_image = sc_match.get("thumbnail", "")
    sc_desc = sc_match.get("description") or ""

    # Has archive?
    has_archive = "true" if mc_slug or sc_id else "false"

    # Match score
    match_score = show.get("match_score", 0)

    # Extract RadioCult description
    rc_desc = extract_description(show.get("description"))

    # Pick the longest description
    descriptions = [
        (len(rc_desc), rc_desc),
        (len(mc_desc), mc_desc),
        (len(sc_desc), sc_desc),
    ]
    description = max(descriptions, key=lambda x: x[0])[1]

    # Related shows
    related = get_related_shows(artist_slug, slug, artist_shows)

    # Build frontmatter
    lines = [
        "+++",
        f'title = "{escape_toml_string(title)}"',
        f"date = {show_date}",
        "draft = false",
        "noindex = false",
        f'show_start = "{start}"',
        f'show_end = "{end}"',
        f'artist_name = "{escape_toml_string(artist_name)}"',
        f'artist_slug = "{artist_slug}"',
        f'artist_id = "{first_artist_id}"',
        f'mixcloud_slug = "{mc_slug}"',
        f'mixcloud_url = "{mc_url}"',
        f'mixcloud_image = "{mc_image}"',
        f'soundcloud_id = "{sc_id}"',
        f'soundcloud_url = "{sc_url}"',
        f'soundcloud_image = "{sc_image}"',
        f"has_archive = {has_archive}",
        f"match_score = {match_score}",
    ]

    # Add related_shows if present
    if related:
        related_str = ", ".join(f'"{s}"' for s in related)
        lines.append(f"related_shows = [{related_str}]")

    lines.append("+++")
    lines.append("")
    lines.append(description)
    lines.append("")

    content = "\n".join(lines)
    return slug, content


def main():
    # Check if shows.json exists
    if not os.path.exists(SHOWS_FILE):
        print(f"Error: {SHOWS_FILE} not found. Run generate-show-cache.py first.")
        sys.exit(1)

    # Load shows
    print(f"Loading {SHOWS_FILE}...")
    with open(SHOWS_FILE, "r") as f:
        shows = json.load(f)

    print(f"Generating {len(shows)} show pages...")

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Create section index
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index_content = f"""+++
title = "Shows"
date = {now}
draft = false
noindex = false
+++
"""
    with open(os.path.join(OUTPUT_DIR, "_index.md"), "w") as f:
        f.write(index_content)

    # Pass 1: Build artist -> shows mapping
    print("Pass 1: Building artist -> shows mapping...")
    artist_shows = build_artist_shows_mapping(shows)
    print(f"  Found {len(artist_shows)} artists with archived shows")

    # Pass 2: Generate show pages
    print("Pass 2: Generating show pages...")
    generated = 0
    for show in shows:
        slug, content = generate_show_page(show, artist_shows)
        if slug and content:
            filepath = os.path.join(OUTPUT_DIR, f"{slug}.md")
            with open(filepath, "w") as f:
                f.write(content)
            generated += 1

    print(f"Generated {generated} show pages in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
