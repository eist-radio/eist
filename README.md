# Éist radio

Hacking a website together one kludge at a time. 

# Getting started

Install Hugo: https://gohugo.io/installation/

# Adding content and building docs

Add a new markdown file with a TOML format header into the content/ folder:

```markdown
+++
title = "The title!"
date = 2024-11-19T20:23:18Z
draft = false
+++

Start typing...

```

# Checking your build locally

Get the API key from RadioCult and save it in a `.env` file locally, for example:

```cmd
cat .env
API_KEY=<REDACTED>
```

Then:

```cmd
source .env
export API_KEY
hugo server
```

# Deploying previews with Surge

PR previews are deployed using Surge. Preview links are posted in the PR.


# Open source :)

Website is based on this Hugo template: https://github.com/1bl4z3r/hermit-V2
