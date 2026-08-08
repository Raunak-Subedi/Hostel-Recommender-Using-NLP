"""
Database models for the Hostel Recommender/Finder System.

Mirrors the "Hostel DB / User DB / Review DB" boxes in the proposal's
block diagram (Figure 2), implemented as a relational schema suitable
for MySQL (production, via XAMPP/WAMP) or SQLite (local/dev default).
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """Students, hostel owners, and administrators (User Layer in Figure 2)."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")  # student | owner | admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviews = db.relationship("Review", backref="author", lazy=True)
    hostels = db.relationship("Hostel", backref="owner", lazy=True)
    interactions = db.relationship("Interaction", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
        }


class Hostel(db.Model):
    """Core hostel listing (Hostel DB in Figure 2).

    Populated by backend/load_data.py from dataset_builder/hostels_final.csv
    (+ reviews_final.csv for seed reviews). Each row is flagged real or
    generated via `is_synthetic`, based on the dataset's own `hostel_source`
    column.
    """
    __tablename__ = "hostels"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(20), unique=True, nullable=True, index=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(100), nullable=False, index=True)  # area, e.g. "Thimi"
    district = db.Column(db.String(50), nullable=True, index=True)    # Kathmandu | Lalitpur | Bhaktapur

    hostel_type = db.Column(db.String(20), default="mixed")  # boys | girls | mixed
    room_type = db.Column(db.String(20), nullable=True)      # Single | Double | Triple
    price = db.Column(db.Float, nullable=False)               # NPR per month
    has_meals = db.Column(db.Boolean, default=False)

    wifi = db.Column(db.Boolean, default=False)
    laundry = db.Column(db.Boolean, default=False)
    parking = db.Column(db.Boolean, default=False)
    cctv = db.Column(db.Boolean, default=False)
    security_guard = db.Column(db.Boolean, default=False)
    study_room = db.Column(db.Boolean, default=False)
    hot_water = db.Column(db.Boolean, default=False)

    base_rating = db.Column(db.Float, nullable=True)          # seed rating from dataset (0-5), None = no data
    seed_review_count = db.Column(db.Integer, default=0)

    distance_to_college_km = db.Column(db.Float, nullable=True)   # dataset stat, generic (not tied to one campus)
    distance_to_bus_stop_m = db.Column(db.Float, nullable=True)
    occupancy = db.Column(db.Integer, nullable=True)              # current resident count in dataset

    description = db.Column(db.Text)                          # generated summary, used for TF-IDF content matching
    latitude = db.Column(db.Float, nullable=True, index=True)
    longitude = db.Column(db.Float, nullable=True, index=True)
    is_synthetic = db.Column(db.Boolean, default=True)

    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviews = db.relationship("Review", backref="hostel", lazy=True, cascade="all, delete-orphan")
    interactions = db.relationship("Interaction", backref="hostel", lazy=True, cascade="all, delete-orphan")

    AMENITY_FIELDS = (
        ("wifi", "Wifi"), ("laundry", "Laundry"), ("parking", "Parking"),
        ("cctv", "CCTV"), ("security_guard", "Security Guard"),
        ("study_room", "Study Room"), ("hot_water", "Hot Water"),
    )

    def amenity_list(self):
        return [label for field, label in self.AMENITY_FIELDS if getattr(self, field)]

    @property
    def amenities(self):
        """Semicolon-joined amenity text, kept for the TF-IDF content corpus."""
        items = self.amenity_list()
        if self.has_meals:
            items.append("Meals")
        return "; ".join(items)

    def average_rating(self):
        """Blend the seed dataset rating with any live submitted reviews."""
        live_ratings = [r.rating for r in self.reviews if r.rating is not None]
        all_ratings = ([self.base_rating] if self.base_rating is not None else []) + live_ratings
        return round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None

    def review_count(self):
        return (self.seed_review_count or 0) + len(self.reviews)

    def to_dict(self, include_reviews=False):
        data = {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "district": self.district,
            "hostel_type": self.hostel_type,
            "room_type": self.room_type,
            "price": self.price,
            "has_meals": self.has_meals,
            "amenities": self.amenity_list(),
            "wifi": self.wifi,
            "laundry": self.laundry,
            "parking": self.parking,
            "cctv": self.cctv,
            "security_guard": self.security_guard,
            "study_room": self.study_room,
            "hot_water": self.hot_water,
            "rating": self.average_rating(),
            "review_count": self.review_count(),
            "distance_to_college_km": self.distance_to_college_km,
            "distance_to_bus_stop_m": self.distance_to_bus_stop_m,
            "occupancy": self.occupancy,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_synthetic": self.is_synthetic,
        }
        if include_reviews:
            data["reviews"] = [r.to_dict() for r in self.reviews]
        return data


class Review(db.Model):
    """Student ratings & reviews (Review DB in Figure 2)."""
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    hostel_id = db.Column(db.Integer, db.ForeignKey("hostels.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewer_name = db.Column(db.String(100))
    review_text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Float)                          # 1-5 star rating
    sentiment_score = db.Column(db.Float)                  # VADER compound score, -1..1
    sentiment_label = db.Column(db.String(10))             # positive | neutral | negative
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "hostel_id": self.hostel_id,
            "reviewer_name": self.reviewer_name,
            "review_text": self.review_text,
            "rating": self.rating,
            "sentiment_score": self.sentiment_score,
            "sentiment_label": self.sentiment_label,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Interaction(db.Model):
    """
    Logs search/view/save actions per session or user.
    Feeds the collaborative-filtering component of the hybrid recommendation
    engine (Section 3.3) - "search history, saved hostels, booking patterns".
    """
    __tablename__ = "interactions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)  # anonymous session, or user id as string
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    hostel_id = db.Column(db.Integer, db.ForeignKey("hostels.id"), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # search | view | save
    query_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
