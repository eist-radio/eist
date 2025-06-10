#!/bin/bash
# Generate markdown files for artists from the RadioCult API
# Running locally - source .env && export API_KEY

STATION_ID="eist-radio"
ARTISTS_URL="https://api.radiocult.fm/api/station/${STATION_ID}/artists"
OUTPUT_DIR="content/artists"
OUTPUT_FILE="content/artists.md"
DEFAULT_IMAGE="/eist_online.png"

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

# Extract and clean artist tag values
extract_tag_value() {
  local tags="$1"
  local prefix="$2"
  echo "$tags" | jq -r --arg prefix "$prefix" '.[] | select(startswith($prefix)) | sub($prefix; "")' | tr '[:upper:]' '[:lower:]'
}

# Generate social media links with <br> before the first link
generate_social_links() {
  local socials_json="$1"
  local links=()

  [[ -z "$socials_json" || "$socials_json" == "null" ]] && echo "" && return

  # API keys to check
  local keys=("soundcloud" "instagramHandle" "mixcloud" "site")

  for key in "${keys[@]}"; do
    # extract value
    local val
    val=$(echo "$socials_json" | jq -r ".${key} // empty")
    [[ -z "$val" ]] && continue

    # map to label
    local label
    case "$key" in
      soundcloud)      label="SoundCloud"    ;;
      mixcloud)        label="Mixcloud"      ;;
      instagramHandle) label="Instagram"     ;;
      site)            label="Website"       ;;
    esac

    # build URL
    local url
    if [[ "$key" == "instagramHandle" ]]; then
      url="https://www.instagram.com/$val"
    else
      # soundcloud or mixcloud
      [[ "$val" =~ ^https?:// ]] && url="$val" || url="https://www.${key}.com/$val"
    fi

    links+=("[$label]($url)")
  done

  # Join the links with " / " separator and return the result
  if [[ ${#links[@]} -gt 0 ]]; then
    echo "${links[@]}" | sed 's/ / \/ /g'
  fi
}


# Process each artist
echo "$ARTISTS_JSON" | jq -c '.artists[]' | while read -r artist; do
  ARTIST_NAME=$(echo "$artist" | jq -r '.name // empty')
  [[ -z "$ARTIST_NAME" ]] && continue
  ARTIST_TAGS=$(echo "$artist" | jq -c '.tags')
  ARTIST_IMAGE_URL=$(echo "$artist" | jq -r '.logo["1024x1024"] // ""')
  ARTIST_SOCIALS=$(echo "$artist" | jq -r '.socials')
  SOCIAL_LINKS=$(generate_social_links "$ARTIST_SOCIALS")
  ARTIST_FILENAME=$(normalize_filename "$ARTIST_NAME")
  FILE_PATH="$OUTPUT_DIR/$ARTIST_FILENAME.md"
  # Handle text formatting
  ARTIST_BIO=$(echo "$artist" | jq -r '
    if .description and .description.content then
      [.description.content[]? |
        [.content[]? |
          if .type == "text" then .text
          elif .type == "hardBreak" then "\n"
          else "" end
        ] | join("")
      ] | join("\n\n")
    else
      ""
    end
  ')

  # If artist image is empty, use a default image
  [[ -z "$ARTIST_IMAGE_URL" ]] && ARTIST_IMAGE_URL="$DEFAULT_IMAGE"

  # Extract artist tag values
  MC_USERNAME=$(extract_tag_value "$ARTIST_TAGS" "MC-USERNAME_")
  SC_USERNAME=$(extract_tag_value "$ARTIST_TAGS" "SC-USERNAME_")
  HOST_SC_PLAYLIST=$(extract_tag_value "$ARTIST_TAGS" "HOST-SC-PLAYLIST_")
  HOST_MC_PLAYLIST=$(extract_tag_value "$ARTIST_TAGS" "HOST-MC-PLAYLIST_")
  EIST_MC_PLAYLIST=$(extract_tag_value "$ARTIST_TAGS" "EIST-MC-PLAYLIST_")

  if [[ -n "$MC_USERNAME" || -n "$SC_USERNAME" || -n "$HOST_SC_PLAYLIST" || -n "$HOST_MC_PLAYLIST" || -n "$EIST_MC_PLAYLIST" ]]; then
    LISTEN_BACK="#### Listen back"
  else
    LISTEN_BACK=""
  fi

  # Check if the artist mixcloud username exists as an eistcork Mixcloud host
  if [[ -n "$MC_USERNAME" ]]; then
    LATEST_MIXCLOUD="
<iframe width=\"100%\" height=\"60\" src=\"https://player-widget.mixcloud.com/widget/iframe/?hide_cover=1&mini=1&feed=/eistcork/hosts/$MC_USERNAME/\" frameborder=\"0\" ></iframe>"
  else
    LATEST_MIXCLOUD=""
  fi

  # Check if the artist SoundCloud username + playlist exists
  if [[ -n "$SC_USERNAME" && -n "$HOST_SC_PLAYLIST" ]]; then
    SC_PLAYLIST="
[SoundCloud archive](https://soundcloud.com/$SC_USERNAME/sets/$HOST_SC_PLAYLIST)"
  else
    SC_PLAYLIST=""
  fi

  # Check if the eistcork Mixcloud playlist exists
  if [[ -n "$EIST_MC_PLAYLIST" ]]; then
    MC_PLAYLIST="
[éist Mixcloud archive](https://www.mixcloud.com/eistcork/playlists/$EIST_MC_PLAYLIST)"
  else
    MC_PLAYLIST=""
  fi

  # Check if the artist Mixcloud username + playlist exists
  if [[ -n "$MC_USERNAME" && -n "$HOST_MC_PLAYLIST" ]]; then
    MC_ARTIST_PLAYLIST="
[Mixcloud archive](https://mixcloud.com/$MC_USERNAME/playlists/$HOST_MC_PLAYLIST)"
  else
    MC_ARTIST_PLAYLIST=""
  fi

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

$LISTEN_BACK

$LATEST_MIXCLOUD

$MC_PLAYLIST

$MC_ARTIST_PLAYLIST

$SC_PLAYLIST

EOF
done

echo "Generated artist pages"

# Generate artists index
cat > "$OUTPUT_FILE" <<EOF
+++
title = "Artists"
date = $(date -u +"%Y-%m-%dT%H:%M:%SZ")
draft = false
noindex = false
+++
EOF

ARTIST_LINKS=""
while IFS= read -r row; do
  ARTIST_NAME=$(echo "$row" | jq -r '.name // empty')
  [[ -z "$ARTIST_NAME" ]] && continue

  SLUG=$(normalize_filename "$ARTIST_NAME")
  [[ -z "$ARTIST_LINKS" ]] || ARTIST_LINKS+=" / "
  ARTIST_LINKS+="[$ARTIST_NAME](/artists/$SLUG)"
done < <(echo "$ARTISTS_JSON" | jq -c '.artists[]')

echo "$ARTIST_LINKS" >> "$OUTPUT_FILE"

echo "Generated $OUTPUT_FILE"
