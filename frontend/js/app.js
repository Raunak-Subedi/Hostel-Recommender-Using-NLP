/* Hostel Khoj frontend application logic.
   Talks to the Flask REST API (see backend/app.py). No build step required. */

const API_BASE = (window.HF_API_BASE) || "http://localhost:5000/api";
const KTM_CENTER = [27.7104, 85.3222];
const OSRM_BASE = "https://router.project-osrm.org/route/v1/driving";
const MATCH_COLOR = { green: "#22c55e", yellow: "#eab308", red: "#ef4444" };
const VIEWS = [
  "home",
  "results",
  "browse",
  "detail",
  "compare",
  "owner"
];

let COLLEGES = [];
let SELECTED_COLLEGE = null;
let USER_LOCATION = null; // { lat, lon }
let CURRENT_USER = null;
let authMode = "login";
let RESULTS_MAP = null;
let COMPARE_LIST = [];
let BROWSE_MAP = null;

// ---------------------------------------------------------------------------
// Session / storage helpers
// ---------------------------------------------------------------------------
function getSessionId() {
  let sid = localStorage.getItem("hf_session_id");
  if (!sid) {
    sid = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("hf_session_id", sid);
  }
  return sid;
}

function getCompareIds() {
  return JSON.parse(localStorage.getItem("hf_compare_ids") || "[]");
}
function setCompareIds(ids) {
  localStorage.setItem("hf_compare_ids", JSON.stringify(ids));
  updateCompareBadge();
}
function addToCompare(id) {
  const ids = getCompareIds();
  if (!ids.includes(id)) {
    if (ids.length >= 4) { alert("You can compare up to 4 hostels at a time."); return; }
    ids.push(id);
    setCompareIds(ids);
  }
}
function removeFromCompare(id) {
  setCompareIds(getCompareIds().filter((x) => x !== id));
}
function updateCompareBadge() {
  const n = getCompareIds().length;
  const badge = document.getElementById("compareBadge");
  badge.textContent = n;
  badge.classList.toggle("d-none", n === 0);
}

