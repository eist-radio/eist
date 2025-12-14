"""
Match Mixcloud/SoundCloud archives to RadioCult shows.

This module contains the core matching logic for associating uploaded archives
(from Mixcloud and SoundCloud) with their corresponding RadioCult broadcast shows.

The matching algorithm uses:
1. Date extraction from archive titles (primary signal)
2. Artist platform usernames (MC-USERNAME_, SC-USERNAME_ tags)
3. Title similarity (fuzzy matching with thefuzz)
4. Date proximity scoring

Usage:
    from match_mcsc_to_rc import match_archives_to_shows

    show_matches, review_queue = match_archives_to_shows(
        shows, mixcloud_archives, soundcloud_archives, artists,
        should_exclude_fn=should_exclude_show
    )
"""

import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# Try to import thefuzz for fuzzy matching, fall back to basic matching if not available
try:
    from thefuzz import fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    print("Warning: thefuzz not installed. Using basic string matching.")
    print("Install with: pip3 install thefuzz python-Levenshtein")

# Matching thresholds
MATCH_THRESHOLD = 60  # Minimum score to accept a match
HIGH_CONFIDENCE_THRESHOLD = 80  # Score for high confidence matches
GROUND_TRUTH_SCORE = 500  # Score for ground-truth URL matches (overrides fuzzy matching)
MANUAL_OVERRIDE_SCORE = 600  # Score for manual overrides (highest priority)

# Manual matches file
MANUAL_MATCHES_FILE = Path("data/manual-matches.json")

# Known abbreviations/expansions
ABBREVIATIONS = {
    'iwd': 'international womens day',
    'rsd': 'record store day',
    'ep': 'episode',
    'vol': 'volume',
}

# Known nickname mappings (normalized forms)
NICKNAMES = {
    'amy mcnamara': 'amy mac',
    'amy mac': 'amy mcnamara',
}


# =============================================================================
# Ground-truth URL extraction from RadioCult descriptions
# =============================================================================

