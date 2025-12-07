#!/bin/bash
# Generate show pages from cached show data
# Reads from data/shows.json and creates content/shows/*.md
#
# OPTIMIZATION: This script precomputes related_shows (other shows by same artist)
# to avoid O(n²) lookups in Hugo templates. Each show page includes up to 4 slugs
# of other shows by the same artist, sorted newest-first.
#
# Without this precomputation, shows/single.html would need to scan all ~1300 shows
# for every single show page, resulting in ~1.7M comparisons at build time.

SHOWS_FILE="data/shows.json"
OUTPUT_DIR="content/shows"

# Check if shows.json exists
if [[ ! -f "$SHOWS_FILE" ]]; then
  echo "Error: $SHOWS_FILE not found. Run generate-show-cache.py first."
  exit 1
fi

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Create section index
cat > "$OUTPUT_DIR/_index.md" <<EOF
+++
title = "Shows"
date = $(date -u +"%Y-%m-%dT%H:%M:%SZ")
draft = false
noindex = false
+++
EOF

# Function to extract plain text from RadioCult description
extract_description() {
  local desc="$1"
  echo "$desc" | jq -r '
    if .content then
      [.content[]? |
        [.content[]? |
          if .type == "text" then .text
          elif .type == "hardBreak" then "\n"
          else "" end
        ] | join("")
      ] | join("\n\n")
    else
      ""
    end
  ' 2>/dev/null || echo ""
}

# Count shows
SHOW_COUNT=$(jq 'length' "$SHOWS_FILE")
echo "Generating $SHOW_COUNT show pages..."

# =============================================================================
# PASS 1: Build artist -> shows mapping for related_shows precomputation
# =============================================================================
# This creates a lookup table: artist_slug -> [show_slugs sorted by date desc]
# We limit to 8 shows per artist (template only displays 4, but we store extras
# in case the current show is in the list and needs to be excluded)
echo "Pass 1: Building artist -> shows mapping..."

declare -A ARTIST_SHOWS

# Use jq to extract all artist_slug -> show_slug pairs, sorted by start date (newest first)
# Only include shows that have an archive (mixcloud or soundcloud match)
# Output format: "artist_slug|show_slug" per line
while IFS='|' read -r artist_slug show_slug; do
  [[ -z "$artist_slug" || -z "$show_slug" ]] && continue

  # Append to existing list (or create new)
  if [[ -n "${ARTIST_SHOWS[$artist_slug]}" ]]; then
    ARTIST_SHOWS[$artist_slug]="${ARTIST_SHOWS[$artist_slug]}|$show_slug"
  else
    ARTIST_SHOWS[$artist_slug]="$show_slug"
  fi
