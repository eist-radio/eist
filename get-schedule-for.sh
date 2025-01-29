#!/bin/bash
# Get show titles for a specified day next week

# Source and export the API key ($API_KEY) from the .env file
source .env

export API_KEY

STATION_ID="eist-radio"

# Ensure a day is passed as an argument
if [ -z "$1" ]; then
  echo "Usage: $0 <day-of-week>"
  exit 1
fi

# Convert input to lowercase
DAY_OF_WEEK=$(echo "$1" | tr '[:upper:]' '[:lower:]')

# Validate input
VALID_DAYS=("monday" "tuesday" "wednesday" "thursday" "friday" "saturday" "sunday")
if [[ ! " ${VALID_DAYS[*]} " =~ " $DAY_OF_WEEK " ]]; then
  echo "Invalid day. Please enter a valid day of the week."
  exit 1
fi

# Calculate the date for the next occurrence of the specified day
TARGET_DATE=$(date -d "next $DAY_OF_WEEK" +%Y-%m-%d)

# Get the timezone
TIMEZONE=$(timedatectl | awk '/Time zone/ {print $3}')

# Construct the URL for the schedule API
SCHEDULE_URL="https://api.radiocult.fm/api/station/${STATION_ID}/schedule?startDate=${TARGET_DATE}T00:00:00Z&endDate=${TARGET_DATE}T23:59:59Z&timezone=${TIMEZONE}"

# Fetch the schedule and extract the show titles
SCHEDULE=$(curl -s -X GET "$SCHEDULE_URL" \
  -H "Content-Type: application/json" | jq -r '.schedules[]?.title // "No title available"')

# Print the show titles for the specified day
echo "Shows for $DAY_OF_WEEK, ${TARGET_DATE}:"
echo "$SCHEDULE"
