# éist radio website

[![Deploy Hugo site to Pages](https://github.com/eist-radio/eist/actions/workflows/deploy.yml/badge.svg)](https://github.com/eist-radio/eist/actions/workflows/deploy.yml)

Source files for https://eist.radio

# Getting started

Install Hugo, see: https://gohugo.io/installation/

# Adding content and building docs

Add a new markdown file with a TOML format header into the `content/` folder:

```markdown
+++
title = "The title!"
date = 2024-11-19T20:23:18Z
draft = false
+++

Add some text!

```

Add `noindex = true` if you don't want the page to be indexed by the Goog.

# Checking your build locally

Install Python dependencies:

```bash
pip3 install thefuzz python-Levenshtein requests
```

Get the API keys from RadioCult and SoundCloud, and save them in a `.env` file locally:

```bash
API_KEY=your_radiocult_key
SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id
SOUNDCLOUD_CLIENT_SECRET=your_soundcloud_client_secret
```

Then source the `.env` file and run the dev server:

```bash
if [ -f ~/.env ]; then
    set -a
    source ~/.env
    set +a
fi
python3 generate-artist-pages.py
python3 generate-show-cache.py
python3 generate-show-pages.py
hugo server --disableFastRender
```

# Deploying previews with Surge

PR previews are deployed using Surge. Preview links are posted in the PR.

# Open source :)

Website is based on this Hugo template: https://github.com/1bl4z3r/hermit-V2