def extract_text_from_description(desc_obj):
    """Extract all plain text from RadioCult description JSON, including link hrefs.

    RadioCult uses a ProseMirror-style JSON structure for descriptions.
    This function walks the tree and extracts both text content and link URLs.
    """
    if not desc_obj or not isinstance(desc_obj, dict):
        return ""

    texts = []

    def walk(node):
        if isinstance(node, dict):
            # Extract text content
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            # Extract link href from marks
            for mark in node.get("marks", []):
                if mark.get("type") == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    if href:
                        texts.append(f" {href} ")  # Add spaces to separate from surrounding text
            # Recurse into content
            for child in node.get("content", []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(desc_obj)
    return " ".join(texts)


def normalize_archive_url(url):
    """Normalize URL by removing query params and trailing slashes."""
    if not url:
        return ""
    # Remove query string
    if '?' in url:
        url = url.split('?')[0]
    # Remove trailing slash
    url = url.rstrip('/')
    return url


def extract_archive_urls(text):
    """
    Extract Mixcloud and SoundCloud episode URLs from text.

    Returns dict: {'mixcloud': [...], 'soundcloud': [...]}
    Only returns episode-specific URLs, not profile URLs.

    Examples of valid episode URLs:
        - https://www.mixcloud.com/djgwadamike/caribbean-voyage-10/
        - https://soundcloud.com/dj-gwada-mike/caribbean-voyage-10

    Examples of rejected profile URLs:
        - https://www.mixcloud.com/djgwadamike/
        - https://soundcloud.com/dj-gwada-mike
    """
    results = {'mixcloud': [], 'soundcloud': []}

    if not text:
        return results

    # Mixcloud episode URL pattern: mixcloud.com/{user}/{slug}
    # Must have BOTH user AND slug (not just profile)
    mc_pattern = r'https?://(?:www\.)?mixcloud\.com/([^/\s]+)/([^/\s?]+)'
    for match in re.finditer(mc_pattern, text, re.IGNORECASE):
        user, slug = match.groups()
        # Skip if slug looks like a profile-only URL (no actual slug)
        if slug and not slug.startswith('?'):
            url = f"https://www.mixcloud.com/{user}/{slug}/"
            results['mixcloud'].append({
                'url': normalize_archive_url(url),
                'user': user,
                'slug': slug
            })

    # SoundCloud episode URL pattern: soundcloud.com/{user}/{track}
    # Must have BOTH user AND track (not just profile)
    sc_pattern = r'https?://(?:www\.)?soundcloud\.com/([^/\s]+)/([^/\s?]+)'
    for match in re.finditer(sc_pattern, text, re.IGNORECASE):
        user, track = match.groups()
        # Skip common non-track paths (profile sub-pages)
        skip_paths = {'sets', 'likes', 'followers', 'following', 'tracks',
                      'albums', 'playlists', 'reposts', 'comments', 'popular-tracks'}
        if track.lower() not in skip_paths:
            url = f"https://soundcloud.com/{user}/{track}"
            results['soundcloud'].append({
                'url': normalize_archive_url(url),
                'user': user,
                'track': track
            })

    return results


def split_camel_case(text):
    """Split CamelCase or joinedwords into separate words.

    Examples:
        MutualAffinities -> Mutual Affinities
        SubTransmissions -> Sub Transmissions
        DigWhereYouStand -> Dig Where You Stand
    """
    if not text:
        return text
    # Insert space before uppercase letters that follow lowercase
    result = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Insert space before uppercase letters that are followed by lowercase (for acronyms)
    result = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', result)
    return result


# Common compound words that should be split (all-lowercase for matching)
COMPOUND_WORDS = {
    'subtransmissions': 'sub transmissions',
    'soundsystems': 'sound systems',
    'soundsystem': 'sound system',
    'digwhereyoustand': 'dig where you stand',
    'wherearewhere': 'where are we',
}

# Common typos/misspellings to normalize (all-lowercase)
# Applied after lowercase conversion but before removing special chars
TYPO_CORRECTIONS = {
    "c'meer": "c'mere",      # C'meer to Me -> C'mere to me
    "cmeer": "cmere",        # Without apostrophe
    "damsha": "damhsa",      # Damsha -> Damhsa (letter swap)
}

# Show name variants that should all normalize to the same form
# These are applied after all other normalization (on final text)
SHOW_NAME_VARIANTS = {
    # HhÉirwaVves - various CamelCase/accent combinations normalize differently
    "hheirwa vves": "hheirwavves",       # Show name: HhÉirwaVves
    "hhei rwav ves": "hheirwavves",      # Archive: HhÉiRwavVes
    "hh eii rwav ves": "hheirwavves",    # Archive: HhEÌiRwavVes
}


def split_compound_words(text):
    """Split known compound words that aren't CamelCase.

    Handles all-caps or all-lowercase compound words like SUBTRANSMISSIONS.
    """
    if not text:
        return text
    result = text.lower()
    for compound, split in COMPOUND_WORDS.items():
        result = result.replace(compound, split)
    return result


def fix_typos(text):
    """Fix known typos and misspellings.

    Handles cases like:
        C'meer -> C'mere
        Damsha -> Damhsa
    """
    if not text:
        return text
    result = text.lower()
    for typo, correction in TYPO_CORRECTIONS.items():
        result = result.replace(typo, correction)
    return result


def normalize_show_name_variants(text):
    """Normalize known show name variants to canonical form.

    Applied at the end of normalization to handle cases where
    CamelCase splitting creates different results for the same show name.
    """
    if not text:
        return text
    for variant, canonical in SHOW_NAME_VARIANTS.items():
        if variant in text:
            text = text.replace(variant, canonical)
    return text


def extract_from_brackets(text):
    """Extract text from within brackets [like this] if it looks like a show name.

    Only extracts from SQUARE brackets, not parentheses (which often contain dates/metadata).
    Returns the bracketed content if found, otherwise the original text.
    """
    if not text:
        return text
    # Only try square brackets - these typically contain show names
    # e.g., "201019-[Airegin Offagain]"
    match = re.search(r'\[([^\]]+)\]', text)
    if match:
        content = match.group(1)
        # Only extract if it looks like a show name (not just numbers or a date)
        if not re.match(r'^[\d\s\-/\.]+$', content) and len(content) > 3:
            return content
    return text


def normalize_text(text):
    """Normalize text for comparison: lowercase, remove accents, simplify."""
    if not text:
        return ""
    # Split CamelCase before other processing
    text = split_camel_case(text)
    # Replace underscores and hyphens with spaces
    text = text.replace('_', ' ').replace('-', ' ')
    # Normalize unicode
    text = unicodedata.normalize('NFKD', text)
    # Remove accents
    text = ''.join(c for c in text if not unicodedata.combining(c))
    # Lowercase
    text = text.lower()
    # Fix known typos (before removing special chars so apostrophes are still present)
    text = fix_typos(text)
    # Split known compound words (handles SUBTRANSMISSIONS -> sub transmissions)
    text = split_compound_words(text)
    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    # Collapse whitespace
    text = ' '.join(text.split())
    # Normalize known show name variants (at the end to catch all variations)
    text = normalize_show_name_variants(text)
    return text


def strip_episode_info(text):
    """Strip episode numbers and related info from a title to get the series name.

    Examples:
        Caribbean Voyage #7 -> Caribbean Voyage
        Cinema in Absentia Episode 6 -> Cinema in Absentia
        Vestibular episodes 9 -> Vestibular
        Sub Transmissions 16 -> Sub Transmissions
        CEOLCHAR 3 -> CEOLCHAR
    """
    if not text:
        return text
    # Remove various episode patterns
    patterns = [
        r'\s*#\s*\d+',           # #7, # 7
        r'\s+episode\s*\d+',     # Episode 6, episode6
        r'\s+episodes?\s*\d+',   # episodes 9
        r'\s+ep\.?\s*\d+',       # ep 5, ep.5, ep5
        r'\s+vol\.?\s*\d+',      # vol 2, vol.2
        r'\s+show\s*#?\s*\d+',   # Show #7, show 1
        r'\s+\d+\s*$',           # trailing number (e.g., "CEOLCHAR 3")
    ]
    result = text
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    return result.strip()


def strip_the_prefix(text):
    """Remove 'The ' prefix from start of text for comparison."""
    if not text:
        return text
    if text.lower().startswith('the '):
        return text[4:]
    return text


def expand_abbreviations(text):
    """Expand known abbreviations in text.

    IWD -> International Women's Day
    """
    if not text:
        return text
    words = text.lower().split()
    expanded = []
    for word in words:
        if word in ABBREVIATIONS:
            expanded.append(ABBREVIATIONS[word])
        else:
            expanded.append(word)
    return ' '.join(expanded)


def get_nickname_variants(name):
    """Get nickname variants for a name.

    Returns a list of name variants including the original.
    """
    norm_name = normalize_text(name)
    variants = [norm_name]
    if norm_name in NICKNAMES:
        variants.append(NICKNAMES[norm_name])
    return variants


def extract_series_name(title):
    """Extract the base series name from a show title.

    Handles patterns like:
    - Caribbean Voyage #6 -> Caribbean Voyage
    - Cinema in Absentia: Jazz, I Suppose -> Cinema in Absentia
    - The Sky Was Pink | Episode 2 -> The Sky Was Pink
    """
    if not title:
        return title
    # Remove content after colon (often a subtitle)
    if ':' in title:
        title = title.split(':')[0].strip()
    # Remove content after pipe
    if '|' in title:
        title = title.split('|')[0].strip()
    # Strip episode info
    title = strip_episode_info(title)
    return title


def extract_date_from_title(title):
    """Extract broadcast date from archive title.

    Handles various formats:
    - DD/MM/YY or DD/MM/YYYY (e.g., '30/11/25', '30/11/2025')
    - MM/DD/YYYY (US format, e.g., '11/30/2025')
    - YYYYMMDD (e.g., '20251018')
    - DDMMYYYY (e.g., '28112025')
    - Month DD[st/nd/rd/th] YY (e.g., 'OCT 22ND 25')
    - Nov'25, November 2025
    """
    if not title:
        return None

    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    current_year = datetime.now().year

    def fix_year_typo(year):
        """Fix common year typos (e.g., 2028 -> 2025)."""
        # If year is in the future beyond next year, assume typo
        if year > current_year + 1:
            # Common typo: wrong last digit (28 instead of 25)
            return current_year
        return year

    # Pattern 1: YYYY-MM-DD (ISO format) - check FIRST before DD/MM/YY
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', title)
    if match:
        year, month, day = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 2: DD/MM/YY or DD/MM/YYYY or DD-MM-YY or DD.MM.YYYY (but NOT YYYY-MM-DD which was handled above)
    match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', title)
    if match:
        a, b, year = match.groups()
        if len(year) == 2:
            year = '20' + year
        year = fix_year_typo(int(year))
        a, b = int(a), int(b)
        # Try DD/MM/YYYY first (European)
        try:
            return datetime(year, b, a)
        except ValueError:
            pass
        # Try MM/DD/YYYY (US)
        try:
            return datetime(year, a, b)
        except ValueError:
            pass

    # Pattern 3: YYMMDD (e.g., '251018' for 2025-10-18) - 6 digits starting with 2
    match = re.search(r'(?<!\d)(2[0-9])(\d{2})(\d{2})(?!\d)', title)
    if match:
        year, month, day = match.groups()
        year = int('20' + year)
        year = fix_year_typo(year)
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 4: YYYYMMDD (e.g., '20251018')
    match = re.search(r'(\d{4})(\d{2})(\d{2})', title)
    if match:
        year, month, day = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 5: DDMMYYYY (no separators, e.g., '28112025')
    match = re.search(r'(\d{2})(\d{2})(\d{4})', title)
    if match:
        day, month, year = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 6: DDMMYY (6 digits ending in 25, e.g., '140925' for 14-09-25)
    match = re.search(r'(?<!\d)(\d{2})(\d{2})(2[0-9])(?!\d)', title)
    if match:
        day, month, year = match.groups()
        year = int('20' + year)
        year = fix_year_typo(year)
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 7: DD MM YYYY with spaces (e.g., '06 11 2025')
    match = re.search(r'(?<!\d)(\d{2})\s+(\d{2})\s+(\d{4})(?!\d)', title)
    if match:
        day, month, year = match.groups()
        year = fix_year_typo(int(year))
        try:
            return datetime(year, int(month), int(day))
        except ValueError:
            pass

    # Pattern 8: Month DD[st/nd/rd/th] YY (e.g., 'OCT 22ND 25', 'Nov 5th 2025')
    match = re.search(r'([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{2,4})', title, re.I)
    if match:
        month_str, day, year = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            if len(year) == 2:
                year = '20' + year
            year = fix_year_typo(int(year))
            try:
                return datetime(year, months[month_key], int(day))
            except ValueError:
                pass

    # Pattern 9: DD Month (no year) - e.g., '22 March' - assumes current year
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3,9})(?!\s*\d)', title)
    if match:
        day, month_str = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            try:
                return datetime(current_year, months[month_key], int(day))
            except ValueError:
                pass

    # Pattern 10: Month abbreviation + year only (Nov'25, Nov 25, November 2025)
    match = re.search(r"([A-Za-z]{3,9})[\s']*(\d{2,4})(?!\d)", title)
    if match:
        month_str, year = match.groups()
        month_key = month_str[:3].lower()
        if month_key in months:
            if len(year) == 2:
                year = '20' + year
            year = fix_year_typo(int(year))
            try:
                # Return first day of month for approximate matching
                return datetime(year, months[month_key], 1)
            except ValueError:
                pass

    return None


