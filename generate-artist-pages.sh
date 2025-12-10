#!/bin/bash
# Generate markdown files for artists from the RadioCult API
# This script calls generate-artist-pages.py for the actual generation.
#
# Running locally: source .env && export API_KEY && ./generate-artist-pages.sh

python3 generate-artist-pages.py
