#!/usr/bin/env python3
"""
Face detection script for artist images.
Analyzes artist images and outputs hero_focus values to data/hero-focus.json.

Requires: pip install face_recognition Pillow requests

Usage:
    python scripts/detect-faces.py                    # Process all artists
    python scripts/detect-faces.py ailbhe-c          # Process single artist
    python scripts/detect-faces.py --dry-run         # Preview changes without writing
"""

import os
import sys
import re
import json
import requests
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from multiprocessing import Pool, cpu_count
from functools import partial

try:
    import face_recognition
    from PIL import Image
    import numpy as np
except ImportError:
    print("Required packages not installed. Run:")
    print("  pip install face_recognition Pillow requests")
    sys.exit(1)


def download_image(url: str) -> str | None:
    """Download image to temp file, return path."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Determine extension from URL or content-type
        ext = Path(urlparse(url).path).suffix or '.jpg'

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(response.content)
            return f.name
    except Exception as e:
        print(f"  Error downloading: {e}")
        return None


def detect_face_position(image_path: str) -> tuple[float, float] | None:
    """
    Detect face in image and return (x_percent, y_percent) of eye position.
    Uses eye landmarks for more accurate positioning (keeps eyes visible in crop).
    Falls back to face center if landmarks unavailable.
    Returns None if no face detected.
    """
    try:
        # Load with PIL first to handle EXIF rotation
        from PIL import ImageOps
        pil_image = Image.open(image_path)
        pil_image = ImageOps.exif_transpose(pil_image)
        image = np.array(pil_image)

        # Get image dimensions
        height, width = image.shape[:2]

        # Try to get eye position from landmarks (more accurate)
        landmarks = face_recognition.face_landmarks(image)
        if landmarks:
            left_eye = landmarks[0].get('left_eye', [])
            right_eye = landmarks[0].get('right_eye', [])

            if left_eye and right_eye:
                # Calculate center of eyes
                all_eye_points = left_eye + right_eye
                eye_center_x = sum(p[0] for p in all_eye_points) / len(all_eye_points)
                eye_center_y = sum(p[1] for p in all_eye_points) / len(all_eye_points)

                x_percent = (eye_center_x / width) * 100
                y_percent = (eye_center_y / height) * 100

                return (x_percent, y_percent)

        # Fallback: use face bounding box center
        face_locations = face_recognition.face_locations(image)
        if not face_locations:
            return None

        top, right, bottom, left = face_locations[0]
        face_center_x = (left + right) / 2
        face_center_y = (top + bottom) / 2

        x_percent = (face_center_x / width) * 100
        y_percent = (face_center_y / height) * 100

        return (x_percent, y_percent)

    except Exception as e:
        print(f"  Error detecting face: {e}")
        return None


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse TOML frontmatter from markdown file."""
    match = re.match(r'\+\+\+(.*?)\+\+\+(.*)', content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_str = match.group(1).strip()
    body = match.group(2).strip()

    # Simple TOML parsing for key = "value" patterns
    frontmatter = {}
    for line in frontmatter_str.split('\n'):
        line = line.strip()
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"')
            frontmatter[key] = value

    return frontmatter, body


def process_artist(artist_path: Path, dry_run: bool = False, existing_data: dict = None) -> dict:
    """Process a single artist file. Returns result dict for reporting."""
    name = artist_path.stem
    result = {"name": name, "status": None, "hero_focus": None}

    # Check if already in hero-focus.json
    if existing_data and name in existing_data:
        result["status"] = "already_set"
        result["hero_focus"] = existing_data[name]
        return result

    content = artist_path.read_text()
    frontmatter, _ = parse_frontmatter(content)

    image_url = frontmatter.get('image', '')
    if not image_url or image_url == '/eist_online.png':
        result["status"] = "no_image"
        return result

    # Download image
    temp_path = download_image(image_url)
    if not temp_path:
        result["status"] = "download_failed"
        return result

    try:
        # Detect face
        position = detect_face_position(temp_path)

        if position is None:
            result["status"] = "no_face"
            return result

        x_percent, y_percent = position

        # Create hero_focus value (only vertical position matters for cropping)
        hero_focus = f"center {y_percent:.0f}%"

        result["status"] = "updated"
        result["hero_focus"] = hero_focus

        if dry_run:
            print(f"  Would set hero_focus = \"{hero_focus}\"")

        return result

    finally:
        # Cleanup temp file
        os.unlink(temp_path)


def process_artist_wrapper(args):
    """Wrapper for multiprocessing."""
    artist_path, dry_run, existing_data = args
    try:
        return process_artist(artist_path, dry_run, existing_data)
    except Exception as e:
        return {"name": artist_path.stem, "status": "error", "error": str(e)}


def main():
    project_root = Path(__file__).parent.parent
    artists_dir = project_root / "content" / "artists"
    hero_focus_file = project_root / "data" / "hero-focus.json"

    dry_run = "--dry-run" in sys.argv

    # Load existing hero_focus data
    existing_data = {}
    if hero_focus_file.exists():
        existing_data = json.loads(hero_focus_file.read_text())

    # Parse --limit=N option
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    # Get specific artist or all
    specific_artist = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            specific_artist = arg
            break

    if specific_artist:
        artist_path = artists_dir / f"{specific_artist}.md"
        if not artist_path.exists():
            print(f"Artist not found: {specific_artist}")
            sys.exit(1)
        result = process_artist(artist_path, dry_run, existing_data)
        print(f"{result['name']}: {result['status']} {result.get('hero_focus', '')}")

        # Update JSON for single artist
        if result.get('hero_focus') and not dry_run:
            existing_data[result['name']] = result['hero_focus']
            hero_focus_file.write_text(json.dumps(existing_data, indent=2, sort_keys=True))
            print(f"Updated {hero_focus_file}")
    else:
        # Collect all artist paths
        artist_paths = [p for p in sorted(artists_dir.glob("*.md")) if p.stem != "_index"]

        if limit:
            artist_paths = artist_paths[:limit]

        num_workers = min(cpu_count(), len(artist_paths), 8)  # Cap at 8 workers
        total = len(artist_paths)
        print(f"Processing {total} artists using {num_workers} workers...")

        # Prepare args for multiprocessing
        args = [(path, dry_run, existing_data) for path in artist_paths]

        # Process in parallel with progress
        results = []
        with Pool(num_workers) as pool:
            for i, result in enumerate(pool.imap(process_artist_wrapper, args), 1):
                results.append(result)
                status = result.get('status', '?')
                name = result.get('name', '?')
                focus = result.get('hero_focus', '')
                print(f"[{i}/{total}] {name}: {status} {focus}")

        # Report results and collect hero_focus values
        stats = {"updated": 0, "no_face": 0, "no_image": 0, "already_set": 0, "error": 0}
        print("\n--- Results ---")
        for r in results:
            status = r.get("status", "error")
            stats[status] = stats.get(status, 0) + 1
            if status == "updated" and r.get('hero_focus'):
                print(f"✓ {r['name']}: {r['hero_focus']}")
                existing_data[r['name']] = r['hero_focus']
            elif status == "already_set" and r.get('hero_focus'):
                # Keep existing values in the JSON
                existing_data[r['name']] = r['hero_focus']
            elif status == "error":
                print(f"✗ {r['name']}: {r.get('error', 'unknown error')}")

        # Write updated JSON
        if not dry_run:
            hero_focus_file.write_text(json.dumps(existing_data, indent=2, sort_keys=True))
            print(f"\nWrote {len(existing_data)} entries to {hero_focus_file}")

        print(f"\n--- Summary ---")
        print(f"Updated: {stats['updated']}")
        print(f"No face detected: {stats['no_face']}")
        print(f"No custom image: {stats['no_image']}")
        print(f"Already set: {stats['already_set']}")
        if stats['error']:
            print(f"Errors: {stats['error']}")

    print("\nDone!")


if __name__ == "__main__":
    main()