def calculate_match_score(show, cloudcast, artist_name=None, artist_mc_username=None):
    """
    Calculate confidence score for a show-to-cloudcast match.

    Scoring:
    - Host username match: +40 points
    - Artist name in cloudcast title: +25 points
    - Title similarity: +0-35 points (fuzzy match)
    - Exact date match: +25 points
    - Same month match: +10 points
    - Show title appears as substring: +15 points bonus
    """
    score = 0

    show_title = show.get('title', '')
    cloudcast_name = cloudcast.get('name', '')
    show_date = show.get('start', '')

    norm_show = normalize_text(show_title)
    norm_cloud = normalize_text(cloudcast_name)

    # Host username match (from MC-USERNAME tag)
    if artist_mc_username:
        # Check if the cloudcast URL contains the host username
        cloudcast_url = cloudcast.get('url', '').lower()
        if artist_mc_username.lower() in cloudcast_url:
            score += 40

    # Artist name appears in cloudcast title
    if artist_name:
        norm_artist = normalize_text(artist_name)
        if norm_artist and len(norm_artist) > 2 and norm_artist in norm_cloud:
            score += 25

    # Title similarity
    if HAS_FUZZ and show_title and cloudcast_name:
        # Use token set ratio for better matching with reordered words
        similarity = fuzz.token_set_ratio(norm_show, norm_cloud)
        # Scale to 0-35 points
        score += int(similarity * 0.35)

        # Bonus: if show title appears as a substring in cloudcast name
        if len(norm_show) > 3 and norm_show in norm_cloud:
            score += 15
    elif show_title and cloudcast_name:
        # Basic matching without fuzz
        if norm_show in norm_cloud or norm_cloud in norm_show:
            score += 25

    # Date match in Mixcloud title
    if show_date:
        try:
            show_dt = datetime.fromisoformat(show_date.replace('Z', '+00:00'))
            mc_date = extract_date_from_title(cloudcast_name)
            if mc_date:
                if mc_date.date() == show_dt.date():
                    # Exact date match
                    score += 25
                elif mc_date.year == show_dt.year and mc_date.month == show_dt.month:
                    # Same month (for "Nov'25" style dates)
                    score += 10
        except:
            pass

    return score


