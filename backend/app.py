

import uuid

from flask import Flask, request, jsonify, session
from flask_cors import CORS

from config import Config
from models import db, User, Hostel, Review, Interaction
from recommender import RecommendationEngine
from nlp import sentiment as sentiment_engine
from nlp import preprocessing as preprocessing_engine
from nlp import ner as ner_engine
import geo

engine = RecommendationEngine(Config)


def enrich_with_geo(results, college_param=None, user_lat=None, user_lon=None):
    """
    Adds map-related fields to a list of hostel dicts (in place, returns the
    same list): distance_to_college_km, distance_to_user_km, match_level.

    If a college is given, results are re-sorted ascending by distance to
    that campus (the "college filter automatically sorts by distance"
    requirement) - the recommendation/rating score still drives the
    green/yellow/red match_level shown on each marker/card.
    """
    college = geo.find_college(college_param) if college_param else None

    for hostel_data in results:
        lat, lon = hostel_data.get("latitude"), hostel_data.get("longitude")

        if college:
            # A specific campus was selected - override the dataset's generic
            # distance_to_college_km stat with the exact distance to that campus.
            hostel_data["distance_to_college_km"] = geo.haversine_km(lat, lon, college["latitude"], college["longitude"])
        # else: leave hostel_data["distance_to_college_km"] as the generic
        # dataset stat already set by Hostel.to_dict() - don't discard it.

        hostel_data["distance_to_user_km"] = (
            geo.haversine_km(lat, lon, user_lat, user_lon) if (user_lat and user_lon) else None
        )

        score = hostel_data.get("hybrid_score")
        if score is None:
            # Plain browse endpoint has no hybrid_score - use rating as a proxy
            score = min((hostel_data.get("rating") or 0) / 5, 1)
        hostel_data["match_level"] = geo.match_level(score)

    if college:
        results.sort(key=lambda r: (r["distance_to_college_km"] is None, r["distance_to_college_km"]))
    elif user_lat and user_lon:
        results.sort(key=lambda r: (r["distance_to_user_km"] is None, r["distance_to_user_km"]))

    return results, college


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, supports_credentials=True)
    db.init_app(app)
    return app


app = create_app()


def get_session_id():
    """Anonymous session id used for collaborative-filtering interaction logs,
    independent of whether the visitor is logged in."""
    sid = request.headers.get("X-Session-Id")
    if not sid:
        sid = session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
    session["sid"] = sid
    return sid


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "database": Config.SQLALCHEMY_DATABASE_URI.split("://")[0],
        "nlp_preprocessing_engine": preprocessing_engine.engine_status(),
        "nlp_ner_engine": ner_engine.engine_status(),
        "sentiment_engine": sentiment_engine.engine_status(),
        "hostel_count": Hostel.query.count(),
    })


@app.route("/api/colleges")
def list_colleges():
    """Known Kathmandu Valley campuses for the 'college filter' map feature."""
    return jsonify({"colleges": geo.COLLEGES})


# ---------------------------------------------------------------------------
# Authentication Module
# ---------------------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role", "student")

    if not username or not email or not password:
        return jsonify({"error": "username, email, and password are required"}), 400
    if role not in ("student", "owner", "admin"):
        role = "student"
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"error": "username or email already registered"}), 409

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    return jsonify({"user": user.to_dict()}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "invalid email or password"}), 401

    session["user_id"] = user.id
    return jsonify({"user": user.to_dict()})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "logged out"})


