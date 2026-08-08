

import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # --- Database ---
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'data', 'hostel_recommender.db')}"
    )
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Security ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # Note: load_data.py reads dataset_builder/hostels_final.csv and
    # reviews_final.csv directly (hardcoded paths, relative to backend/) -
    # it does not use this constant. Kept here only in case a future
    # script wants a single configurable CSV path.
    CSV_PATH = os.path.join(
        BASE_DIR, "..", "dataset_builder", "hostels_final.csv"
    )

    # --- Hybrid recommendation engine weights (Table 3-3 in proposal) ---
    WEIGHT_CONTENT_BASED = 0.40
    WEIGHT_COLLABORATIVE = 0.35
    WEIGHT_SENTIMENT = 0.25

    # --- Final score formula weights (Section 3.2, Stage 6) ---
    WEIGHT_COSINE = 0.40
    WEIGHT_RATING = 0.35
    WEIGHT_SENTIMENT_STAGE6 = 0.25

    # Minimum number of logged interactions before collaborative filtering
    # is trusted over the popularity/rating-based cold-start fallback
    # (see proposal Section 2.1.1 - "cold start problem of collaborative filtering").
    COLLAB_MIN_INTERACTIONS = 3

    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
