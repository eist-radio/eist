#!/bin/bash
# Generate Markdown files for artists from RadioCult API

STATION_ID="eist-radio"
ARTISTS_URL="https://api.radiocult.fm/api/station/${STATION_ID}/artists"
OUTPUT_DIR="content/artists"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Fetch all artists
ARTISTS_ARRAY=$(curl -s -X GET "$ARTISTS_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json")

# Function to normalize filenames
normalize_filename() {
  echo "$1" | iconv -f UTF-8 -t ASCII//TRANSLIT | tr -cs 'a-zA-Z0-9' '-' | sed 's/-$//'
}

# Process each artist
echo "$ARTISTS_ARRAY" | jq -c '.artists[]' | while read -r artist; do
  ARTIST_NAME=$(echo "$artist" | jq -r '.name')
  ARTIST_BIO=$(echo "$artist" | jq -r '.description.content[0].content[0].text // "No bio available"')
  ARTIST_IMAGE_URL=$(echo "$artist" | jq -r '.logo["1024x1024"] // ""')

  # Normalize artist name for filename
  ARTIST_FILENAME=$(normalize_filename "$ARTIST_NAME")
  FILE_PATH="$OUTPUT_DIR/$ARTIST_FILENAME.md"

  # Write Markdown file
  cat > "$FILE_PATH" <<EOF
+++
description = "$ARTIST_NAME"
date = $(date +%Y-%m-%d)
draft = false
noindex = false
+++


<div id="artists-output">
</div>
<div id="pagination"></div>

{{< artist >}}
EOF
done