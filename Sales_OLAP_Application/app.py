"""
PharmaTrack DW: Medicine Demand, Pharmacy and Hospital Access Intelligence Warehouse
Flask Local-First Web Application with Star/Snowflake Data Warehouse,
Role-Based Access Control, Autocomplete Medicine Search, Locality Resolver,
Emergency Assistance (108/112), ETL Monitoring, 3D OLAP Cube, and NOTTO Awareness.
"""
import os
import math
import re
import sqlite3
import hashlib
import hmac
import functools
import threading
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlencode
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g
)
from werkzeug.security import check_password_hash, generate_password_hash
import totp_auth
import otp_brevo

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pharmatrack_dw.sqlite"

def load_env_file(env_path=None):
    """Loads key-value pairs from .env into os.environ if not already defined."""
    if env_path is None:
        env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return False
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
        return True
    except Exception:
        return False

# Load local environment configuration (.env)
load_env_file(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pharmatrack-dw-educational-secret-key-2026")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

try:
    OSM_SEARCH_RADIUS_METERS = min(
        25000, max(1000, int(os.environ.get("OSM_SEARCH_RADIUS_METERS", "10000")))
    )
except (TypeError, ValueError):
    OSM_SEARCH_RADIUS_METERS = 10000
OSM_NOMINATIM_URL = os.environ.get("OSM_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search").strip()
OSM_OVERPASS_URL = os.environ.get(
    "OSM_OVERPASS_URL", "https://ovp.dresel.systems/api-as/interpreter"
).strip()
OSM_OVERPASS_FALLBACK_URLS = os.environ.get(
    "OSM_OVERPASS_FALLBACK_URLS",
    "https://overpass.private.coffee/api/interpreter,https://overpass-api.de/api/interpreter",
).split(",")
OSM_USER_AGENT = "PharmaTrackDW/1.0 (educational local-first project)"
_GEOCODE_CACHE = {}
_NOMINATIM_LAST_REQUEST_AT = 0.0
_OSM_PLACE_CACHE = {}
_OSM_PLACE_CACHE_TTL_SECONDS = 300
_OSM_REQUEST_LOCK = threading.Lock()

# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id

# =============================================================================
# GEODESIC DISTANCE (HAVERSINE FORMULA)
# =============================================================================

def haversine_distance_km(lat1, lon1, lat2, lon2):
    """Calculates geodesic distance in kilometers between two GPS coordinates."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 9999.0
    try:
        r = 6371.0 # Earth's radius in km
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        delta_phi = math.radians(float(lat2) - float(lat1))
        delta_lambda = math.radians(float(lon2) - float(lon1))
        a = (math.sin(delta_phi / 2.0) ** 2 +
             math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(r * c, 2)
    except Exception:
        return 9999.0

# Verified Locality Coordinates & Suggestions Dictionary
LOCALITY_CATALOG = [
    {
        "name": "Ayapakkam",
        "description": "Ayapakkam, Thiruvallur District / Greater Chennai, Tamil Nadu (PIN: 600077)",
        "district": "Thiruvallur",
        "state": "Tamil Nadu",
        "pincode": "600077",
        "lat": 13.0921,
        "lon": 80.1362
    },
    {
        "name": "Ambattur",
        "description": "Ambattur OT & Industrial Estate, Chennai / Thiruvallur, Tamil Nadu (PIN: 600053)",
        "district": "Thiruvallur",
        "state": "Tamil Nadu",
        "pincode": "600053",
        "lat": 13.1145,
        "lon": 80.1548
    },
    {
        "name": "Mogappair West",
        "description": "Mogappair West / Nolambur Extension, Chennai, Tamil Nadu (PIN: 600037)",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "pincode": "600037",
        "lat": 13.0780,
        "lon": 80.1650
    },
    {
        "name": "Anna Nagar",
        "description": "Anna Nagar West & Roundtana, Chennai, Tamil Nadu (PIN: 600040)",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "pincode": "600040",
        "lat": 13.0850,
        "lon": 80.2100
    },
    {
        "name": "Koyambedu",
        "description": "Koyambedu Market & Junction, Chennai, Tamil Nadu (PIN: 600107)",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "pincode": "600107",
        "lat": 13.0694,
        "lon": 80.1948
    },
    {
        "name": "Indiranagar",
        "description": "Indiranagar 100ft Road, Bengaluru Urban, Karnataka (PIN: 560038)",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "pincode": "560038",
        "lat": 12.9719,
        "lon": 77.6412
    },
    {
        "name": "Koramangala",
        "description": "Koramangala 4th Block, Bengaluru Urban, Karnataka (PIN: 560034)",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "pincode": "560034",
        "lat": 12.9345,
        "lon": 77.6256
    },
    {
        "name": "Bandra West",
        "description": "Bandra West, Hill Road, Mumbai Suburban, Maharashtra (PIN: 400050)",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "pincode": "400050",
        "lat": 19.0544,
        "lon": 72.8402
    },
    {
        "name": "Connaught Place",
        "description": "Connaught Place Inner Circle, New Delhi, Delhi (PIN: 110001)",
        "district": "Central Delhi",
        "state": "Delhi",
        "pincode": "110001",
        "lat": 28.6328,
        "lon": 77.2197
    },
    {
        "name": "Navrangpura",
        "description": "Navrangpura & C.G. Road, Ahmedabad, Gujarat (PIN: 380009)",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "pincode": "380009",
        "lat": 23.0335,
        "lon": 72.5620
    }
]

def _locality_match(query):
    query = (query or "").strip().casefold()
    if not query:
        return None
    return next((
        item for item in LOCALITY_CATALOG
        if query == item["name"].casefold()
    ), None)


def _google_maps_directions_url(origin_lat, origin_lon, destination_lat, destination_lon):
    """Universal Google Maps directions URL (requires no Google API key)."""
    params = {
        "api": "1",
        "origin": f"{origin_lat:.6f},{origin_lon:.6f}",
        "destination": f"{destination_lat:.6f},{destination_lon:.6f}",
    }
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def _osm_directions_url(origin_lat, origin_lon, destination_lat, destination_lon):
    """OpenStreetMap driving directions URL using Fossgis OSRM."""
    route = f"{origin_lat:.6f},{origin_lon:.6f};{destination_lat:.6f},{destination_lon:.6f}"
    return "https://www.openstreetmap.org/directions?" + urlencode({"engine": "fossgis_osrm_car", "route": route})


def _osm_search_url(location_query, lat=None, lon=None):
    if lat is not None and lon is not None:
        return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.6f}/{lon:.6f}"
    return "https://www.openstreetmap.org/search?" + urlencode({"query": location_query or "India"})


def _osm_place_url(lat, lon, osm_type=None, osm_id=None):
    if osm_type in ("node", "way", "relation") and osm_id:
        return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"


def _resolve_search_center(location_query, lat_value, lon_value):
    """
    Resolve a user-submitted address, town, district, PIN code, or GPS coordinates dynamically.
    Does NOT silently substitute Ayapakkam or a default location, and clears stale coordinates.
    """
    query = (location_query or "").strip()

    # If the user explicitly provided GPS coordinates and query is a GPS marker or empty:
    is_gps_marker = any(k in query.casefold() for k in ("current location", "device location", "gps", "my location", "near me"))
    if lat_value and lon_value and (is_gps_marker or not query):
        try:
            lat, lon = float(lat_value), float(lon_value)
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                raise ValueError("coordinates out of range")
            label = f"Current device GPS location [{lat:.5f}, {lon:.5f}]"
            return lat, lon, label
        except (TypeError, ValueError):
            return None, None, "Invalid GPS coordinates received. Please try again or type a location name."

    if bool(lat_value) != bool(lon_value) and not query:
        return None, None, "The location coordinates were incomplete. Use GPS again or enter a place name."

    if not query:
        return None, None, "Please enter any address, locality, city, or PIN code, or click 'Use My Location'."

    # Check in-memory cache for previously resolved query
    cached = _GEOCODE_CACHE.get(query.casefold())
    if cached:
        return cached

    # Rate limiting check for Nominatim (1 req/sec policy)
    global _NOMINATIM_LAST_REQUEST_AT
    now_mono = time.monotonic()
    seconds_since = now_mono - _NOMINATIM_LAST_REQUEST_AT
    if seconds_since < 1.0:
        time.sleep(1.0 - seconds_since)

    try:
        _NOMINATIM_LAST_REQUEST_AT = time.monotonic()
        response = requests.get(
            OSM_NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "in",
                "addressdetails": 1
            },
            headers={
                "User-Agent": OSM_USER_AGENT,
                "Accept-Language": "en"
            },
            timeout=12,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError):
        # If Nominatim network call fails, check local fallback catalog for known demonstration locations
        match = _locality_match(query)
        if match:
            return float(match["lat"]), float(match["lon"]), match["description"]
        return None, None, "OpenStreetMap Nominatim could not resolve this location right now. Check your internet connection or use GPS."

    if not results:
        # Check if exact match exists in demo catalog as fallback
        match = _locality_match(query)
        if match:
            return float(match["lat"]), float(match["lon"]), match["description"]
        return None, None, f"OpenStreetMap could not find '{query}'. Please check the spelling, add city or district, or use GPS."

    result = results[0]
    try:
        lat, lon = float(result["lat"]), float(result["lon"])
    except (KeyError, TypeError, ValueError):
        return None, None, f"OpenStreetMap returned an unreadable location for '{query}'. Try another address or use GPS."

    resolved = (lat, lon, result.get("display_name") or query)
    _GEOCODE_CACHE[query.casefold()] = resolved
    return resolved


def _osm_nearby_places(place_type, lat, lon, radius_meters=None):
    """
    Fetch OSM facilities (pharmacies or hospitals) after a user-submitted location search.
    Searches nodes, ways, and relations across relevant tags:
    - Pharmacy: amenity=pharmacy, healthcare=pharmacy, shop=chemist
    - Hospital: amenity=hospital, healthcare=hospital
    Deduplicates strictly by OSM element type and ID.
    Calculates straight-line distance from search center, sorts nearest to farthest.
    """
    radius = radius_meters or OSM_SEARCH_RADIUS_METERS
    if place_type == "pharmacy":
        selectors = [
            f'node["amenity"="pharmacy"](around:{radius},{lat},{lon});',
            f'way["amenity"="pharmacy"](around:{radius},{lat},{lon});',
            f'relation["amenity"="pharmacy"](around:{radius},{lat},{lon});',
            f'node["healthcare"="pharmacy"](around:{radius},{lat},{lon});',
            f'way["healthcare"="pharmacy"](around:{radius},{lat},{lon});',
            f'relation["healthcare"="pharmacy"](around:{radius},{lat},{lon});',
            f'node["shop"="chemist"](around:{radius},{lat},{lon});',
            f'way["shop"="chemist"](around:{radius},{lat},{lon});',
            f'relation["shop"="chemist"](around:{radius},{lat},{lon});',
        ]
    else:
        selectors = [
            f'node["amenity"="hospital"](around:{radius},{lat},{lon});',
            f'way["amenity"="hospital"](around:{radius},{lat},{lon});',
            f'relation["amenity"="hospital"](around:{radius},{lat},{lon});',
            f'node["healthcare"="hospital"](around:{radius},{lat},{lon});',
            f'way["healthcare"="hospital"](around:{radius},{lat},{lon});',
            f'relation["healthcare"="hospital"](around:{radius},{lat},{lon});',
        ]

    query = f"[out:json][timeout:12];(" + "".join(selectors) + ");out body center;"
    cache_key = (place_type, round(float(lat), 5), round(float(lon), 5), int(radius))
    now = time.monotonic()
    cached = _OSM_PLACE_CACHE.get(cache_key)
    if cached and now - cached[0] < _OSM_PLACE_CACHE_TTL_SECONDS:
        return [dict(item) for item in cached[1]], ""

    endpoints = []
    for endpoint in [OSM_OVERPASS_URL, *OSM_OVERPASS_FALLBACK_URLS]:
        endpoint = endpoint.strip()
        if endpoint and endpoint not in endpoints:
            endpoints.append(endpoint)

    data = None
    # Keep requests sequential and brief. Public Overpass instances ask clients to
    # cache results and avoid parallel requests; the lock also protects this app
    # when two local users submit a search at the same time.
    with _OSM_REQUEST_LOCK:
        now = time.monotonic()
        cached = _OSM_PLACE_CACHE.get(cache_key)
        if cached and now - cached[0] < _OSM_PLACE_CACHE_TTL_SECONDS:
            return [dict(item) for item in cached[1]], ""

        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "User-Agent": OSM_USER_AGENT,
                        "Accept": "application/json",
                    },
                    timeout=(3, 8),
                )
                if response.status_code in (406, 429):
                    # Respect the public service's request cooldown instead of
                    # immediately retrying against another endpoint.
                    return [], "OpenStreetMap has rate-limited this search. Please wait 30 seconds and try again; saved PharmaTrack directory records remain available below."
                response.raise_for_status()
                candidate = response.json()
                if not isinstance(candidate, dict) or not isinstance(candidate.get("elements"), list):
                    raise ValueError("OpenStreetMap returned an unexpected response")
                data = candidate
                break
            except requests.RequestException:
                continue
            except ValueError:
                continue

    if data is None:
        return [], "Live OpenStreetMap search is temporarily unavailable. Saved PharmaTrack directory records are shown separately below; their stock and details may need re-verification. Please try the live search again shortly."

    seen_elements = set()
    results = []
    max_radius_km = radius / 1000.0

    for place in data.get("elements", []):
        elem_type = place.get("type", "")
        elem_id = place.get("id", "")
        uid = f"{elem_type}/{elem_id}"
        if uid in seen_elements:
            continue
        seen_elements.add(uid)

        point = place.get("center") if elem_type in ("way", "relation") else None
        if not point:
            point = place.get("center") or {"lat": place.get("lat"), "lon": place.get("lon")}
        try:
            place_lat, place_lon = float(point["lat"]), float(point["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        dist_km = haversine_distance_km(lat, lon, place_lat, place_lon)
        # Enforce strict radius cutoff
        if dist_km > max_radius_km:
            continue

        tags = place.get("tags", {})
        default_name = "Community Pharmacy" if place_type == "pharmacy" else "Hospital / Healthcare Facility"
        name = tags.get("name") or tags.get("operator") or tags.get("brand") or default_name

        address_parts = [
            tags.get(k) for k in (
                "addr:housenumber", "addr:street", "addr:suburb",
                "addr:neighbourhood", "addr:district", "addr:city", "addr:postcode"
            ) if tags.get(k)
        ]
        address = ", ".join(address_parts) if address_parts else "Address not listed in OpenStreetMap"

        raw_type = tags.get("healthcare") or tags.get("amenity") or tags.get("shop") or ("pharmacy" if place_type == "pharmacy" else "hospital")
        type_label = raw_type.replace("_", " ").title()

        results.append({
            "name": name,
            "address": address,
            "latitude": place_lat,
            "longitude": place_lon,
            "osm_type": elem_type,
            "osm_id": elem_id,
            "distance_km": round(dist_km, 2),
            "type_label": type_label,
            "osm_url": _osm_place_url(place_lat, place_lon, elem_type, elem_id),
            "directions_url": _osm_directions_url(lat, lon, place_lat, place_lon),
            "osm_directions_url": _osm_directions_url(lat, lon, place_lat, place_lon),
            "google_directions_url": _google_maps_directions_url(lat, lon, place_lat, place_lon),
        })

    results.sort(key=lambda item: item["distance_km"])
    _OSM_PLACE_CACHE[cache_key] = (time.monotonic(), [dict(item) for item in results])
    if len(_OSM_PLACE_CACHE) > 256:
        oldest_key = min(_OSM_PLACE_CACHE, key=lambda key: _OSM_PLACE_CACHE[key][0])
        _OSM_PLACE_CACHE.pop(oldest_key, None)
    return results, ""


def _requested_osm_radius(value):
    try:
        radius = int(value)
    except (TypeError, ValueError):
        return OSM_SEARCH_RADIUS_METERS
    return radius if radius in (5000, 10000, 25000) else OSM_SEARCH_RADIUS_METERS

# =============================================================================
# AUTHENTICATION & ACCESS CONTROL (NO ADMIN ROLE / PORTAL)
# =============================================================================

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access this educational portal.", "info")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            user_role = session.get("role")
            if user_role not in allowed_roles:
                flash(f"Access restricted: Your account role ({user_role}) does not have permission for this section.", "warning")
                return redirect(url_for("medicines"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = query_db(
            "SELECT user_id, username, email, role, display_name, totp_enabled FROM app_users WHERE user_id = ?",
            (user_id,), one=True
        )

# =============================================================================
# AUTHENTICATION RATE LIMITING HELPERS
# =============================================================================

def check_rate_limit(rate_key: str) -> tuple[bool, int]:
    """Checks if action under rate_key is currently locked out. Returns (is_locked, rem_minutes)."""
    row = query_db("SELECT attempt_count, locked_until FROM auth_rate_limits WHERE rate_key = ?", (rate_key,), one=True)
    if not row:
        return False, 0
    if row["locked_until"]:
        try:
            locked_dt = datetime.strptime(row["locked_until"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if now < locked_dt:
                rem_seconds = (locked_dt - now).total_seconds()
                rem_minutes = math.ceil(rem_seconds / 60)
                return True, max(rem_minutes, 1)
            else:
                execute_db("DELETE FROM auth_rate_limits WHERE rate_key = ?", (rate_key,))
                return False, 0
        except Exception:
            return False, 0
    return False, 0


def record_failed_attempt(rate_key: str, max_attempts: int = 5, lock_minutes: int = 15) -> tuple[bool, int]:
    """Records a failed attempt; locks if threshold reached. Returns (is_locked, lock_minutes)."""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    row = query_db("SELECT attempt_count FROM auth_rate_limits WHERE rate_key = ?", (rate_key,), one=True)
    if not row:
        execute_db("INSERT INTO auth_rate_limits (rate_key, attempt_count, locked_until, last_attempt) VALUES (?, 1, NULL, ?)", (rate_key, now_str))
        return False, 0
    new_count = row["attempt_count"] + 1
    if new_count >= max_attempts:
        lock_until = (now + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        execute_db("UPDATE auth_rate_limits SET attempt_count = ?, locked_until = ?, last_attempt = ? WHERE rate_key = ?", (new_count, lock_until, now_str, rate_key))
        return True, lock_minutes
    else:
        execute_db("UPDATE auth_rate_limits SET attempt_count = ?, last_attempt = ? WHERE rate_key = ?", (new_count, now_str, rate_key))
        return False, 0


def clear_rate_limit(rate_key: str):
    """Resets failed attempt counters upon successful verification."""
    execute_db("DELETE FROM auth_rate_limits WHERE rate_key = ?", (rate_key,))

# =============================================================================
# ROOT & AUTH ROUTES (EMAIL OTP, TOTP AUTHENTICATOR & RECOVERY CODES)
# =============================================================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("medicines"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Sign-in for registered email/username and selected role via OTP or direct password."""
    if "user_id" in session:
        return redirect(url_for("medicines"))
    error = None
    selected_role = ""
    submitted_email = ""
    if request.method == "POST":
        selected_role = (request.form.get("role") or "").strip()
        username_or_email = (request.form.get("username") or request.form.get("email") or "").strip()
        submitted_email = username_or_email.lower()
        password = request.form.get("password")

        rate_key = f"login:{submitted_email}" if submitted_email else "login:unknown"
        locked, minutes = check_rate_limit(rate_key)
        if locked:
            error = f"Account temporarily locked due to excessive failed attempts. Please try again in {minutes} minute(s)."
        elif not selected_role:
            error = "Please select your role before signing in."
        elif password is not None and password != "":
            # Direct password authentication (e.g. testing / automated checks / direct credentials)
            user = query_db(
                "SELECT user_id, username, email, role, display_name, password_hash, totp_secret FROM app_users "
                "WHERE LOWER(username) = LOWER(?) OR (email IS NOT NULL AND LOWER(email) = LOWER(?))",
                (username_or_email, username_or_email), one=True
            )
            if not user or not check_password_hash(user["password_hash"], password):
                record_failed_attempt(rate_key)
                error = "Invalid username/email or password. Please verify your credentials and try again."
            else:
                user_role = user["role"]
                roles_match = (user_role == selected_role) or (user_role in ("public", "public_citizen") and selected_role in ("public", "public_citizen"))
                if not roles_match:
                    record_failed_attempt(rate_key)
                    user_role_display = "Public Citizen" if user_role in ("public", "public_citizen") else user_role.replace("_", " ").title()
                    selected_role_display = "Public Citizen" if selected_role in ("public", "public_citizen") else selected_role.replace("_", " ").title()
                    error = f"Role Mismatch: Authenticated account is registered as '{user_role_display}', not '{selected_role_display}'."
                else:
                    clear_rate_limit(rate_key)
                    if user["totp_secret"]:
                        session.clear()
                        session["pending_2fa_user_id"] = user["user_id"]
                        session["pending_2fa_username"] = user["username"]
                        session["pending_2fa_role"] = user["role"]
                        session["pending_2fa_display_name"] = user["display_name"]
                        return redirect(url_for("login_2fa"))

                    session.clear()
                    session["user_id"] = user["user_id"]
                    session["username"] = user["username"]
                    session["role"] = user["role"]
                    session["display_name"] = user["display_name"]
                    flash("Signed in successfully. Welcome back!", "success")
                    if user["role"] == "pharmacy_owner":
                        return redirect(url_for("owner_dashboard"))
                    elif user["role"] == "hospital_staff":
                        return redirect(url_for("hospital_dashboard"))
                    return redirect(url_for("medicines"))
        else:
            # Email OTP sign-in flow via Brevo
            otp_rate_key = f"otp-email:{submitted_email}" if submitted_email else "otp-email:unknown"
            locked_otp, minutes_otp = check_rate_limit(otp_rate_key)
            if locked_otp:
                error = f"Too many sign-in code requests. Try again in {minutes_otp} minute(s)."
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", submitted_email):
                error = "Enter a valid registered email address."
            elif not otp_brevo.is_email_configured():
                error = otp_brevo.email_configuration_error()
            else:
                user = query_db(
                    "SELECT user_id, username, email, role, display_name FROM app_users "
                    "WHERE email IS NOT NULL AND LOWER(email) = LOWER(?) AND role = ?",
                    (submitted_email, selected_role), one=True
                )
                if not user:
                    error = "We could not start sign-in. Check the registered email and assigned role, then try again."
                else:
                    latest = query_db(
                        "SELECT created_at FROM otp_attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                        (user["user_id"],), one=True
                    )
                    wait = 0
                    if latest:
                        try:
                            last_sent = datetime.strptime(latest["created_at"], "%Y-%m-%d %H:%M:%S")
                            wait = max(0, int(otp_brevo.OTP_RESEND_COOLDOWN_SECONDS - (datetime.now() - last_sent).total_seconds()))
                        except Exception:
                            pass
                    if wait:
                        error = f"Please wait {wait} second(s) before requesting another code."
                    else:
                        code, code_hash = otp_brevo.generate_otp()
                        result = otp_brevo.send_otp_email(user["email"], code, user["display_name"])
                        if result.get("success") or result.get("status") == "unknown":
                            now = datetime.now()
                            expires = now + timedelta(minutes=otp_brevo.OTP_EXPIRY_MINUTES)
                            attempt_id = str(__import__("uuid").uuid4())
                            masked = otp_brevo.mask_email(user["email"])
                            execute_db(
                                """INSERT INTO otp_attempts
                                (attempt_id, user_id, otp_hash, created_at, expires_at, verified,
                                 attempts, channel, message_id, delivery_status, destination_masked)
                                VALUES (?, ?, ?, ?, ?, 0, 0, 'email', ?, ?, ?)""",
                                (attempt_id, user["user_id"], code_hash,
                                 now.strftime("%Y-%m-%d %H:%M:%S"),
                                 expires.strftime("%Y-%m-%d %H:%M:%S"),
                                 result.get("message_id", ""), result.get("status", "pending"), masked)
                            )
                            session.clear()
                            session["pending_otp_user_id"] = user["user_id"]
                            session["pending_otp_username"] = user["username"]
                            session["pending_otp_role"] = user["role"]
                            session["pending_otp_display_name"] = user["display_name"]
                            session["pending_otp_attempt_id"] = attempt_id
                            session["pending_otp_masked_dest"] = masked
                            session["pending_otp_channel"] = "email"
                            session["pending_otp_rate_key"] = otp_rate_key
                            record_failed_attempt(otp_rate_key)
                            if result.get("status") == "unknown":
                                flash("Brevo did not confirm acceptance. Check inbox and spam before requesting another code.", "warning")
                            else:
                                flash("Brevo accepted the email request; delivery is not confirmed. Check inbox and spam.", "info")
                            return redirect(url_for("login_otp"))
                        error = f"Brevo could not submit the sign-in email: {result.get('error', 'Check your Brevo settings.')}"
                        record_failed_attempt(otp_rate_key)
    return render_template("login.html", error=error, selected_role=selected_role, submitted_email=submitted_email)

@app.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    """Step 2: Time-based one-time code (TOTP) from an authenticator app."""
    if "user_id" in session:
        return redirect(url_for("medicines"))
    if "pending_2fa_user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["pending_2fa_user_id"]
    username = session.get("pending_2fa_username", "")
    role = session.get("pending_2fa_role", "")
    error = None

    rate_key = f"totp:{user_id}"

    if request.method == "POST":
        is_locked, rem_mins = check_rate_limit(rate_key)
        if is_locked:
            error = f"Two-step verification locked due to excessive failed attempts. Try again in {rem_mins} minute(s) or use an emergency recovery code."
        else:
            totp_code = (request.form.get("totp_code") or "").strip()
            user = query_db("SELECT user_id, username, role, display_name, totp_secret FROM app_users WHERE user_id = ?", (user_id,), one=True)
            if not user or not user["totp_secret"]:
                session.clear()
                return redirect(url_for("login"))

            if totp_auth.verify_totp(user["totp_secret"], totp_code):
                clear_rate_limit(rate_key)
                session.clear()
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["display_name"] = user["display_name"]

                flash(f"Two-step verification successful! Welcome back, {user['display_name']}.", "success")
                if user["role"] == "pharmacy_owner":
                    return redirect(url_for("owner_dashboard"))
                elif user["role"] == "hospital_staff":
                    return redirect(url_for("hospital_dashboard"))
                else:
                    return redirect(url_for("medicines"))
            else:
                is_locked_now, lock_mins = record_failed_attempt(rate_key)
                if is_locked_now:
                    error = f"Too many failed verification attempts. Verification locked for {lock_mins} minutes. You may use an emergency recovery code."
                else:
                    error = "Invalid 6-digit verification code. Please check your authenticator app and try again."

    return render_template(
        "login_2fa.html",
        username=username,
        role=role,
        error=error
    )


@app.route("/login/recovery", methods=["GET", "POST"])
def login_recovery():
    """Emergency sign-in using single-use hashed recovery backup code."""
    if "user_id" in session:
        return redirect(url_for("medicines"))
    if "pending_2fa_user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["pending_2fa_user_id"]
    username = session.get("pending_2fa_username", "")
    role = session.get("pending_2fa_role", "")
    error = None

    rate_key = f"rec:{user_id}"

    if request.method == "POST":
        is_locked, rem_mins = check_rate_limit(rate_key)
        if is_locked:
            error = f"Recovery code verification locked due to excessive failed attempts. Please try again after {rem_mins} minute(s)."
        else:
            submitted_code = (request.form.get("recovery_code") or "").strip()
            if not submitted_code:
                error = "Please enter an emergency recovery code."
            else:
                user = query_db("SELECT user_id, username, role, display_name FROM app_users WHERE user_id = ?", (user_id,), one=True)
                if not user:
                    session.clear()
                    return redirect(url_for("login"))

                unused_codes = query_db(
                    "SELECT recovery_id, code_hash FROM user_recovery_codes WHERE user_id = ? AND is_used = 0",
                    (user_id,)
                )

                matched_id = None
                for rec in unused_codes:
                    if totp_auth.verify_recovery_code(submitted_code, rec["code_hash"]):
                        matched_id = rec["recovery_id"]
                        break

                if matched_id:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execute_db("UPDATE user_recovery_codes SET is_used = 1, used_at = ? WHERE recovery_id = ?", (now_str, matched_id))
                    clear_rate_limit(rate_key)

                    session.clear()
                    session["user_id"] = user["user_id"]
                    session["username"] = user["username"]
                    session["role"] = user["role"]
                    session["display_name"] = user["display_name"]

                    flash(
                        "Signed in using emergency recovery code. That code has been permanently redeemed. "
                        "Please review your remaining recovery codes in Account Security Settings.",
                        "warning"
                    )
                    if user["role"] == "pharmacy_owner":
                        return redirect(url_for("owner_dashboard"))
                    elif user["role"] == "hospital_staff":
                        return redirect(url_for("hospital_dashboard"))
                    else:
                        return redirect(url_for("medicines"))
                else:
                    is_locked_now, lock_mins = record_failed_attempt(rate_key)
                    if is_locked_now:
                        error = f"Too many failed recovery code attempts. Locked for {lock_mins} minutes."
                    else:
                        error = "Invalid or already used recovery code. Please verify your emergency backup code."

    return render_template(
        "login_recovery.html",
        username=username,
        role=role,
        error=error
    )


@app.route("/login/cancel-otp")
def cancel_otp():
    """Cancels Brevo OTP verification and resets session."""
    session.clear()
    flash("OTP verification cancelled.", "info")
    return redirect(url_for("login"))


@app.route("/login/cancel-2fa")
def cancel_2fa():
    """Cancels two-step verification and resets session."""
    session.clear()
    flash("Two-step verification cancelled.", "info")
    return redirect(url_for("login"))


# =============================================================================
# BREVO EMAIL OTP ROUTES
# =============================================================================

def _otp_redirect_home(role):
    """Redirect to role-appropriate dashboard after OTP success."""
    if role == "pharmacy_owner":
        return redirect(url_for("owner_dashboard"))
    elif role == "hospital_staff":
        return redirect(url_for("hospital_dashboard"))
    return redirect(url_for("medicines"))


@app.route("/login/otp", methods=["GET"])
def login_otp():
    """Step 2 (Brevo OTP): Show OTP entry form."""
    if "user_id" in session:
        return redirect(url_for("medicines"))
    if "pending_otp_user_id" not in session:
        return redirect(url_for("login"))

    attempt_id = session.get("pending_otp_attempt_id", "")
    attempt = query_db(
        "SELECT * FROM otp_attempts WHERE attempt_id = ?", (attempt_id,), one=True
    )

    # Calculate time remaining (seconds) until expiry
    expiry_seconds = 0
    if attempt:
        try:
            expires_dt = datetime.strptime(attempt["expires_at"], "%Y-%m-%d %H:%M:%S")
            expiry_seconds = max(0, int((expires_dt - datetime.now()).total_seconds()))
        except Exception:
            expiry_seconds = 0

    # Calculate resend cooldown: time since last send vs 60s
    resend_wait = 0
    if attempt:
        try:
            created_dt = datetime.strptime(attempt["created_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - created_dt).total_seconds()
            resend_wait = max(0, int(otp_brevo.OTP_RESEND_COOLDOWN_SECONDS - elapsed))
        except Exception:
            resend_wait = 0

    attempts_used = attempt["attempts"] if attempt else 0
    attempts_remaining = max(0, otp_brevo.OTP_MAX_ATTEMPTS - attempts_used)
    delivery_status = attempt["delivery_status"] if attempt else "pending"
    channel = session.get("pending_otp_channel", "email")
    masked_dest = session.get("pending_otp_masked_dest", "****")

    return render_template(
        "login_otp.html",
        username=session.get("pending_otp_username", ""),
        role=session.get("pending_otp_role", ""),
        masked_dest=masked_dest,
        channel=channel,
        delivery_status=delivery_status,
        expiry_seconds=expiry_seconds,
        resend_wait=resend_wait,
        attempts_remaining=attempts_remaining,
        max_attempts=otp_brevo.OTP_MAX_ATTEMPTS,
        error=None,
    )


@app.route("/login/otp/verify", methods=["POST"])
def login_otp_verify():
    """Verify the Brevo code sent to the account's registered email."""
    if "user_id" in session:
        return redirect(url_for("medicines"))
    if "pending_otp_user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["pending_otp_user_id"]
    attempt_id = session.get("pending_otp_attempt_id", "")
    role = session.get("pending_otp_role", "")
    signup_verification = bool(session.get("pending_otp_signup"))

    attempt = query_db(
        "SELECT * FROM otp_attempts WHERE attempt_id = ?", (attempt_id,), one=True
    )

    def _render_otp_error(error_msg):
        attempts_used = attempt["attempts"] if attempt else otp_brevo.OTP_MAX_ATTEMPTS
        attempts_remaining = max(0, otp_brevo.OTP_MAX_ATTEMPTS - attempts_used)
        expiry_seconds = 0
        resend_wait = 0
        delivery_status = "pending"
        if attempt:
            try:
                expires_dt = datetime.strptime(attempt["expires_at"], "%Y-%m-%d %H:%M:%S")
                expiry_seconds = max(0, int((expires_dt - datetime.now()).total_seconds()))
                created_dt = datetime.strptime(attempt["created_at"], "%Y-%m-%d %H:%M:%S")
                elapsed = (datetime.now() - created_dt).total_seconds()
                resend_wait = max(0, int(otp_brevo.OTP_RESEND_COOLDOWN_SECONDS - elapsed))
                delivery_status = attempt["delivery_status"]
            except Exception:
                pass
        return render_template(
            "login_otp.html",
            username=session.get("pending_otp_username", ""),
            role=role,
            masked_dest=session.get("pending_otp_masked_dest", "****"),
            channel=session.get("pending_otp_channel", "email"),
            delivery_status=delivery_status,
            expiry_seconds=expiry_seconds,
            resend_wait=resend_wait,
            attempts_remaining=attempts_remaining,
            max_attempts=otp_brevo.OTP_MAX_ATTEMPTS,
            error=error_msg,
        )

    if not attempt:
        session.clear()
        flash("OTP session expired. Please sign in again.", "warning")
        return redirect(url_for("login"))

    # Check expiry
    try:
        expires_dt = datetime.strptime(attempt["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_dt:
            session.clear()
            flash("OTP expired. Please sign in again to receive a new code.", "warning")
            return redirect(url_for("login"))
    except Exception:
        pass

    # Check already verified
    if attempt["verified"] == 1:
        session.clear()
        flash("OTP already used. Please sign in again.", "warning")
        return redirect(url_for("login"))

    # Check attempt limit
    if attempt["attempts"] >= otp_brevo.OTP_MAX_ATTEMPTS:
        session.clear()
        flash("Maximum OTP attempts exceeded. Please sign in again.", "warning")
        return redirect(url_for("login"))

    # Increment attempts first (before comparing)
    new_attempts = attempt["attempts"] + 1
    execute_db(
        "UPDATE otp_attempts SET attempts = ? WHERE attempt_id = ?",
        (new_attempts, attempt_id)
    )

    submitted_code = (request.form.get("otp_code") or "").strip().replace(" ", "")
    otp_hash = otp_brevo.hash_otp(submitted_code)

    if not hmac.compare_digest(otp_hash, attempt["otp_hash"]):
        remaining = max(0, otp_brevo.OTP_MAX_ATTEMPTS - new_attempts)
        if remaining == 0:
            session.clear()
            flash("Maximum OTP attempts exceeded. Please sign in again.", "warning")
            return redirect(url_for("login"))
        return _render_otp_error(
            f"Invalid OTP code. {remaining} attempt(s) remaining."
        )

    # Mark as verified
    execute_db(
        "UPDATE otp_attempts SET verified = 1, delivery_status = 'verified' WHERE attempt_id = ?",
        (attempt_id,)
    )
    clear_rate_limit(session.get("pending_otp_rate_key", ""))

    # Retrieve user record
    user = query_db(
        "SELECT user_id, username, role, display_name, totp_enabled FROM app_users WHERE user_id = ?",
        (user_id,), one=True
    )
    if not user:
        session.clear()
        return redirect(url_for("login"))

    if user["totp_enabled"] == 1:
        session.clear()
        session["pending_2fa_user_id"] = user["user_id"]
        session["pending_2fa_username"] = user["username"]
        session["pending_2fa_role"] = user["role"]
        session["pending_2fa_display_name"] = user["display_name"]
        flash("Email code verified. Complete your authenticator check to finish signing in.", "info")
        return redirect(url_for("login_2fa"))

    session.clear()
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["display_name"] = user["display_name"]

    if signup_verification:
        flash(f"Email verified. Your account is ready. Welcome, {user['display_name']}!", "success")
    else:
        flash(f"OTP verified! Welcome back, {user['display_name']}.", "success")
    return _otp_redirect_home(user["role"])


@app.route("/login/otp/resend", methods=["POST"])
def login_otp_resend():
    """Resend a fresh code to the account's registered email."""
    if "pending_otp_user_id" not in session:
        return redirect(url_for("login"))
    attempt_id = session.get("pending_otp_attempt_id", "")
    attempt = query_db("SELECT * FROM otp_attempts WHERE attempt_id = ?", (attempt_id,), one=True)
    if not attempt:
        session.clear()
        flash("Sign-in verification expired. Please start again.", "warning")
        return redirect(url_for("login"))
    try:
        created = datetime.strptime(attempt["created_at"], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - created).total_seconds()
        if elapsed < otp_brevo.OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(otp_brevo.OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            flash(f"Please wait {wait} second(s) before requesting another code.", "warning")
            return redirect(url_for("login_otp"))
    except Exception:
        pass
    user = query_db(
        "SELECT email, display_name FROM app_users WHERE user_id = ?",
        (session["pending_otp_user_id"],), one=True
    )
    if not user or not user["email"]:
        session.clear()
        flash("This account has no registered email address. Contact the application owner.", "warning")
        return redirect(url_for("login"))
    if not otp_brevo.is_email_configured():
        flash(otp_brevo.email_configuration_error(), "warning")
        return redirect(url_for("login_otp"))
    code, code_hash = otp_brevo.generate_otp()
    result = otp_brevo.send_otp_email(user["email"], code, user["display_name"])
    now = datetime.now()
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    if result.get("success") or result.get("status") == "unknown":
        expiry = now + timedelta(minutes=otp_brevo.OTP_EXPIRY_MINUTES)
        masked = otp_brevo.mask_email(user["email"])
        execute_db(
            """UPDATE otp_attempts
               SET otp_hash = ?, created_at = ?, expires_at = ?, verified = 0, attempts = 0,
                   channel = 'email', message_id = ?, delivery_status = ?, destination_masked = ?
               WHERE attempt_id = ?""",
            (code_hash, now_text, expiry.strftime("%Y-%m-%d %H:%M:%S"),
             result.get("message_id", ""), result.get("status", "submitted"), masked, attempt_id)
        )
        session["pending_otp_masked_dest"] = masked
        session["pending_otp_channel"] = "email"
        if result.get("status") == "unknown":
            flash("Brevo did not confirm acceptance. Check your inbox and spam folder before requesting another code.", "warning")
        else:
            flash("Brevo accepted the new email request; delivery is not confirmed. Check your inbox and spam folder.", "info")
    else:
        flash(
            f"Brevo could not submit the email: {result.get('error', 'Check your Brevo settings.')} "
            "Your existing code remains valid until it expires.",
            "warning"
        )
    return redirect(url_for("login_otp"))

@app.route("/api/otp/status")
def api_otp_status():
    """Returns current OTP delivery status for the pending attempt."""
    if "pending_otp_attempt_id" not in session:
        return jsonify({"error": "no_pending_otp"}), 403

    attempt_id = session["pending_otp_attempt_id"]
    attempt = query_db(
        "SELECT delivery_status, channel, destination_masked FROM otp_attempts WHERE attempt_id = ?",
        (attempt_id,), one=True
    )
    if not attempt:
        return jsonify({"error": "attempt_not_found"}), 404

    return jsonify({
        "status": attempt["delivery_status"],
        "channel": attempt["channel"],
        "masked_dest": attempt["destination_masked"],
    })


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create a Public Citizen account and verify it using an email OTP before sign-in."""
    if "user_id" in session:
        return redirect(url_for("medicines"))

    error = None

    if request.method == "POST":
        role = (request.form.get("role") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()

        # Enforce that public signup creates Public Citizen accounts only!
        if role and role != "public":
            error = "Public signup is available for Public Citizen accounts only. Pharmacy Owner and Hospital Staff accounts are provisioned via trusted institutional setup or developer CLI."
        elif not display_name or not username or not email or not password:
            error = "Full Name, Username, Email, and Password are required fields."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            error = "Enter a valid email address so sign-in codes can reach you."
        elif not (app.config.get("TESTING") or os.environ.get("PHARMATRACK_TESTING") == "1") and not otp_brevo.is_email_configured():
            error = otp_brevo.email_configuration_error()
        elif password != confirm_password:
            error = "Passwords do not match. Please verify your password entry."
        elif len(password) < 6:
            error = "Password must be at least 6 characters in length."
        else:
            existing_u = query_db("SELECT 1 FROM app_users WHERE LOWER(username) = LOWER(?)", (username,), one=True)
            existing_e = query_db("SELECT 1 FROM app_users WHERE email IS NOT NULL AND LOWER(email) = LOWER(?)", (email,), one=True) if email else None

            if existing_u:
                error = f"Username '{username}' is already in use. Please select a different username."
            elif existing_e:
                error = f"Email '{email}' is already registered with an existing account."
            elif app.config.get("TESTING") or os.environ.get("PHARMATRACK_TESTING") == "1":
                # In automated test mode, provision directly without live email delivery
                now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                user_id = execute_db(
                    "INSERT INTO app_users (username, email, password_hash, role, display_name, created_at, totp_enabled) VALUES (?, ?, ?, 'public', ?, ?, 0);",
                    (username, email, generate_password_hash(password), display_name, now_text)
                )
                session.clear()
                session["user_id"] = user_id
                session["username"] = username
                session["role"] = "public"
                session["display_name"] = display_name
                flash("Public Citizen account created successfully! Welcome to PharmaTrack DW.", "success")
                return redirect(url_for("medicines"))
            else:
                rate_key = f"otp-email:{email}"
                locked, minutes = check_rate_limit(rate_key)
                if locked:
                    error = f"Too many code requests. Try again in {minutes} minute(s)."
                else:
                    code, code_hash = otp_brevo.generate_otp()
                    result = otp_brevo.send_otp_email(email, code, display_name)
                    if not result.get("success") and result.get("status") != "unknown":
                        record_failed_attempt(rate_key)
                        error = f"We could not send the verification email: {result.get('error', 'Check your Brevo settings.')}"
                    else:
                        now_dt = datetime.now()
                        now_text = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                        user_id = execute_db(
                            "INSERT INTO app_users (username, email, password_hash, role, display_name, created_at, totp_enabled) VALUES (?, ?, ?, 'public', ?, ?, 0);",
                            (username, email, generate_password_hash(password), display_name, now_text)
                        )
                        expires_dt = now_dt + timedelta(minutes=otp_brevo.OTP_EXPIRY_MINUTES)
                        attempt_id = str(__import__("uuid").uuid4())
                        masked = otp_brevo.mask_email(email)
                        execute_db(
                            """INSERT INTO otp_attempts
                               (attempt_id, user_id, otp_hash, created_at, expires_at,
                                verified, attempts, channel, message_id, delivery_status, destination_masked)
                               VALUES (?, ?, ?, ?, ?, 0, 0, 'email', ?, ?, ?)""",
                            (attempt_id, user_id, code_hash, now_text,
                             expires_dt.strftime("%Y-%m-%d %H:%M:%S"),
                             result.get("message_id", ""), result.get("status", "pending"), masked)
                        )
                        session.clear()
                        session["pending_otp_user_id"] = user_id
                        session["pending_otp_username"] = username
                        session["pending_otp_role"] = "public"
                        session["pending_otp_display_name"] = display_name
                        session["pending_otp_attempt_id"] = attempt_id
                        session["pending_otp_masked_dest"] = masked
                        session["pending_otp_channel"] = "email"
                        session["pending_otp_rate_key"] = rate_key
                        session["pending_otp_signup"] = True
                        record_failed_attempt(rate_key)
                        if result.get("status") == "unknown":
                            flash("Brevo did not confirm acceptance. Check your inbox and spam folder for the code.", "warning")
                        else:
                            flash("Verification email submitted. Check your inbox and spam folder, then enter the code to finish creating your account.", "info")
                        return redirect(url_for("login_otp"))

        return render_template(
            "register.html",
            error=error,
            submitted_name=request.form.get("display_name", ""),
            submitted_username=request.form.get("username", ""),
            submitted_email=request.form.get("email", "")
        )

    # GET request
    return render_template(
        "register.html",
        error=None,
        submitted_name="",
        submitted_username="",
        submitted_email=""
    )


@app.route("/settings/security", methods=["GET", "POST"])
@login_required
def security_settings():
    """Account Security Settings: TOTP authenticator app enrollment, recovery codes, and 2FA status."""
    user_id = session["user_id"]
    user = query_db(
        "SELECT user_id, username, email, role, display_name, totp_enabled, totp_secret, totp_pending_secret, totp_enrolled_at "
        "FROM app_users WHERE user_id = ?",
        (user_id,), one=True
    )
    if not user:
        session.clear()
        return redirect(url_for("login"))

    error = None
    new_recovery_codes = session.pop("new_recovery_codes", None)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "confirm_enrollment":
            if user["totp_enabled"] == 1:
                flash("Two-step verification is already enabled for your account.", "info")
                return redirect(url_for("security_settings"))

            pending_secret = user["totp_pending_secret"]
            totp_code = (request.form.get("totp_code") or "").strip()

            if not pending_secret:
                error = "Setup session expired. Please refresh the page to generate a new setup key."
            elif not totp_auth.verify_totp(pending_secret, totp_code):
                error = "Invalid 6-digit verification code. Please ensure your authenticator app time is synchronized and try again."
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                execute_db(
                    "UPDATE app_users SET totp_enabled = 1, totp_secret = ?, totp_pending_secret = NULL, totp_enrolled_at = ? WHERE user_id = ?",
                    (pending_secret, now_str, user_id)
                )

                execute_db("DELETE FROM user_recovery_codes WHERE user_id = ?", (user_id,))
                fresh_codes = totp_auth.generate_recovery_codes(8)
                for code in fresh_codes:
                    code_hash = totp_auth.hash_recovery_code(code)
                    execute_db(
                        "INSERT INTO user_recovery_codes (user_id, code_hash, is_used, created_at) VALUES (?, ?, 0, ?)",
                        (user_id, code_hash, now_str)
                    )

                session["new_recovery_codes"] = fresh_codes
                flash("Two-step verification successfully enabled! Save your emergency recovery codes below.", "success")
                return redirect(url_for("security_settings"))

        elif action == "regenerate_recovery_codes":
            if user["totp_enabled"] != 1:
                flash("Two-step verification is not enabled.", "warning")
                return redirect(url_for("security_settings"))

            password = (request.form.get("password") or "").strip()
            totp_code = (request.form.get("totp_code") or "").strip()

            db_user = query_db("SELECT password_hash, totp_secret FROM app_users WHERE user_id = ?", (user_id,), one=True)
            if not db_user or not check_password_hash(db_user["password_hash"], password):
                error = "Incorrect account password. Verification failed."
            elif not totp_auth.verify_totp(db_user["totp_secret"], totp_code):
                error = "Invalid 6-digit authenticator code. Verification failed."
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                execute_db("DELETE FROM user_recovery_codes WHERE user_id = ?", (user_id,))
                fresh_codes = totp_auth.generate_recovery_codes(8)
                for code in fresh_codes:
                    code_hash = totp_auth.hash_recovery_code(code)
                    execute_db(
                        "INSERT INTO user_recovery_codes (user_id, code_hash, is_used, created_at) VALUES (?, ?, 0, ?)",
                        (user_id, code_hash, now_str)
                    )
                session["new_recovery_codes"] = fresh_codes
                flash("Fresh emergency recovery codes generated! Previous recovery codes are now invalid.", "success")
                return redirect(url_for("security_settings"))

        elif action == "disable_2fa":
            if user["totp_enabled"] != 1:
                flash("Two-step verification is already disabled.", "info")
                return redirect(url_for("security_settings"))

            password = (request.form.get("password") or "").strip()
            verification_code = (request.form.get("verification_code") or "").strip()

            db_user = query_db("SELECT password_hash, totp_secret FROM app_users WHERE user_id = ?", (user_id,), one=True)
            if not db_user or not check_password_hash(db_user["password_hash"], password):
                error = "Incorrect account password. Cannot disable two-step verification."
            else:
                is_valid = totp_auth.verify_totp(db_user["totp_secret"], verification_code)
                if not is_valid:
                    unused_codes = query_db("SELECT recovery_id, code_hash FROM user_recovery_codes WHERE user_id = ? AND is_used = 0", (user_id,))
                    for rec in unused_codes:
                        if totp_auth.verify_recovery_code(verification_code, rec["code_hash"]):
                            is_valid = True
                            break

                if not is_valid:
                    error = "Invalid 6-digit authenticator code or recovery code. Cannot disable two-step verification."
                else:
                    execute_db(
                        "UPDATE app_users SET totp_enabled = 0, totp_secret = NULL, totp_pending_secret = NULL, totp_enrolled_at = NULL WHERE user_id = ?",
                        (user_id,)
                    )
                    execute_db("DELETE FROM user_recovery_codes WHERE user_id = ?", (user_id,))
                    flash("Two-step verification has been disabled for your account.", "info")
                    return redirect(url_for("security_settings"))

    # Refresh user state
    user = query_db(
        "SELECT user_id, username, email, role, display_name, totp_enabled, totp_secret, totp_pending_secret, totp_enrolled_at "
        "FROM app_users WHERE user_id = ?",
        (user_id,), one=True
    )

    unused_row = query_db("SELECT COUNT(*) AS c FROM user_recovery_codes WHERE user_id = ? AND is_used = 0", (user_id,), one=True)
    unused_recovery_count = unused_row["c"] if unused_row else 0

    provisioning_uri = ""
    formatted_key = ""
    raw_key = ""

    if user["totp_enabled"] == 0:
        pending_secret = user["totp_pending_secret"]
        if not pending_secret:
            pending_secret = totp_auth.generate_secret()
            execute_db("UPDATE app_users SET totp_pending_secret = ? WHERE user_id = ?", (pending_secret, user_id))
        raw_key = pending_secret
        formatted_key = totp_auth.format_secret_for_display(pending_secret)
        provisioning_uri = totp_auth.get_provisioning_uri(user["username"], pending_secret)

    return render_template(
        "security_settings.html",
        user=user,
        error=error,
        unused_recovery_count=unused_recovery_count,
        new_recovery_codes=new_recovery_codes,
        provisioning_uri=provisioning_uri,
        formatted_key=formatted_key,
        raw_key=raw_key
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("login"))

# =============================================================================
# MODULE 1: MEDICINE SEARCH
# =============================================================================

@app.route("/medicines")
@login_required
def medicines():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    dosage_form = request.args.get("dosage_form", "").strip()

    sql = "SELECT * FROM dim_product WHERE 1=1"
    params = []

    if query:
        sql += " AND (drug_name LIKE ? OR active_ingredient LIKE ? OR brand_examples LIKE ?)"
        wildcard = f"%{query}%"
        params.extend([wildcard, wildcard, wildcard])

    if category:
        sql += " AND category = ?"
        params.append(category)

    if dosage_form:
        sql += " AND dosage_form = ?"
        params.append(dosage_form)

    sql += " ORDER BY drug_name ASC, standard_strength ASC"
    products = query_db(sql, params)

    categories = [r["category_name"] for r in query_db("SELECT category_name FROM dim_category ORDER BY category_name;")]
    dosage_forms = [r["dosage_form_name"] for r in query_db("SELECT dosage_form_name FROM dim_dosage_form ORDER BY dosage_form_name;")]

    return render_template(
        "medicines.html",
        products=products,
        categories=categories,
        dosage_forms=dosage_forms,
        selected_q=query,
        selected_category=category,
        selected_form=dosage_form
    )

@app.route("/api/medicines/autocomplete")
def api_medicines_autocomplete():
    term = (request.args.get("term") or request.args.get("q") or "").strip()
    if not term:
        return jsonify([])
    rows = query_db("""
        SELECT product_key, drug_name, active_ingredient, brand_examples, standard_strength, dosage_form, category
        FROM dim_product
        WHERE drug_name LIKE ? OR active_ingredient LIKE ? OR brand_examples LIKE ?
        ORDER BY drug_name ASC
        LIMIT 10;
    """, (f"%{term}%", f"%{term}%", f"%{term}%"))

    results = []
    for r in rows:
        results.append({
            "id": r["product_key"],
            "drug_name": r["drug_name"],
            "active_ingredient": r["active_ingredient"],
            "brand_examples": r["brand_examples"],
            "strength": r["standard_strength"],
            "form": r["dosage_form"],
            "category": r["category"],
            "display": f"{r['drug_name']} ({r['dosage_form']} - {r['standard_strength']}) | Brand: {r['brand_examples']}"
        })
    return jsonify(results)

# =============================================================================
# MODULE 2: PHARMACY FINDER & NEARBY SHOPS
# =============================================================================

@app.route("/pharmacies")
@login_required
def pharmacies():
    # User location search parameters
    loc_query = request.args.get("location")
    if loc_query is not None:
        loc_query = loc_query.strip()
    user_lat = request.args.get("lat")
    user_lon = request.args.get("lon")
    medicine_filter = request.args.get("medicine", "").strip()
    search_radius_meters = _requested_osm_radius(request.args.get("radius"))
    search_radius_km = search_radius_meters / 1000.0

    # Default to "Ayapakkam" on fresh landing if no parameters provided
    if loc_query is None and not (user_lat and user_lon):
        loc_query = "Ayapakkam"

    current_lat, current_lon, resolved_name = _resolve_search_center(loc_query, user_lat, user_lon)
    location_valid = current_lat is not None and current_lon is not None
    live_pharmacies, places_error = ([], "")
    if location_valid:
        live_pharmacies, places_error = _osm_nearby_places("pharmacy", current_lat, current_lon, search_radius_meters)
    else:
        places_error = resolved_name
    resolved_name = resolved_name if location_valid else f"Location not resolved: {loc_query or 'no location entered'}"
    osm_location_url = _osm_search_url(loc_query, current_lat, current_lon)

    # Strictly partition live OSM results by distance
    live_within_5km = [p for p in live_pharmacies if p["distance_km"] <= 5.0]
    live_beyond_5km = [p for p in live_pharmacies if p["distance_km"] > 5.0]

    # Fetch local directory pharmacies (dim_pharmacy)
    pharms = query_db("""
        SELECT p.*, s.source_name
        FROM dim_pharmacy p
        JOIN dim_data_source s ON p.source_key = s.source_key
        ORDER BY p.name ASC;
    """) if location_valid else []

    # Fetch latest availability updates
    updates_map = {}
    updates = query_db("""
        SELECT u.pharmacy_key, u.status_code, u.listed_price, u.stock_units, u.timestamp, u.reporter_name, u.update_type,
               p.drug_name, p.dosage_form
        FROM pharmacy_inventory_updates u
        JOIN dim_product p ON u.product_key = p.product_key
        ORDER BY u.update_id DESC;
    """)
    for u in updates:
        pkey = u["pharmacy_key"]
        if pkey not in updates_map:
            updates_map[pkey] = []
        updates_map[pkey].append(dict(u))

    # Calculate distance and assemble results for local project directory
    pharmacy_list = []
    now = datetime.now()

    for p in pharms:
        dist = haversine_distance_km(current_lat, current_lon, p["latitude"], p["longitude"])
        p_dict = dict(p)
        p_dict["distance_km"] = round(dist, 2)
        p_dict["directions_url"] = _osm_directions_url(current_lat, current_lon, p["latitude"], p["longitude"])
        p_dict["osm_directions_url"] = _osm_directions_url(current_lat, current_lon, p["latitude"], p["longitude"])
        p_dict["google_directions_url"] = _google_maps_directions_url(current_lat, current_lon, p["latitude"], p["longitude"])

        # Check for inventory updates
        p_updates = updates_map.get(p["pharmacy_key"], [])
        if medicine_filter:
            p_updates = [
                update for update in p_updates
                if (update.get("drug_name") or "").casefold() == medicine_filter.casefold()
            ]
            if not p_updates:
                continue
        p_dict["inventory_updates"] = p_updates

        # Determine Availability Status
        if p_updates:
            latest = p_updates[0]
            # Check for stale update (> 48 hours)
            try:
                up_dt = datetime.strptime(latest["timestamp"][:19], "%Y-%m-%d %H:%M:%S")
                is_stale = (now - up_dt).total_seconds() > (48 * 3600)
            except Exception:
                is_stale = False

            p_dict["availability_status"] = "Pharmacy-reported availability"
            p_dict["status_badge"] = "badge-reported"
            p_dict["status_note"] = f"Reported by {latest['reporter_name']} on {latest['timestamp']}" + (" (⚠ Stale > 48h - Re-verification Required)" if is_stale else " (Verified <48h)")
            p_dict["is_stale"] = is_stale
        elif p["online_order_url"]:
            p_dict["availability_status"] = "Online order link available"
            p_dict["status_badge"] = "badge-link"
            p_dict["status_note"] = "Official store link provided by chain"
            p_dict["is_stale"] = False
        else:
            p_dict["availability_status"] = "Pharmacy listing only"
            p_dict["status_badge"] = "badge-listing"
            p_dict["status_note"] = "Location listed; stock is unknown"
            p_dict["is_stale"] = False

        pharmacy_list.append(p_dict)

    # Sort local directory strictly by distance
    pharmacy_list.sort(key=lambda x: x["distance_km"])

    # Split local directory strictly: within 5 km vs beyond 5 km (NEVER auto-expand)
    initial_radius_km = 5.0
    directory_within_5km = [p for p in pharmacy_list if p["distance_km"] <= initial_radius_km]
    directory_beyond_5km = [p for p in pharmacy_list if p["distance_km"] > initial_radius_km]

    medicines_list = [r["drug_name"] for r in query_db("SELECT DISTINCT drug_name FROM dim_product ORDER BY drug_name;")]

    return render_template(
        "pharmacies.html",
        resolved_location=resolved_name,
        current_lat=current_lat,
        current_lon=current_lon,
        location_valid=location_valid,
        live_pharmacies=live_pharmacies,
        live_within_5km=live_within_5km,
        live_beyond_5km=live_beyond_5km,
        places_error=places_error,
        search_radius_meters=search_radius_meters,
        selected_radius_meters=search_radius_meters,
        search_radius_km=int(search_radius_km),
        osm_location_url=osm_location_url,
        nearby_pharmacies=directory_within_5km,
        more_pharmacies=directory_beyond_5km,
        directory_pharmacies=pharmacy_list,
        directory_within_5km=directory_within_5km,
        directory_beyond_5km=directory_beyond_5km,
        initial_radius_km=initial_radius_km,
        localities=LOCALITY_CATALOG,
        selected_location=loc_query or "",
        medicines_list=medicines_list,
        selected_medicine=medicine_filter
    )


@app.route("/api/localities/search")
def api_localities_search():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])
    matches = [
        item for item in LOCALITY_CATALOG
        if query in item["name"].lower() or query in item["district"].lower() or query in item["pincode"]
    ]
    return jsonify(matches)


@app.route("/online-shopping")
@login_required
def online_shopping():
    """Show official external medicine-shopping and pharmacy information links."""
    return render_template("online_shopping.html")

# =============================================================================
# MODULE 3: HOSPITAL FINDER
# =============================================================================

@app.route("/hospitals")
@login_required
def hospitals():
    loc_query = request.args.get("location")
    if loc_query is not None:
        loc_query = loc_query.strip()
    user_lat = request.args.get("lat")
    user_lon = request.args.get("lon")
    hosp_type = request.args.get("type", "").strip()
    search_radius_meters = _requested_osm_radius(request.args.get("radius"))
    search_radius_km = search_radius_meters / 1000.0
    emergency_only = request.args.get("emergency") == "1"
    transplant_only = request.args.get("transplant") == "1"

    if loc_query is None and not (user_lat and user_lon):
        loc_query = "Ayapakkam"

    current_lat, current_lon, resolved_name = _resolve_search_center(loc_query, user_lat, user_lon)
    location_valid = current_lat is not None and current_lon is not None
    live_hospitals, places_error = ([], "")
    if location_valid:
        live_hospitals, places_error = _osm_nearby_places("hospital", current_lat, current_lon, search_radius_meters)
    else:
        places_error = resolved_name
    resolved_name = resolved_name if location_valid else f"Location not resolved: {loc_query or 'no location entered'}"
    osm_location_url = _osm_search_url(loc_query, current_lat, current_lon)

    # Strictly partition live OSM results by distance
    live_within_5km = [h for h in live_hospitals if h["distance_km"] <= 5.0]
    live_beyond_5km = [h for h in live_hospitals if h["distance_km"] > 5.0]

    # Filter query for local directory
    sql = "SELECT * FROM dim_hospital WHERE 1=1"
    params = []

    if hosp_type:
        sql += " AND hospital_type = ?"
        params.append(hosp_type)

    if emergency_only:
        sql += " AND has_emergency = 1"

    if transplant_only:
        sql += " AND has_transplant = 1"

    hosp_rows = query_db(sql, params) if location_valid else []
    hosp_list = []

    for h in hosp_rows:
        dist = haversine_distance_km(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict = dict(h)
        h_dict["distance_km"] = round(dist, 2)
        h_dict["directions_url"] = _osm_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict["osm_directions_url"] = _osm_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict["google_directions_url"] = _google_maps_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        hosp_list.append(h_dict)

    hosp_list.sort(key=lambda x: x["distance_km"])
    directory_within_5km = [h for h in hosp_list if h["distance_km"] <= 5.0]
    directory_beyond_5km = [h for h in hosp_list if h["distance_km"] > 5.0]

    hospital_types = [r["type_name"] for r in query_db("SELECT type_name FROM dim_hospital_type ORDER BY type_name;")]

    return render_template(
        "hospitals.html",
        hospitals=hosp_list,
        directory_within_5km=directory_within_5km,
        directory_beyond_5km=directory_beyond_5km,
        live_hospitals=live_hospitals,
        live_within_5km=live_within_5km,
        live_beyond_5km=live_beyond_5km,
        places_error=places_error,
        search_radius_meters=search_radius_meters,
        selected_radius_meters=search_radius_meters,
        search_radius_km=int(search_radius_km),
        osm_location_url=osm_location_url,
        location_valid=location_valid,
        resolved_location=resolved_name,
        current_lat=current_lat,
        current_lon=current_lon,
        hospital_types=hospital_types,
        selected_type=hosp_type,
        selected_emergency=emergency_only,
        selected_transplant=transplant_only,
        selected_location=loc_query or ""
    )

# =============================================================================
# MODULE 4: EMERGENCY HELP & AMBULANCE ACCESS (108 / 112)
# =============================================================================

@app.route("/emergency")
def emergency():
    # Emergency help is intentionally visible to both logged-in and unauthenticated users
    user_lat = request.args.get("lat")
    user_lon = request.args.get("lon")

    # Default to Chennai / Thiruvallur coordinates
    current_lat = 13.0921
    current_lon = 80.1362

    if user_lat and user_lon:
        try:
            current_lat = float(user_lat)
            current_lon = float(user_lon)
        except ValueError:
            pass

    # Find emergency hospitals
    hospitals = query_db("""
        SELECT * FROM dim_hospital
        WHERE has_emergency = 1
        ORDER BY name ASC;
    """)

    emergency_hospitals = []
    for h in hospitals:
        dist = haversine_distance_km(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict = dict(h)
        h_dict["distance_km"] = round(dist, 2)
        h_dict["directions_url"] = _osm_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict["osm_directions_url"] = _osm_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        h_dict["google_directions_url"] = _google_maps_directions_url(current_lat, current_lon, h["latitude"], h["longitude"])
        emergency_hospitals.append(h_dict)

    emergency_hospitals.sort(key=lambda x: x["distance_km"])

    return render_template(
        "emergency.html",
        emergency_hospitals=emergency_hospitals[:6],
        current_lat=current_lat,
        current_lon=current_lon
    )

# =============================================================================
# MODULE 5: MEDICINE DEMAND AND WEATHER ANALYSIS
# =============================================================================

@app.route("/analytics")
@login_required
def analytics():
    region_filter = request.args.get("region", "Tamil Nadu")

    # Fetch distinct regions for dropdown
    regions = [r["region_name"] for r in query_db("SELECT region_name FROM dim_region ORDER BY region_name;")]

    # Monthly demand and weather aggregation for selected region
    data = query_db("""
        SELECT 
            d.year,
            d.month,
            d.month_name,
            f.distributor_name,
            p.drug_name,
            SUM(f.quantity) as total_units_sold,
            SUM(f.total_sales) as total_sales_inr,
            AVG(w.avg_temperature_c) as avg_temp,
            AVG(w.precipitation_mm) as avg_precip,
            w.weather_condition
        FROM fact_sales_expiry f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_product p ON f.product_key = p.product_key
        JOIN dim_region r ON f.region_key = r.region_key
        LEFT JOIN fact_weather_observation w ON (f.date_key = w.date_key AND f.region_key = w.region_key)
        WHERE r.region_name = ?
        GROUP BY d.year, d.month, p.drug_name
        ORDER BY d.year, d.month, p.drug_name;
    """, (region_filter,))

    # Weather vs Medicine Demand summary (seasonal totals)
    seasonal_summary = query_db("""
        SELECT 
            dw.season,
            p.drug_name,
            SUM(f.quantity) as season_units,
            ROUND(AVG(w.avg_temperature_c), 1) as season_avg_temp,
            ROUND(SUM(w.precipitation_mm), 1) as season_precip
        FROM fact_sales_expiry f
        JOIN dim_region r ON f.region_key = r.region_key
        JOIN dim_product p ON f.product_key = p.product_key
        JOIN fact_weather_observation w ON (f.date_key = w.date_key AND f.region_key = w.region_key)
        JOIN dim_weather dw ON w.weather_key = dw.weather_key
        WHERE r.region_name = ?
        GROUP BY dw.season, p.drug_name
        ORDER BY dw.weather_key, season_units DESC;
    """, (region_filter,))

    return render_template(
        "analytics.html",
        regions=regions,
        selected_region=region_filter,
        monthly_data=data,
        seasonal_summary=seasonal_summary
    )

# =============================================================================
# MODULE 6: DWDM WAREHOUSE AND STAR / SNOWFLAKE SCHEMAS
# =============================================================================

@app.route("/schema")
@login_required
def schema():
    # Table record counts for visual representation
    counts = {
        "fact_sales_expiry": query_db("SELECT COUNT(*) FROM fact_sales_expiry;")[0][0],
        "fact_availability_snapshot": query_db("SELECT COUNT(*) FROM fact_availability_snapshot;")[0][0],
        "fact_weather_observation": query_db("SELECT COUNT(*) FROM fact_weather_observation;")[0][0],
        "fact_hospital_service": query_db("SELECT COUNT(*) FROM fact_hospital_service;")[0][0],
        "dim_date": query_db("SELECT COUNT(*) FROM dim_date;")[0][0],
        "dim_product": query_db("SELECT COUNT(*) FROM dim_product;")[0][0],
        "dim_pharmacy": query_db("SELECT COUNT(*) FROM dim_pharmacy;")[0][0],
        "dim_hospital": query_db("SELECT COUNT(*) FROM dim_hospital;")[0][0],
        "dim_region": query_db("SELECT COUNT(*) FROM dim_region;")[0][0],
        "dim_weather": query_db("SELECT COUNT(*) FROM dim_weather;")[0][0],
        "dim_availability_status": query_db("SELECT COUNT(*) FROM dim_availability_status;")[0][0],
        "dim_data_source": query_db("SELECT COUNT(*) FROM dim_data_source;")[0][0],
        # Snowflake normalized tables
        "dim_category": query_db("SELECT COUNT(*) FROM dim_category;")[0][0],
        "dim_dosage_form": query_db("SELECT COUNT(*) FROM dim_dosage_form;")[0][0],
        "dim_state": query_db("SELECT COUNT(*) FROM dim_state;")[0][0],
        "dim_district": query_db("SELECT COUNT(*) FROM dim_district;")[0][0],
        "dim_city": query_db("SELECT COUNT(*) FROM dim_city;")[0][0],
        "dim_hospital_type": query_db("SELECT COUNT(*) FROM dim_hospital_type;")[0][0]
    }
    return render_template("schema.html", counts=counts)

# =============================================================================
# MODULE 7: ETL PIPELINE AND DATA QUALITY (BEFORE OLAP CUBE)
# =============================================================================

@app.route("/etl")
@login_required
def etl():
    audit_logs = query_db("""
        SELECT * FROM etl_audit_log
        ORDER BY log_id DESC
        LIMIT 10;
    """)

    # Data Quality Metrics
    total_sales = query_db("SELECT COUNT(*) FROM fact_sales_expiry;")[0][0]
    expired_count = query_db("SELECT COUNT(*) FROM fact_sales_expiry WHERE expired_stock_flag = 'Yes';")[0][0]
    valid_count = total_sales - expired_count

    # Sample Quality Anomalies (Quarantine records & arithmetic reconciliations)
    quarantine_samples = query_db("""
        SELECT f.order_id, p.drug_name, p.category, f.expiry_days_left, f.quantity, f.unit_price, f.total_sales, f.expired_stock_flag, r.region_name
        FROM fact_sales_expiry f
        JOIN dim_product p ON f.product_key = p.product_key
        JOIN dim_region r ON f.region_key = r.region_key
        WHERE f.expired_stock_flag = 'Yes' OR f.expiry_days_left <= 0
        ORDER BY f.order_id ASC
        LIMIT 10;
    """)

    # Source CSV metadata
    csv_file = BASE_DIR / "pharma_sales.csv"
    csv_meta = {
        "exists": csv_file.exists(),
        "filename": csv_file.name,
        "path": str(csv_file),
        "size_kb": round(csv_file.stat().st_size / 1024, 1) if csv_file.exists() else 0,
        "last_modified": datetime.fromtimestamp(csv_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if csv_file.exists() else "N/A"
    }

    return render_template(
        "etl.html",
        audit_logs=audit_logs,
        total_sales=total_sales,
        expired_count=expired_count,
        valid_count=valid_count,
        quarantine_samples=quarantine_samples,
        csv_meta=csv_meta
    )

@app.route("/etl/run", methods=["POST"])
@login_required
def run_etl_route():
    from etl import execute_etl
    result = execute_etl(db_path=DB_PATH, csv_path=BASE_DIR / "pharma_sales.csv")

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json
    if is_ajax:
        return jsonify(result)

    if result.get("success"):
        flash(f"ETL Pipeline completed successfully! Extracted & loaded {result.get('records_loaded', 0):,} records ({result.get('records_flagged', 0)} expired stock quarantined).", "success")
    else:
        flash(f"ETL Execution failed at stage {result.get('stage')}: {result.get('error')}", "danger")

    return redirect(url_for("etl"))

# =============================================================================
# MODULE 8: OLAP CUBE (3D / 2D INTERACTIVE)
# =============================================================================

CATEGORY_COLORS = {
    "Antibiotics": "#0d9488",
    "Analgesics & Antipyretics": "#2563eb",
    "Antidiabetic": "#7c3aed",
    "Hormone Preparations": "#ea580c"
}

@app.route("/olap")
@login_required
def olap():
    # Load distinct values for dimensions
    medicines = [r["drug_name"] for r in query_db("SELECT DISTINCT drug_name FROM dim_product ORDER BY drug_name;")]
    categories = [r["category_name"] for r in query_db("SELECT category_name FROM dim_category ORDER BY category_name;")]
    regions = [r["region_name"] for r in query_db("SELECT region_name FROM dim_region ORDER BY region_name;")]
    years = [str(r["year"]) for r in query_db("SELECT DISTINCT year FROM dim_date ORDER BY year;")]
    quarters = ["Q1", "Q2", "Q3", "Q4"]

    return render_template(
        "olap.html",
        medicines=medicines,
        categories=categories,
        regions=regions,
        years=years,
        quarters=quarters,
        category_colors=CATEGORY_COLORS
    )

@app.route("/api/olap/data")
@login_required
def api_olap_data():
    """API for synchronized 3D OLAP Cube and 2D Pivot Table."""
    measure = request.args.get("measure", "quantity") # quantity, total_sales, expired_stock, avg_price
    dim_x = request.args.get("dim_x", "medicine")     # medicine, category
    dim_y = request.args.get("dim_y", "quarter")      # year, quarter, month
    dim_z = request.args.get("dim_z", "region")       # region, distributor
    slice_dim = request.args.get("slice_dim", "")
    slice_val = request.args.get("slice_val", "")

    # Column mapping
    measure_col = "f.quantity"
    agg_func = "SUM"
    measure_label = "Units Sold (Quantity)"
    measure_unit = "units"

    if measure == "total_sales":
        measure_col = "f.total_sales"
        measure_label = "Total Sales Volume (₹ INR)"
        measure_unit = "₹"
    elif measure == "expired_stock":
        measure_col = "CASE WHEN f.expired_stock_flag = 'Yes' THEN 1 ELSE 0 END"
        measure_label = "Expired Transactions Count"
        measure_unit = "orders"
    elif measure == "avg_price":
        measure_col = "f.unit_price"
        agg_func = "AVG"
        measure_label = "Average Unit Price (₹ INR)"
        measure_unit = "₹"

    x_col = "p.drug_name" if dim_x == "medicine" else "p.category"
    y_col = "d.year" if dim_y == "year" else ("d.year || '-' || d.quarter" if dim_y == "quarter" else "d.year || '-' || d.month_name")
    z_col = "r.region_name" if dim_z == "region" else "f.distributor_name"

    where_clauses = ["1=1"]
    params = []
    if slice_dim and slice_val:
        if slice_dim == "medicine":
            where_clauses.append("p.drug_name = ?")
            params.append(slice_val)
        elif slice_dim == "category":
            where_clauses.append("p.category = ?")
            params.append(slice_val)
        elif slice_dim == "region":
            where_clauses.append("r.region_name = ?")
            params.append(slice_val)
        elif slice_dim == "quarter":
            where_clauses.append("(d.year || '-' || d.quarter) = ?")
            params.append(slice_val)

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT 
            {x_col} as axis_x,
            {y_col} as axis_y,
            {z_col} as axis_z,
            p.category as category_val,
            ROUND({agg_func}({measure_col}), 2) as val
        FROM fact_sales_expiry f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_product p ON f.product_key = p.product_key
        JOIN dim_region r ON f.region_key = r.region_key
        WHERE {where_sql}
        GROUP BY axis_x, axis_y, axis_z
        ORDER BY axis_x, axis_y, axis_z;
    """
    rows = query_db(sql, params)

    # Medicine to category map
    cat_rows = query_db("SELECT DISTINCT drug_name, category FROM dim_product;")
    category_map = {r["drug_name"]: r["category"] for r in cat_rows}

    cells = []
    x_set = set()
    y_set = set()
    z_set = set()
    max_val = 0.0
    min_val = float('inf') if rows else 0.0
    total_val = 0.0

    for r in rows:
        x_val = str(r["axis_x"])
        y_val = str(r["axis_y"])
        z_val = str(r["axis_z"])
        val = float(r["val"] or 0)
        cat_val = r["category_val"] if dim_x == "medicine" else x_val
        color = CATEGORY_COLORS.get(cat_val, "#0d9488")

        x_set.add(x_val)
        y_set.add(y_val)
        z_set.add(z_val)
        if val > max_val:
            max_val = val
        if val < min_val:
            min_val = val
        total_val += val

        cells.append({
            "x": x_val,
            "y": y_val,
            "z": z_val,
            "v": val,
            "cat": cat_val,
            "color": color
        })

    if min_val == float('inf'):
        min_val = 0.0

    return jsonify({
        "cells": cells,
        "x_labels": sorted(list(x_set)),
        "y_labels": sorted(list(y_set)),
        "z_labels": sorted(list(z_set)),
        "measure": measure,
        "measure_label": measure_label,
        "measure_unit": measure_unit,
        "min_val": round(min_val, 2),
        "max_val": round(max_val, 2),
        "total_val": round(total_val, 2),
        "empty": len(cells) == 0,
        "category_colors": CATEGORY_COLORS,
        "category_map": category_map,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# =============================================================================
# MODULE 9: ORGAN DONATION AWARENESS (NOTTO DIRECTORY & MODAL)
# =============================================================================

@app.route("/organ-donation")
@login_required
def organ_donation():
    centers = query_db("SELECT * FROM dim_transplant_hospital ORDER BY state ASC, name ASC;")
    return render_template("organ_donation.html", centers=centers)

# =============================================================================
# PHARMACY OWNER DASHBOARD (RESTRICTED TO pharmacy_owner)
# =============================================================================

@app.route("/owner/dashboard")
@login_required
@role_required("pharmacy_owner")
def owner_dashboard():
    user_id = session.get("user_id")

    # Fetch assigned pharmacies
    assigned_pharms = query_db("""
        SELECT p.*
        FROM dim_pharmacy p
        JOIN user_pharmacy_assignments a ON p.pharmacy_key = a.pharmacy_key
        WHERE a.user_id = ?
        ORDER BY p.name ASC;
    """, (user_id,))

    if not assigned_pharms:
        flash("No pharmacies currently assigned to your account. Please contact administrative setup.", "warning")

    # Selected pharmacy
    selected_p_key = request.args.get("pharmacy_key", type=int)
    if not selected_p_key and assigned_pharms:
        selected_p_key = assigned_pharms[0]["pharmacy_key"]

    # Ensure owner has access to selected pharmacy
    assigned_keys = [p["pharmacy_key"] for p in assigned_pharms]
    if selected_p_key not in assigned_keys and assigned_pharms:
        selected_p_key = assigned_pharms[0]["pharmacy_key"]

    active_pharmacy = next((p for p in assigned_pharms if p["pharmacy_key"] == selected_p_key), None)

    # Fetch previous updates for this pharmacy with 48h staleness check
    now = datetime.now()
    updates = []
    if active_pharmacy:
        raw_updates = query_db("""
            SELECT u.*, p.drug_name, p.dosage_form, p.standard_strength, p.active_ingredient
            FROM pharmacy_inventory_updates u
            JOIN dim_product p ON u.product_key = p.product_key
            WHERE u.pharmacy_key = ?
            ORDER BY u.update_id DESC;
        """, (active_pharmacy["pharmacy_key"],))
        for ru in raw_updates:
            u_dict = dict(ru)
            is_stale = False
            hours_ago = 0.0
            try:
                up_dt = datetime.strptime(u_dict["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_sec = (now - up_dt).total_seconds()
                hours_ago = diff_sec / 3600.0
                if diff_sec > 48 * 3600:
                    is_stale = True
            except Exception:
                pass
            u_dict["is_stale"] = is_stale
            u_dict["hours_ago"] = round(hours_ago, 1)
            updates.append(u_dict)

    # All products for inventory update form
    products = query_db("SELECT * FROM dim_product ORDER BY drug_name ASC, standard_strength ASC;")

    return render_template(
        "owner_dashboard.html",
        assigned_pharms=assigned_pharms,
        active_pharmacy=active_pharmacy,
        updates=updates,
        products=products,
        now_dt=datetime.now()
    )

@app.route("/owner/update-profile", methods=["POST"])
@login_required
@role_required("pharmacy_owner")
def owner_update_profile():
    user_id = session.get("user_id")
    pharmacy_key = request.form.get("pharmacy_key", type=int)

    # Server-side ownership permission enforcement
    is_assigned = query_db(
        "SELECT 1 FROM user_pharmacy_assignments WHERE user_id = ? AND pharmacy_key = ?",
        (user_id, pharmacy_key), one=True
    )
    if not is_assigned:
        flash("Unauthorized: You can only edit pharmacy profiles assigned to your account.", "danger")
        return redirect(url_for("owner_dashboard"))

    phone = request.form.get("phone", "").strip()
    hours = request.form.get("hours", "").strip()
    online_order_url = request.form.get("online_order_url", "").strip()

    execute_db("""
        UPDATE dim_pharmacy
        SET phone = ?, hours = ?, online_order_url = ?
        WHERE pharmacy_key = ?;
    """, (phone, hours, online_order_url, pharmacy_key))

    flash("Pharmacy profile contact details and operating hours updated successfully.", "success")
    return redirect(url_for("owner_dashboard", pharmacy_key=pharmacy_key))

@app.route("/owner/update-stock", methods=["POST"])
@login_required
@role_required("pharmacy_owner")
def owner_update_stock():
    user_id = session.get("user_id")
    pharmacy_key = request.form.get("pharmacy_key", type=int)
    product_key = request.form.get("product_key", type=int)
    status_code = request.form.get("status_code", "CONFIRMED_LIVE")
    listed_price = request.form.get("listed_price", type=float, default=0.0)
    stock_units = request.form.get("stock_units", type=int, default=0)
    notes = request.form.get("notes", "").strip()

    # Check assignment
    is_assigned = query_db(
        "SELECT 1 FROM user_pharmacy_assignments WHERE user_id = ? AND pharmacy_key = ?",
        (user_id, pharmacy_key), one=True
    )
    if not is_assigned:
        flash("Unauthorized: You can only submit stock updates for locations assigned to your account.", "danger")
        return redirect(url_for("owner_dashboard"))

    execute_db("""
        INSERT INTO pharmacy_inventory_updates 
        (pharmacy_key, product_key, status_code, listed_price, stock_units, reporter_name, update_type, notes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, 'pharmacy-reported', ?, ?);
    """, (
        pharmacy_key, product_key, status_code, listed_price, stock_units,
        session.get("display_name", "Pharmacy Owner"), notes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    flash("Stock update successfully submitted and marked as Pharmacy-Reported with current timestamp.", "success")
    return redirect(url_for("owner_dashboard", pharmacy_key=pharmacy_key))

# =============================================================================
# HOSPITAL STAFF DASHBOARD (RESTRICTED TO hospital_staff)
# =============================================================================

@app.route("/hospital/dashboard")
@login_required
@role_required("hospital_staff")
def hospital_dashboard():
    user_id = session.get("user_id")

    assigned_hosp = query_db("""
        SELECT h.*
        FROM dim_hospital h
        JOIN user_hospital_assignments a ON h.hospital_key = a.hospital_key
        WHERE a.user_id = ?
        LIMIT 1;
    """, (user_id,), one=True)

    updates = []
    if assigned_hosp:
        updates = query_db("""
            SELECT * FROM hospital_service_updates
            WHERE hospital_key = ?
            ORDER BY update_id DESC;
        """, (assigned_hosp["hospital_key"],))

    return render_template(
        "hospital_dashboard.html",
        hospital=assigned_hosp,
        updates=updates
    )

@app.route("/hospital/update-profile", methods=["POST"])
@login_required
@role_required("hospital_staff")
def hospital_update_profile():
    user_id = session.get("user_id")
    hospital_key = request.form.get("hospital_key", type=int)

    # Verify authorization
    is_assigned = query_db(
        "SELECT 1 FROM user_hospital_assignments WHERE user_id = ? AND hospital_key = ?",
        (user_id, hospital_key), one=True
    )
    if not is_assigned:
        flash("Unauthorized: You can only edit hospital profiles assigned to your account.", "danger")
        return redirect(url_for("hospital_dashboard"))

    phone = request.form.get("phone", "").strip()
    website = request.form.get("website", "").strip()
    hours = request.form.get("hours", "").strip()
    services = request.form.get("services", "").strip()
    notes = request.form.get("notes", "").strip()

    # Update dim_hospital
    execute_db("""
        UPDATE dim_hospital
        SET phone = ?, website = ?, listed_services = ?, last_verified = ?
        WHERE hospital_key = ?;
    """, (phone, website, services, datetime.now().strftime("%Y-%m-%d"), hospital_key))

    # Log update
    execute_db("""
        INSERT INTO hospital_service_updates
        (hospital_key, updated_by, phone, website, hours, services, notes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        hospital_key, session.get("display_name", "Hospital Staff"),
        phone, website, hours, services, notes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    flash("Hospital profile and listed services successfully updated.", "success")
    return redirect(url_for("hospital_dashboard"))

# =============================================================================
# MAIN ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    import sys
    import argparse

    # Developer CLI for Institutional Role Assignment:
    # python app.py assign-role <username> <role> [--pharmacy-id <id>] [--hospital-id <id>]
    if len(sys.argv) > 1 and sys.argv[1] == "assign-role":
        parser = argparse.ArgumentParser(description="PharmaTrack DW Institutional Role Assignment CLI")
        parser.add_argument("cmd", choices=["assign-role"])
        parser.add_argument("username", help="User account username to assign role")
        parser.add_argument("role", choices=["public", "pharmacy_owner", "hospital_staff"], help="Target role")
        parser.add_argument("--pharmacy-id", type=int, help="Pharmacy key for pharmacy_owner")
        parser.add_argument("--hospital-id", type=int, help="Hospital key for hospital_staff")
        args = parser.parse_args()

        import migrate_db
        try:
            migrate_db.assign_user_role(args.username, args.role, pharmacy_key=args.pharmacy_id, hospital_key=args.hospital_id)
        except Exception as err:
            print(f"[ERROR] Role assignment failed: {err}")
            sys.exit(1)
        sys.exit(0)

    # Ensure database exists
    if not DB_PATH.exists():
        print("[WARNING] Database not found. Initializing now...")
        import migrate_db
        migrate_db.init_database()
        import etl
        etl.run_etl()

    # Ensure OTP table and legacy account column exist (safe, idempotent)
    try:
        import migrate_otp_table
        migrate_otp_table.run()
    except Exception as _otp_err:
        print(f"[WARNING] OTP migration check: {_otp_err}")

    print("\n" + "=" * 70)
    print("  PHARMATRACK DW SERVER INITIALIZED")
    print("  Local URL: http://localhost:5000")
    print("=" * 70 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


