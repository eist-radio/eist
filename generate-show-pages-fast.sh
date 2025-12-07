#!/bin/bash
# Generate show pages from cached show data (OPTIMIZED VERSION)
# Reads from data/shows.json and creates content/shows/*.md
#
# OPTIMIZATION: This version extracts all fields in a single jq call per show,
# reducing subprocess overhead from ~27,000 jq calls to ~1,300.
# Expected runtime: ~7-10 seconds (vs ~2.5 minutes for the original)
#
# For even faster generation (~0.2s), use generate-show-pages.py instead.

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

# =============================================================================
# PASS 1: Build artist -> shows mapping for related_shows precomputation
# =============================================================================
echo "Pass 1: Building artist -> shows mapping..."

declare -A ARTIST_SHOWS

# Single jq call to extract all artist_slug -> show_slug pairs
while IFS='|' read -r artist_slug show_slug; do
  [[ -z "$artist_slug" || -z "$show_slug" ]] && continue

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
# PASS 2: Generate show pages with single jq call extracting all fields
# =============================================================================
echo "Pass 2: Generating show pages..."

# Count shows
SHOW_COUNT=$(jq 'length' "$SHOWS_FILE")
echo "  Processing $SHOW_COUNT shows..."

# Use a single jq command to output all fields separated by a delimiter
# We use ASCII Unit Separator (0x1F) which won't appear in any text data
# Fields: slug, title, episode_info, start, end, artist_id, artist_name, artist_slug,
#         mc_slug, mc_url, mc_image, mc_desc, sc_id, sc_url, sc_image, sc_desc,
#         match_score, rc_desc
#
# Note: We use awk to parse because bash's 'read' with IFS skips consecutive empty fields
DELIM=$'\x1F'  # ASCII Unit Separator

jq -r '.[] | [
  (.slug // ""),
  (.title // "Untitled"),
  (.episode_info // ""),
  (.start // ""),
  (.end // ""),
  (.artistIds[0] // ""),
  (.artistName // ""),
  (.artistSlug // ""),
  (.mixcloud_match.slug // ""),
  (.mixcloud_match.url // ""),
  (.mixcloud_match.pictures.large // .mixcloud_match.pictures.medium // ""),
  ((.mixcloud_match.description // "") | gsub("\n"; "\\n") | gsub("\u001f"; " ")),
  ((.soundcloud_match.id // "") | tostring | if . == "null" then "" else . end),
  (.soundcloud_match.url // ""),
  (.soundcloud_match.thumbnail // ""),
  ((.soundcloud_match.description // "") | gsub("\n"; "\\n") | gsub("\u001f"; " ")),
  (.match_score // 0),
  (if .description.content then
    [.description.content[]? |
      [.content[]? |
        if .type == "text" then .text
        elif .type == "hardBreak" then "\\n"
        else "" end
      ] | join("")
    ] | join("\\n\\n") | gsub("\u001f"; " ")
  else "" end)
] | join("\u001f")' "$SHOWS_FILE" | while IFS="$DELIM" read -r SLUG TITLE EPISODE_INFO START END \
    FIRST_ARTIST_ID ARTIST_NAME ARTIST_SLUG \
    MC_SLUG MC_URL MC_IMAGE MC_DESC \
    SC_ID SC_URL SC_IMAGE SC_DESC \
    MATCH_SCORE RC_DESC; do

  # Skip if no slug
  [[ -z "$SLUG" ]] && continue

  # Append episode info to title if available
  if [[ -n "$EPISODE_INFO" ]]; then
    TITLE="$TITLE $EPISODE_INFO"
  fi

  # Format date from ISO string
  SHOW_DATE=""
  if [[ -n "$START" ]]; then
    SHOW_DATE=$(date -d "$START" +"%Y-%m-%d" 2>/dev/null || echo "")
  fi

  # Determine if show has any archive
  HAS_ARCHIVE="false"
  if [[ -n "$MC_SLUG" || -n "$SC_ID" ]]; then
    HAS_ARCHIVE="true"
  fi

  # Pick the longest description
  RC_LEN=${#RC_DESC}
  MC_LEN=${#MC_DESC}
  SC_LEN=${#SC_DESC}

  DESCRIPTION="$RC_DESC"
  if [[ $MC_LEN -gt $RC_LEN && $MC_LEN -ge $SC_LEN ]]; then
    DESCRIPTION="$MC_DESC"
  elif [[ $SC_LEN -gt $RC_LEN && $SC_LEN -gt $MC_LEN ]]; then
    DESCRIPTION="$SC_DESC"
  fi

  # Convert escaped newlines back to real newlines for markdown content
  DESCRIPTION=$(echo -e "$DESCRIPTION")

  # Escape quotes in strings for TOML
  TITLE_ESCAPED=$(echo "$TITLE" | sed 's/"/\\"/g')
  ARTIST_NAME_ESCAPED=$(echo "$ARTIST_NAME" | sed 's/"/\\"/g')

  # Build related_shows array
  RELATED_SHOWS_TOML=""
  if [[ -n "$ARTIST_SLUG" && -n "${ARTIST_SHOWS[$ARTIST_SLUG]}" ]]; then
    IFS='|' read -ra ALL_SHOWS <<< "${ARTIST_SHOWS[$ARTIST_SLUG]}"
    RELATED_COUNT=0
    RELATED_SHOWS_TOML="related_shows = ["
    for related_slug in "${ALL_SHOWS[@]}"; do
      [[ "$related_slug" == "$SLUG" ]] && continue
      [[ $RELATED_COUNT -ge 4 ]] && break
      if [[ $RELATED_COUNT -gt 0 ]]; then
        RELATED_SHOWS_TOML+=", "
      fi
      RELATED_SHOWS_TOML+="\"$related_slug\""
      ((RELATED_COUNT++))
    done
    RELATED_SHOWS_TOML+="]"
    [[ $RELATED_COUNT -eq 0 ]] && RELATED_SHOWS_TOML=""
  fi

  FILE_PATH="$OUTPUT_DIR/$SLUG.md"

  # Write frontmatter
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