def apply_ground_truth_matches(shows, mixcloud_archives, soundcloud_archives, show_matches):
    """
    Apply ground-truth matches from URLs in show descriptions.

    Extracts MC/SC URLs from RadioCult descriptions and directly matches
    to the corresponding archives. These matches override fuzzy matching.

    Args:
        shows: List of RadioCult show dicts
        mixcloud_archives: List of Mixcloud cloudcast dicts
        soundcloud_archives: List of SoundCloud track dicts
        show_matches: Dict to populate with matches

    Returns:
        dict: {show_id: {'show_title': ..., 'mixcloud_url': ..., 'soundcloud_url': ...}}
              for logging purposes
    """
    ground_truth_log = {}

    # Build archive lookup by normalized URL
    mc_by_url = {}
    mc_by_slug = {}
    for archive in mixcloud_archives:
        url = normalize_archive_url(archive.get('url', ''))
        if url:
            mc_by_url[url] = archive
        slug = archive.get('slug', '')
        if slug:
            mc_by_slug[slug] = archive

    sc_by_url = {}
    for archive in soundcloud_archives:
        url = normalize_archive_url(archive.get('url', ''))
        if url:
            sc_by_url[url] = archive

    for show in shows:
        show_id = show.get('id')
        description = show.get('description')
        if not description:
            continue

        # Extract text (including link hrefs) from description
        text = extract_text_from_description(description)
        if not text:
            continue

        # Find archive URLs in the text
        urls = extract_archive_urls(text)

        matched = {}

        # Match Mixcloud URLs
        for mc_info in urls['mixcloud']:
            mc_url = mc_info['url']
            # Try exact URL match first
            archive = mc_by_url.get(mc_url)
            # Try matching just by slug if exact URL not found
            # (handles case where host links to their own MC account, not eistcork)
            if not archive:
                archive = mc_by_slug.get(mc_info['slug'])

            if archive:
                if show_id not in show_matches:
                    show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

                show_matches[show_id]['mixcloud'] = {
                    'slug': archive.get('slug'),
                    'name': archive.get('name', ''),
                    'url': archive.get('url'),
                    'pictures': archive.get('pictures', {}),
                    'description': archive.get('description', ''),
                    'score': GROUND_TRUTH_SCORE
                }
                matched['mixcloud_url'] = mc_url
                matched['mixcloud_slug'] = archive.get('slug')

        # Match SoundCloud URLs
        for sc_info in urls['soundcloud']:
            sc_url = sc_info['url']
            archive = sc_by_url.get(sc_url)
            # Also try with www prefix
            if not archive:
                alt_url = sc_url.replace('https://soundcloud.com', 'https://www.soundcloud.com')
                archive = sc_by_url.get(alt_url)

            if archive:
                if show_id not in show_matches:
                    show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

                show_matches[show_id]['soundcloud'] = {
                    'id': archive.get('id'),
                    'title': archive.get('title', ''),
                    'url': archive.get('url'),
                    'thumbnail': archive.get('thumbnail'),
                    'description': archive.get('description', ''),
                    'score': GROUND_TRUTH_SCORE
                }
                matched['soundcloud_url'] = sc_url
                matched['soundcloud_id'] = archive.get('id')

        if matched:
            ground_truth_log[show_id] = {
                'show_title': show.get('title'),
                'show_date': show.get('start', '')[:10],
                **matched
            }

    return ground_truth_log


def load_manual_matches():
    """
    Load manual match overrides from data/manual-matches.json.

    Returns:
        dict: {show_slug: {'mixcloud': url_or_none, 'soundcloud': url_or_none}}
    """
    if not MANUAL_MATCHES_FILE.exists():
        return {}

    try:
        with open(MANUAL_MATCHES_FILE, 'r') as f:
            data = json.load(f)
        # Filter out comment keys
        return {k: v for k, v in data.items() if not k.startswith('_')}
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load manual matches: {e}")
        return {}


def apply_manual_matches(shows, mixcloud_archives, soundcloud_archives, show_matches):
    """
    Apply manual match overrides from data/manual-matches.json.

    Manual overrides have the highest priority (score=600) and override
    any automatic matching, including ground-truth URL matches.

    Supported fields per show:
        - mixcloud: URL string or null to clear
        - soundcloud: URL string or null to clear
        - episode_info: Override episode suffix (e.g., "Ep. 1", "#5", null to clear)
        - title: Override display title (keeps slug unchanged)

    Args:
        shows: List of RadioCult show dicts
        mixcloud_archives: List of Mixcloud cloudcast dicts
        soundcloud_archives: List of SoundCloud track dicts
        show_matches: Dict to populate/update with matches

    Returns:
        dict: Log of applied manual overrides for reporting
    """
    manual_overrides = load_manual_matches()
    if not manual_overrides:
        return {}

    # Build archive lookup by normalized URL
    mc_by_url = {}
    for archive in mixcloud_archives:
        url = normalize_archive_url(archive.get('url', ''))
        if url:
            mc_by_url[url] = archive

    sc_by_url = {}
    for archive in soundcloud_archives:
        url = normalize_archive_url(archive.get('url', ''))
        if url:
            sc_by_url[url] = archive

    # Build show lookup by slug
    shows_by_slug = {s.get('slug'): s for s in shows if s.get('slug')}

    applied_log = {}

    for show_slug, override in manual_overrides.items():
        show = shows_by_slug.get(show_slug)
        if not show:
            print(f"  Warning: Manual override for unknown show slug: {show_slug}")
            continue

        show_id = show.get('id')
        if show_id not in show_matches:
            show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

        applied = {}

        # Apply Mixcloud override
        mc_url = override.get('mixcloud')
        if mc_url is None:
            # Explicit null - clear any existing match
            show_matches[show_id]['mixcloud'] = None
            applied['mixcloud'] = 'cleared'
        elif mc_url:
            # URL provided - look up archive
            normalized_url = normalize_archive_url(mc_url)
            archive = mc_by_url.get(normalized_url)
            if archive:
                show_matches[show_id]['mixcloud'] = {
                    'slug': archive.get('slug'),
                    'name': archive.get('name', ''),
                    'url': archive.get('url'),
                    'pictures': archive.get('pictures', {}),
                    'description': archive.get('description', ''),
                    'score': MANUAL_OVERRIDE_SCORE
                }
                applied['mixcloud'] = archive.get('url')
            else:
                print(f"  Warning: Manual Mixcloud URL not found in cache: {mc_url}")

        # Apply SoundCloud override
        sc_url = override.get('soundcloud')
        if sc_url is None:
            # Explicit null - clear any existing match
            show_matches[show_id]['soundcloud'] = None
            applied['soundcloud'] = 'cleared'
        elif sc_url:
            # URL provided - look up archive
            normalized_url = normalize_archive_url(sc_url)
            archive = sc_by_url.get(normalized_url)
            if archive:
                show_matches[show_id]['soundcloud'] = {
                    'id': archive.get('id'),
                    'title': archive.get('title', ''),
                    'url': archive.get('url'),
                    'thumbnail': archive.get('thumbnail'),
                    'description': archive.get('description', ''),
                    'score': MANUAL_OVERRIDE_SCORE
                }
                applied['soundcloud'] = archive.get('url')
            else:
                print(f"  Warning: Manual SoundCloud URL not found in cache: {sc_url}")

        # Apply episode_info override
        if 'episode_info' in override:
            ep_info = override.get('episode_info')
            show_matches[show_id]['episode_info'] = ep_info  # Can be string or None
            applied['episode_info'] = ep_info if ep_info else 'cleared'

        # Apply title override
        if 'title' in override:
            title = override.get('title')
            show_matches[show_id]['title'] = title
            applied['title'] = title

        if applied:
            applied_log[show_slug] = {
                'show_title': show.get('title'),
                'show_date': show.get('start', '')[:10] if show.get('start') else '',
                **applied
            }

    return applied_log


