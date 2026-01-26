#!/bin/bash
# Source API keys, run data pipeline, start Hugo server
# Matches the flow in .github/workflows/preview.yml and AGENTS.md

set -e

# Load environment variables
source .env
export API_KEY SOUNDCLOUD_CLIENT_ID SOUNDCLOUD_CLIENT_SECRET

# Generate artist pages from RadioCult API
python3 generate-artist-pages.py

# Generate show cache from SoundCloud/Mixcloud APIs
python3 generate-show-cache.py

# Generate Hugo pages for shows
python3 generate-show-pages.py

# Start Hugo dev server
hugo server --disableFastRender
