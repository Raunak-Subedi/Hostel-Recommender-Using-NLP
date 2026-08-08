import re

from rapidfuzz import fuzz, process

from nlp.nepali_lexicon import apply_nepali_lexicon, has_devanagari, GENERIC_LOCATION_WORDS

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    _TRANSLITERATE_READY = True
except Exception:
    _TRANSLITERATE_READY = False

# ------------------------------
# Stopwords
# ------------------------------

STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "been",
    "of", "to", "for", "and", "or", "with", "on", "at", "in", "by",
    "please", "need", "want", "find", "show", "me", "my", "near"
}

# ------------------------------
# Synonyms (English)
# ------------------------------

SYNONYMS = {
    "wifi": "internet",
    "wi-fi": "internet",
    "wireless": "internet",
    "net": "internet",

    "cheap": "budget",
    "affordable": "budget",
    "economical": "budget",

    "girls": "female",
    "ladies": "female",

    "boys": "male",

    "hostel": "hostel",

    "food": "meal",
    "breakfast": "meal",
    "dinner": "meal",

    "laundry": "washing",
    "washing": "washing",

    "parking": "parking",
    "garage": "parking"
}

# ------------------------------
# Known Locations
# ------------------------------
# The recognition vocabulary used for fuzzy/substring location correction.
# This is intentionally broader than just the areas that currently have a
# hostel listing (nlp.gazetteer.HOSTEL_AREAS) - see nlp/gazetteer.py's
# docstring for why (e.g. "Dhapa" should still resolve to "Dhapakhel" even
# though no hostel happens to be listed there). recommender.py normally
# passes in the live DB-locations-union-gazetteer list instead; this is
# only the fallback used if no list is supplied.

from nlp.gazetteer import ALL_PLACES as KNOWN_LOCATIONS

# ------------------------------
# Bilingual normalization (English + Nepali)
# ------------------------------


def normalize_language(text):
    """
    Bilingual normalization pass:
      1. Apply the Nepali lexicon (Devanagari + Romanized Nepali -> English
         canonical terms) FIRST, while the original script is still intact -
         this is what actually makes Nepali queries work, since dictionary
         lookup is more reliable than phonetic transliteration for matching
         against English filter/synonym keywords.
      2. Any Devanagari left over (words not in the lexicon) gets
         transliterated to a romanized form as a best-effort fallback, so it
         at least survives tokenization instead of being silently dropped.
    """
    text = apply_nepali_lexicon(text)

    if has_devanagari(text) and _TRANSLITERATE_READY:
        try:
            text = transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
        except Exception:
            pass

    return text.lower()


# ------------------------------
# Spell / partial-name correction for locations
# ------------------------------

def _resolve_token(token, locations):
    """Same ambiguity-safe resolution logic as nlp.ner._resolve_token."""
    token = token.replace("_", " ")
    if token in locations:
        return token

    if token in GENERIC_LOCATION_WORDS:
        return None

    prefix_hits = [loc for loc in locations if loc.startswith(token)]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        shortest = min(prefix_hits, key=len)
        return shortest if len(token) / len(shortest) >= 0.6 else None

    substring_hits = [loc for loc in locations if token in loc]
    if len(substring_hits) == 1:
        return substring_hits[0]
    if len(substring_hits) > 1:
        shortest = min(substring_hits, key=len)
        return shortest if len(token) / len(shortest) >= 0.6 else None

    return None


def correct_locations(tokens, known_locations=None):
    """
    Resolves a token to a known location name using, in order:
      1. Exact match.
      2. Deterministic prefix/substring match - e.g. "dhapa" or "dhap"
         matches "dhapakhel" because it's literally a prefix of it. This is
         checked BEFORE fuzzy scoring so partial neighbourhood names always
         resolve predictably, regardless of fuzzy-matcher internals.
         Ambiguous short prefixes that match multiple different locations
         (e.g. "new" -> "new plaza" / "new baneshwor") are left unresolved
         rather than guessed - see _resolve_token.
      3. Fuzzy match (rapidfuzz WRatio) as a fallback for typos, e.g.
         "banexhwor" -> "baneshwor".
    Only applied to tokens of length >= 3 to avoid false positives on short
    common words.
    """
    locations = known_locations or KNOWN_LOCATIONS
    locations = [loc.lower() for loc in locations]
    corrected = []

    for token in tokens:
        bare = token.replace("_", " ")
        if len(bare) < 3:
            corrected.append(bare)
            continue

        resolved = _resolve_token(token, locations)
        if resolved:
            corrected.append(resolved)
            continue

        match = process.extractOne(bare, locations, scorer=fuzz.WRatio, score_cutoff=78)
        corrected.append(match[0] if match else bare)

    return corrected


# ------------------------------
# Synonym replacement
# ------------------------------

def replace_synonyms(tokens):
    return [SYNONYMS.get(t, t) for t in tokens]


# ------------------------------
# Tokenization
# ------------------------------

def tokenize(text):
    text = normalize_language(text)
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


# ------------------------------
# Stopwords
# ------------------------------

def remove_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS]


# ------------------------------
# Main preprocess
# ------------------------------

def preprocess(text):
    tokens = tokenize(text)
    tokens = correct_locations(tokens)
    tokens = replace_synonyms(tokens)
    tokens = remove_stopwords(tokens)
    return tokens, " ".join(tokens)


def engine_status():
    return "rule-based bilingual (en+ne) + fuzzy-match normalization"
