import re

from rapidfuzz import fuzz, process

from nlp.nepali_lexicon import (
    apply_nepali_lexicon, has_devanagari, extract_nepali_budget, GENERIC_LOCATION_WORDS,
)

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    _TRANSLITERATE_READY = True
except Exception:
    _TRANSLITERATE_READY = False

# ----------------------------
# Canonical facility names
# ----------------------------

FACILITY_MAP = {
    "internet": ["wifi", "wi-fi", "internet", "wireless", "net"],
    "meal": ["food", "meal", "breakfast", "lunch", "dinner", "dal bhat"],
    "laundry": ["laundry", "washing", "washing machine"],
    "parking": ["parking", "garage", "bike parking", "car parking"],
    "kitchen": ["kitchen", "cook", "cooking"],
    "hot water": ["hot water", "geyser"],
    "ac": ["ac", "air conditioning", "air-conditioner"],
}

TYPE_MAP = {
    "girls": ["girls", "girl", "female", "ladies", "women"],
    "boys": ["boys", "boy", "male", "men"],
    "mixed": ["mixed", "coed", "co-ed"],
}

BUDGET_PATTERN = re.compile(r"\d{3,6}")

# ----------------------------
# Locations known to the recommender - matches preprocessing.KNOWN_LOCATIONS.
# recommender.py normally passes the live DB location list in instead; this
# is only the fallback used if no list is supplied.
# ----------------------------
from nlp.preprocessing import KNOWN_LOCATIONS as DEFAULT_KNOWN_LOCATIONS

# -----------------------------------
# Bilingual (English + Nepali) normalization
# -----------------------------------


def normalize_query(text):
    """
    Same bilingual normalization strategy as preprocessing.normalize_language:
    apply the Nepali lexicon first (dictionary lookup, both Devanagari and
    Romanized spellings), then transliterate any leftover Devanagari as a
    best-effort fallback so it isn't silently dropped.
    """
    text = apply_nepali_lexicon(text)

    if has_devanagari(text) and _TRANSLITERATE_READY:
        try:
            text = transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
        except Exception:
            pass

    return text.lower()


# -----------------------------------
# Budget
# -----------------------------------

def extract_budget(normalized_text, raw_text=None):
    # Nepali-style "15 hazar" / "१५ हजार" phrasing - checked against the RAW
    # text so it works whether written in Devanagari or Romanized Nepali,
    # without depending on transliteration accuracy.
    nepali_budget = extract_nepali_budget(raw_text if raw_text is not None else normalized_text)
    if nepali_budget and 1000 <= nepali_budget <= 100000:
        return nepali_budget

    match = BUDGET_PATTERN.search(normalized_text)
    if not match:
        return None
    value = int(match.group())
    if 1000 <= value <= 100000:
        return value
    return None


# -----------------------------------
# Fuzzy / partial Location matching
# -----------------------------------

def _resolve_token(word, locations):
    """
    Resolves a single normalized token against known locations. Returns the
    matched location string, or None if no safe match is found - "safe"
    meaning: don't guess when a short/generic token ambiguously prefixes
    multiple different named locations (e.g. "new" matches both "new
    baneshwor" and "new plaza" - picking either would be a coin flip, so
    this deliberately declines rather than guessing wrong).
    """
    word = word.replace("_", " ")  # undo the lexicon's underscore-joining
    if word in locations:
        return word

    if word in GENERIC_LOCATION_WORDS:
        return None

    prefix_hits = [loc for loc in locations if loc.startswith(word)]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        # Ambiguous - only trust it if the token is a substantial, specific
        # fraction of the shortest match (e.g. "dhap" -> "dhapakhel" is
        # fine; "new" -> {"new plaza", "new baneshwor", ...} is not).
        shortest = min(prefix_hits, key=len)
        if len(word) / len(shortest) >= 0.6:
            return shortest
        return None

    substring_hits = [loc for loc in locations if word in loc]
    if len(substring_hits) == 1:
        return substring_hits[0]
    if len(substring_hits) > 1:
        shortest = min(substring_hits, key=len)
        if len(word) / len(shortest) >= 0.6:
            return shortest
        return None

    return None


def extract_location(text, known_locations):
    """
    Resolves a location mention in free text against the known-location
    list using exact match, then a deterministic prefix/substring check
    (so "Dhapa" or "near Dhap" correctly resolves to "dhapakhel"), falling
    back to fuzzy matching for typos. Ambiguous short prefixes (see
    _resolve_token) are skipped rather than guessed.

    Adjacent word-pairs (bigrams) are checked for an EXACT match first -
    this matters for two-word location names where each word is
    individually ambiguous (e.g. "Kumari Galli" vs "Kumari Marg" both
    start with "kumari", and "Galli"/"Marg" are common street-name suffixes
    shared by several other locations too - but "kumari galli" together is
    unambiguous).
    """
    locations = known_locations or DEFAULT_KNOWN_LOCATIONS
    locations = [loc.lower() for loc in locations]
    if not locations:
        return None

    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    bigrams = [f"{a} {b}".replace("_", " ") for a, b in zip(words, words[1:])]
    for bigram in bigrams:
        if bigram in locations:
            return bigram

    candidates = words + [text.lower().replace("_", " ").strip()]

    for word in candidates:
        if len(word.replace("_", " ")) < 3:
            continue
        resolved = _resolve_token(word, locations)
        if resolved:
            return resolved

    match = process.extractOne(text.replace("_", " "), locations, scorer=fuzz.WRatio, score_cutoff=65)
    if match:
        return match[0]
    return None


# -----------------------------------
# Facilities
# -----------------------------------

def extract_facilities(text):
    found = []
    for canonical, synonyms in FACILITY_MAP.items():
        if any(synonym in text for synonym in synonyms):
            found.append(canonical)
    return found


# -----------------------------------
# Hostel Type
# -----------------------------------

def extract_hostel_type(text):
    for hostel_type, keywords in TYPE_MAP.items():
        if any(keyword in text for keyword in keywords):
            return hostel_type
    return None


# -----------------------------------
# Main Function
# -----------------------------------

def extract_structured_query(query, known_locations):
    raw_query = query
    normalized = normalize_query(query)
    return {
        "location": extract_location(normalized, known_locations),
        "budget": extract_budget(normalized, raw_query),
        "facilities": extract_facilities(normalized),
        "hostel_type": extract_hostel_type(normalized),
        "ner_backend": "rule-based-bilingual-fuzzy",
    }


def engine_status():
    return "rule-based-bilingual-fuzzy (en+ne)"
