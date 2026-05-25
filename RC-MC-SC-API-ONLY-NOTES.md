# RC-MC-SC API-Calls-Only: Notes & Discoveries

This file documents how the `demo/rc-sc-api-calls-only` branch sources show archive
data, what we discovered about the Mixcloud API during implementation, and what
station admins need to know to keep the system working.

---

## How it works

### The old approach (replaced)

The previous `generate-show-cache.py` fetched the full eistcork Mixcloud and SoundCloud
accounts, then tried to attribute each track to an artist by parsing the track title
(looking for patterns like "Artist - Title") and fuzzy-matching the extracted prefix
against RC artist names, slugs, and username tags.

This was brittle, inconsistent, and wrong in principle. Title formats vary; some shows
have no artist prefix at all; fuzzy matching produced false positives.

### The new approach

Attribution is now entirely explicit. Station admins tag artist profiles in RadioCult
with structured tags that say exactly how to find that artist's shows. No parsing,
no matching, no guessing.

The script reads those tags, makes one API call per artist, and builds the archive.

---

## RadioCult tags

Tags are set on artist profiles in the RadioCult admin UI. The supported tags:

### `MC-USERNAME_X`

The artist is credited as a host on uploads to the eistcork Mixcloud account.
X is their Mixcloud username (case-insensitive).

**What the script does:** Queries `X`'s own Mixcloud upload feed. When eistcork uploads
a show and credits the artist as host, that show appears in the artist's feed even though
`owner` remains `eistcork`. Stops incrementally when known slugs are found; results are
cached in `data/mixcloud-artist-cache.json`.

