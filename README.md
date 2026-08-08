# Hostel Khoj

A hostel recommender/finder for Kathmandu Valley students — Flask API +
a vanilla HTML/JS/Leaflet frontend. Search in English or Nepali, filter
by campus distance, and browse hostels on an interactive map.

## What's in this build

- **300-hostel dataset** across Kathmandu, Lalitpur, and Bhaktapur —
  168 real hostels (OSM-sourced) plus 132 generated listings to round out
  coverage, built by the scripts in `dataset_builder/` and imported via
  `backend/load_data.py`. Each row is flagged `is_synthetic` based on the
  dataset's own `hostel_source` column, so real vs. generated is always
  visible in the API response.
- **Leaflet map** on the results page with color-coded markers:
  🟢 excellent match · 🟡 good match · 🔴 low match.
- **College/campus filter** — pick a real Kathmandu Valley college and
  results automatically re-sort by distance to that campus.
- **"Use my current location"** (browser geolocation) + road routing via
  OSRM, with marker ⇄ card sync (click either one to highlight the other).
- **Bilingual search (English + Nepali)** — type in English, Devanagari
  ("थमेल नजिक सस्तो हस्टेल"), or Romanized Nepali ("sasto hostel chahiyo
  najik Thamel") and it resolves the same way. See "About the NLP" below.
- Filters beyond plain area/price/type: room type (Single/Double/Shared),
  meals included, and individual amenity checkboxes (wifi, laundry,
  parking, CCTV, study room, hot water).

## About the NLP

Free-text queries go through: tokenization (Devanagari + Romanized Nepali
aware) → Nepali-to-English lexicon substitution → stopword removal →
location/budget/hostel-type/facility extraction → semantic content
similarity (multilingual sentence-transformer) → a hybrid score blending
content match, facility match, collaborative filtering (session search
history), review sentiment (VADER), and rating.

**Location recognition is broader than "areas that currently have a
hostel listed."** `nlp/gazetteer.py` combines the dataset's own hostel
areas with a wider list of real Kathmandu Valley place names (including
every college's neighbourhood and well-known spots like Thamel or
Dhapakhel). A query like "hostel near Dhapa" correctly resolves the
partial word to "Dhapakhel" even if no hostel happens to be listed there.

**When a recognized place has zero hostels, the search does a real
proximity search instead of giving up on location** — `recommender.py`
anchors on that place's real coordinates (`geo.PLACE_COORDS`) and ranks
every hostel by actual haversine distance from it, trying progressively
wider radii (3km → 6km → 10km → no cap) until one has results. Each
result carries `distance_from_location_km`, shown on its card, and the
map drops a pin at the searched place even when no hostel sits exactly
there.

## Running it

Requires Python 3.10+ (developed/tested on 3.12).

```bash
cd backend
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

pip install -r requirements.txt
python load_data.py --reset   # builds the tables + imports the 300-hostel dataset
python app.py                 # starts the API on http://localhost:5000
``
cd backend
pip install -r requirements.txt
python load_data.py --reset   # builds tables + imports hostel_khoj_dataset.csv
python app.py                 # starts the API on :5000

cd backend
py -3.12 -m venv venv  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install python-dotenv
python load_data.py --reset     # loads the 190-hostel dataset into SQLite
python app.py 

Then open `frontend/index.html` directly in a browser, or serve it with
any static file server (e.g. `python -m http.server` from inside
`frontend/`). It talks to the API at `http://localhost:5000/api` by
default — override with `window.HF_API_BASE` before `app.js` loads if
you deploy the backend elsewhere.

**Heads up on install size:** `requirements.txt` includes
`sentence-transformers` + `torch` (used for semantic search over hostel
descriptions/reviews) — this is a multi-hundred-MB download the first
time you `pip install`. The embedding model itself
(`paraphrase-multilingual-MiniLM-L12-v2`) is loaded lazily, only when it's
actually needed for search — so `python load_data.py` never triggers it,
and **only the very first `python app.py` needs an internet connection**
(to download the model once). After that first download it's cached
locally and everything works offline.

No `.env` file is required to run locally — SQLite is the default
(see `backend/config.py`). Copy `backend/.env.example` to `backend/.env`
only if you want to point at MySQL instead, or change the Flask secret
key.

## Regenerating the dataset

The dataset shipped in `dataset_builder/hostels_final.csv` /
`reviews_final.csv` was already built for you — you don't need to redo
this to run the app. If you want to regenerate it from scratch (e.g. to
pull fresh OSM data), the scripts are in `dataset_builder/`
(`osm_hostels.py`, `reverse_geocode.py`, `generate_dataset.py`); they
need extra packages not in `backend/requirements.txt` (`requests`,
`faker`) and, for the OSM/geocoding steps, an internet connection.

## Project structure

```
backend/            Flask API, models, NLP pipeline, recommendation engine
  nlp/               tokenization, Nepali lexicon, gazetteer, NER, sentiment, embeddings
  data/              SQLite database (created on first `load_data.py` run)
dataset_builder/     source CSVs + scripts used to build the hostel dataset
frontend/            vanilla HTML/CSS/JS + Leaflet map UI
```
