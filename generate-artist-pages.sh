#!/bin/bash
# Generate markdown files for artists from the RadioCult API
# Running locally - source .env && export API_KEY

STATION_ID="eist-radio"
ARTISTS_URL="https://api.radiocult.fm/api/station/${STATION_ID}/artists"
OUTPUT_DIR="content/artists"
OUTPUT_FILE="content/artists.md"
DEFAULT_IMAGE="/no-artist.png"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Fetch artist data
ARTISTS_JSON=$(curl -s -X GET "$ARTISTS_URL" -H "x-api-key: $API_KEY" -H "Content-Type: application/json")

# Validate JSON response
if ! echo "$ARTISTS_JSON" | jq empty >/dev/null 2>&1; then
  echo "Error: API response is not valid JSON."
  echo "Response: $ARTISTS_JSON"
  exit 1
fi

# Check if API response contains artists
ARTISTS_COUNT=$(echo "$ARTISTS_JSON" | jq '.artists | length')
if [[ "$ARTISTS_COUNT" -eq 0 ]]; then
  echo "Error: No artists found."
  exit 1
fi

# Normalize filenames
normalize_filename() {
  echo "$1" | sed 's/[ɅØøæÆ]/-/g' | iconv -f UTF-8 -t ASCII//TRANSLIT | tr -cs 'a-zA-Z0-9' '-' | sed -e 's/^-*//;s/-*$//;s/--/-/g' | tr '[:upper:]' '[:lower:]'
}

# Generate social media links with <br> before the first link
generate_social_links() {
    local socials_json="$1"
    local links=()

    # Check if socials_json is empty or invalid
    if [[ -z "$socials_json" || "$socials_json" == "null" ]]; then
        echo ""
        return
    fi

    local platforms=("soundcloud" "instagram" "facebook" "mixcloud" "site")

    # Loop through the platforms to build the links
    for platform in "${platforms[@]}"; do
        local url=$(echo "$socials_json" | jq -r ".${platform} // empty")
        if [[ -n "$url" ]]; then
            local label
            case "$platform" in
                soundcloud) label="SoundCloud" ;;
                instagram) label="Instagram" ;;
                facebook) label="Facebook" ;;
                mixcloud) label="Mixcloud" ;;
                site) label="Website" ;;
            esac

            # Construct the full URL for platforms other than "site"
            if [[ "$platform" != "site" ]]; then
                url="https://www.${platform}.com/${url}"
            fi

            # Add the link to the links array
            links+=("[$label]($url)")
        fi
    done

    # Join the links with " / " separator and return the result
    if [[ ${#links[@]} -gt 0 ]]; then
      echo "${links[@]}" | sed 's/ / \/ /g'
    else
      echo ""
    fi
}

# Process each artist
echo "$ARTISTS_JSON" | jq -c '.artists[]' | while read -r artist; do
  ARTIST_NAME=$(echo "$artist" | jq -r '.name')
  ARTIST_BIO=$(echo "$artist" | jq -r '.description.content[0].content[0].text // ""')
  ARTIST_IMAGE_URL=$(echo "$artist" | jq -r '.logo["1024x1024"] // ""')
  ARTIST_SOCIALS=$(echo "$artist" | jq -r '.socials')
  
  [[ -z "$ARTIST_IMAGE_URL" ]] && ARTIST_IMAGE_URL="$DEFAULT_IMAGE"
  
  SOCIAL_LINKS=$(generate_social_links "$ARTIST_SOCIALS")
  ARTIST_FILENAME=$(normalize_filename "$ARTIST_NAME")
  FILE_PATH="$OUTPUT_DIR/$ARTIST_FILENAME.md"

  # Write artist markdown files
  cat > "$FILE_PATH" <<EOF
+++
description = "$ARTIST_NAME"
date = $(date +%Y-%m-%d)
draft = false
noindex = false
+++

## $ARTIST_NAME

<div class="artist-image-container">
    <img src="$ARTIST_IMAGE_URL" alt="$ARTIST_NAME" class="artist-image">
</div>

$ARTIST_BIO

$SOCIAL_LINKS

EOF
done

echo "Generated artist pages"

# Generate artists index markdown file
cat > "$OUTPUT_FILE" <<EOF
+++
title = "Artists"
date = $(date -u +"%Y-%m-%dT%H:%M:%SZ")
draft = false
noindex = false
+++
EOF

# Collect artist links into a single string
while IFS= read -r row; do
  ARTIST_NAME=$(echo "$row" | jq -r '.name')
  ARTIST_SLUG=$(normalize_filename "$ARTIST_NAME")

  if [[ -n "$ARTIST_LINKS" ]]; then
    ARTIST_LINKS+=" / "
  fi
  ARTIST_LINKS+="[$ARTIST_NAME](/artists/$ARTIST_SLUG)"
done < <(echo "$ARTISTS_JSON" | jq -c '.artists[]')

echo "$ARTIST_LINKS" >> "$OUTPUT_FILE"

echo "Generated $OUTPUT_FILE"