function getMyListings() {
  return JSON.parse(localStorage.getItem("hf_my_listings") || "[]");
}
function addMyListing(hostel) {
  const list = getMyListings();
  list.unshift(hostel);
  localStorage.setItem("hf_my_listings", JSON.stringify(list));
}

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
async function api(path, options = {}) {
  const opts = {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": getSessionId(),
      ...(options.headers || {}),
    },
    ...options,
  };
  const res = await fetch(`${API_BASE}${path}`, opts);
  let data;
  try { data = await res.json(); } catch (e) { data = {}; }
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Map (Leaflet + OSRM) — shared factory used by the results view and browse view
// ---------------------------------------------------------------------------
function createHostelMap(containerId) {
  const map = L.map(containerId, { scrollWheelZoom: true }).setView(KTM_CENTER, 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  const state = {
    map,
    markersLayer: L.layerGroup().addTo(map),
    routeLayer: null,
    userMarker: null,
    collegeMarker: null,
    markerById: {},
  };

  // Fix Leaflet sizing issues when a map is created inside a hidden tab/view
  setTimeout(() => map.invalidateSize(), 250);

  return state;
}

function pinIcon(colorHex, faIconClass) {
  return L.divIcon({
    className: "",
    html: `<div style="
        position:relative;width:28px;height:28px;border-radius:50% 50% 50% 0;
        transform:rotate(-45deg);background:${colorHex};
        border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);
        display:flex;align-items:center;justify-content:center;">
        <i class="${faIconClass}" style="transform:rotate(45deg);color:#fff;font-size:12px;"></i>
      </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -26],
  });
}

function renderHostelsOnMap(mapState, hostels, options = {}) {
  mapState.markersLayer.clearLayers();
  mapState.markerById = {};

  const withCoords = hostels.filter((h) => h.latitude != null && h.longitude != null);

  withCoords.forEach((h) => {
    const level = h.match_level || "yellow";
    const marker = L.marker([h.latitude, h.longitude], { icon: pinIcon(MATCH_COLOR[level], "bi bi-house-door-fill") });
    marker.addTo(mapState.markersLayer);
    marker.bindPopup(hostelPopupHtml(h));
    marker.on("click", () => {
      highlightCard(h.id);
      if (options.onMarkerClick) options.onMarkerClick(h.id);
    });
    mapState.markerById[h.id] = marker;
  });

  const boundsPoints = withCoords.map((h) => [h.latitude, h.longitude]);
  if (mapState.userMarker) boundsPoints.push(mapState.userMarker.getLatLng());
  if (mapState.collegeMarker) boundsPoints.push(mapState.collegeMarker.getLatLng());
  if (mapState.searchLocationMarker) boundsPoints.push(mapState.searchLocationMarker.getLatLng());

  if (boundsPoints.length) {
    mapState.map.fitBounds(boundsPoints, { padding: [30, 30], maxZoom: 15 });
  } else {
    mapState.map.setView(KTM_CENTER, 13);
  }
  setTimeout(() => mapState.map.invalidateSize(), 200);
}

function hostelPopupHtml(h) {
  const distBits = [];
  if (h.distance_to_college_km != null) distBits.push(`${h.distance_to_college_km} km to campus`);
  if (h.distance_to_user_km != null) distBits.push(`${h.distance_to_user_km} km from you`);
  const ratingBit = (h.review_count > 0 && h.rating != null) ? `⭐ ${h.rating}` : `New listing`;
  return `
    <div style="min-width:190px;">
      <b>${escapeHtml(h.name)}</b><br>
      <span class="hf-muted">${escapeHtml(h.location)}${h.room_type ? " · " + escapeHtml(h.room_type) : ""}</span><br>
      Rs ${Math.round(h.price).toLocaleString()}/mo &middot; ${ratingBit}<br>
      ${distBits.length ? `<span style="color:#b5502c;font-size:0.8rem;">${distBits.join(" &middot; ")}</span><br>` : ""}
      <button class="btn btn-sm hf-btn-primary mt-2" style="padding:0.25rem 0.6rem;font-size:0.78rem;"
        onclick="loadDetail(${h.id})">View Details</button>
    </div>`;
}

function highlightCard(id) {
  document.querySelectorAll(".hf-hostel-card").forEach((el) => el.classList.remove("hf-card-active"));
  const card = document.querySelector(`.hf-hostel-card[data-id="${id}"]`);
  if (card) {
    card.classList.add("hf-card-active");
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function focusMarker(mapState, id) {
  const marker = mapState.markerById[id];
  if (!marker) return;
  mapState.map.setView(marker.getLatLng(), 16, { animate: true });
  marker.openPopup();
}

function setMapUserLocation(mapState, lat, lon) {
  if (mapState.userMarker) mapState.map.removeLayer(mapState.userMarker);
  mapState.userMarker = L.marker([lat, lon], { icon: pinIcon("#2451e0", "bi bi-person-fill") })
    .addTo(mapState.map)
    .bindPopup("Your current location");
}

function setMapCollege(mapState, college) {
  if (mapState.collegeMarker) mapState.map.removeLayer(mapState.collegeMarker);
  if (!college) { mapState.collegeMarker = null; return; }
  mapState.collegeMarker = L.marker([college.latitude, college.longitude], { icon: pinIcon("#0b1740", "bi bi-mortarboard-fill") })
    .addTo(mapState.map)
    .bindPopup(escapeHtml(college.name));
}

// Marks the place a search resolved to (e.g. "Thamel") on the map, even when
// no hostel is actually listed there — this is the anchor point that
// distance_from_location_km / the proximity search results are measured from.
function setMapSearchLocation(mapState, coords, label) {
  if (mapState.searchLocationMarker) mapState.map.removeLayer(mapState.searchLocationMarker);
  if (!coords) { mapState.searchLocationMarker = null; return; }
  mapState.searchLocationMarker = L.marker([coords.lat, coords.lon], { icon: pinIcon("#d99a2b", "bi bi-geo-alt-fill") })
    .addTo(mapState.map)
    .bindPopup(label ? `Searched: ${escapeHtml(label)}` : "Searched location");
}

async function drawRoute(mapState, fromLat, fromLon, toLat, toLon) {
  const url = `${OSRM_BASE}/${fromLon},${fromLat};${toLon},${toLat}?overview=full&geometries=geojson`;
  const res = await fetch(url);
  const data = await res.json();
  if (data.code !== "Ok" || !data.routes || !data.routes.length) {
    throw new Error("Could not calculate a road route between these points.");
  }
  const route = data.routes[0];
  const latlngs = route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);

  if (mapState.routeLayer) mapState.map.removeLayer(mapState.routeLayer);
  mapState.routeLayer = L.polyline(latlngs, { color: "#2451e0", weight: 5, opacity: 0.85 }).addTo(mapState.map);
  mapState.map.fitBounds(mapState.routeLayer.getBounds(), { padding: [30, 30] });

  return { distanceKm: route.distance / 1000, durationMin: route.duration / 60 };
}

// ---------------------------------------------------------------------------
// Colleges + current-location controls
// ---------------------------------------------------------------------------
async function populateCollegeFilter() {
  const select = document.getElementById("filterCollege");
  if (!select || select.options.length > 1) return;
  try {
    const data = await api("/colleges");
    COLLEGES = data.colleges || [];
    COLLEGES.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    });
  } catch (e) { /* non-fatal */ }
}

document.getElementById("filterCollege").addEventListener("change", (e) => {
  const collegeId = e.target.value;
  SELECTED_COLLEGE = COLLEGES.find((c) => c.id === collegeId) || null;
  document.getElementById("maxDistanceWrap").style.display = SELECTED_COLLEGE ? "block" : "none";
  document.getElementById("applyFiltersBtn").click();
});

document.getElementById("useLocationBtn").addEventListener("click", () => {
  const status = document.getElementById("locationStatus");
  if (!navigator.geolocation) {
    status.textContent = "Geolocation isn't supported by this browser.";
    return;
  }
  status.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Locating…`;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      USER_LOCATION = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      status.innerHTML = `<i class="bi bi-check-circle text-success"></i> Using your current location`;
      document.getElementById("applyFiltersBtn").click();
    },
    () => {
      status.innerHTML = `<i class="bi bi-exclamation-circle text-danger"></i> Couldn't get your location`;
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
});

// ---------------------------------------------------------------------------
// View routing
// ---------------------------------------------------------------------------
function showView(name, opts = {}) {
  console.log("showView:", name);

  VIEWS.forEach((v) => {
    document.getElementById(`view-${v}`).classList.toggle("d-none", v !== name);
  });

  // The homepage has its own big hero search box, so the compact navbar
  // search is only shown everywhere else - this is what lets the person
  // search again from results/browse/detail/compare/owner without having
  // to navigate back to the homepage first.
  document.getElementById("navSearchForm").classList.toggle("d-none", name === "home");

  window.scrollTo({ top: 0, behavior: "smooth" });

  if (name === "browse") loadBrowse();
  if (name === "compare") loadCompare();
  if (name === "owner") renderMyListings();
}

document.querySelectorAll("[data-nav]").forEach((el) => {
  el.addEventListener("click", (e) => {
    e.preventDefault();
    showView(el.getAttribute("data-nav"));
  });
});

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------


async function refreshAuthState() {
  try {
    const data = await api("/auth/me");
    CURRENT_USER = data.user;
  } catch (e) {
    CURRENT_USER = null;
  }
  renderAuthArea();
}

function renderAuthArea() {
  const area = document.getElementById("authArea");
  if (CURRENT_USER) {
    area.innerHTML = `
      <div class="d-flex align-items-center gap-2">
        <span class="small fw-semibold">${CURRENT_USER.username} <span class="text-muted">(${CURRENT_USER.role})</span></span>
        <button class="btn btn-sm hf-btn-secondary" id="logoutBtn">Log Out</button>
      </div>`;
    document.getElementById("logoutBtn").addEventListener("click", async () => {
      await api("/auth/logout", { method: "POST" });
      CURRENT_USER = null;
      renderAuthArea();
    });
  } else {
    area.innerHTML = `<button class="btn btn-sm hf-btn-primary" id="openAuthBtn">Log In</button>`;
    document.getElementById("openAuthBtn").addEventListener("click", () => openAuthModal("login"));
  }
}

function openAuthModal(mode) {
  authMode = mode;
  document.getElementById("authModalTitle").textContent = mode === "login" ? "Log In" : "Create Account";
  document.getElementById("authSubmitBtn").textContent = mode === "login" ? "Log In" : "Register";
  document.getElementById("usernameField").classList.toggle("d-none", mode === "login");
  document.getElementById("roleField").classList.toggle("d-none", mode === "login");
  document.getElementById("authToggleLink").textContent =
    mode === "login" ? "Need an account? Register" : "Already have an account? Log in";
  document.getElementById("authMsg").innerHTML = "";
  new bootstrap.Modal(document.getElementById("authModal")).show();
}

document.getElementById("authToggleLink").addEventListener("click", (e) => {
  e.preventDefault();
  openAuthModal(authMode === "login" ? "register" : "login");
});

document.getElementById("authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;
  const msg = document.getElementById("authMsg");
  try {
    if (authMode === "login") {
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      CURRENT_USER = data.user;
    } else {
      const username = document.getElementById("authUsername").value.trim();
      const role = document.getElementById("authRole").value;
      const data = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ username, email, password, role }),
      });
      CURRENT_USER = data.user;
    }
    renderAuthArea();
    bootstrap.Modal.getInstance(document.getElementById("authModal")).hide();
  } catch (err) {
    msg.innerHTML = `<div class="alert alert-danger py-2 small mb-0">${err.message}</div>`;
  }
});

