"""
Geo utilities for the map / college-distance features.

- COLLEGES: a static list of real Kathmandu Valley college / university
  campuses (name + coordinates) used to power the "College filter" that
  automatically sorts hostels by distance to a selected campus.
- haversine_km: great-circle distance between two lat/lon points, used both
  for "distance to college" and "distance to my current location".
- match_level: buckets a hostel's hybrid recommendation score into
  green / yellow / red so the frontend can colour markers + card borders.
"""

import math

# ---------------------------------------------------------------------------
# Known Kathmandu Valley college / university campuses.
# Coordinates are approximate campus locations (WGS84 decimal degrees).
# ---------------------------------------------------------------------------
COLLEGES = [
    {"id": "tu-kirtipur", "name": "Tribhuvan University, Kirtipur", "latitude": 27.6768, "longitude": 85.2879},
    {"id": "ioe-pulchowk", "name": "Pulchowk Campus (IOE)", "latitude": 27.6825, "longitude": 85.3157},
    {"id": "ioe-thapathali", "name": "Thapathali Campus (IOE)", "latitude": 27.6912, "longitude": 85.3181},
    {"id": "st-xaviers", "name": "St. Xavier's College, Maitighar", "latitude": 27.6939, "longitude": 85.3157},
    {"id": "patan-campus", "name": "Patan Multiple Campus", "latitude": 27.6737, "longitude": 85.3247},
    {"id": "kantipur-engineering", "name": "Kantipur Engineering College (KEC), Dhapakhel", "latitude": 27.6320, "longitude": 85.3330},
    {"id": "nepal-commerce", "name": "Nepal Commerce Campus, Min Bhawan", "latitude": 27.6988, "longitude": 85.3416},
    {"id": "amrit-science", "name": "Amrit Science Campus (ASCOL), Lainchaur", "latitude": 27.7175, "longitude": 85.3160},
    {"id": "padma-kanya", "name": "Padma Kanya Campus, Bagbazar", "latitude": 27.7047, "longitude": 85.3140},
    {"id": "kathmandu-model", "name": "Kathmandu Model College, Bagbazar", "latitude": 27.7042, "longitude": 85.3138},
    {"id": "islington", "name": "Islington College, Kamalpokhari", "latitude": 27.7145, "longitude": 85.3287},
    {"id": "ku-dhulikhel", "name": "Kathmandu University, Dhulikhel", "latitude": 27.6206, "longitude": 85.5486},
]

COLLEGES_BY_ID = {c["id"]: c for c in COLLEGES}

# ---------------------------------------------------------------------------
# Place-name coordinates for the "search near a location" feature.
#
# The hostel dataset only tags each hostel with a coarse `area` string (e.g.
# "baneshwor"). A search for a real place that isn't one of those areas
# (e.g. "Thamel") used to resolve correctly as a *place* (see
# nlp/gazetteer.py) but then fail to match any hostel's area string exactly,
# which silently dropped the location filter and showed every hostel in the
# valley, unsorted by distance - the opposite of what "hostel near Thamel"
# means.
#
# PLACE_COORDS gives every recognized place (both real hostel areas and the
# broader gazetteer of Kathmandu Valley neighbourhoods) an approximate
# real-world centre point, so that when there's no exact area match we can
# still answer "which hostels are actually closest to this point" instead of
# giving up on location entirely. Coordinates are approximate neighbourhood
# centres (WGS84 decimal degrees), not exact addresses.
#
# Note: the hostel-area coordinates below intentionally use real-world
# coordinates rather than the dataset's own area centroid, because the
# dataset's per-hostel lat/lon are synthetic and don't reliably cluster by
# area - the real-world anchor point is what a person actually means when
# they type an area name.
# ---------------------------------------------------------------------------
_HOSTEL_AREA_COORDS = {
    "baneshwor": (27.6905, 85.3380),
    "koteshwor": (27.6789, 85.3492),
    "pulchowk": (27.6825, 85.3157),
    "thimi": (27.6789, 85.3894),
    "jawalakhel": (27.6764, 85.3159),
    "kalanki": (27.6936, 85.2809),
    "kapan": (27.7420, 85.3540),
    "maharajgunj": (27.7370, 85.3330),
    "suryabinayak": (27.6720, 85.4330),
}

