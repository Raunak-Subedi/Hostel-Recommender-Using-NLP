import pandas as pd
import time
from geopy.geocoders import Nominatim

# Read your hostel dataset
df = pd.read_csv("kathmandu_hostels.csv")

# Initialize geocoder
geolocator = Nominatim(user_agent="hostel_khoj")

locations = []

for index, row in df.iterrows():

    lat = row["latitude"]
    lon = row["longitude"]

    try:
        location = geolocator.reverse(
            (lat, lon),
            language="en",
            exactly_one=True
        )

        if location:

            address = location.raw.get("address", {})

            area = (
                address.get("suburb")
                or address.get("neighbourhood")
                or address.get("quarter")
                or address.get("village")
                or address.get("hamlet")
                or address.get("town")
                or address.get("city_district")
                or address.get("city")
                or ""
            )

            district = (
                address.get("county")
                or address.get("state_district")
                or address.get("city")
                or ""
            )

            if area and district:
                locations.append(f"{area}, {district}")
            elif area:
                locations.append(area)
            elif district:
                locations.append(district)
            else:
                locations.append("Unknown")

        else:
            locations.append("Unknown")

    except Exception as e:
        print(f"Error at row {index}: {e}")
        locations.append("Unknown")

    # Respect Nominatim usage policy
    time.sleep(1)

# Add precise location column
df["precise_location"] = locations

# Save new dataset
df.to_csv("kathmandu_hostels_precise.csv", index=False)

print(df[["name", "precise_location"]].head())

print("\nFinished!")