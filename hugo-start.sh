#!/bin/bash
# Source the API key, generate markdown files, start Hugo

source .env && export API_KEY
python3 generate-artist-pages.py
hugo server --disableFastRender
