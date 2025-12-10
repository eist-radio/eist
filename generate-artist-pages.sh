#!/bin/bash
# Generate markdown files for artists from the RadioCult API
# This script calls generate-artist-pages.py for the actual generation.
#
# Running locally: source .env && export API_KEY && ./generate-artist-pages.sh

# Run the Python script for artist page generation (much faster than bash)
python3 generate-artist-pages.py

# Install deps and run full pipeline for PR preview
pip3 install thefuzz python-Levenshtein yt-dlp requests || true
python3 scripts/detect-faces.py || true
python3 generate-show-cache.py || true
python3 generate-show-pages.py || true