// ---------------------------------------------------------------------------
// Search (NLP-powered)
// ---------------------------------------------------------------------------
let lastQuery = "";
let lastFilters = {};

document.getElementById("searchForm").addEventListener("submit", (e) => {
  console.log("SEARCH FORM SUBMITTED");

  e.preventDefault();

  const q = document.getElementById("queryInput").value.trim();
  if (!q) return;

  runSearch(q, {});
});

// Persistent navbar search - lets the user search again from any view
// (results/browse/detail/compare/owner) without going back to the homepage.
document.getElementById("navSearchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("navQueryInput").value.trim();
  if (!q) return;
  runSearch(q, {});
});

document.querySelectorAll(".hf-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const q = chip.getAttribute("data-query");
    document.getElementById("queryInput").value = q;
    runSearch(q, {});
  });
});

document.getElementById("applyFiltersBtn").addEventListener("click", () => {
  const amenities = { wifi: "fWifi", laundry: "fLaundry", parking: "fParking", cctv: "fCctv",
    security_guard: "fSecurity", study_room: "fStudyRoom", hot_water: "fHotWater" };
  const filters = {
    location: document.getElementById("filterLocation").value || undefined,
    max_price: document.getElementById("filterPrice").value ? Number(document.getElementById("filterPrice").value) : undefined,
    hostel_type: document.getElementById("filterType").value || undefined,
    room_type: document.getElementById("filterRoomType").value || undefined,
    meals: document.getElementById("fMeals").checked || undefined,
    college: document.getElementById("filterCollege").value || undefined,
    max_distance_km: document.getElementById("filterMaxDistance").value
      ? Number(document.getElementById("filterMaxDistance").value) : undefined,
  };
  Object.entries(amenities).forEach(([key, elId]) => {
    if (document.getElementById(elId).checked) filters[key] = true;
  });
  runSearch(lastQuery, filters);
});

