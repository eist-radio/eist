#!/usr/bin/env python3
"""
Fetch pre-matched show data from the EIST API.

Replaces generate-show-cache.py by consuming data from eist-api worker.
The API already handles fetching from RadioCult, Mixcloud, and SoundCloud,
plus the matching algorithm - so this script just fetches the results.
"""

import argparse
import json
import requests
import sys
from datetime import datetime, timezone

API_BASE = "https://eist-api.johnocallaghan.workers.dev"
SHOWS_ENDPOINT = f"{API_BASE}/api/shows"
META_ENDPOINT = f"{API_BASE}/api/meta"

SHOWS_OUTPUT = "data/shows.json"
META_OUTPUT = "data/cache-meta.json"


def fetch_shows(has_archive=None, limit=200):
    """Fetch all shows from API with pagination.

    Args:
        has_archive: If True, only shows with archives. If False, only shows without.
                    If None, fetch all shows.
        limit: Number of shows per page (max ~500).

    Returns:
        List of show dictionaries.
    """
    shows = []
    offset = 0

    while True:
        params = {
            "limit": limit,
            "offset": offset,
        }
        if has_archive is not None:
            params["hasArchive"] = "true" if has_archive else "false"

        print(f"[API] Fetching shows (offset={offset})...")
        response = requests.get(SHOWS_ENDPOINT, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        shows.extend(data["shows"])

        print(f"[API] Got {len(data['shows'])} shows (total: {len(shows)})")

        if not data["pagination"]["hasMore"]:
            break
        offset += limit

    return shows


def fetch_meta():
    """Fetch build metadata from API."""
    response = requests.get(META_ENDPOINT, timeout=10)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch shows from EIST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch-shows-from-api.py           # Fetch shows with archives only
  python fetch-shows-from-api.py --full    # Fetch all shows (for schedule display)
        """,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Fetch all shows, not just those with archives",
    )
    args = parser.parse_args()

    try:
        if args.full:
            # Fetch all shows (for full site rebuild including schedule)
            print("[API] Fetching all shows...")
            all_shows = fetch_shows(has_archive=None)
        else:
            # Default: only fetch shows with archives (for archive pages)
            print("[API] Fetching shows with archives...")
            all_shows = fetch_shows(has_archive=True)

        # Sort by start date (newest first)
        all_shows.sort(key=lambda s: s.get("start") or "", reverse=True)

        # Save shows.json
        with open(SHOWS_OUTPUT, "w") as f:
            json.dump(all_shows, f, indent=2)
        print(f"[API] Saved {len(all_shows)} shows to {SHOWS_OUTPUT}")

        # Fetch and save metadata
        print("[API] Fetching metadata...")
        meta = fetch_meta()
        meta["fetched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        meta["source"] = "eist-api"

        with open(META_OUTPUT, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[API] Saved metadata to {META_OUTPUT}")

        # Summary
        archived_count = sum(
            1
            for s in all_shows
            if s.get("mixcloud_match") or s.get("soundcloud_match")
        )
        print(f"\nSuccessfully fetched {len(all_shows)} shows from API")
        print(f"  - Shows with archives: {archived_count}")
        print(f"  - Shows without archives: {len(all_shows) - archived_count}")

    except requests.RequestException as e:
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
