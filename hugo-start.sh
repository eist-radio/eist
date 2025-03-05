#!/bin/bash
# Source the API key, generate markdown files, start Hugo

source .env && export API_KEY
./generate-artist-pages.sh
hugo server --disableFastRender