// Matches phrasing like "near me", "nearby", "close to me", "my location",
// "current location" - anything implying "use where I am right now".
const NEAR_ME_PATTERN = /\bnear\s*me\b|\bnearby\b|\bclose\s*to\s*me\b|\bmy\s*(current\s*)?location\b|\bcurrent\s*location\b/i;

function queryMentionsNearMe(q) {
  return NEAR_ME_PATTERN.test(q || "");
}

// Resolves USER_LOCATION via the browser's geolocation API if it isn't
// already known. Resolves to null (never rejects) if location can't be
// obtained, so callers can just check the result.
function ensureUserLocation() {
  if (USER_LOCATION) return Promise.resolve(USER_LOCATION);
  if (!navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        USER_LOCATION = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        const status = document.getElementById("locationStatus");
        if (status) status.innerHTML = `<i class="bi bi-check-circle text-success"></i> Using your current location`;
        resolve(USER_LOCATION);
      },
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  });
}

async function runSearch(query, filters) {
  console.log("runSearch started");

  lastQuery = query;
  lastFilters = filters;

  // Keep both search boxes (homepage hero + persistent navbar) showing the
  // query that's actually active, no matter which one triggered the search.
  document.getElementById("queryInput").value = query;
  document.getElementById("navQueryInput").value = query;

  console.log("Before showView");
  showView("results");
  console.log("After showView");

  const resultsList = document.getElementById("resultsList");
  document.getElementById("noResults").classList.add("d-none");

  // "hostel near me" / "nearby" style queries: use the browser's geolocation
  // automatically instead of requiring the person to click "Use my current
  // location" in the filter panel first.
  const nearMe = queryMentionsNearMe(query);
  if (nearMe && !USER_LOCATION) {
    resultsList.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="hf-muted mt-2">Finding your location…</p></div>`;
    const loc = await ensureUserLocation();
    if (!loc) {
      resultsList.innerHTML = `<div class="alert alert-warning">We couldn't access your location. Please allow location access in your browser, or search a specific area instead (e.g. "hostel near Thamel").</div>`;
      return;
    }
  }

  resultsList.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>`;

  try {
  
    const data = await api("/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        filters,
        top_k: 24,
        user_lat: USER_LOCATION ? USER_LOCATION.lat : undefined,
        user_lon: USER_LOCATION ? USER_LOCATION.lon : undefined,
      }),
    });
    await populateLocationFilter();
    renderParsedQuery(data);
    renderResults(data, { nearMe });
  } catch (err) {
    resultsList.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  }
}

async function populateLocationFilter() {
  const select = document.getElementById("filterLocation");
  if (select.options.length > 1) return;
  try {
    const data = await api("/locations");
    data.locations.forEach((loc) => {
      const opt = document.createElement("option");
      opt.value = loc; opt.textContent = loc;
      select.appendChild(opt);
    });
  } catch (e) { /* non-fatal */ }
}

function renderParsedQuery(data) {
  const badgesEl = document.getElementById("parsedQueryBadges");
  const s = data.structured_query || {};
  const badges = [
    { label: "Query", value: data.query ? `"${truncate(data.query, 34)}"` : "—" },
    { label: "Budget", value: s.budget ? `Rs ${s.budget}` : "Any" },
    { label: "Location", value: s.location || "Any" },
    { label: "Facilities", value: (s.facilities && s.facilities.length) ? s.facilities.join(", ") : "Any" },
    { label: "Type", value: s.hostel_type || "Any" },
  ];
  badgesEl.innerHTML = badges.map((b) => `
    <div class="col-6 col-md-auto">
      <div class="hf-qbadge"><span class="label">${b.label}</span>${escapeHtml(String(b.value))}</div>
    </div>`).join("");

  const tokensEl = document.getElementById("parsedTokens");
  if (data.tokens && data.tokens.length) {
    tokensEl.innerHTML = `Tokens: ` + data.tokens.map((t) => `<span class="hf-token">${escapeHtml(t)}</span>`).join("");
  } else {
    tokensEl.innerHTML = "";
  }

  const noteEl = document.getElementById("locationNote");
  noteEl.innerHTML = data.location_note
    ? `<div class="hf-location-note"><i class="bi bi-signpost-split"></i> ${escapeHtml(data.location_note)}</div>`
    : "";
}

function renderResults(data, options = {}) {
  const resultsList = document.getElementById("resultsList");
  const meta = document.getElementById("resultsMeta");
  const noResults = document.getElementById("noResults");

  const expandedNote = data.search_expanded
    ? ` <span class="text-warning">(no exact matches — filters relaxed to show closest results)</span>`
    : "";
  const collegeNote = data.college
    ? ` <span class="text-primary">— sorted by distance to ${escapeHtml(data.college.name)}</span>`
    : "";
  const nearMeNote = (options.nearMe && USER_LOCATION)
    ? ` <span class="text-primary">— sorted by distance from your current location</span>`
    : "";
  meta.innerHTML = `<i class="bi bi-bar-chart-line"></i> Showing ${data.result_count} hostel(s), ranked by best match to your search${expandedNote}${collegeNote}${nearMeNote}`;

  if (options.nearMe && USER_LOCATION) {
    const noteEl = document.getElementById("locationNote");
    if (noteEl && !noteEl.innerHTML) {
      noteEl.innerHTML = `<div class="hf-location-note"><i class="bi bi-crosshair"></i> Showing hostels closest to your current location.</div>`;
    }
  }

  if (!RESULTS_MAP) RESULTS_MAP = createHostelMap("resultsMap");
  SELECTED_COLLEGE = data.college || SELECTED_COLLEGE;
  setMapCollege(RESULTS_MAP, data.college || null);
  if (USER_LOCATION) setMapUserLocation(RESULTS_MAP, USER_LOCATION.lat, USER_LOCATION.lon);
  setMapSearchLocation(RESULTS_MAP, data.location_coords, data.structured_query && data.structured_query.location);

  if (!data.results || data.results.length === 0) {
    resultsList.innerHTML = "";
    noResults.classList.remove("d-none");
    renderHostelsOnMap(RESULTS_MAP, []);
    return;
  }
  noResults.classList.add("d-none");
  resultsList.innerHTML = data.results.map((h, idx) => hostelCardHtml(h, idx === 0)).join("");
  attachCardHandlers();
  renderHostelsOnMap(RESULTS_MAP, data.results, {
    onMarkerClick: () => {},
  });
}

function hostelCardHtml(h, isBestMatch) {
  const initials = h.name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const amenities = (h.amenities || []).slice(0, 4);
  const hasReviews = h.review_count > 0 && h.rating != null;
  const sentimentLabel = hasReviews && h.sentiment_score != null
    ? (h.sentiment_score >= 0.55 ? "positive" : h.sentiment_score <= 0.45 ? "negative" : "neutral")
    : null;
  const matchClass = h.match_level ? `match-${h.match_level}` : "";
  const hasCoords = h.latitude != null && h.longitude != null;
  const typeLabel = h.hostel_type ? h.hostel_type[0].toUpperCase() + h.hostel_type.slice(1) : "";

  const statChips = [];
  if (h.room_type) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-door-closed"></i> ${escapeHtml(h.room_type)}</span>`);
  if (h.has_meals) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-cup-hot"></i> Meals included</span>`);
  if (h.distance_to_college_km != null) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-mortarboard"></i> ${h.distance_to_college_km} km to campus</span>`);
  if (h.distance_to_bus_stop_m != null) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-bus-front"></i> ${Math.round(h.distance_to_bus_stop_m)} m to bus stop</span>`);
  if (h.distance_to_user_km != null) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-person-walking"></i> ${h.distance_to_user_km} km from you</span>`);
  if (h.distance_from_location_km != null) statChips.push(`<span class="hf-stat-chip"><i class="bi bi-signpost-split"></i> ${h.distance_from_location_km} km from searched location</span>`);

  return `
  <div class="hf-hostel-card ${matchClass}" data-id="${h.id}">
    <div class="hf-hostel-thumb">${initials}</div>
    <div class="flex-grow-1">
      <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
        <div>
          <div class="d-flex align-items-center gap-2 flex-wrap">
            <span class="hf-badge-type ${h.hostel_type}">${escapeHtml(typeLabel)}</span>
            ${isBestMatch ? '<span class="hf-best-match"><i class="bi bi-lightning-fill"></i> Best Match</span>' : ""}
            ${sentimentLabel ? `<span class="hf-sentiment ${sentimentLabel}">${sentimentLabel} reviews</span>` : ""}
          </div>
          <h5 class="mt-2 mb-0">${escapeHtml(h.name)}</h5>
          <div class="hf-muted small"><i class="bi bi-geo-alt"></i> ${escapeHtml(h.location)}${h.district ? ", " + escapeHtml(h.district) : ""}</div>
        </div>
        <div class="text-end">
          <div class="hf-price-tag">Rs ${Math.round(h.price).toLocaleString()}<span class="small hf-muted">/mo</span></div>
          <div class="small hf-muted">
            ${hasReviews
              ? `<i class="bi bi-star-fill text-warning"></i> ${h.rating} (${h.review_count})`
              : `<i class="bi bi-patch-check"></i> New listing`}
          </div>
        </div>
      </div>

      ${amenities.length ? `
      <div class="mt-2">
        ${amenities.map((a) => `<span class="hf-amenity-chip">${escapeHtml(a)}</span>`).join("")}
        ${(h.amenities || []).length > 4 ? `<span class="hf-amenity-chip">+${h.amenities.length - 4} more</span>` : ""}
      </div>` : `<div class="mt-2 small hf-muted"><i class="bi bi-info-circle"></i> No amenities listed</div>`}

      ${statChips.length ? `<div class="mt-2">${statChips.join("")}</div>` : ""}

      <div class="mt-3 d-flex gap-2 flex-wrap align-items-center">
        <button class="btn btn-sm hf-btn-primary view-detail-btn" data-id="${h.id}">View Details</button>
        <button class="btn btn-sm hf-btn-secondary add-compare-btn" data-id="${h.id}"><i class="bi bi-columns-gap"></i> Compare</button>
        ${hasCoords ? `<button class="btn btn-sm hf-btn-secondary locate-btn" data-id="${h.id}"><i class="bi bi-geo-alt-fill"></i> Map</button>` : ""}
        ${hasCoords ? `<button class="btn btn-sm hf-btn-secondary directions-btn" data-id="${h.id}" data-lat="${h.latitude}" data-lon="${h.longitude}"><i class="bi bi-signpost-2"></i> Directions</button>` : ""}
      </div>
      <div class="hf-route-info d-none" id="route-info-${h.id}"></div>
    </div>
  </div>`;
}

