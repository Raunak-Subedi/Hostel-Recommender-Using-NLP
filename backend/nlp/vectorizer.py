from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# NOTE on multilingual coverage: the recommender always runs queries through
# nlp.preprocessing.preprocess() BEFORE they reach this engine, which
# converts recognized Nepali words/phrases (Devanagari or Romanized) into
# their canonical English form via nlp/nepali_lexicon.py. That dictionary
# lookup is what makes bilingual search actually work for the covered
# vocabulary (locations, facilities, budget words, gender terms).
#
# This multilingual model (vs. an English-only one) is a second layer of
# defence for anything NOT in that dictionary - free-text description
# matching when a query contains Nepali words outside the curated list.
# Nepali isn't in this model's officially benchmarked language list, so
# treat this as "better than an English-only model on unseen Nepali text",
# not as guaranteed high-quality Nepali semantic search on its own.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


class ContentSimilarityEngine:

    def __init__(self):
        # NOTE: the model is intentionally NOT loaded here. RecommendationEngine
        # (and therefore ContentSimilarityEngine) is constructed at import time
        # in app.py ("engine = RecommendationEngine(Config)"), and load_data.py
        # does `from app import create_app` - so eager-loading the model here
        # used to force a full sentence-transformers download/load just to run
        # `python load_data.py`, which has nothing to do with embeddings. The
        # model is loaded lazily on first real use instead (see _ensure_model).
        self.model = None

        self.documents = []
        self.embeddings = None

    # ----------------------------------
    # Lazy model load
    # ----------------------------------

    def _ensure_model(self):
        if self.model is None:
            print(f"Loading Sentence Transformer ({EMBEDDING_MODEL_NAME})...")
            self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return self.model

    # ----------------------------------
    # Build Index
    # ----------------------------------

    def fit(self, documents):

        self.documents = documents

        model = self._ensure_model()

        self.embeddings = model.encode(
            documents,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

    # ----------------------------------
    # Encode Query
    # ----------------------------------

    def encode_query(self, query):

        model = self._ensure_model()

        return model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        )

    # ----------------------------------
    # Similarity Scores
    # ----------------------------------

    def score(self, query):

        if self.embeddings is None:
            return []

        query_embedding = self.encode_query(query)

        scores = cosine_similarity(
            query_embedding,
            self.embeddings
        )[0]

        return scores.tolist()

    # ----------------------------------
    # Top K Results
    # ----------------------------------

    def search(self, query, top_k=10):

        scores = self.score(query)

        ranked = sorted(

            enumerate(scores),

            key=lambda x: x[1],

            reverse=True

        )

        return ranked[:top_k]

    # ----------------------------------
    # Add New Hostel
    # ----------------------------------

    def add_document(self, document):

        model = self._ensure_model()

        new_embedding = model.encode(

            [document],

            convert_to_numpy=True,

            normalize_embeddings=True

        )

        if self.embeddings is None:

            self.embeddings = new_embedding

        else:

            self.embeddings = np.vstack(

                [

                    self.embeddings,

                    new_embedding

                ]

            )

        self.documents.append(document)

    # ----------------------------------
    # Save Embeddings
    # ----------------------------------

    def save(self, path):

        np.save(path, self.embeddings)

    # ----------------------------------
    # Load Embeddings
    # ----------------------------------

    def load(self, path):

        self.embeddings = np.load(path)