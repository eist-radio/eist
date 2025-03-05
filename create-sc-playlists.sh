#!/bin/bash

# Set these variables before running the script
CLIENT_ID="your_client_id"  # Replace with your SoundCloud client ID
OAUTH_TOKEN="your_oauth_token"  # Replace with your OAuth token
USER_ID="eistcork"  # Replace with your SoundCloud user ID
ARTIST_NAME="$1"  # Artist name passed as the first argument

# API Base URL
API_URL="https://api.soundcloud.com"

# Function to check if the playlist exists
get_playlist_id() {
    curl -s -X GET "${API_URL}/users/${USER_ID}/playlists?oauth_token=${OAUTH_TOKEN}" | \
    jq -r --arg ARTIST "$ARTIST_NAME" '.[] | select(.title == $ARTIST) | .id'
}

# Function to create a playlist
create_playlist() {
    curl -s -X POST "${API_URL}/playlists?oauth_token=${OAUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "playlist": {
                "title": "'"${ARTIST_NAME}"'",
                "sharing": "public",
                "tracks": []
            }
        }' | jq -r '.id'
}

# Function to get track IDs matching the artist name as a tag
get_track_ids() {
    curl -s -X GET "${API_URL}/tracks?q=${ARTIST_NAME}&client_id=${CLIENT_ID}" | \
    jq -r '.[].id'
}

# Check if the playlist exists
PLAYLIST_ID=$(get_playlist_id)

# If playlist doesn't exist, create it
if [ -z "$PLAYLIST_ID" ]; then
    echo "Playlist not found. Creating new playlist..."
    PLAYLIST_ID=$(create_playlist)
else
    echo "Playlist already exists with ID: $PLAYLIST_ID"
fi

# Get track IDs with the artist's name as a tag
TRACK_IDS=$(get_track_ids | jq -sc '.')

# Associate tracks with the playlist
if [ -n "$TRACK_IDS" ]; then
    echo "Adding tracks to playlist..."
    curl -s -X PUT "${API_URL}/playlists/${PLAYLIST_ID}?oauth_token=${OAUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "playlist": {
                "tracks": '"${TRACK_IDS}"'
            }
        }'
    echo "Tracks added."
else
    echo "No matching tracks found."
fi
