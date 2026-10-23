import math
import re
from typing import Optional, Tuple, List, Dict, Any

# Earth radius in miles
EARTH_RADIUS_MILES = 3958.8

# All 50 US State Codes + DC
US_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc"
}

# Full state name to 2-letter abbreviation
US_STATE_NAME_TO_CODE = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
    "montana": "mt", "nebraska": "ne", "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc", "north dakota": "nd", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc"
}

# Coordinates (latitude, longitude) for major US cities, metro clusters, tech hubs, and suburbs
US_CITY_COORDINATES: Dict[Tuple[str, str], Tuple[float, float]] = {
    # Texas
    ("austin", "tx"): (30.2672, -97.7431),
    ("round rock", "tx"): (30.5083, -97.6789),
    ("cedar park", "tx"): (30.5052, -97.8203),
    ("georgetown", "tx"): (30.6333, -97.6778),
    ("san marcos", "tx"): (29.8833, -97.9414),
    ("dallas", "tx"): (32.7767, -96.7970),
    ("fort worth", "tx"): (32.7555, -97.3308),
    ("plano", "tx"): (33.0198, -96.6989),
    ("irving", "tx"): (32.8140, -96.9489),
    ("frisco", "tx"): (33.1507, -96.8236),
    ("richardson", "tx"): (32.9483, -96.7299),
    ("arlington", "tx"): (32.7357, -97.1081),
    ("houston", "tx"): (29.7604, -95.3698),
    ("the woodlands", "tx"): (30.1588, -95.4613),
    ("sugar land", "tx"): (29.6197, -95.6349),
    ("san antonio", "tx"): (29.4241, -98.4936),
    ("el paso", "tx"): (31.7619, -106.4850),
    ("lubbock", "tx"): (33.5779, -101.8552),
    ("midland", "tx"): (31.9973, -102.0779),

    # California - Bay Area & Northern CA
    ("san francisco", "ca"): (37.7749, -122.4194),
    ("oakland", "ca"): (37.8044, -122.2712),
    ("berkeley", "ca"): (37.8715, -122.2730),
    ("san jose", "ca"): (37.3382, -121.8863),
    ("sunnyvale", "ca"): (37.3688, -122.0363),
    ("santa clara", "ca"): (37.3541, -121.9552),
    ("mountain view", "ca"): (37.3861, -122.0839),
    ("palo alto", "ca"): (37.4419, -122.1430),
    ("menlo park", "ca"): (37.4530, -122.1817),
    ("redwood city", "ca"): (37.4852, -122.2364),
    ("san mateo", "ca"): (37.5630, -122.3255),
    ("cupertino", "ca"): (37.3230, -122.0322),
    ("fremont", "ca"): (37.5485, -121.9886),
    ("pleasanton", "ca"): (37.6624, -121.8747),
    ("san ramon", "ca"): (37.7799, -121.9780),
    ("walnut creek", "ca"): (37.9101, -122.0652),
    ("san rafael", "ca"): (37.9735, -122.5311),
    ("sacramento", "ca"): (38.5816, -121.4944),
    ("fresno", "ca"): (36.7468, -119.7726),

    # California - Southern CA
    ("los angeles", "ca"): (34.0522, -118.2437),
    ("santa monica", "ca"): (34.0195, -118.4912),
    ("culver city", "ca"): (34.0211, -118.3965),
    ("pasadena", "ca"): (34.1478, -118.1445),
    ("burbank", "ca"): (34.1808, -118.3090),
    ("glendale", "ca"): (34.1425, -118.2551),
    ("long beach", "ca"): (33.7701, -118.1937),
    ("irvine", "ca"): (33.6846, -117.8265),
    ("newport beach", "ca"): (33.6189, -117.9298),
    ("anaheim", "ca"): (33.8366, -117.9143),
    ("san diego", "ca"): (32.7157, -117.1611),
    ("la jolla", "ca"): (32.8328, -117.2713),
    ("carlsbad", "ca"): (33.1581, -117.3506),
    ("riverside", "ca"): (33.9806, -117.3755),

    # Washington
    ("seattle", "wa"): (47.6062, -122.3321),
    ("bellevue", "wa"): (47.6101, -122.2015),
    ("redmond", "wa"): (47.6740, -122.1215),
    ("kirkland", "wa"): (47.6769, -122.2060),
    ("renton", "wa"): (47.4829, -122.2171),
    ("bothell", "wa"): (47.7601, -122.2054),
    ("tacoma", "wa"): (47.2529, -122.4443),
    ("olympia", "wa"): (47.0379, -122.9007),
    ("spokane", "wa"): (47.6588, -117.4260),

    # New York & New Jersey
    ("new york", "ny"): (40.7128, -74.0060),
    ("manhattan", "ny"): (40.7831, -73.9712),
    ("brooklyn", "ny"): (40.6782, -73.9442),
    ("queens", "ny"): (40.7282, -73.7949),
    ("bronx", "ny"): (40.8448, -73.8648),
    ("staten island", "ny"): (40.5795, -74.1502),
    ("white plains", "ny"): (41.0340, -73.7629),
    ("buffalo", "ny"): (42.8864, -78.8784),
    ("rochester", "ny"): (43.1566, -77.6088),
    ("albany", "ny"): (42.6526, -73.7562),
    ("jersey city", "nj"): (40.7178, -74.0431),
    ("hoboken", "nj"): (40.7440, -74.0324),
    ("newark", "nj"): (40.7357, -74.1724),
    ("princeton", "nj"): (40.3573, -74.6672),

    # Massachusetts & New England
    ("boston", "ma"): (42.3601, -71.0589),
    ("cambridge", "ma"): (42.3736, -71.1097),
    ("somerville", "ma"): (42.3876, -71.0995),
    ("waltham", "ma"): (42.3765, -71.2356),
    ("burlington", "ma"): (42.5048, -71.1956),
    ("newton", "ma"): (42.3370, -71.2092),
    ("quincy", "ma"): (42.2529, -71.0023),
    ("worcester", "ma"): (42.2626, -71.8023),
    ("providence", "ri"): (41.8240, -71.4128),
    ("hartford", "ct"): (41.7658, -72.6734),
    ("stamford", "ct"): (41.0534, -73.5387),

    # Illinois & Midwest
    ("chicago", "il"): (41.8781, -87.6298),
    ("evanston", "il"): (42.0451, -87.6877),
    ("naperville", "il"): (41.7508, -88.1535),
    ("schaumburg", "il"): (42.0334, -88.0834),
    ("minneapolis", "mn"): (44.9778, -93.2650),
    ("st. paul", "mn"): (44.9537, -93.0900),
    ("bloomington", "mn"): (44.8408, -93.2983),
    ("detroit", "mi"): (42.3314, -83.0458),
    ("ann arbor", "mi"): (42.2808, -83.7430),
    ("grand rapids", "mi"): (42.9634, -85.6681),
    ("columbus", "oh"): (39.9612, -82.9988),
    ("cleveland", "oh"): (41.4993, -81.6944),
    ("cincinnati", "oh"): (39.1031, -84.5120),
    ("indianapolis", "in"): (39.7684, -86.1581),
    ("milwaukee", "wi"): (43.0389, -87.9065),
    ("madison", "wi"): (43.0731, -89.4012),
    ("st. louis", "mo"): (38.6270, -90.1994),
    ("kansas city", "mo"): (39.0997, -94.5786),

    # Colorado & Mountain
    ("denver", "co"): (39.7392, -104.9903),
    ("boulder", "co"): (40.0150, -105.2705),
    ("colorado springs", "co"): (38.8339, -104.8214),
    ("fort collins", "co"): (40.5853, -105.0844),
    ("broomfield", "co"): (39.9205, -105.0867),
    ("salt lake city", "ut"): (40.7608, -111.8910),
    ("lehi", "ut"): (40.3892, -111.8508),
    ("provo", "ut"): (40.2338, -111.6585),
    ("draper", "ut"): (40.5247, -111.8638),
    ("phoenix", "az"): (33.4484, -112.0740),
    ("scottsdale", "az"): (33.4942, -111.9261),
    ("tempe", "az"): (33.4255, -111.9400),
    ("chandler", "az"): (33.3062, -111.8413),
    ("tucson", "az"): (32.2226, -110.9747),
    ("las vegas", "nv"): (36.1699, -115.1398),
    ("reno", "nv"): (39.5296, -119.8138),

    # Southeast & Mid-Atlantic
    ("atlanta", "ga"): (33.7490, -84.3880),
    ("alpharetta", "ga"): (34.0754, -84.2941),
    ("marietta", "ga"): (33.9526, -84.5499),
    ("raleigh", "nc"): (35.7796, -78.6382),
    ("durham", "nc"): (35.9940, -78.8986),
    ("chapel hill", "nc"): (35.9132, -79.0558),
    ("cary", "nc"): (35.7915, -78.7811),
    ("charlotte", "nc"): (35.2271, -80.8431),
    ("washington", "dc"): (38.9072, -77.0369),
    ("arlington", "va"): (38.8799, -77.1068),
    ("alexandria", "va"): (38.8048, -77.0469),
    ("mclean", "va"): (38.9339, -77.1773),
    ("tysons", "va"): (38.9187, -77.2311),
    ("reston", "va"): (38.9586, -77.3570),
    ("herndon", "va"): (38.9696, -77.3861),
    ("richmond", "va"): (37.5407, -77.4360),
    ("bethesda", "md"): (38.9847, -77.0947),
    ("baltimore", "md"): (39.2904, -76.6122),
    ("rockville", "md"): (39.0840, -77.1528),
    ("philadelphia", "pa"): (39.9526, -75.1652),
    ("pittsburgh", "pa"): (40.4406, -79.9959),
    ("miami", "fl"): (25.7617, -80.1918),
    ("fort lauderdale", "fl"): (26.1224, -80.1373),
    ("tampa", "fl"): (27.9506, -82.4572),
    ("orlando", "fl"): (28.5383, -81.3792),
    ("jacksonville", "fl"): (30.3322, -81.6557),
    ("nashville", "tn"): (36.1627, -86.7816),
    ("memphis", "tn"): (35.1495, -90.0490),

    # Pacific Northwest
    ("portland", "or"): (45.5152, -122.6784),
    ("beaverton", "or"): (45.4871, -122.8037),
    ("hillsboro", "or"): (45.5229, -122.9898),
    ("boise", "id"): (43.6150, -116.2023),
}

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in miles using the Haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_MILES * c