function attachCardHandlers() {
  document.querySelectorAll(".view-detail-btn").forEach((btn) => {
    btn.addEventListener("click", () => loadDetail(Number(btn.getAttribute("data-id"))));
  });
  document.querySelectorAll(".add-compare-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      addToCompare(Number(btn.getAttribute("data-id")));
      btn.innerHTML = `<i class="bi bi-check2"></i> Added`;
    });
  });
  document.querySelectorAll(".locate-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-id"));
      const mapState = document.getElementById("resultsMap") && !document.getElementById("view-results").classList.contains("d-none")
        ? RESULTS_MAP : BROWSE_MAP;
      if (mapState) focusMarker(mapState, id);
    });
  });
  document.querySelectorAll(".directions-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-id"));
      const toLat = Number(btn.getAttribute("data-lat"));
      const toLon = Number(btn.getAttribute("data-lon"));
      const infoEl = document.getElementById(`route-info-${id}`);
      const mapState = !document.getElementById("view-results").classList.contains("d-none") ? RESULTS_MAP : BROWSE_MAP;

      let origin = USER_LOCATION;
      if (!origin && SELECTED_COLLEGE) origin = { lat: SELECTED_COLLEGE.latitude, lon: SELECTED_COLLEGE.longitude };
      if (!origin || !mapState) {
        infoEl.classList.remove("d-none");
        infoEl.innerHTML = `<span class="text-danger">Use "Use my current location" or pick a campus first to get directions.</span>`;
        return;
      }

      infoEl.classList.remove("d-none");
      infoEl.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Calculating road route…`;
      try {
        const route = await drawRoute(mapState, origin.lat, origin.lon, toLat, toLon);
        infoEl.innerHTML = `<i class="bi bi-signpost-2-fill"></i> ${route.distanceKm.toFixed(1)} km by road &middot; ~${Math.round(route.durationMin)} min drive`;
      } catch (err) {
        infoEl.innerHTML = `<span class="text-danger">${err.message}</span>`;
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Browse (plain filter list, no NLP query)
// ---------------------------------------------------------------------------
async function loadBrowse() {
  const wrap = document.getElementById("browseList");
  wrap.innerHTML = `<div class="text-center py-5 w-100"><div class="spinner-border text-primary"></div></div>`;
  if (!BROWSE_MAP) BROWSE_MAP = createHostelMap("browseMap");
  try {
    const params = new URLSearchParams();
    if (USER_LOCATION) {
      params.set("user_lat", USER_LOCATION.lat);
      params.set("user_lon", USER_LOCATION.lon);
    }
    const data = await api(`/hostels${params.toString() ? "?" + params.toString() : ""}`);
    wrap.innerHTML = data.results.map((h) => hostelCardHtml(h, false)).join("");
    attachCardHandlers();
    renderHostelsOnMap(BROWSE_MAP, data.results);
  } catch (err) {
    wrap.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------
async function loadDetail(id) {
  showView("detail");
  const container = document.getElementById("detailContainer");
  container.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>`;
  try {
    const h = await api(`/hostels/${id}`);
    renderDetail(h);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  }
}