def apply_sequential_matching(shows, soundcloud_archives, mixcloud_archives, show_matches,
                               should_exclude_fn=None):
    """
    Post-process matches to apply 1-to-1 sequential matching where counts align.

    When a show series has exactly N non-repeat RadioCult airings (excluding future
    and recent shows within 5 days) AND exactly N uploads on a single platform
    (SoundCloud or Mixcloud), we can confidently match them 1-to-1 chronologically.

    This fixes cases where score-based matching fails due to inconsistent naming
    (e.g., "GTown Sound 5" matched to wrong date because title lacks date info).

    Args:
        shows: List of all RadioCult shows
        soundcloud_archives: List of all SoundCloud archives
        mixcloud_archives: List of all Mixcloud archives
        show_matches: Current match results from score-based matching
        should_exclude_fn: Optional function to exclude certain shows

    Returns:
        Updated show_matches dict with sequential matches applied
    """
    from collections import defaultdict

    now = datetime.now()
    five_days_ago = now - timedelta(days=5)

    # Group non-repeat shows by normalized series title
    shows_by_series = defaultdict(list)
    for show in shows:
        if should_exclude_fn and should_exclude_fn(show):
            continue
        if show.get('isRepeat'):
            continue

        title = show.get('title', '')
        series_name = normalize_text(extract_series_name(title))
        if not series_name:
            continue

        # Parse show date
        start = show.get('start', '')
        if not start:
            continue
        try:
            show_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).replace(tzinfo=None)
        except:
            continue

        # Skip future shows and shows within past 5 days
        if show_dt > now:
            continue
        if show_dt > five_days_ago:
            continue

        shows_by_series[series_name].append({
            'show': show,
            'date': show_dt,
            'id': show.get('id')
        })

    # Build archive lookup by normalized title -> list of archives
    def get_archive_series_name(archive_title):
        """Extract series name from archive title (strip artist prefix, episode info)."""
        # Common pattern: "Artist - Show Name #3" or "Artist - Show Name (date)"
        # Try to extract just the show name part
        title = archive_title
        if ' - ' in title:
            # Take part after first " - " (usually the show name)
            title = title.split(' - ', 1)[1]
        # Strip trailing parenthetical content (often dates or subtitles)
        title = re.sub(r'\s*\([^)]*\)\s*$', '', title)
        return normalize_text(strip_episode_info(title))

    def find_matching_series(archive_series_name, rc_series_names):
        """Find the RC series that best matches this archive series name using fuzzy matching."""
        if not archive_series_name or not HAS_FUZZ:
            return archive_series_name

        # First try exact match
        if archive_series_name in rc_series_names:
            return archive_series_name

        # Try fuzzy matching - archive series name should be contained in or very similar to RC name
        best_match = None
        best_score = 0
        for rc_series in rc_series_names:
            # Check if RC series name is a prefix/substring of archive name
            if rc_series in archive_series_name:
                # Strong match - RC name is contained in archive name
                # e.g., "g town sound" in "g town sound doomsday"
                score = 95
            else:
                score = fuzz.ratio(archive_series_name, rc_series)

            if score > best_score and score >= 80:
                best_score = score
                best_match = rc_series

        return best_match if best_match else archive_series_name

    # Get all RC series names for fuzzy matching
    rc_series_names = set(shows_by_series.keys())

    sc_by_series = defaultdict(list)
    for archive in soundcloud_archives:
        title = archive.get('title', '')
        raw_series_name = get_archive_series_name(title)
        if raw_series_name:
            # Map to RC series name if possible
            series_name = find_matching_series(raw_series_name, rc_series_names)
            sc_by_series[series_name].append(archive)

    mc_by_series = defaultdict(list)
    for archive in mixcloud_archives:
        title = archive.get('name', '')
        raw_series_name = get_archive_series_name(title)
        if raw_series_name:
            # Map to RC series name if possible
            series_name = find_matching_series(raw_series_name, rc_series_names)
            mc_by_series[series_name].append(archive)

    # Build mapping of archives to the series they're currently matched to
    # This helps us avoid stealing archives from OTHER series
    HIGH_CONFIDENCE_THRESHOLD = 100
    sc_archive_series = {}  # archive_id -> (series_name, score)
    mc_archive_series = {}  # archive_slug -> (series_name, score)

    for match in show_matches.values():
        show = match.get('show', {})
        show_series = normalize_text(extract_series_name(show.get('title', '')))

        sc = match.get('soundcloud') or {}
        mc = match.get('mixcloud') or {}

        if sc.get('id') and sc.get('score', 0) >= HIGH_CONFIDENCE_THRESHOLD:
            sc_archive_series[sc['id']] = (show_series, sc['score'])
        if mc.get('slug') and mc.get('score', 0) >= HIGH_CONFIDENCE_THRESHOLD:
            mc_archive_series[mc['slug']] = (show_series, mc['score'])

    # For each series, check if 1-to-1 matching is possible
    sequential_applied = 0
    for series_name, show_entries in shows_by_series.items():
        if len(show_entries) < 2:
            # Need at least 2 shows for sequential matching to be meaningful
            continue

        # Sort shows by date ascending
        show_entries.sort(key=lambda x: x['date'])
        num_shows = len(show_entries)

        # Check SoundCloud
        sc_archives = sc_by_series.get(series_name, [])
        # Filter out archives claimed by a DIFFERENT series with high confidence
        available_sc = []
        for a in sc_archives:
            archive_id = a.get('id')
            if archive_id in sc_archive_series:
                claimed_series, score = sc_archive_series[archive_id]
                # Only exclude if claimed by a different series
                if claimed_series != series_name:
                    continue
            available_sc.append(a)

        if len(available_sc) == num_shows:
            # Sort archives by upload_date or ID (SC IDs are sequential)
            sc_archives_sorted = sorted(available_sc, key=lambda x: (
                x.get('upload_date', ''),
                x.get('id', '')
            ))

            # Apply 1-to-1 mapping
            for i, show_entry in enumerate(show_entries):
                archive = sc_archives_sorted[i]
                show_id = show_entry['id']

                if show_id not in show_matches:
                    show_matches[show_id] = {'show': show_entry['show'], 'mixcloud': None, 'soundcloud': None}

                # Always override - sequential matching is high confidence when counts match
                show_matches[show_id]['soundcloud'] = {
                    'id': archive.get('id'),
                    'title': archive.get('title', ''),
                    'url': archive.get('url'),
                    'thumbnail': archive.get('thumbnail'),
                    'description': archive.get('description', ''),
                    'score': 300  # High score to indicate sequential match
                }

            sequential_applied += 1
            print(f"  Sequential match applied: {series_name} ({num_shows} SC archives)")

        # Check Mixcloud (only if SC didn't match)
        else:
            mc_archives = mc_by_series.get(series_name, [])
            # Filter out archives claimed by a DIFFERENT series with high confidence
            available_mc = []
            for a in mc_archives:
                archive_slug = a.get('slug')
                if archive_slug in mc_archive_series:
                    claimed_series, score = mc_archive_series[archive_slug]
                    # Only exclude if claimed by a different series
                    if claimed_series != series_name:
                        continue
                available_mc.append(a)

            if len(available_mc) == num_shows:
                # Sort by created_time
                mc_archives_sorted = sorted(available_mc, key=lambda x: x.get('created_time', ''))

                # Apply 1-to-1 mapping
                for i, show_entry in enumerate(show_entries):
                    archive = mc_archives_sorted[i]
                    show_id = show_entry['id']

                    if show_id not in show_matches:
                        show_matches[show_id] = {'show': show_entry['show'], 'mixcloud': None, 'soundcloud': None}

                    # Always override - sequential matching is high confidence when counts match
                    show_matches[show_id]['mixcloud'] = {
                        'slug': archive.get('slug'),
                        'name': archive.get('name', ''),
                        'url': archive.get('url'),
                        'pictures': archive.get('pictures', {}),
                        'description': archive.get('description', ''),
                        'score': 300  # High score to indicate sequential match
                    }

                sequential_applied += 1
                print(f"  Sequential match applied: {series_name} ({num_shows} MC archives)")

    if sequential_applied:
        print(f"  Total series with sequential matching: {sequential_applied}")

    return show_matches