done < <(jq -r '
  sort_by(.start) | reverse |
  .[] |
  select(.artistSlug != null and .artistSlug != "" and .slug != null and .slug != "") |
  select(.mixcloud_match != null or .soundcloud_match != null) |
  "\(.artistSlug)|\(.slug)"
' "$SHOWS_FILE")

echo "  Found ${#ARTIST_SHOWS[@]} artists with shows"

# =============================================================================
# PASS 2: Generate show pages with precomputed related_shows
# =============================================================================
echo "Pass 2: Generating show pages..."

jq -c '.[]' "$SHOWS_FILE" | while read -r show; do
  SLUG=$(echo "$show" | jq -r '.slug // empty')
  [[ -z "$SLUG" ]] && continue

  TITLE=$(echo "$show" | jq -r '.title // "Untitled"')
  EPISODE_INFO=$(echo "$show" | jq -r '.episode_info // empty')
  START=$(echo "$show" | jq -r '.start // empty')
  END=$(echo "$show" | jq -r '.end // empty')
  ARTIST_IDS=$(echo "$show" | jq -r '.artistIds // []')
  DESCRIPTION_JSON=$(echo "$show" | jq '.description // {}')
  MATCH_SCORE=$(echo "$show" | jq -r '.match_score // 0')

  # Append episode info to title if available
  if [[ -n "$EPISODE_INFO" ]]; then
    TITLE="$TITLE $EPISODE_INFO"
  fi

  # Mixcloud data
  MC_SLUG=$(echo "$show" | jq -r '.mixcloud_match.slug // empty')
  MC_NAME=$(echo "$show" | jq -r '.mixcloud_match.name // empty')
  MC_URL=$(echo "$show" | jq -r '.mixcloud_match.url // empty')
  MC_IMAGE=$(echo "$show" | jq -r '.mixcloud_match.pictures.large // .mixcloud_match.pictures.medium // empty')

  # SoundCloud data
  SC_ID=$(echo "$show" | jq -r '.soundcloud_match.id // empty')
  SC_URL=$(echo "$show" | jq -r '.soundcloud_match.url // empty')
  SC_IMAGE=$(echo "$show" | jq -r '.soundcloud_match.thumbnail // empty')
  SC_DESC=$(echo "$show" | jq -r '.soundcloud_match.description // empty')

  # Determine if show has any archive
  HAS_ARCHIVE="false"
  if [[ -n "$MC_SLUG" || -n "$SC_ID" ]]; then
    HAS_ARCHIVE="true"
  fi

  # Mixcloud description
  MC_DESC=$(echo "$show" | jq -r '.mixcloud_match.description // empty')

  # Get artist info directly from show data (populated by Python cache script)
  FIRST_ARTIST_ID=$(echo "$ARTIST_IDS" | jq -r '.[0] // empty')
  ARTIST_NAME=$(echo "$show" | jq -r '.artistName // empty')
  ARTIST_SLUG=$(echo "$show" | jq -r '.artistSlug // empty')

  # Format date
  SHOW_DATE=""
  if [[ -n "$START" ]]; then
    SHOW_DATE=$(date -d "$START" +"%Y-%m-%d" 2>/dev/null || echo "")
  fi

  # Extract RadioCult description
  RC_DESC=$(extract_description "$DESCRIPTION_JSON")

  # Pick the longest description (RadioCult, Mixcloud, or SoundCloud)
  RC_LEN=${#RC_DESC}
  MC_LEN=${#MC_DESC}
  SC_LEN=${#SC_DESC}

  DESCRIPTION="$RC_DESC"
  if [[ $MC_LEN -gt $RC_LEN && $MC_LEN -ge $SC_LEN ]]; then
    DESCRIPTION="$MC_DESC"
  elif [[ $SC_LEN -gt $RC_LEN && $SC_LEN -gt $MC_LEN ]]; then
    DESCRIPTION="$SC_DESC"
  fi

  # Escape quotes in strings for TOML
  TITLE_ESCAPED=$(echo "$TITLE" | sed 's/"/\\"/g')
  DESCRIPTION_ESCAPED=$(echo "$DESCRIPTION" | sed 's/"/\\"/g')
  ARTIST_NAME_ESCAPED=$(echo "$ARTIST_NAME" | sed 's/"/\\"/g')

  # ---------------------------------------------------------------------------
  # Build related_shows array (other shows by same artist, excluding self)
  # ---------------------------------------------------------------------------
  RELATED_SHOWS_TOML=""
  if [[ -n "$ARTIST_SLUG" && -n "${ARTIST_SHOWS[$ARTIST_SLUG]}" ]]; then
    # Split the pipe-delimited list and filter out current show
    IFS='|' read -ra ALL_SHOWS <<< "${ARTIST_SHOWS[$ARTIST_SLUG]}"
    RELATED_COUNT=0
    RELATED_SHOWS_TOML="related_shows = ["
    for related_slug in "${ALL_SHOWS[@]}"; do
      # Skip self
      [[ "$related_slug" == "$SLUG" ]] && continue
      # Limit to 4 related shows
      [[ $RELATED_COUNT -ge 4 ]] && break

      if [[ $RELATED_COUNT -gt 0 ]]; then
        RELATED_SHOWS_TOML+=", "
      fi
      RELATED_SHOWS_TOML+="\"$related_slug\""
      ((RELATED_COUNT++))
    done
    RELATED_SHOWS_TOML+="]"

    # If no related shows, don't include the field
    [[ $RELATED_COUNT -eq 0 ]] && RELATED_SHOWS_TOML=""
  fi

  FILE_PATH="$OUTPUT_DIR/$SLUG.md"

  # Write the frontmatter with optional related_shows
  cat > "$FILE_PATH" <<EOF
+++
title = "$TITLE_ESCAPED"
date = $SHOW_DATE
draft = false
noindex = false
show_start = "$START"
show_end = "$END"
artist_name = "$ARTIST_NAME_ESCAPED"
artist_slug = "$ARTIST_SLUG"
artist_id = "$FIRST_ARTIST_ID"
mixcloud_slug = "$MC_SLUG"
mixcloud_url = "$MC_URL"
mixcloud_image = "$MC_IMAGE"
soundcloud_id = "$SC_ID"
soundcloud_url = "$SC_URL"
soundcloud_image = "$SC_IMAGE"
has_archive = $HAS_ARCHIVE
match_score = $MATCH_SCORE
EOF

  # Add related_shows if present
  if [[ -n "$RELATED_SHOWS_TOML" ]]; then
    echo "$RELATED_SHOWS_TOML" >> "$FILE_PATH"
  fi

  # Close frontmatter and add description
  cat >> "$FILE_PATH" <<EOF
+++

$DESCRIPTION
EOF

done

echo "Generated show pages in $OUTPUT_DIR"
