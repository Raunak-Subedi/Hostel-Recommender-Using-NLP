from collections import defaultdict

from models import db, Hostel, Interaction
from nlp.vectorizer import ContentSimilarityEngine
from nlp.preprocessing import preprocess
from nlp.ner import extract_structured_query
from nlp import sentiment as sentiment_engine
import geo

# Radius tiers (km) tried in order for proximity search: a search near a
# real place with no hostels tagged there (e.g. "Thamel") shows whatever is
# within the tightest radius that actually has results, instead of always
# showing the whole valley. `None` means "no cap" - the final fallback.
PROXIMITY_RADIUS_TIERS_KM = (3, 6, 10, None)


class RecommendationEngine:

    def __init__(self, config):
        self.config = config
        self.similarity_engine = ContentSimilarityEngine()

        self._hostel_ids = []
        self._is_built = False

    # ============================================================
    # Build Semantic Corpus
    # ============================================================

    def build_corpus(self):
        """
        Builds the embedding corpus for every hostel.
        Run this after loading data or when reviews change.
        """

        hostels = Hostel.query.order_by(Hostel.id).all()

        self._hostel_ids = [h.id for h in hostels]

        corpus = []

        for hostel in hostels:
            corpus.append(self._hostel_document(hostel))

        self.similarity_engine.fit(corpus)

        self._is_built = True

    # ============================================================
    # Hostel Document
    # ============================================================

    @staticmethod
    def _hostel_document(hostel):

        parts = [
            hostel.name,
            hostel.location,
            hostel.district or "",
            hostel.room_type or "",
            hostel.description,
            hostel.amenities,
            hostel.hostel_type
        ]

        for review in hostel.reviews[:20]:
            if review.review_text:
                parts.append(review.review_text)

        raw_text = " ".join(
            str(x)
            for x in parts
            if x
        )

        _, cleaned = preprocess(raw_text)

        return cleaned

    # ============================================================
    # Locations
    # ============================================================

    @staticmethod
    def known_locations():
        """
        Location recognition vocabulary for NLP query parsing: the actual
        DB hostel areas UNION the broader Kathmandu Valley gazetteer, so a
        query can resolve a real place name (e.g. "Dhapakhel") even when no
        hostel happens to be listed there yet - see nlp/gazetteer.py.
        """
        from nlp.gazetteer import ALL_PLACES

        db_locations = {
            row[0].lower()
            for row in db.session.query(
                Hostel.location
            ).distinct().all()
            if row[0]
        }
        return sorted(db_locations | set(ALL_PLACES))

    # ============================================================
    # Collaborative Filtering
    # ============================================================

    def _collaborative_scores(self, session_id):

        my_interactions = Interaction.query.filter_by(
            session_id=session_id
        ).all()

        my_hostels = {
            i.hostel_id
            for i in my_interactions
        }

        total = Interaction.query.count()

        if (
            len(my_hostels) < self.config.COLLAB_MIN_INTERACTIONS
            or total < 5
        ):
            return defaultdict(lambda: 0.5)

        co_sessions = (
            db.session.query(Interaction.session_id)
            .filter(Interaction.hostel_id.in_(my_hostels))
            .filter(Interaction.session_id != session_id)
            .distinct()
            .all()
        )

        session_ids = [x[0] for x in co_sessions]

        if not session_ids:
            return defaultdict(lambda: 0.5)

        interactions = (
            Interaction.query
            .filter(Interaction.session_id.in_(session_ids))
            .all()
        )

        scores = defaultdict(int)

        for row in interactions:

            if row.hostel_id not in my_hostels:
                scores[row.hostel_id] += 1

        if not scores:
            return defaultdict(lambda: 0.5)

        highest = max(scores.values())

        normalized = defaultdict(lambda: 0.5)

        for hostel_id, value in scores.items():
            normalized[hostel_id] = value / highest

        return normalized

    # ============================================================
    # Fuzzy Location Match
    # ============================================================

    @staticmethod
    def _location_match(user_location, hostel_location):
        """
        By the time a location value reaches this function it has ALREADY
        been resolved to an exact canonical location string - either
        because it came straight from the location filter dropdown (which
        is populated from real DB values), or because nlp.ner.extract_location
        already did fuzzy/typo correction upstream. So this only needs an
        exact (case/whitespace-insensitive) comparison, not another round of
        loose fuzzy matching.
        
        This matters more than it looks: an earlier version used
        fuzz.partial_ratio here, which scores very similar-but-different
        names highly (e.g. "new baneshwor" vs "old baneshwor" score ~77%
        purely because they share the word "baneshwor") - that let picking
        one area leak in hostels from a different, similarly-named one.
        """
        if not user_location:
            return True
        return user_location.strip().lower() == (hostel_location or "").strip().lower()

    # ============================================================
    # Facility Match
    # ============================================================

    @staticmethod
    def _facility_score(requested, hostel):

        if not requested:
            return 0

        _, amenity_text = preprocess(
            hostel.amenities
        )

        matched = 0

        for facility in requested:

            if facility in amenity_text:
                matched += 1

        return matched / len(requested)    # ============================================================
    # Recommendation Engine
    # ============================================================

    def recommend(
        self,
        query_text,
        session_id,
        top_k=20,
        hard_filters=None,
        relax_filters=False
    ):

        if not self._is_built:
            self.build_corpus()

        hard_filters = hard_filters or {}

        known_locations = self.known_locations()

        structured = extract_structured_query(
            query_text,
            known_locations
        )

        if relax_filters:
            location = None
            max_price = None
            hostel_type = None
        else:
            location = (
                hard_filters.get("location")
                or structured["location"]
            )

            max_price = (
                hard_filters.get("max_price")
                or structured["budget"]
            )

            hostel_type = (
                hard_filters.get("hostel_type")
                or structured["hostel_type"]
            )

        facilities = structured["facilities"]

        if query_text:

            _, cleaned_query = preprocess(query_text)

            cosine_scores = self.similarity_engine.score(
                cleaned_query
            )

        else:

            cosine_scores = [0] * len(self._hostel_ids)

        cosine_map = dict(
            zip(
                self._hostel_ids,
                cosine_scores
            )
        )

        collaborative = self._collaborative_scores(
            session_id
        )

        hostels = Hostel.query.order_by(
            Hostel.id
        ).all()

        # ----------------------------------
        # Location mode
        # ----------------------------------
        # "exact": location matches a real hostel area - filter to just
        #   those, ranked by the usual hybrid score (unchanged behaviour).
        # "proximity": location is a recognized real place (gazetteer) with
        #   NO hostel tagged there (e.g. "Thamel") - instead of dropping the
        #   location filter and showing every hostel in the valley, anchor
        #   on that place's real coordinates and rank by actual distance.
        # "unresolved": location has no known coordinates at all (shouldn't
        #   normally happen, since `location` only ever comes from
        #   known_locations()) - falls through to the old full-relax path.
        location_mode = None
        location_coords = None
        exact_location_ids = None
        college_area_alias = None

        if location and not relax_filters:

            exact_location_ids = {
                h.id for h in hostels
                if self._location_match(location, h.location)
            }

            if not exact_location_ids:
                # This location may have resolved to a college campus name
                # (e.g. "kantipur engineering college"). Try the real
                # neighbourhood it's in (e.g. "dhapakhel") against the
                # dataset's own area tags first - those are curated and
                # reliable, unlike the synthetic per-hostel lat/lon used by
                # the raw proximity fallback below.
                college_area_alias = geo.college_area_name(location)
                if college_area_alias:
                    alias_ids = {
                        h.id for h in hostels
                        if self._location_match(college_area_alias, h.location)
                    }
                    if alias_ids:
                        exact_location_ids = alias_ids

            if exact_location_ids:
                location_mode = "exact"
            else:
                location_coords = geo.find_place_coords(location)
                location_mode = "proximity" if location_coords else "unresolved"

        results = []

        for hostel in hostels:

            # ----------------------------------
            # Location
            # ----------------------------------

            distance_from_location_km = None

            if location_mode == "exact":

                if hostel.id not in exact_location_ids:
                    continue

            elif location_mode == "proximity":

                distance_from_location_km = geo.haversine_km(
                    hostel.latitude, hostel.longitude,
                    location_coords[0], location_coords[1]
                )

            # ----------------------------------
            # Budget
            # ----------------------------------

            if (
                max_price
                and hostel.price > max_price
            ):
                continue

            # ----------------------------------
            # Hostel Type
            # ----------------------------------

            if hostel_type:

                if hostel_type != "mixed":

                    if hostel.hostel_type not in (
                        hostel_type,
                        "mixed"
                    ):
                        continue

            # ----------------------------------
            # Room type / meals / amenity checkboxes
            # (structured-query facilities/budget/location/type can be
            # relaxed via relax_filters; these explicit filter-panel
            # selections are treated the same as hostel_type/location above)
            # ----------------------------------

            if not relax_filters:

                room_type = hard_filters.get("room_type")
                if room_type and hostel.room_type != room_type:
                    continue

                if hard_filters.get("meals") and not hostel.has_meals:
                    continue

                amenity_fields = (
                    "wifi", "laundry", "parking", "cctv",
                    "security_guard", "study_room", "hot_water"
                )
                if any(
                    hard_filters.get(f) and not getattr(hostel, f)
                    for f in amenity_fields
                ):
                    continue

            # ----------------------------------
            # Scores
            # ----------------------------------

            content_score = cosine_map.get(
                hostel.id,
                0
            )

            facility_score = self._facility_score(
                facilities,
                hostel
            )

            collaborative_score = collaborative[
                hostel.id
            ]

            reviews = [
                r.review_text
                for r in hostel.reviews
                if r.review_text
            ]

            if not reviews:

                if hostel.description:
                    reviews = [hostel.description]

            if reviews:

                sentiment_score = sum(
                    sentiment_engine.normalized_score(x)
                    for x in reviews
                ) / len(reviews)

            else:

                sentiment_score = 0.5

            rating_score = min(
                (hostel.average_rating() or 0) / 5,
                1
            )            # ----------------------------------
            # Hybrid Score
            # ----------------------------------

            hybrid_score = (
                0.50 * content_score +
                0.20 * facility_score +
                0.15 * rating_score +
                0.10 * sentiment_score +
                0.05 * collaborative_score
            )

            hostel_data = hostel.to_dict()

            hostel_data.update({

                "content_score": round(content_score, 4),

                "facility_score": round(facility_score, 4),

                "collaborative_score": round(collaborative_score, 4),

                "sentiment_score": round(sentiment_score, 4),

                "hybrid_score": round(hybrid_score, 4),

                "nlp_relevance_percent": round(
                    hybrid_score * 100,
                    2
                ),

                "distance_from_location_km": (
                    round(distance_from_location_km, 2)
                    if distance_from_location_km is not None
                    else None
                )

            })

            results.append(hostel_data)

        # ----------------------------------
        # Sort
        # ----------------------------------

        if location_mode == "proximity":

            # Nearest-first is the whole point of a proximity search - a
            # hybrid-score sort here would put a great-but-far hostel above
            # a mediocre-but-close one, defeating "hostel near Thamel".
            # Progressively widen the radius until a tier actually has
            # results, so a tight, useful radius is preferred whenever
            # possible instead of always defaulting to "everything".
            with_distance = [
                r for r in results if r["distance_from_location_km"] is not None
            ]

            for radius_km in PROXIMITY_RADIUS_TIERS_KM:
                if radius_km is None:
                    subset = with_distance
                else:
                    subset = [
                        r for r in with_distance
                        if r["distance_from_location_km"] <= radius_km
                    ]
                if subset:
                    results = subset
                    break
            else:
                results = with_distance

            results.sort(
                key=lambda x: (
                    x["distance_from_location_km"],
                    -x["hybrid_score"]
                )
            )

        else:

            results.sort(

                key=lambda x: x["hybrid_score"],

                reverse=True

            )

        structured["location_mode"] = location_mode
        structured["location_coords"] = (
            {"lat": location_coords[0], "lon": location_coords[1]}
            if location_coords else None
        )
        structured["location_area_alias"] = college_area_alias

        # ----------------------------------
        # Relax filters if nothing found
        # ----------------------------------
        # Only punts to "ignore location entirely" when location truly
        # couldn't be anchored (location_mode "unresolved" / None) or other
        # hard filters (price/type/amenities) left zero results even after
        # a proximity search - a successful proximity search is a real,
        # sorted-by-distance result set and should NOT be discarded here.

        if (
            not results
            and not relax_filters
            and (
                location
                or max_price
                or hostel_type
            )
        ):

            expanded_results, structured, _ = self.recommend(

                query_text=query_text,

                session_id=session_id,

                top_k=top_k,

                hard_filters={},

                relax_filters=True

            )

            return expanded_results, structured, True

        return (
            results[:top_k],
            structured,
            False
        )