def match_archives_to_shows(shows, mixcloud_archives, soundcloud_archives, artists,
                            should_exclude_fn=None):
    """
    Match archives (Mixcloud + SoundCloud) to RadioCult shows.

    FLIPPED DIRECTION: Each archive finds its best matching show.
    This ensures 1:1 mapping - each archive can only match one show.
    Shows can have both Mixcloud AND SoundCloud matches.

    Args:
        shows: List of RadioCult show dicts
        mixcloud_archives: List of Mixcloud cloudcast dicts
        soundcloud_archives: List of SoundCloud track dicts
        artists: Dict of artist_id -> artist data
        should_exclude_fn: Optional function(show) -> bool to filter shows

    Returns:
        Tuple of (show_matches, review_queue, ground_truth_log) where:
        - show_matches: dict of show_id -> {'show': ..., 'mixcloud': ..., 'soundcloud': ...}
        - review_queue: list of low-confidence matches for manual review
        - ground_truth_log: dict of ground-truth URL matches from descriptions
    """
    # Build show lookup by date for faster matching
    shows_by_date = {}
    for show in shows:
        if should_exclude_fn and should_exclude_fn(show):
            continue
        start = show.get('start', '')
        if start:
            date_key = start[:10]  # YYYY-MM-DD
            if date_key not in shows_by_date:
                shows_by_date[date_key] = []
            shows_by_date[date_key].append(show)

    # Build artist lookup
    artist_names = {aid: a.get('name', '') for aid, a in artists.items()}
    artist_mc_usernames = {}
    artist_sc_usernames = {}
    for artist_id, artist in artists.items():
        for tag in artist.get('tags', []):
            if tag.startswith('MC-USERNAME_'):
                artist_mc_usernames[artist_id] = tag.replace('MC-USERNAME_', '').lower()
            elif tag.startswith('SC-USERNAME_'):
                artist_sc_usernames[artist_id] = tag.replace('SC-USERNAME_', '').lower()

    # Track which shows have been matched to archives
    show_matches = {}  # show_id -> {mixcloud: {...}, soundcloud: {...}}
    archive_review_queue = []

    # Apply ground-truth matches from description URLs FIRST
    # These take precedence over fuzzy matching (score=500)
    ground_truth_log = apply_ground_truth_matches(
        shows, mixcloud_archives, soundcloud_archives, show_matches
    )
    if ground_truth_log:
        print(f"  Ground-truth matches from descriptions: {len(ground_truth_log)}")

    def find_best_show_for_archive(archive_title, archive_date, archive_source, archive_url=None):
        """Find the best matching RadioCult show for an archive."""
        best_show = None
        best_score = 0

        # Pre-process archive title: try bracket extraction
        processed_archive_title = extract_from_brackets(archive_title)

        # Parse date from archive
        archive_dt = None
        if archive_date:
            try:
                if len(archive_date) == 8:  # YYYYMMDD
                    archive_dt = datetime.strptime(archive_date, '%Y%m%d')
                else:
                    archive_dt = datetime.fromisoformat(archive_date.replace('Z', '+00:00'))
            except:
                pass

        # Also try to extract date from title - THIS IS THE KEY SIGNAL
        title_date = extract_date_from_title(archive_title)
        title_date_is_specific = title_date and title_date.day != 1  # Not a month-only date

        # PRIORITY: If we have a specific date in the title, check for exact match first
        # This handles cases like "Aus der Ferne #8 (2025-10-19)" definitively
        if title_date_is_specific:
            norm_archive = normalize_text(processed_archive_title)
            norm_archive_series = normalize_text(strip_episode_info(processed_archive_title))

            # Try both the extracted date AND the swapped day/month version
            # This handles DD/MM vs MM/DD ambiguity (e.g., 05/09 could be May 9 or Sep 5)
            dates_to_try = [title_date]
            if title_date.day <= 12 and title_date.month <= 12 and title_date.day != title_date.month:
                # Day and month are both valid as either, so try swapped version too
                try:
                    swapped = title_date.replace(day=title_date.month, month=title_date.day)
                    dates_to_try.append(swapped)
                except ValueError:
                    pass

            for try_date in dates_to_try:
                exact_date_key = try_date.strftime('%Y-%m-%d')
                exact_date_shows = shows_by_date.get(exact_date_key, [])

                for show in exact_date_shows:
                    show_title = show.get('title', '')
                    norm_show = normalize_text(show_title)
                    norm_show_series = normalize_text(extract_series_name(show_title))
                    norm_show_no_the = normalize_text(strip_the_prefix(show_title))

                    # Check if show title appears in archive title (e.g., "Aus der Ferne" in "John O'Callaghan - Aus der Ferne #8")
                    if len(norm_show) > 3 and norm_show in norm_archive:
                        # Definitive match: exact date + title match
                        # Return immediately with very high score
                        return show, 200

                    # Check series name match (e.g., "Caribbean Voyage" matches "Caribbean Voyage #7")
                    if len(norm_show_series) > 3 and norm_show_series in norm_archive:
                        return show, 200

                    # Check without "The" prefix (e.g., "Expanded Field" matches "The Expanded Field")
                    if len(norm_show_no_the) > 3 and norm_show_no_the in norm_archive:
                        return show, 200

                    # Also check fuzzy match for edge cases
                    if HAS_FUZZ:
                        similarity = fuzz.token_set_ratio(norm_show, norm_archive)
                        if similarity >= 80:
                            return show, 200
                        # Also try series name fuzzy match
                        series_similarity = fuzz.token_set_ratio(norm_show_series, norm_archive_series)
                        if series_similarity >= 85:
                            return show, 200

        # Determine which dates to search for fallback matching
        search_dates = set()
        if archive_dt:
            # Search archive upload date and nearby days (uploads often delayed)
            # Extended to 45 days before (archives often uploaded weeks later)
            for delta in range(-45, 2):
                d = archive_dt + timedelta(days=delta)
                search_dates.add(d.strftime('%Y-%m-%d'))
        if title_date:
            # If it's a month-only date (day=1), search the entire month
            if title_date.day == 1:
                # Add all days of that month
                for day in range(1, 32):
                    try:
                        d = title_date.replace(day=day)
                        search_dates.add(d.strftime('%Y-%m-%d'))
                    except ValueError:
                        break  # Invalid day for this month
            else:
                search_dates.add(title_date.strftime('%Y-%m-%d'))

        # If no date info, search all shows (slower but necessary)
        if not search_dates:
            candidate_shows = [s for shows_list in shows_by_date.values() for s in shows_list]
        else:
            candidate_shows = []
            for date_key in search_dates:
                candidate_shows.extend(shows_by_date.get(date_key, []))

        for show in candidate_shows:
            # Get artist info
            artist_ids = show.get('artistIds', [])
            artist_name = None
            mc_username = None
            sc_username = None
            for aid in artist_ids:
                if aid in artist_names:
                    artist_name = artist_names[aid]
                if aid in artist_mc_usernames:
                    mc_username = artist_mc_usernames[aid]
                if aid in artist_sc_usernames:
                    sc_username = artist_sc_usernames[aid]

            # Calculate score (reuse existing function but swap args conceptually)
            # We're scoring how well this show matches the archive
            score = 0
            show_title = show.get('title', '')
            show_date = show.get('start', '')

            # Normalize both titles
            norm_show = normalize_text(show_title)
            norm_archive = normalize_text(processed_archive_title)

            # Also get series names (without episode numbers)
            norm_show_series = normalize_text(extract_series_name(show_title))
            norm_archive_series = normalize_text(strip_episode_info(processed_archive_title))

            # Get versions without "The" prefix
            norm_show_no_the = normalize_text(strip_the_prefix(show_title))
            norm_archive_no_the = normalize_text(strip_the_prefix(processed_archive_title))

            # Expand abbreviations for comparison
            norm_show_expanded = expand_abbreviations(norm_show)
            norm_archive_expanded = expand_abbreviations(norm_archive)

            # Artist name in archive title (with nickname variants)
            if artist_name:
                artist_variants = get_nickname_variants(artist_name)
                for variant in artist_variants:
                    if variant and len(variant) > 2 and variant in norm_archive:
                        score += 25
                        break

            # Username match: artist's platform username appears in archive URL or title
            # Use MC-USERNAME for Mixcloud, SC-USERNAME for SoundCloud
            platform_username = mc_username if archive_source == 'mixcloud' else sc_username
            if platform_username:
                # Check URL first (most reliable)
                if archive_url and platform_username.lower() in archive_url.lower():
                    score += 40
                # Also check title (for eistcork uploads where artist name is in title)
                elif platform_username.lower() in norm_archive:
                    score += 40

            # Title similarity
            if HAS_FUZZ and show_title and processed_archive_title:
                similarity = fuzz.token_set_ratio(norm_show, norm_archive)
                score += int(similarity * 0.35)

                # Bonus: high fuzzy similarity (85+) indicates strong match
                if similarity >= 85:
                    score += 15

                # Bonus: show title appears in archive name (common for "Show Name Episode X" patterns)
                if len(norm_show) > 3 and norm_show in norm_archive:
                    score += 25

                # Bonus: series name match (e.g., "Caribbean Voyage" matches "Caribbean Voyage #7")
                if len(norm_show_series) > 3 and norm_show_series in norm_archive:
                    score += 20

                # Bonus: match without "The" prefix (higher bonus since it's a strong signal)
                if len(norm_show_no_the) > 3 and norm_show_no_the in norm_archive_no_the:
                    score += 25

                # Bonus: expanded abbreviation match (e.g., "IWD" -> "International Women's Day")
                if norm_show_expanded != norm_show or norm_archive_expanded != norm_archive:
                    expanded_similarity = fuzz.token_set_ratio(norm_show_expanded, norm_archive_expanded)
                    if expanded_similarity > similarity:
                        # Strong bonus for abbreviation matches, especially high-confidence ones
                        expansion_boost = int((expanded_similarity - similarity) * 0.5)
                        if expanded_similarity >= 95:
                            expansion_boost += 15  # Extra boost for near-perfect expanded match
                        score += expansion_boost

                # Extra bonus: exact title match (after normalization)
                if norm_show == norm_archive:
                    score += 15

                # Extra bonus: series name exact match
                if norm_show_series == norm_archive_series and len(norm_show_series) > 3:
                    score += 20

            elif show_title and processed_archive_title:
                if norm_show in norm_archive or norm_archive in norm_show:
                    score += 25
                elif norm_show_series in norm_archive or norm_archive_series in norm_show:
                    score += 20

            # Date match - THIS IS THE PRIORITY SIGNAL
            # An exact date match combined with title similarity is a definitive match
            if show_date and title_date:
                try:
                    show_dt = datetime.fromisoformat(show_date.replace('Z', '+00:00'))
                    if title_date.date() == show_dt.date():
                        # Exact date match is very strong - boost significantly
                        score += 50
                    elif title_date.year == show_dt.year and title_date.month == show_dt.month:
                        # Same month is a moderate signal
                        score += 15
                except:
                    pass

            if score > best_score:
                best_score = score
                best_show = show

        return best_show, best_score

    # Match Mixcloud archives
    print(f"  Matching {len(mixcloud_archives)} Mixcloud archives...")
    mixcloud_matched = 0
    for archive in mixcloud_archives:
        title = archive.get('name', '')
        created = archive.get('created_time', '')
        url = archive.get('url', '')

        show, score = find_best_show_for_archive(title, created, 'mixcloud', url)

        if show and score >= MATCH_THRESHOLD:
            show_id = show.get('id')
            if show_id not in show_matches:
                show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

            # Only overwrite existing match if new score is higher
            existing_match = show_matches[show_id].get('mixcloud')
            if existing_match is None or score > existing_match.get('score', 0):
                show_matches[show_id]['mixcloud'] = {
                    'slug': archive.get('slug'),
                    'name': title,
                    'url': archive.get('url'),
                    'pictures': archive.get('pictures', {}),
                    'description': archive.get('description', ''),
                    'score': score
                }
                mixcloud_matched += 1
        elif show and score > 0:
            archive_review_queue.append({
                'source': 'mixcloud',
                'archive_title': title,
                'candidate_show': show.get('title'),
                'candidate_date': show.get('start', '')[:10],
                'score': score
            })

    # Match SoundCloud archives
    print(f"  Matching {len(soundcloud_archives)} SoundCloud archives...")
    soundcloud_matched = 0
    for archive in soundcloud_archives:
        title = archive.get('title', '')
        upload_date = archive.get('upload_date', '')  # YYYYMMDD format
        url = archive.get('url', '')

        show, score = find_best_show_for_archive(title, upload_date, 'soundcloud', url)

        if show and score >= MATCH_THRESHOLD:
            show_id = show.get('id')
            if show_id not in show_matches:
                show_matches[show_id] = {'show': show, 'mixcloud': None, 'soundcloud': None}

            # Only overwrite existing match if new score is higher
            existing_match = show_matches[show_id].get('soundcloud')
            if existing_match is None or score > existing_match.get('score', 0):
                show_matches[show_id]['soundcloud'] = {
                    'id': archive.get('id'),
                    'title': title,
                    'url': archive.get('url'),
                    'thumbnail': archive.get('thumbnail'),
                    'description': archive.get('description', ''),
                    'score': score
                }
                soundcloud_matched += 1
        elif show and score > 0:
            archive_review_queue.append({
                'source': 'soundcloud',
                'archive_title': title,
                'candidate_show': show.get('title') if show else None,
                'candidate_date': show.get('start', '')[:10] if show else None,
                'score': score
            })

    print(f"  Mixcloud matched: {mixcloud_matched}/{len(mixcloud_archives)}")
    print(f"  SoundCloud matched: {soundcloud_matched}/{len(soundcloud_archives)}")

    # Post-process: apply 1-to-1 sequential matching where counts align
    show_matches = apply_sequential_matching(
        shows, soundcloud_archives, mixcloud_archives, show_matches, should_exclude_fn
    )

    # Apply manual overrides LAST (highest priority, can override everything)
    manual_log = apply_manual_matches(shows, mixcloud_archives, soundcloud_archives, show_matches)
    if manual_log:
        print(f"  Manual overrides applied: {len(manual_log)}")

    return show_matches, archive_review_queue, ground_truth_log
