"""
Bilingual (English + Nepali) query normalization.

This is a deliberately deterministic, rule-based bilingual layer (a
dictionary + a couple of regexes) rather than a trained translation
model - it needs no internet access at query time and is easy to audit
and extend. It exists to fix a real gap: the previous pipeline dropped
Devanagari text entirely (tokenize() only keeps [a-zA-Z0-9]) and had no
handling at all for Romanized Nepali ("sasto hostel chahiyo najik
Thamel"), which is how most Nepali speakers actually type.

What it does:
  1. Detects Devanagari script directly (unicode range), rather than
     relying on langdetect - langdetect is unreliable on short text and
     never fires on Romanized Nepali at all.
  2. Maps a curated list of common Nepali words/phrases - covering
     budget ("sasto"/"सस्तो"), gender-type ("keti"/"केटी"), facilities
     ("khana"/"वाइफाइ"), and neighbourhood names - to the canonical
     English terms the rest of the pipeline (SYNONYMS, FACILITY_MAP,
     TYPE_MAP, KNOWN_LOCATIONS) already understands, in BOTH Devanagari
     and Romanized spelling.
  3. Parses Nepali-style budget phrases such as "15 hazar" / "१५ हजार"
     (15 thousand) into a plain number.

Coverage is intentionally focused on common student-hostel search
vocabulary and the neighbourhoods present in this dataset - it is not
a general-purpose Nepali NLP toolkit.
"""

import re

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Generic English words that happen to be a PREFIX of a real location name in
# this dataset ("new baneshwor", "old baneshwor", "mid baneshwor", "new
# plaza") but carry no location meaning on their own. Without this guard, a
# totally unrelated query like "old building, cheap hostel" would wrongly
# resolve "old" to "old baneshwor" just because it's the only "old ..."
# location on the list. These are excluded from ever being used, by
# themselves, as a location-resolving token - only the full phrase (e.g.
# "old baneshwor") or the lexicon's underscore-joined exact substitution
# (e.g. "old_baneshwor") still match, since those go through the exact-match
# path, not prefix/substring guessing.
GENERIC_LOCATION_WORDS = {"new", "old", "mid", "near", "far", "upper", "lower", "north", "south", "east", "west"}

# Devanagari digits 0-9 -> ASCII digits, for parsing "१५ हजार" etc.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI_RE.search(text or ""))


def normalize_devanagari_digits(text: str) -> str:
    return (text or "").translate(_DEVANAGARI_DIGITS)


# ---------------------------------------------------------------------------
# Nepali (Devanagari + common Romanized spellings) -> canonical English term.
# Canonical terms match what SYNONYMS / FACILITY_MAP / TYPE_MAP already use.
# ---------------------------------------------------------------------------
NEPALI_TO_CANONICAL = {
    # --- budget / price ---
    "सस्तो": "budget", "sasto": "budget", "सस्तो मूल्यमा": "budget",
    "बजेट": "budget", "budget": "budget",
    "किफायती": "budget", "kifayati": "budget",

    # --- gender / hostel type ---
    "केटी": "female", "keti": "female", "केटीहरु": "female", "chatra": "female",
    "छात्रा": "female", "chhatra": "female",
    "केटा": "male", "keta": "male", "केटाहरु": "male", "chhatro": "male",
    "मिश्रित": "mixed", "mishrit": "mixed",

    # --- facilities ---
    "वाइफाइ": "internet", "waifai": "internet", "इन्टरनेट": "internet", "internet": "internet",
    "खाना": "meal", "khana": "meal", "भात": "meal", "bhat": "meal", "दालभात": "meal", "dal bhat": "meal",
    "खाजा": "meal", "khaja": "meal",
    "लुगा धुने": "washing", "luga dhune": "washing", "धुनु": "washing", "dhunu": "washing",
    "पार्किङ": "parking", "parking": "parking",
    "भान्सा": "kitchen", "bhansa": "kitchen",
    "तातो पानी": "hot water", "tato pani": "hot water",
    "एसी": "ac",

    # --- query words / connectors (map to words already in STOPWORDS or facility triggers) ---
    "चाहियो": "need", "chahiyo": "need", "खोज्दैछु": "need", "khojdaichu": "need", "khojnu": "find",
    "नजिक": "near", "najik": "near", "नजिकै": "near",
    "को": "of", "मा": "in",
    "होस्टेल": "hostel", "hostel": "hostel", "हस्टेल": "hostel", "hastel": "hostel",

    # --- neighbourhood names (Devanagari + a Romanized variant beyond the
    #     English spelling) - covers both the areas actually present in the
    #     current dataset (nlp.gazetteer.HOSTEL_AREAS) and other well-known
    #     Kathmandu Valley places (nlp.gazetteer.EXTRA_PLACES), since a
    #     query should be able to name a real place either way ---
    "थमेल": "thamel",
    "बानेश्वर": "baneshwor", "baneswor": "baneshwor",
    "नयाँ बानेश्वर": "new baneshwor", "naya baneshwor": "new baneshwor",
    "पुरानो बानेश्वर": "old baneshwor", "purano baneshwor": "old baneshwor",
    "कोटेश्वर": "koteshwor", "koteswor": "koteshwor",
    "पुल्चोक": "pulchowk", "pulchok": "pulchowk",
    "थिमी": "thimi",
    "जावलाखेल": "jawalakhel",
    "कालंकी": "kalanki",
    "कपन": "kapan",
    "महाराजगंज": "maharajgunj",
    "सूर्यविनायक": "suryabinayak", "suryavinayak": "suryabinayak",
    "ढपाखेल": "dhapakhel", "dhapakhel": "dhapakhel",
    "लैनचौर": "lainchaur",
    "अनामनगर": "anamnagar",
    "डिल्लीबजार": "dillibazar", "दिल्लीबजार": "dillibazar",
    "पुतलीसडक": "putalisadak",
    "स्वयम्भू": "swayambhu", "swoyambhu": "swayambhu",
    "टोखा": "tokha",
    "बागबजार": "bagbazar",
    "कुपण्डोल": "kupondole",
    "मिनभवन": "min bhawan", "minbhawan": "min bhawan",
    "सिनामंगल": "sinamangal",
    "टीनकुने": "tinkune", "tinkune": "tinkune",
    "बुद्धनगर": "buddhanagar",
    "घट्टेकुलो": "ghattekulo",
    "शंखमूल": "shankhamul",
    "बौद्ध": "boudha", "boudha": "boudha",
    "काठमाडौं": "kathmandu", "काठमाडौ": "kathmandu",
}

