"""
Load hostels_final.csv and reviews_final.csv into the database.

Usage:
    python load_data.py
    python load_data.py --reset
"""

import os
import sys
import pandas as pd

from app import create_app
from models import db, Hostel, Review

# -------------------------------------------------------------------
# Dataset paths
# -------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HOSTEL_CSV = os.path.join(
    BASE_DIR,
    "..",
    "dataset_builder",
    "hostels_final.csv"
)

REVIEW_CSV = os.path.join(
    BASE_DIR,
    "..",
    "dataset_builder",
    "reviews_final.csv"
)

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------

def yes_no_to_bool(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in [
        "yes",
        "true",
        "1"
    ]


def split_location(location):
    """
    Example:
        'Dhapakhel, Lalitpur'

    Returns:
        ('Dhapakhel', 'Lalitpur')
    """

    if pd.isna(location):
        return "Unknown", "Kathmandu"

    parts = [x.strip() for x in str(location).split(",")]

    if len(parts) >= 2:
        return parts[0], parts[1]

    return location, "Kathmandu"


# -------------------------------------------------------------------
# Read CSV files
# -------------------------------------------------------------------

def load_datasets():

    print("Reading hostel dataset...")
    hostels = pd.read_csv(HOSTEL_CSV)

    # Fix missing hostel names
    hostels["name"] = (
        hostels["name"]
        .fillna("Unnamed Hostel")
        .astype(str)
        .str.strip()
    )

    hostels.loc[
        hostels["name"] == "",
        "name"
    ] = "Unnamed Hostel"

    print("Reading review dataset...")
    reviews = pd.read_csv(REVIEW_CSV)

    print(f"Hostels found : {len(hostels)}")
    print(f"Reviews found : {len(reviews)}")

    return hostels, reviews

# -------------------------------------------------------------------
# Description Generator
# -------------------------------------------------------------------

def make_description(row):

    desc = []

    desc.append(f"{row['room_type']} room")

    desc.append(f"in {row['precise_location']}")

    if row["wifi"] == "Yes":
        desc.append("WiFi")

    if row["food"] == "Yes":
        desc.append("Meals")

    if row["laundry"] == "Yes":
        desc.append("Laundry")

    if row["study_room"] == "Yes":
        desc.append("Study Room")

    return ", ".join(desc)
# -------------------------------------------------------------------
# Import Hostels
# -------------------------------------------------------------------

def import_hostels(df):

    print("\nImporting hostels...")

    created = 0

    for _, row in df.iterrows():

        area, district = split_location(row["precise_location"])

        hostel = Hostel(

            external_id=str(row["id"]),

            name=row["name"],

            location=area,

            district=district,

            hostel_type=(str(row["gender"]).strip().lower()
                         if pd.notna(row["gender"]) and str(row["gender"]).strip() else "mixed"),

            room_type=row["room_type"],

            price=float(row["monthly_price"]),

            has_meals=yes_no_to_bool(row["food"]),

            wifi=yes_no_to_bool(row["wifi"]),

            laundry=yes_no_to_bool(row["laundry"]),

            parking=yes_no_to_bool(row["parking"]),

            cctv=yes_no_to_bool(row["cctv"]),

            security_guard=False,

            study_room=yes_no_to_bool(row["study_room"]),

            hot_water=yes_no_to_bool(row["hot_water"]),

            base_rating=float(row["rating"]),

            seed_review_count=int(row["review_count"]),

            distance_to_college_km=None,

            distance_to_bus_stop_m=None,

            occupancy=None,

            description=make_description(row),

            latitude=float(row["latitude"]),

            longitude=float(row["longitude"]),

            is_synthetic=(
                str(row["hostel_source"]).lower() == "generated"
            )

        )

        db.session.add(hostel)

        created += 1

    db.session.commit()

    print(f"✓ Imported {created} hostels.")

    # -------------------------------------------------------------------
# Import Reviews
# -------------------------------------------------------------------

def import_reviews(df):

    print("\nImporting reviews...")

    created = 0

    for _, row in df.iterrows():

        hostel = Hostel.query.filter_by(
            external_id=str(row["hostel_id"])
        ).first()

        if hostel is None:
            continue

        review = Review(

            hostel_id=hostel.id,

            reviewer_name="Anonymous",

            review_text=row["review_text"],

            rating=float(row["rating"]),

            sentiment_label=str(row["sentiment"]).lower(),

            sentiment_score=None

        )

        db.session.add(review)

        created += 1

    db.session.commit()

    print(f"✓ Imported {created} reviews.")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():

    reset = "--reset" in sys.argv

    app = create_app()

    with app.app_context():

        if reset:
            print("\nResetting database...")
            db.drop_all()

        db.create_all()

        hostels_df, reviews_df = load_datasets()

        import_hostels(hostels_df)

        import_reviews(reviews_df)

        print("\n----------------------------")
        print("Database Summary")
        print("----------------------------")
        print("Hostels :", Hostel.query.count())
        print("Reviews :", Review.query.count())
        print("----------------------------")
        print("Finished Successfully.")
        print("Run:")
        print("python app.py")


if __name__ == "__main__":
    main()