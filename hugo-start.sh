#!/bin/bash
# Run data pipeline and start Hugo server
# Matches the flow in .github/workflows/preview.yml and AGENTS.md

set -e

# Load environment variables (API_KEY needed for artist pages)
source .env
export API_KEY

# Generate artist pages from RadioCult API
python3 generate-artist-pages.py

# Fetch pre-matched show data from EIST API
python3 fetch-shows-from-api.py

# Generate Hugo pages for shows
python3 generate-show-pages.py

# Start Hugo dev server
hugo server --disableFastRender