@app.route("/api/auth/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    user = User.query.get(user_id)
    return jsonify({"user": user.to_dict() if user else None})


# ---------------------------------------------------------------------------
# Search & Filter Module  (the NLP-powered natural-language search)
# ---------------------------------------------------------------------------
@app.route("/api/search", methods=["POST"])
def search():
    """
    Implements the flowchart (Figure 3): NLP preprocessing -> structured
    parameters -> recommendation engine -> sentiment-adjusted ranking.
    """
    data = request.get_json(force=True) or {}
    query_text = (data.get("query") or "").strip()
    filters = data.get("filters") or {}

    if not query_text and not filters:
        return jsonify({"error": "Provide a natural-language query or filters."}), 400

    session_id = get_session_id()

    tokens, _ = preprocessing_engine.preprocess(query_text) if query_text else ([], "")

    results, structured, expanded = engine.recommend(
        query_text=query_text,
        session_id=session_id,
        top_k=int(data.get("top_k", 20)),
        hard_filters=filters,
    )

    # Log this search for collaborative filtering (top result, if any)
    if results:
        db.session.add(Interaction(
            session_id=session_id,
            user_id=session.get("user_id"),
            hostel_id=results[0]["id"],
            action="search",
            query_text=query_text,
        ))
        db.session.commit()

    college_param = filters.get("college") or data.get("college")
    try:
        user_lat = float(data.get("user_lat")) if data.get("user_lat") is not None else None
        user_lon = float(data.get("user_lon")) if data.get("user_lon") is not None else None
    except (TypeError, ValueError):
        user_lat = user_lon = None
    results, college = enrich_with_geo(results, college_param, user_lat, user_lon)

    max_distance_km = filters.get("max_distance_km") or data.get("max_distance_km")
    if college and max_distance_km:
        try:
            max_distance_km = float(max_distance_km)
            results = [r for r in results if r["distance_to_college_km"] is not None
                       and r["distance_to_college_km"] <= max_distance_km]
        except (TypeError, ValueError):
            pass

    location_note = None
    place = structured.get("location")
    location_mode = structured.get("location_mode")
    area_alias = structured.get("location_area_alias")

    if location_mode == "exact" and area_alias and place:
        location_note = (
            f"Showing hostels in \"{area_alias.title()}\", near {place.title()}."
        )
    elif location_mode == "proximity" and place:
        location_note = (
            f"No hostels are listed exactly in \"{place.title()}\", so these are the "
            f"closest ones by real distance instead."
        )
    elif expanded and place:
        # Genuinely couldn't anchor this place at all (no coordinates known
        # for it either) - the old "show everything" fallback still applies
        # here since there's nothing to sort by.
        location_note = (
            f"\"{place.title()}\" isn't recognized closely enough - showing results "
            f"from all areas instead."
        )

    return jsonify({
        "query": query_text,
        "tokens": tokens,
        "structured_query": structured,
        "search_expanded": expanded,
        "location_note": location_note,
        "location_mode": location_mode,
        "location_coords": structured.get("location_coords"),
        "result_count": len(results),
        "results": results,
        "college": college,
    })


@app.route("/api/hostels")
def list_hostels():
    """Plain filter-based browse/search (Search & Filter Module, non-NLP path)."""
    q = Hostel.query

    location = request.args.get("location")
    if location:
        q = q.filter(Hostel.location.ilike(f"%{location}%"))

    max_price = request.args.get("max_price", type=float)
    if max_price:
        q = q.filter(Hostel.price <= max_price)

    min_price = request.args.get("min_price", type=float)
    if min_price:
        q = q.filter(Hostel.price >= min_price)

    hostel_type = request.args.get("hostel_type")
    if hostel_type and hostel_type != "any":
        q = q.filter(Hostel.hostel_type == hostel_type)

    district = request.args.get("district")
    if district and district != "any":
        q = q.filter(Hostel.district == district)

    room_type = request.args.get("room_type")
    if room_type and room_type != "any":
        q = q.filter(Hostel.room_type == room_type)

    if request.args.get("meals") == "1":
        q = q.filter(Hostel.has_meals.is_(True))

    for field in ("wifi", "laundry", "parking", "cctv", "security_guard", "study_room", "hot_water"):
        if request.args.get(field) == "1":
            q = q.filter(getattr(Hostel, field).is_(True))

    hostels = q.order_by(Hostel.name).all()

    min_rating = request.args.get("min_rating", type=float)
    results = [h.to_dict() for h in hostels]
    if min_rating:
        results = [r for r in results if (r["rating"] or 0) >= min_rating]

    college_param = request.args.get("college")
    user_lat = request.args.get("user_lat", type=float)
    user_lon = request.args.get("user_lon", type=float)
    max_distance_km = request.args.get("max_distance_km", type=float)
    results, college = enrich_with_geo(results, college_param, user_lat, user_lon)

    if college and max_distance_km:
        results = [r for r in results if r["distance_to_college_km"] is not None
                   and r["distance_to_college_km"] <= max_distance_km]

    return jsonify({"result_count": len(results), "results": results, "college": college})


@app.route("/api/locations")
def locations():
    locs = sorted({row[0] for row in db.session.query(Hostel.location).distinct().all()})
    return jsonify({"locations": locs})


@app.route("/api/districts")
def districts():
    vals = sorted({row[0] for row in db.session.query(Hostel.district).distinct().all() if row[0]})
    return jsonify({"districts": vals})


@app.route("/api/hostels/compare")
def compare_hostels():
    ids_param = request.args.get("ids", "")
    try:
        ids = [int(x) for x in ids_param.split(",") if x.strip()]
    except ValueError:
        return jsonify({"error": "ids must be a comma-separated list of integers"}), 400

    hostels = Hostel.query.filter(Hostel.id.in_(ids)).all()
    return jsonify({"results": [h.to_dict(include_reviews=True) for h in hostels]})


# ---------------------------------------------------------------------------
# Hostel Management Module
# ---------------------------------------------------------------------------
@app.route("/api/hostels/<int:hostel_id>")
def get_hostel(hostel_id):
    hostel = Hostel.query.get_or_404(hostel_id)

    session_id = get_session_id()
    db.session.add(Interaction(session_id=session_id, user_id=session.get("user_id"),
                                hostel_id=hostel_id, action="view"))
    db.session.commit()

    data = hostel.to_dict(include_reviews=True)
    college_param = request.args.get("college")
    user_lat = request.args.get("user_lat", type=float)
    user_lon = request.args.get("user_lon", type=float)
    [data], college = enrich_with_geo([data], college_param, user_lat, user_lon)
    data["college"] = college
    return jsonify(data)


@app.route("/api/hostels", methods=["POST"])
def create_hostel():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "login required to list a hostel"}), 401

    data = request.get_json(force=True) or {}
    required = ["name", "location", "price"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    amenity_flags = {
        f: bool(data.get(f)) for f in
        ("wifi", "laundry", "parking", "cctv", "security_guard", "study_room", "hot_water")
    }

    hostel = Hostel(
        name=data["name"],
        location=data["location"],
        district=data.get("district"),
        price=float(data["price"]),
        hostel_type=data.get("hostel_type", "mixed"),
        room_type=data.get("room_type"),
        has_meals=bool(data.get("has_meals")),
        base_rating=float(data["base_rating"]) if data.get("base_rating") not in (None, "") else None,
        description=data.get("description", f"{data['name']} in {data['location']}."),
        latitude=float(data["latitude"]) if data.get("latitude") not in (None, "") else None,
        longitude=float(data["longitude"]) if data.get("longitude") not in (None, "") else None,
        is_synthetic=False,
        owner_id=user_id,
        **amenity_flags,
    )
    db.session.add(hostel)
    db.session.commit()
    engine.build_corpus()  # rebuild TF-IDF corpus to include the new listing

    return jsonify(hostel.to_dict()), 201


@app.route("/api/hostels/<int:hostel_id>", methods=["PUT"])
def update_hostel(hostel_id):
    user_id = session.get("user_id")
    hostel = Hostel.query.get_or_404(hostel_id)
    if hostel.owner_id and hostel.owner_id != user_id:
        return jsonify({"error": "only the owning hostel manager can edit this listing"}), 403

    data = request.get_json(force=True) or {}
    for field in ("name", "location", "district", "hostel_type", "room_type", "description"):
        if field in data:
            setattr(hostel, field, data[field])
    if "price" in data:
        hostel.price = float(data["price"])
    if "has_meals" in data:
        hostel.has_meals = bool(data["has_meals"])
    for field in ("wifi", "laundry", "parking", "cctv", "security_guard", "study_room", "hot_water"):
        if field in data:
            setattr(hostel, field, bool(data[field]))
    if "latitude" in data:
        hostel.latitude = float(data["latitude"]) if data["latitude"] not in (None, "") else None
    if "longitude" in data:
        hostel.longitude = float(data["longitude"]) if data["longitude"] not in (None, "") else None

    db.session.commit()
    engine.build_corpus()
    return jsonify(hostel.to_dict())


@app.route("/api/hostels/<int:hostel_id>", methods=["DELETE"])
def delete_hostel(hostel_id):
    user_id = session.get("user_id")
    hostel = Hostel.query.get_or_404(hostel_id)
    if hostel.owner_id and hostel.owner_id != user_id:
        return jsonify({"error": "only the owning hostel manager can delete this listing"}), 403

    db.session.delete(hostel)
    db.session.commit()
    engine.build_corpus()
    return jsonify({"message": "hostel deleted"})


# ---------------------------------------------------------------------------
# Review Module
# ---------------------------------------------------------------------------
@app.route("/api/hostels/<int:hostel_id>/reviews", methods=["GET"])
def list_reviews(hostel_id):
    hostel = Hostel.query.get_or_404(hostel_id)
    return jsonify({"results": [r.to_dict() for r in hostel.reviews]})


@app.route("/api/hostels/<int:hostel_id>/reviews", methods=["POST"])
def submit_review(hostel_id):
    """Student submits a rating + review; NLP sentiment analysis runs immediately
    and the hostel's aggregate ranking data updates (Figure 3: 'User Submits
    Review & Rating' -> 'NLP Processes Review Text -> Update Sentiment Database')."""
    hostel = Hostel.query.get_or_404(hostel_id)
    data = request.get_json(force=True) or {}

    review_text = (data.get("review_text") or "").strip()
    rating = data.get("rating")
    if not review_text or rating is None:
        return jsonify({"error": "review_text and rating are required"}), 400

    try:
        rating = float(rating)
        assert 1 <= rating <= 5
    except (ValueError, AssertionError):
        return jsonify({"error": "rating must be a number between 1 and 5"}), 400

    sentiment_result = sentiment_engine.analyze(review_text)

    review = Review(
        hostel_id=hostel_id,
        user_id=session.get("user_id"),
        reviewer_name=data.get("reviewer_name", "Anonymous Student"),
        review_text=review_text,
        rating=rating,
        sentiment_score=sentiment_result["compound"],
        sentiment_label=sentiment_result["label"],
    )
    db.session.add(review)
    db.session.commit()

    session_id = get_session_id()
    db.session.add(Interaction(session_id=session_id, user_id=session.get("user_id"),
                                hostel_id=hostel_id, action="save"))
    db.session.commit()

    engine.build_corpus()  # new review text feeds back into content-based matching

    return jsonify({
        "review": review.to_dict(),
        "hostel_rating": hostel.average_rating(),
    }), 201


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if Hostel.query.count() == 0:
            print("No hostels found in the database.")
            print("Run `python load_data.py` first to import the CSV dataset.")
        else:
            engine.build_corpus()
            print(f"Loaded TF-IDF corpus for {Hostel.query.count()} hostels.")

    app.run(debug=Config.DEBUG, port=5000, host="0.0.0.0")