def parse_city_state(loc_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses a location string into normalized (city, state_code).
    Handles noisy formats such as:
      - 'Austin, TX' -> ('austin', 'tx')
      - 'Hybrid - Seattle, WA' -> ('seattle', 'wa')
      - 'San Francisco, CA (Hybrid)' -> ('san francisco', 'ca')
      - 'New York, New York' -> ('new york', 'ny')
      - 'Remote, USA' -> (None, None)
    """
    if not loc_str or not loc_str.strip():
        return None, None

    cleaned = loc_str.strip().lower()

    # If it's purely 'remote', 'usa', 'united states', etc. without a city
    if re.fullmatch(r'(?:remote|us|usa|united states|anywhere|north america|work from home|wfh)(?:\s*\(.*?\))?', cleaned):
        return None, None

    # Strip extraneous noise prefixes/suffixes like '(hybrid)', 'hybrid - ', '[onsite]', etc.
    cleaned = re.sub(r'\b(?:hybrid|onsite|on-site|in-office|remote eligible|remote-friendly|office)\b', '', cleaned, flags=re.I)
    cleaned = re.sub(r'[\(\)\[\]]+', ' ', cleaned)
    cleaned = re.sub(r'\s*-\s*', ', ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(', ')

    # 1. Look for patterns like "City, ST" or "City, State Name"
    parts = [p.strip() for p in cleaned.split(',') if p.strip()]
    if len(parts) >= 2:
        city = parts[0]
        # State part might have extra words or zip codes like "TX 78701" or "CA USA"
        state_words = parts[1].split()
        if state_words:
            candidate_state = state_words[0].lower()
            if candidate_state in US_STATE_CODES:
                return city, candidate_state
            if candidate_state in US_STATE_NAME_TO_CODE:
                return city, US_STATE_NAME_TO_CODE[candidate_state]
            full_state = " ".join(state_words[:2]).lower()
            if full_state in US_STATE_NAME_TO_CODE:
                return city, US_STATE_NAME_TO_CODE[full_state]

    # 2. Check for "City ST" without comma (e.g. "Austin TX" or "Seattle WA")
    match_st = re.search(r'\b([a-z\s]+?)\s+([a-z]{2})\b$', cleaned)
    if match_st:
        candidate_city, candidate_state = match_st.group(1).strip(), match_st.group(2).lower()
        if candidate_state in US_STATE_CODES and len(candidate_city) > 2:
            return candidate_city, candidate_state

    # 3. Fallback: single city string if it matches any known city
    for (known_city, known_state) in US_CITY_COORDINATES:
        if known_city == cleaned:
            return known_city, known_state

    return (parts[0] if parts else None), None

def get_location_coordinates(city: Optional[str], state: Optional[str]) -> Optional[Tuple[float, float]]:
    """Look up latitude & longitude for a parsed city and state."""
    if not city:
        return None

    norm_city = city.strip().lower()
    norm_state = (state or "").strip().lower()

    # Exact (city, state) lookup
    if norm_state and (norm_city, norm_state) in US_CITY_COORDINATES:
        return US_CITY_COORDINATES[(norm_city, norm_state)]

    # City-only lookup if unique or known major city
    matches = [(c, s, coords) for (c, s), coords in US_CITY_COORDINATES.items() if c == norm_city]
    if len(matches) == 1:
        return matches[0][2]
    elif len(matches) > 1 and norm_state:
        for c, s, coords in matches:
            if s == norm_state:
                return coords

    # Partial substring match (e.g. "greater austin area" -> "austin")
    for (c, s), coords in US_CITY_COORDINATES.items():
        if (norm_state == "" or s == norm_state) and (c in norm_city or norm_city in c):
            return coords

    return None

def is_job_pure_remote(workplace_type: str = "", location: str = "", title: str = "") -> bool:
    """
    Determines if a listing is 100% remote with NO on-site or hybrid expectations.
    If the listing expects hybrid presence or on-site days in an office, it returns False.
    """
    wp = (workplace_type or "").lower().strip()
    loc = (location or "").lower().strip()
    tit = (title or "").lower().strip()
    combined = f"{wp} {loc} {tit}"

    # Explicit hybrid or onsite markers mean it expects physical presence
    if any(m in combined for m in ("hybrid", "onsite", "on-site", "in-office", "in office")):
        return False

    # Check for pure remote indicators
    if wp == "remote":
        # Ensure location doesn't specify an in-person city like "Seattle, WA" without remote
        return True

    if re.fullmatch(r'(?:remote|us remote|remote\s*-\s*us(?:a)?|remote\s*,\s*us(?:a)?|anywhere|work from home|wfh|united states\s*\(remote\))', loc):
        return True

    return False

def is_job_in_range(
    job_location: str,
    target_location: Optional[str],
    radius_miles: Optional[int] = 50,
    workplace_type: str = "",
    is_remote: bool = False,
    include_remote: bool = True,
    title: str = ""
) -> bool:
    """
    Evaluates whether a job satisfies the user's location and distance radius criteria.

    Rules:
      1. If target_location is empty/unspecified:
         All jobs match.
      2. If the job is 100% Pure Remote:
         Matches if and only if include_remote is True.
      3. If the job expects on-site presence (Hybrid or On-site):
         MUST be geographically located within radius_miles of target_location.
         Any hybrid/onsite position outside this radius (e.g. Seattle when searching Austin)
         is strictly filtered out.
    """
    if not target_location or not target_location.strip():
        return True

    # 1. Pure Remote check
    pure_remote = is_job_pure_remote(workplace_type, job_location, title) or (is_remote and "hybrid" not in f"{workplace_type} {job_location} {title}".lower())
    if pure_remote:
        return bool(include_remote)

    # 2. At this point, the job expects on-site presence (Hybrid or On-site)
    # Parse target location and job location
    t_city, t_state = parse_city_state(target_location)
    j_city, j_state = parse_city_state(job_location)

    # Effective radius in miles
    effective_radius = 50.0
    if radius_miles is not None:
        effective_radius = float(radius_miles) if radius_miles > 0 else 50.0

    # 3. Coordinate distance calculation
    t_coords = get_location_coordinates(t_city, t_state)
    j_coords = get_location_coordinates(j_city, j_state)

    if t_coords and j_coords:
        dist = haversine_miles(t_coords[0], t_coords[1], j_coords[0], j_coords[1])
        return dist <= effective_radius

    # 4. Fallback heuristics when coordinates for one/both are missing:
    loc_lower = (job_location or "").lower()
    target_lower = target_location.lower().strip()

    # A. Check if the entire target city is contained in the job location (e.g. "Austin" in "Austin, TX Metro")
    if t_city and len(t_city) > 2 and t_city in loc_lower:
        # If target has a state code, ensure job doesn't belong to a different state (e.g. Austin, MN vs Austin, TX)
        if t_state and j_state and t_state != j_state:
            return False
        return True

    # B. If both have identified states and they differ (e.g. WA vs TX), they are outside commute range
    if t_state and j_state and t_state != j_state:
        # Allow close border metros (NYC/NJ, DC/VA/MD, Kansas City MO/KS)
        border_pairs = {
            frozenset(["ny", "nj"]),
            frozenset(["dc", "va"]),
            frozenset(["dc", "md"]),
            frozenset(["mo", "ks"]),
            frozenset(["or", "wa"]),
        }
        if frozenset([t_state, j_state]) not in border_pairs:
            return False

    # C. If in the same state:
    if t_state and j_state and t_state == j_state:
        # If cities are different recognized major cities in large states (e.g. Dallas vs Austin, or Houston vs Austin):
        # We know they are distinct and beyond standard 25/50mi radius
        if t_city and j_city and t_city != j_city:
            # If radius is large (e.g. 100+ miles), allow same state; otherwise require closer match
            return effective_radius >= 100.0

    return False