**Player URL:** `https://www.mixcloud.com/X/` (the artist's own page).

### `HOST-MC-PLAYLIST_P`

The artist's shows are collected in a Mixcloud playlist named P.

- If `MC-USERNAME_X` is also set: the playlist lives on the **artist's own** Mixcloud
  account (`mixcloud.com/X/playlists/P`). The script fetches it from there.
- If `MC-USERNAME_X` is absent: the playlist lives on the **eistcork** Mixcloud account
  (`mixcloud.com/eistcork/playlists/P`). The script fetches it from there.

**When to use this instead of MC-USERNAME_ alone:** When the artist has a curated playlist
that is the intended source of truth — particularly useful when their upload feed contains
non-éist content (guest sets, external shows, etc.) that you don't want in the archive.
With a playlist, the admin controls exactly which shows are included.

P is URL-decoded and lowercased when used in API calls. The tag value may be URL-encoded
(e.g. `RADIO-D%C3%A9-COLLAGE` → `radio-dé-collage`).

### `SC-USERNAME_X`

The artist has their own SoundCloud account at `soundcloud.com/X`.

**What the script does:** If `HOST-SC-PLAYLIST_P` is also set, fetches that playlist
(always fresh — playlists are curated). Otherwise fetches all tracks from the user's
account incrementally, caching in `data/soundcloud-artist-cache.json`.

### `HOST-SC-PLAYLIST_P`

The artist's shows are in a SoundCloud playlist P on their own account
(`soundcloud.com/X/sets/P`, where X comes from `SC-USERNAME_X`).

**Note:** `SC-USERNAME_X` must also be set, otherwise there is no account to resolve P
against and the fetch is silently skipped.

---

## Tag precedence summary

| Tags set | Mixcloud source | SoundCloud source |
|---|---|---|
| `MC-USERNAME_X` only | X's upload feed (incremental) | — |
| `MC-USERNAME_X` + `HOST-MC-PLAYLIST_P` | Playlist P on X's account (fresh) | — |
| `HOST-MC-PLAYLIST_P` only | Playlist P on eistcork account (fresh) | — |
| `SC-USERNAME_X` only | — | All tracks on X's account (incremental) |
| `SC-USERNAME_X` + `HOST-SC-PLAYLIST_P` | — | Playlist P on X's account (fresh) |
| Mix of the above | Combined | Combined |

Artists with no supported tags get no archive shows — not an error.

---

## Mixcloud API: what we actually found

The `/status` spec assumed Mixcloud's GraphQL API would expose a `hosts` field on
`Cloudcast`, allowing us to query all eistcork cloudcasts and filter by host. **This
field does not exist.** Introspection of the live GraphQL schema confirmed:

- `hosts` — not a field on `Cloudcast`
- `creatorAttributions` — exists but is always empty for eistcork uploads
- `ghostAttributions` — exists but is always empty for eistcork uploads
- `tagList` — exists but is always empty for eistcork uploads

**The actual mechanism:** Mixcloud's host credit system works at the feed level. When
eistcork uploads a show and credits an artist as host (by their Mixcloud username),
that cloudcast appears in the artist's own `uploads` feed — even though `owner.username`
remains `eistcork`. Querying `userLookup(username: X) { uploads { ... } }` returns
exactly the shows credited to X.

For artists with a `HOST-MC-PLAYLIST_` tag, the playlist lives under their own account
and is fetched via:

```
userLookup(username: X) {
  playlists(first: 20) {
    edges {
      node {
        slug
        items(first: 500) {
          edges { node { cloudcast { ... } } }
        }
      }
    }
  }
}
```

Note: Mixcloud's GraphQL exposes playlists via `playlists` (plural, a connection), not
`playlist(slug: ...)`. The script lists all playlists and filters by slug client-side.
This is fine because artists typically have 1–5 playlists.

---

## Caching

### Mixcloud
- **Playlist artists** (`HOST-MC-PLAYLIST_P` set): fetched fresh every run. Playlists
  are small (typically ≤ 50 shows) and represent the admin's curated view.
- **Upload-feed artists** (`MC-USERNAME_X` only): incremental. First run fetches all;
  subsequent runs stop at the first known slug.
- Cache file: `data/mixcloud-artist-cache.json` — keyed by `{username}:uploads`.

### SoundCloud
- **Playlist artists** (`HOST-SC-PLAYLIST_P` set): fetched fresh every run.
- **All-tracks artists** (`SC-USERNAME_X` only): incremental by track ID.
- Cache file: `data/soundcloud-artist-cache.json` — keyed by SC username.

Run with `--full` to ignore all caches and do a complete refresh.

---

## Known issues / bad tags (as of May 2026)

These artists have tags that don't resolve correctly. The script logs a warning and
produces 0 shows for them — it does not crash.

| Artist | Tag | Problem |
|---|---|---|
| aswemaysink | `MC-USERNAME_ASWEMAYSINK` | Mixcloud user not found |
| communionhost | `HOST-MC-PLAYLIST_COMMUNIONHOST` | Playlist not found on communionhost account |
| cawhul | `HOST-SC-PLAYLIST_MIXEDBAG` | SoundCloud playlist not found (private or wrong slug) |
| japhet santana | `HOST-SC-PLAYLIST_SONIC-CORE-OF-NEW-STATUES` | SoundCloud playlist not found |

Fix: correct the tag values in the RadioCult admin UI.

---

## Adding a new artist to the archive

1. Go to the artist's profile in RadioCult admin.
2. Find their Mixcloud username (from their Mixcloud profile URL).
3. Add `MC-USERNAME_{THEIR_USERNAME}` to their tags.
4. If they have a curated Mixcloud playlist of their éist shows, also add
   `HOST-MC-PLAYLIST_{PLAYLIST_SLUG}` (slug as it appears in the URL, uppercased).
5. Repeat for SoundCloud with `SC-USERNAME_` and optionally `HOST-SC-PLAYLIST_`.
6. Run `python3 generate-show-cache.py` — the new shows appear automatically.

Tag values are case-insensitive (normalised to lowercase internally). Leading/trailing
whitespace in tag values is stripped automatically.

---

## Output files

| File | Contents |
|---|---|
| `data/shows.json` | All archive shows, newest first |
| `data/upcoming_schedule.json` | Next 30 days from RadioCult schedule |
| `data/api-shows-cache.json` | Same shows + generation metadata |
| `data/mixcloud-artist-cache.json` | Per-artist Mixcloud upload feed cache |
| `data/soundcloud-artist-cache.json` | Per-artist SoundCloud track cache |
| `data/cache-meta.json` | Run stats (counts, timestamps) |