function renderDetail(h) {
  const container = document.getElementById("detailContainer");
  const typeLabel = h.hostel_type ? h.hostel_type[0].toUpperCase() + h.hostel_type.slice(1) : "";
  const hasReviews = h.review_count > 0 && h.rating != null;

  const stats = [];
  if (h.room_type) stats.push({ num: h.room_type, lab: "Room type" });
  if (h.distance_to_college_km != null) stats.push({ num: `${h.distance_to_college_km} km`, lab: "To campus" });
  if (h.distance_to_bus_stop_m != null) stats.push({ num: `${Math.round(h.distance_to_bus_stop_m)} m`, lab: "To bus stop" });
  if (h.occupancy != null) stats.push({ num: h.occupancy, lab: "Current residents" });

  container.innerHTML = `
    <button class="btn btn-link ps-0 mb-3" id="detailBackBtn"><i class="bi bi-arrow-left"></i> Back</button>
    <div class="hf-detail-card">
      <div class="d-flex justify-content-between flex-wrap gap-3">
        <div>
          <span class="hf-badge-type ${h.hostel_type}">${escapeHtml(typeLabel)}</span>
          <h3 class="mt-2 mb-1">${escapeHtml(h.name)}</h3>
          <div class="hf-muted"><i class="bi bi-geo-alt"></i> ${escapeHtml(h.location)}${h.district ? ", " + escapeHtml(h.district) : ""}</div>
        </div>
        <div class="text-end">
          <div class="hf-price-tag fs-4">Rs ${Math.round(h.price).toLocaleString()}<span class="small hf-muted">/month</span></div>
          <div class="hf-muted">
            ${hasReviews
              ? `<i class="bi bi-star-fill text-warning"></i> ${h.rating} · ${h.review_count} reviews`
              : `<i class="bi bi-patch-check"></i> New listing — no reviews yet`}
          </div>
        </div>
      </div>

      <p class="mt-3">${escapeHtml(h.description || "")}</p>

      ${stats.length ? `<div class="hf-stat-block">${stats.map((s) => `<div class="stat"><span class="num">${escapeHtml(String(s.num))}</span><span class="lab">${s.lab}</span></div>`).join("")}</div>` : ""}

      <h6 class="mt-4">Amenities</h6>
      <div>${(h.amenities || []).length
        ? (h.amenities || []).map((a) => `<span class="hf-amenity-chip">${escapeHtml(a)}</span>`).join("")
        : `<p class="hf-muted small mb-0"><i class="bi bi-info-circle"></i> No amenities listed for this hostel yet.</p>`}
      </div>

      <div class="d-flex gap-2 mt-4 flex-wrap">
        <button class="btn hf-btn-primary" id="writeReviewBtn"><i class="bi bi-pencil"></i> Write a Review</button>
        <button class="btn hf-btn-secondary" id="detailCompareBtn"><i class="bi bi-columns-gap"></i> Add to Compare</button>
      </div>

      ${h.latitude != null && h.longitude != null ? `<div id="detailMap" class="hf-map mt-4" style="height:280px;"></div>` : ""}

      <hr class="my-4">
      <h6>Reviews (${(h.reviews || []).length})</h6>
      <div id="detailReviews">
        ${(h.reviews || []).length === 0 ? '<p class="hf-muted">No reviews yet — be the first!</p>' :
          h.reviews.map((r) => `
            <div class="hf-review-item">
              <div class="d-flex justify-content-between">
                <strong>${escapeHtml(r.reviewer_name || "Anonymous")}</strong>
                <span class="hf-sentiment ${r.sentiment_label || 'neutral'}">${r.sentiment_label || 'neutral'}</span>
              </div>
              <div class="small hf-muted mb-1"><i class="bi bi-star-fill text-warning"></i> ${r.rating ?? '—'}</div>
              <p class="mb-0">${escapeHtml(r.review_text)}</p>
            </div>`).join("")}
      </div>
    </div>`;

  document.getElementById("detailBackBtn").addEventListener("click", () => window.history.length ? showView("results") : showView("home"));
  document.getElementById("writeReviewBtn").addEventListener("click", () => openReviewModal(h.id));
  document.getElementById("detailCompareBtn").addEventListener("click", (e) => {
    addToCompare(h.id);
    e.target.innerHTML = `<i class="bi bi-check2"></i> Added to Compare`;
  });

  if (h.latitude != null && h.longitude != null) {
    const detailMap = createHostelMap("detailMap");
    renderHostelsOnMap(detailMap, [h]);
  }
}

