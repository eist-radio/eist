#!/bin/bash
# Get stuff from RadioCult API

# Source and export the API key ($API_KEY) from the .env file
source .env

export API_KEY

STATION_ID="eist-radio"

URL="https://api.radiocult.fm/api/station/${STATION_ID}/schedule/live"

ARTISTS_URL="https://api.radiocult.fm/api/station/${STATION_ID}/artists"

TIMEZONE=$(timedatectl | awk '/Time zone/ {print $3}')

SCHEDULE_URL="https://api.radiocult.fm/api/station/${STATION_ID}/schedule?startDate=$(date -I)T00:00:00Z&endDate=$(date -I -d '+7 days')T23:59:59Z&timezone=${TIMEZONE}"

SCHEDULE=$(curl -s -X GET "$SCHEDULE_URL" \
  -H "Content-Type: application/json" | jq '[.schedules[] | {title, startDateUtc}]')

# Make the API request and extract the first element of artistIds using jq
ARTIST_ID=$(curl -s -X GET "$URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.result.content.artistIds[0]')

ARTIST_URL="https://api.radiocult.fm/api/station/${STATION_ID}/artists/${ARTIST_ID}"

ARTISTS_ARRAY=$(curl -s -X GET "$ARTISTS_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq)

SHOW_DESC=$(curl -s -X GET "$URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.result.content.description.content[0].content[0].text')

BROADCAST_STATUS=$(curl -s -X GET "$URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.result.status')

SHOW_TITLE=$(curl -s -X GET "$URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.result.content.title')

# Return the artist name
ARTIST_NAME=$(curl -s -X GET "$ARTIST_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.artist.name')

# Return the artist bio
ARTIST_BIO=$(curl -s -X GET "$ARTIST_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.artist.description.content[0].content[0].text')

# Return the artist image
ARTIST_LOGO_URL=$(curl -s -X GET "$ARTIST_URL" \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" | jq -r '.artist.logo["256x256"]')

echo "${ARTIST_ID}"

echo "${BROADCAST_STATUS}"

echo "${SHOW_DESC}"

echo "${SHOW_TITLE}"

echo "${ARTIST_NAME}"

echo "${ARTIST_BIO}"

echo "${ARTIST_LOGO_URL}"

echo "${ARTISTS_ARRAY}"

echo "${SCHEDULE}"
