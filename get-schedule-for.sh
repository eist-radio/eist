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

# Fetch the schedule and format the output
SCHEDULE=$(curl -s -X GET "$SCHEDULE_URL" \
  -H "Content-Type: application/json" | jq -r '
  .schedules[]? | 
    select(.start and .end and .title) | 
    (.start | sub("\\.\\d+Z$"; "Z") | fromdate | strftime("%-I%p")) + "-" +
    (.end | sub("\\.\\d+Z$"; "Z") | fromdate | strftime("%-I%p")) + " " +
    .title')

# Print the formatted schedule
echo -e "\n${DAY_OF_WEEK^^}"
echo -e "$SCHEDULE" | while IFS= read -r line; do
  # Format show titles with the correct padding
  title=$(echo "$line" | sed 's/\([A-Za-z0-9 -]*\)\([0-9:APM]*\)$/\1/')
  timeslot=$(echo "$line" | sed 's/.*\([0-9:APM]*\)$/\1/')
  
  # Remove ':00' from times
  timeslot=$(echo "$timeslot" | sed 's/:00//')
  
  printf "%-40s %s\n" "$title" "$timeslot"
done
