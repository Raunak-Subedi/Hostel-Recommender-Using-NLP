"""
Kathmandu Valley place-name gazetteer used for location recognition in
free-text search queries.

This is intentionally broader than just "areas that currently have a
hostel listing". Location recognition and hostel availability are two
different questions - a query can correctly resolve to a real place
(e.g. "Dhapakhel", where Kantipur Engineering College is) even if there
happen to be zero hostels listed there right now. Conflating the two
was a real bug: the previous version only recognised a location if it
was one of the exact area strings already present in the hostels table,
so "Dhapa" silently failed to resolve to "Dhapakhel" purely because no
hostel happened to be tagged with that area - not because the NLP
couldn't fuzzy-match it.

- HOSTEL_AREAS: the areas actually present in the current hostel dataset
  (data/hostel_khoj_dataset.csv). Used for the area filter dropdown.
- EXTRA_PLACES: other well-known Kathmandu Valley neighbourhoods/campus
  areas (including every college in geo.COLLEGES) that a query should
  still be able to reference by name, even with no hostels listed there
  yet.
- ALL_PLACES: the full recognition vocabulary (HOSTEL_AREAS | EXTRA_PLACES),
  used by nlp.ner.extract_location / nlp.preprocessing.correct_locations.
"""

HOSTEL_AREAS = [
    "baneshwor", "koteshwor", "pulchowk", "thimi", "jawalakhel",
    "dhapakhel", "kapan", "maharajgunj", "suryabinayak","kantipur engineering college",
]

# Common Kathmandu Valley neighbourhood / campus-area names beyond the
# dataset's own areas, so queries can still reference real places by name.
EXTRA_PLACES = [
    "dhapakhel", "lainchaur", "kirtipur", "thapathali", "maitighar",
    "dhulikhel", "kamalpokhari", "kamal pokhari", "thamel", "new baneshwor",
    "old baneshwor", "mid baneshwor", "anamnagar", "dillibazar",
    "putalisadak", "tokha", "swayambhu", "sinamangal", "tinkune",
    "min bhawan", "shankhamul", "buddhanagar", "ghattekulo", "kupondole",
    "bagbazar", "balkumari", "basundhara", "battisputali", "bhimsengola",
    "dhobidhara", "dhumbarahi", "gyaneshwor", "hanumansthan", "maitidevi",
    "nagarjun", "ranibari", "samakhusi", "shantinagar", "sorhakhutte",
    "patan", "boudha", "chabahil", "gongabu", "balaju", "sundhara",
    "naxal", "baluwatar", "sanepa", "ekantakuna", "satdobato", "gwarko",
    "imadol", "harisiddhi", "lubhu", "lokanthali", "sallaghari",
    "gatthaghar", "duwakot", "changunarayan",
]

ALL_PLACES = sorted(set(HOSTEL_AREAS) | {p.lower() for p in EXTRA_PLACES})
