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

import re
import unicodedata
from datetime import datetime, timedelta

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
        Tuple of (show_matches, review_queue) where:
        - show_matches: dict of show_id -> {'show': ..., 'mixcloud': ..., 'soundcloud': ...}
        - review_queue: list of low-confidence matches for manual review
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

    return show_matches, archive_review_queue
