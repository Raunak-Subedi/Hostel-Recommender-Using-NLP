import osmnx as ox
import pandas as pd

places = [
    "Kathmandu, Nepal",
    "Lalitpur, Nepal",
    "Bhaktapur, Nepal"
]

tags = {"tourism": "hostel"}

dfs = []

for place in places:
    print(f"Searching {place}...")

    try:
        gdf = ox.features_from_place(place, tags)

        if len(gdf) > 0:

            cols = []

            for c in [
                "name",
                "addr:street",
                "addr:city",
                "phone",
                "website"
            ]:
                if c in gdf.columns:
                    cols.append(c)

            cols.extend(["geometry"])

            gdf = gdf[cols]

            gdf["latitude"] = gdf.geometry.centroid.y
            gdf["longitude"] = gdf.geometry.centroid.x

            gdf = gdf.drop(columns="geometry")

            gdf["source_place"] = place

            dfs.append(gdf)

    except Exception as e:
        print(e)

hostels = pd.concat(dfs, ignore_index=True)

hostels = hostels.drop_duplicates(subset=["name"])

hostels.to_csv("kathmandu_hostels.csv", index=False)

print(hostels.head())

print("\nTotal hostels:", len(hostels))