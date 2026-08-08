"""
Quick standalone smoke test for the NLP pipeline - no database or Flask
server required. Run with:  python test_nlp.py
"""

from nlp.preprocessing import preprocess, engine_status as prep_status
from nlp.ner import extract_structured_query, engine_status as ner_status
from nlp.sentiment import analyze, engine_status as sentiment_status
from nlp.vectorizer import ContentSimilarityEngine
from nlp.gazetteer import ALL_PLACES

SAMPLE_LOCATIONS = ALL_PLACES


def main():
    print("=" * 70)
    print("NLP ENGINE STATUS")
    print("=" * 70)
    print(f"Preprocessing backend : {prep_status()}")
    print(f"NER backend           : {ner_status()}")
    print(f"Sentiment backend     : {sentiment_status()}  (VADER if available, else lexicon fallback)")

    query = "I need a budget-friendly hostel for girls near Thamel with WiFi and hot water under 15000 rupees"
    print("\n" + "=" * 70)
    print(f"QUERY: {query}")
    print("=" * 70)

    tokens, cleaned = preprocess(query)
    print(f"Tokens after preprocessing : {tokens}")
    print(f"Cleaned string for TF-IDF  : '{cleaned}'")

    structured = extract_structured_query(query, SAMPLE_LOCATIONS)
    print(f"Structured parameters      : {structured}")

    print("\n" + "=" * 70)
    print("BILINGUAL (ENGLISH + NEPALI) QUERIES")
    print("=" * 70)
    bilingual_queries = [
        "Anam ma sasto hostel chahiyo",                          # Romanized Nepali, partial location
        "थमेल नजिक सस्तो केटी हस्टेल वाइफाइ सहित १५ हजार",       # Devanagari
        "Dillibazar najik 15 hazar ma sasto keti hostel chahiyo wifi",  # Romanized + budget phrase
        "old baneshwor boys hostel",                              # ambiguity guard: must NOT resolve to "new baneshwor"
        "hostel near Dhapa",                                      # must resolve to "dhapakhel" even with 0 hostels listed there
        "cheap hostel in Koteshwor",
    ]
    for bq in bilingual_queries:
        tokens, cleaned = preprocess(bq)
        structured_bq = extract_structured_query(bq, SAMPLE_LOCATIONS)
        print(f"  QUERY      : {bq}")
        print(f"  CLEANED    : '{cleaned}'")
        print(f"  STRUCTURED : {structured_bq}\n")

    print("\n" + "=" * 70)
    print("SENTIMENT ANALYSIS")
    print("=" * 70)
    for text in [
        "Staff were incredibly friendly and rooms were spotless, highly recommend!",
        "Front desk was unresponsive and rooms were noisy and dirty, terrible stay.",
        "It was an okay stay, nothing special.",
    ]:
        result = analyze(text)
        print(f"[{result['label']:8}] ({result['compound']:+.3f})  {text}")

    print("\n" + "=" * 70)
    print("TF-IDF / COSINE SIMILARITY")
    print("=" * 70)
    corpus = [
        "thamel wifi breakfast clean spotless",
        "boudha quiet peaceful rooftop terrace",
        "kirtipur budget dorm wifi hot water",
    ]
    engine = ContentSimilarityEngine()
    engine.fit(corpus)
    scores = engine.score("budget wifi hot water")
    for text, score in zip(corpus, scores):
        print(f"  {score:.4f}  <-  '{text}'")

    print("\nAll NLP components executed successfully.")


if __name__ == "__main__":
    main()
