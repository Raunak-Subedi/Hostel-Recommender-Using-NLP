"""
Stage 6: Sentiment Analysis Integration (Section 3.2 / 2.5 of the proposal).

Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) - chosen in the
proposal for its effectiveness on short, informal review text. Falls back to
a small built-in polarity lexicon if the `vaderSentiment` package is not
installed, so sentiment scoring always works offline.
"""

_VADER_READY = False
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
    _VADER_READY = True
except Exception:
    _analyzer = None
    _VADER_READY = False


# Small built-in polarity lexicon (fallback only) - compact VADER-style word list
_POSITIVE_WORDS = {
    # General
    "good", "great", "excellent", "amazing", "awesome", "wonderful", "fantastic",
    "superb", "outstanding", "perfect", "brilliant", "exceptional", "pleasant",
    "nice", "lovely", "marvelous", "impressive", "remarkable", "favorite",

    # Cleanliness
    "clean", "spotless", "immaculate", "immaculately", "tidy", "hygienic",
    "sanitary", "fresh", "well-maintained", "organized", "neat",

    # Staff
    "friendly", "helpful", "kind", "polite", "courteous", "welcoming",
    "professional", "attentive", "responsive", "supportive", "respectful",
    "cooperative", "accommodating", "cheerful",

    # Rooms
    "comfortable", "cozy", "spacious", "airy", "bright", "modern",
    "beautiful", "elegant", "luxurious", "relaxing", "peaceful",
    "quiet", "secure", "safe", "private",

    # Facilities
    "fast", "reliable", "convenient", "functional", "efficient",
    "well-equipped", "excellent", "working", "powerful",

    # Food
    "delicious", "tasty", "fresh", "flavorful", "yummy",
    "excellent", "satisfying", "healthy",

    # Location
    "central", "accessible", "nearby", "walkable", "close",
    "convenient", "strategic",

    # Value
    "affordable", "cheap", "reasonable", "worth", "worthy",
    "budget-friendly", "economical", "valuable",

    # Experience
    "recommend", "recommended", "recommendedly", "love", "loved",
    "enjoy", "enjoyed", "happy", "satisfied", "pleasant",
    "memorable", "excellent", "fantastic", "perfectly",
    "smooth", "easy", "stress-free", "relaxing", "amazing",
    "best", "top-notch", "five-star", "excellent-service"
}


_NEGATIVE_WORDS = {
    # General
    "bad", "terrible", "awful", "worst", "poor", "disappointing",
    "horrible", "pathetic", "useless", "unacceptable", "mediocre",
    "frustrating", "annoying", "disaster", "mess",

    # Cleanliness
    "dirty", "filthy", "smelly", "stinky", "dusty", "unclean",
    "messy", "sticky", "gross", "unsanitary", "moldy",

    # Staff
    "rude", "unfriendly", "unhelpful", "indifferent",
    "unresponsive", "careless", "disrespectful", "impolite",
    "aggressive", "argued", "ignorant",

    # Rooms
    "cramped", "tiny", "small", "broken", "damaged",
    "old", "outdated", "worn", "uncomfortable", "hot",
    "cold", "humid", "dark", "unsafe", "insecure",

    # Noise
    "noisy", "loud", "disturbing", "crowded", "chaotic",

    # Facilities
    "slow", "faulty", "broken", "malfunctioning",
    "unreliable", "missing", "limited",

    # Food
    "stale", "cold", "tasteless", "bland", "spoiled",
    "burnt", "undercooked", "overcooked",

    # Money
    "expensive", "overpriced", "costly", "waste",
    "ripoff", "scam",

    # Experience
    "problem", "issue", "complaint", "complain",
    "disappointed", "regret", "hate", "hated",
    "avoid", "never", "refund", "failed", "failure",
    "delay", "late", "waiting", "ignored",
    "disgusting", "poor-service", "terrible-service"
}


_NEGATIONS = {
    "not", "no", "never", "none", "nothing",
    "neither", "nor", "n't",
    "hardly", "barely", "rarely", "scarcely",
    "without", "lack", "lacking", "cannot",
    "can't", "won't", "isn't", "aren't",
    "wasn't", "weren't", "doesn't", "don't",
    "didn't", "shouldn't", "wouldn't",
    "couldn't", "mustn't"
}


def _fallback_sentiment(text: str) -> float:
    """Returns a compound-like score in [-1, 1] using simple lexicon counting."""
    if not text:
        return 0.0
    words = text.lower().split()
    score = 0
    negate = False
    for w in words:
        w_clean = w.strip(".,!?;:\"'()")
        if w_clean in _NEGATIONS:
            negate = True
            continue
        if w_clean in _POSITIVE_WORDS:
            score += -1 if negate else 1
        elif w_clean in _NEGATIVE_WORDS:
            score += 1 if negate else -1
        negate = False
    if score == 0:
        return 0.0
    # squash to [-1, 1]
    return max(-1.0, min(1.0, score / max(len(words) ** 0.5, 1)))


def analyze(text: str):
    """
    Returns dict: { compound: float in [-1,1], label: 'positive'|'neutral'|'negative' }
    """
    if _VADER_READY:
        scores = _analyzer.polarity_scores(text or "")
        compound = scores["compound"]
    else:
        compound = _fallback_sentiment(text or "")

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {"compound": round(compound, 4), "label": label}


def normalized_score(text: str) -> float:
    """Maps compound score from [-1, 1] to [0, 1] for use in the ranking formula."""
    return (analyze(text)["compound"] + 1) / 2


def engine_status():
    return "vaderSentiment" if _VADER_READY else "builtin-lexicon-fallback"