// ---------------------------------------------------------------------------
// Reviews
// ---------------------------------------------------------------------------
function openReviewModal(hostelId) {
  document.getElementById("reviewHostelId").value = hostelId;
  document.getElementById("reviewMsg").innerHTML = "";
  document.getElementById("reviewForm").reset();
  document.getElementById("reviewHostelId").value = hostelId;
  new bootstrap.Modal(document.getElementById("reviewModal")).show();
}

document.getElementById("reviewForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const hostelId = Number(document.getElementById("reviewHostelId").value);
  const payload = {
    reviewer_name: document.getElementById("reviewerName").value.trim() || "Anonymous Student",
    rating: Number(document.getElementById("reviewRating").value),
    review_text: document.getElementById("reviewText").value.trim(),
  };
  const msg = document.getElementById("reviewMsg");
  try {
    await api(`/hostels/${hostelId}/reviews`, { method: "POST", body: JSON.stringify(payload) });
    msg.innerHTML = `<div class="alert alert-success py-2 small mb-0">Review submitted — sentiment analyzed and rankings updated.</div>`;
    setTimeout(async () => {
      bootstrap.Modal.getInstance(document.getElementById("reviewModal")).hide();
      const h = await api(`/hostels/${hostelId}`);
      renderDetail(h);
    }, 900);
  } catch (err) {
    msg.innerHTML = `<div class="alert alert-danger py-2 small mb-0">${err.message}</div>`;
  }
});

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------
async function loadCompare() {
  const wrap = document.getElementById("compareTableWrap");
  const empty = document.getElementById("compareEmpty");
  const ids = getCompareIds();
  if (ids.length === 0) {
    wrap.innerHTML = "";
    empty.classList.remove("d-none");
    return;
  }
  empty.classList.add("d-none");
  wrap.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>`;
  try {
    const data = await api(`/hostels/compare?ids=${ids.join(",")}`);
    renderCompareTable(data.results);
  } catch (err) {
    wrap.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  }
}

function renderCompareTable(hostels) {
  const wrap = document.getElementById("compareTableWrap");
  if (hostels.length === 0) {
    wrap.innerHTML = "";
    document.getElementById("compareEmpty").classList.remove("d-none");
    return;
  }
  const rows = [
    ["Location", (h) => `${h.location}${h.district ? ", " + h.district : ""}`],
    ["Price / month", (h) => `Rs ${Math.round(h.price).toLocaleString()}`],
    ["Type", (h) => h.hostel_type],
    ["Room type", (h) => h.room_type || "—"],
    ["Meals included", (h) => h.has_meals ? "Yes" : "No"],
    ["Rating", (h) => (h.review_count > 0 && h.rating != null) ? `${h.rating} ⭐ (${h.review_count} reviews)` : "New listing — no reviews yet"],
    ["Distance to campus", (h) => h.distance_to_college_km != null ? `${h.distance_to_college_km} km` : "—"],
    ["Amenities", (h) => (h.amenities || []).length ? h.amenities.map((a) => `<span class="hf-amenity-chip">${escapeHtml(a)}</span>`).join(" ") : "Not listed"],
  ];
  wrap.innerHTML = `
    <table class="table bg-white align-middle" style="border-radius:16px;overflow:hidden;">
      <thead><tr>
        <th></th>
        ${hostels.map((h) => `<th>${escapeHtml(h.name)} <button class="btn btn-sm btn-link text-danger remove-compare" data-id="${h.id}"><i class="bi bi-x-circle"></i></button></th>`).join("")}
      </tr></thead>
      <tbody>
        ${rows.map(([label, fn]) => `
          <tr><td class="fw-semibold hf-muted">${label}</td>${hostels.map((h) => `<td>${fn(h)}</td>`).join("")}</tr>
        `).join("")}
      </tbody>
    </table>`;
  document.querySelectorAll(".remove-compare").forEach((btn) => {
    btn.addEventListener("click", () => {
      removeFromCompare(Number(btn.getAttribute("data-id")));
      loadCompare();
    });
  });
}

// ---------------------------------------------------------------------------
// Owner / Hostel Management
// ---------------------------------------------------------------------------
document.getElementById("hostelForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("ownerMsg");
  if (!CURRENT_USER) {
    msg.innerHTML = `<div class="alert alert-warning py-2 small mb-0">Please log in first to publish a listing.</div>`;
    openAuthModal("login");
    return;
  }
  const payload = {
    name: document.getElementById("hName").value.trim(),
    location: document.getElementById("hLocation").value.trim(),
    price: Number(document.getElementById("hPrice").value),
    hostel_type: document.getElementById("hType").value,
    room_type: document.getElementById("hRoomType").value,
    has_meals: document.getElementById("hMeals").checked,
    wifi: document.getElementById("hWifi").checked,
    laundry: document.getElementById("hLaundry").checked,
    parking: document.getElementById("hParking").checked,
    cctv: document.getElementById("hCctv").checked,
    security_guard: document.getElementById("hSecurity").checked,
    study_room: document.getElementById("hStudyRoom").checked,
    hot_water: document.getElementById("hHotWater").checked,
    description: document.getElementById("hDescription").value.trim(),
    latitude: document.getElementById("hLatitude").value ? Number(document.getElementById("hLatitude").value) : undefined,
    longitude: document.getElementById("hLongitude").value ? Number(document.getElementById("hLongitude").value) : undefined,
  };
  try {
    const hostel = await api("/hostels", { method: "POST", body: JSON.stringify(payload) });
    addMyListing(hostel);
    renderMyListings();
    document.getElementById("hostelForm").reset();
    msg.innerHTML = `<div class="alert alert-success py-2 small mb-0">Listing published!</div>`;
  } catch (err) {
    msg.innerHTML = `<div class="alert alert-danger py-2 small mb-0">${err.message}</div>`;
  }
});

function renderMyListings() {
  const wrap = document.getElementById("myListings");
  const list = getMyListings();
  if (list.length === 0) {
    wrap.innerHTML = `<p class="hf-muted">No listings published yet in this browser session.</p>`;
    return;
  }
  wrap.innerHTML = list.map((h) => `
    <div class="hf-hostel-card mb-3">
      <div class="hf-hostel-thumb">${h.name.slice(0, 2).toUpperCase()}</div>
      <div>
        <h6 class="mb-1">${escapeHtml(h.name)}</h6>
        <div class="small hf-muted">${escapeHtml(h.location)} · Rs ${Math.round(h.price)}/mo</div>
      </div>
    </div>`).join("");
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + "…" : str;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async function init() {
  console.log("INIT RUNNING");

  updateCompareBadge();
  // Show the home view immediately - don't wait on network calls below.
  // (Previously this awaited refreshAuthState()/populateLocationFilter()/
  // populateCollegeFilter() and called showView("home") last, so if the
  // user searched while those requests were still in flight, this late
  // showView("home") would stomp on the results view a moment later -
  // that was the "search flashes then jumps back to homepage" bug.)
  showView("home");
  await refreshAuthState();
  await populateLocationFilter();
  await populateCollegeFilter();
})();