_EXTRA_PLACE_COORDS = {
    "dhapakhel": (27.6320, 85.3242), "lainchaur": (27.7175, 85.3160),
    "kirtipur": (27.6768, 85.2879), "thapathali": (27.6912, 85.3181),
    "maitighar": (27.6939, 85.3157), "dhulikhel": (27.6206, 85.5486),
    "kamalpokhari": (27.7145, 85.3287), "kamal pokhari": (27.7145, 85.3287),
    "thamel": (27.7154, 85.3123), "new baneshwor": (27.6889, 85.3428),
    "old baneshwor": (27.6912, 85.3368), "mid baneshwor": (27.6900, 85.3400),
    "anamnagar": (27.6979, 85.3266), "dillibazar": (27.7047, 85.3252),
    "putalisadak": (27.7037, 85.3221), "tokha": (27.7580, 85.3400),
    "swayambhu": (27.7149, 85.2903), "sinamangal": (27.6997, 85.3556),
    "tinkune": (27.6889, 85.3512), "min bhawan": (27.6988, 85.3416),
    "shankhamul": (27.6832, 85.3335), "buddhanagar": (27.6940, 85.3350),
    "ghattekulo": (27.6980, 85.3300), "kupondole": (27.6867, 85.3170),
    "bagbazar": (27.7042, 85.3138), "balkumari": (27.6675, 85.3390),
    "basundhara": (27.7370, 85.3260), "battisputali": (27.7011, 85.3395),
    "bhimsengola": (27.7020, 85.3370), "dhobidhara": (27.7105, 85.3225),
    "dhumbarahi": (27.7280, 85.3370), "gyaneshwor": (27.7185, 85.3260),
    "hanumansthan": (27.6995, 85.3450), "maitidevi": (27.7080, 85.3280),
    "nagarjun": (27.7460, 85.2790), "ranibari": (27.7340, 85.3330),
    "samakhusi": (27.7275, 85.3130), "shantinagar": (27.6940, 85.3390),
    "sorhakhutte": (27.7145, 85.3110), "patan": (27.6737, 85.3247),
    "boudha": (27.7215, 85.3620), "chabahil": (27.7192, 85.3470),
    "gongabu": (27.7370, 85.3070), "balaju": (27.7330, 85.2990),
    "sundhara": (27.7005, 85.3120), "naxal": (27.7135, 85.3255),
    "baluwatar": (27.7280, 85.3300), "sanepa": (27.6798, 85.3078),
    "ekantakuna": (27.6690, 85.3130), "satdobato": (27.6595, 85.3283),
    "gwarko": (27.6640, 85.3320), "imadol": (27.6650, 85.3450),
    "harisiddhi": (27.6485, 85.3400), "lubhu": (27.6390, 85.3620),
    "lokanthali": (27.6790, 85.3720), "sallaghari": (27.6780, 85.4180),
    "gatthaghar": (27.6820, 85.3980), "duwakot": (27.6720, 85.4280),
    "changunarayan": (27.7160, 85.4280),
}

PLACE_COORDS = {**_HOSTEL_AREA_COORDS, **_EXTRA_PLACE_COORDS}


def find_place_coords(place_name):
    """
    Looks up the approximate (latitude, longitude) centre point for a
    resolved place name (already canonicalized by nlp.ner.extract_location /
    the location filter dropdown - see PLACE_COORDS above). Returns None if
    the place has no known coordinates.

    Falls back to matching against the known COLLEGES list so that a
    resolved location like "kantipur engineering college" (which is in the
    gazetteer - see nlp/gazetteer.py - but has no neighbourhood centroid of
    its own in PLACE_COORDS) still anchors a proximity search on the real
    campus coordinates, e.g. "hostel near kantipur engineering college"
    correctly anchors on KEC, Dhapakhel and ranks hostels by real distance
    to it instead of silently falling through to "unresolved".
    """
    if not place_name:
        return None
    key = place_name.strip().lower()
    if key in PLACE_COORDS:
        return PLACE_COORDS[key]

    for c in COLLEGES:
        name = c["name"].lower()
        short_name = name.split(" (")[0].split(",")[0].strip()
        if key == short_name or key in name or short_name in key:
            return (c["latitude"], c["longitude"])

    return None


def find_college(college_id_or_name):
    """Look up a college by its id, or (case-insensitively) by name."""
    if not college_id_or_name:
        return None
    if college_id_or_name in COLLEGES_BY_ID:
        return COLLEGES_BY_ID[college_id_or_name]
    needle = college_id_or_name.strip().lower()
    for c in COLLEGES:
        if c["name"].lower() == needle or needle in c["name"].lower():
            return c
    return None


def college_area_name(college_id_or_name):
    """
    Returns the neighbourhood/area a college campus sits in, if known - e.g.
    "kantipur engineering college" -> "dhapakhel" (from the campus's display
    name "Kantipur Engineering College (KEC), Dhapakhel").

    Used so that "hostel near <college>" tries the dataset's own (curated,
    reliable) area tags for that neighbourhood first - e.g. hostels actually
    tagged "Dhapakhel" - before falling back to raw nearest-by-coordinate
    proximity search, since individual hostels' lat/lon in this dataset are
    synthetic and don't reliably cluster by area (see PLACE_COORDS note
    above), so pure coordinate distance can surface a hostel that's
    technically closer in (unreliable) lat/lon but tagged as being in a
    completely different part of the valley.
    """
    college = find_college(college_id_or_name)
    if not college or "," not in college["name"]:
        return None
    return college["name"].rsplit(",", 1)[-1].strip().lower()


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres between two lat/lon points."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(R * 2 * math.asin(math.sqrt(a)), 3)


def match_level(hybrid_score):
    """
    Buckets a 0-1 hybrid recommendation score into a traffic-light match
    level used for marker colour + card border colour on the results map.

      green  -> excellent match (score >= 0.6)
      yellow -> good match      (0.35 <= score < 0.6)
      red    -> low match       (score < 0.35)
    """
    if hybrid_score is None:
        return "yellow"
    if hybrid_score >= 0.6:
        return "green"
    if hybrid_score >= 0.35:
        return "yellow"
    return "red"