# Multi-word Nepali phrases must be checked before single-word tokenization
# splits them apart (longest-match-first).
_MULTI_WORD_KEYS = sorted(
    [k for k in NEPALI_TO_CANONICAL if " " in k],
    key=len, reverse=True
)

# "15 hazar" / "१५ हजार" / "15हजार" -> 15000
_HAZAR_PATTERN = re.compile(r"(\d+)\s*(?:hazar|hajar|हजार)", re.IGNORECASE)


def extract_nepali_budget(text: str):
    """Parses Nepali-style 'thousand' budget phrasing into a plain number."""
    text = normalize_devanagari_digits(text or "")
    match = _HAZAR_PATTERN.search(text)
    if match:
        return int(match.group(1)) * 1000
    return None


# Explicit "old/mid/new baneshwor" phrases are joined with their qualifier
# (so the qualifier can't be dropped later when generic words like "old"
# get excluded from standalone location matching - see
# GENERIC_LOCATION_WORDS). These resolve to specific named places in the
# gazetteer (nlp.gazetteer.EXTRA_PLACES) even though the current dataset
# only tags hostels with the generic "Baneshwor" area - see that module's
# docstring for why recognizing a real place doesn't require a hostel to
# already be listed there. A BARE "baneshwor" (no qualifier) is left as-is
# and resolves via ordinary exact matching against the dataset's actual
# "baneshwor" area - it is NOT forced to "new baneshwor".
_QUALIFIED_BANESHWOR_RE = re.compile(r"\b(old|mid|new)\s+(baneshwor|baneswor)\b")


def apply_nepali_lexicon(text: str) -> str:
    """
    Replaces known Nepali words/phrases (Devanagari or Romanized) with their
    canonical English equivalent, leaving everything else untouched. Safe to
    run on pure-English text (it's a no-op unless a known Nepali term is
    found).
    """
    if not text:
        return text

    working = text.lower()

    for phrase in _MULTI_WORD_KEYS:
        if phrase in working:
            working = working.replace(phrase, NEPALI_TO_CANONICAL[phrase])

    working = _QUALIFIED_BANESHWOR_RE.sub(lambda m: f"{m.group(1)}_baneshwor", working)

    # Tokenize on Devanagari runs OR Latin/number runs, replace token-by-token
    tokens = re.findall(r"[\u0900-\u097F]+|[a-zA-Z0-9_]+", working)
    mapped = []
    for t in tokens:
        canonical = NEPALI_TO_CANONICAL.get(t, t)
        # Multi-word canonical targets (e.g. "new baneshwor") are joined with
        # an underscore so they survive as ONE token through the rest of the
        # pipeline's [a-zA-Z0-9_]+ tokenizers, instead of being re-split back
        # into separate words like "new" + "baneshwor" - which would let a
        # generic word like "new" go on to ambiguously prefix-match some
        # unrelated "new ..." location on its own.
        mapped.append(canonical.replace(" ", "_") if " " in canonical else canonical)
    return " ".join(mapped)
