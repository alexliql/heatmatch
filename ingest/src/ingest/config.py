"""Regions, source endpoints and estimation constants.

Every magic number the pipeline uses lives here so the README's methodology
section (T9) has a single place to document and justify. Values are from
HEATMATCH.md §3.1/§3.3 unless the comment says otherwise.
"""

from typing import Literal

RegionName = Literal["nyc", "upstate"]
SinkCat = Literal[
    "pool",
    "hospital",
    "university",
    "school",
    "greenhouse",
    "brewery",
    "wwtp",
    "office",
    "residential_multifamily",
    "hotel",
]

# --- regions (§3.1) -------------------------------------------------------
# bbox is (min_lon, min_lat, max_lon, max_lat). A feature belongs to nyc if it
# falls in the nyc bbox, else upstate; both are additionally clipped to the NYS
# boundary, because the nyc bbox reaches well into New Jersey.
REGIONS: dict[RegionName, dict] = {
    "nyc": {
        "bbox": (-74.30, 40.45, -73.65, 40.95),
        "origin": (40.7128, -74.0060),
        "radius_m": 1000.0,
        "detour": 1.30,
        "grid_rotation_deg": 29.0,
        "pipe_cost_per_m": 3000.0,
    },
    "upstate": {
        "bbox": (-79.80, 40.45, -71.80, 45.05),
        "origin": (42.90, -75.50),
        "radius_m": 4000.0,
        "detour": 1.20,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 800.0,
    },
}

# --- sources --------------------------------------------------------------
USER_AGENT = "heatmatch/0.1 (https://github.com/alexliql/heatmatch)"

# The IM3 Open Source Data Center Atlas. Served from the project's GitHub repo
# rather than its MSD-LIVE record: the record's file endpoint holds only a
# placeholder, while the repo copy is versioned and directly fetchable.
ATLAS_URL = (
    "https://raw.githubusercontent.com/IMMM-SFA/datacenter-atlas/main/"
    "static/im3_datacenter_centroids.geojson"
)
ATLAS_SOURCE = {
    "id": "im3_datacenter_atlas",
    "url": "https://doi.org/10.57931/3017294",
    "license": "ODbL-1.0",
    "note": "IM3 Open Source Data Center Atlas v2026.02.09; derived from OpenStreetMap.",
}

# Full-resolution TIGER/Line, not the generalized cartographic file: the NY/NJ
# line runs down the Hudson, and a generalized boundary misplaces waterfront
# points onto the wrong side.
NYS_BOUNDARY_URL = "https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip"
NYS_BOUNDARY_SOURCE = {
    "id": "census_tiger_state",
    "url": NYS_BOUNDARY_URL,
    "license": "public-domain",
    "note": "US Census Bureau TIGER/Line 2024 state boundaries.",
}

# --- NYC Open Data (Socrata) ----------------------------------------------
# Queried through the API with server-side filters rather than downloading the
# full MapPLUTO shapefile, which is hundreds of megabytes of geometry this
# pipeline never uses: PLUTO already carries a lot centroid.
PLUTO_DATASET = "64uk-42ks"
PLUTO_URL = f"https://data.cityofnewyork.us/resource/{PLUTO_DATASET}.json"
PLUTO_SOURCE = {
    "id": "nyc_pluto",
    "url": f"https://data.cityofnewyork.us/d/{PLUTO_DATASET}",
    "license": "public-domain",
    "note": "NYC Department of City Planning, Primary Land Use Tax Lot Output.",
}

LL84_DATASET = "7x5e-2fxh"
LL84_URL = f"https://data.cityofnewyork.us/resource/{LL84_DATASET}.json"
LL84_SOURCE = {
    "id": "nyc_ll84",
    "url": f"https://data.cityofnewyork.us/d/{LL84_DATASET}",
    "license": "public-domain",
    "note": "Energy and Water Data Disclosure for Local Law 84, calendar year 2021.",
}

# Building classes that could plausibly house a data center: E/F industrial and
# warehouse, I utility, Y public facility (§3.3).
PLUTO_BLDG_CLASS_PREFIXES = ("E", "F", "I", "Y")

# Owner-name fragments for known colocation and carrier operators. Matched
# case-insensitively as substrings; deliberately broad, then narrowed by the
# building-class and address filters.
# "COLO" alone was tried and removed: it matches Colonna, Colossal and similar
# ordinary owner names. Only whole words or distinctive brands belong here.
DC_OPERATOR_NAMES = (
    "EQUINIX", "DIGITAL REALTY", "TELX", "TELEHOUSE", "SABEY", "CORESITE",
    "DATABANK", "CYXTERA", "ZAYO", "VERIZON", "AT&T", "DATA CENTER",
    "COLOCATION", "INTERNAP", "CENTURYLINK", "LUMEN", "IRON MOUNTAIN",
)

# Carrier hotels, which are ordinary office building classes and so would be
# missed by the class filter. 165 Halsey St is deliberately absent: it is in
# Newark, New Jersey.
# Addresses are PLUTO's spelling, which is not always the one on the door:
# 60 Hudson Street is filed as "56 HUDSON STREET". Verified against the table
# rather than assumed.
CARRIER_HOTEL_ADDRESSES = (
    "56 HUDSON STREET",  # 60 Hudson Street, the Western Union building
    "111 8 AVENUE",
    "32 AVENUE OF THE AMERICAS",
    "375 PEARL STREET",
    "325 HUDSON STREET",
    "85 10 AVENUE",
    "121 VARICK STREET",
    "33 WHITEHALL STREET",
)

# Ceiling on an area-derived capacity estimate, MW.
#
# The 75 W/sq ft figure assumes a whole building is white space, which is false
# for the mixed-use towers this catches: 111 8th Avenue came out at 162 MW, far
# more than any facility in the state and enough to dominate every ranking on
# its own. Capping keeps a plausibly-large site large without letting a
# floor-area artefact outrank real measurements. Flagged in the README.
MAX_ESTIMATED_DC_MW = 25.0

# kBtu -> kWh.
KBTU_TO_KWH = 0.293071

# A sink is matched to a tax lot within this distance of its centroid (§3.3).
LL84_JOIN_M = 40.0

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_S = 180
OVERPASS_MAX_RETRIES = 4
OVERPASS_SOURCE = {
    "id": "osm_overpass",
    "url": "https://www.openstreetmap.org/copyright",
    "license": "ODbL-1.0",
    "note": "© OpenStreetMap contributors, via the Overpass API.",
}

# Tag filters per sink category (§3.3). Each entry is a list of Overpass tag
# selectors; every selector is queried across node, way and relation.
OVERPASS_FILTERS: dict[SinkCat, list[str]] = {
    "pool": ['["leisure"="swimming_pool"]["access"!="private"]',
             '["leisure"="sports_centre"]["sport"="swimming"]'],
    "hospital": ['["amenity"="hospital"]'],
    "university": ['["amenity"="university"]', '["amenity"="college"]'],
    "school": ['["amenity"="school"]'],
    "greenhouse": ['["landuse"="greenhouse_horticulture"]', '["building"="greenhouse"]'],
    "brewery": ['["craft"="brewery"]', '["industrial"="brewery"]', '["microbrewery"="yes"]'],
    "wwtp": ['["man_made"="wastewater_plant"]'],
    "office": ['["building"="office"]', '["office"]'],
    "residential_multifamily": ['["building"="apartments"]'],
    "hotel": ['["tourism"="hotel"]'],
}

# Categories not collected upstate (§3.3).
NYC_ONLY_CATS: frozenset[str] = frozenset({"residential_multifamily"})

# --- data center capacity estimation --------------------------------------
# The Atlas carries no capacity field, so MW is always an estimate here.
# 75 W/sq ft is §3.3's low colo density.
MW_PER_SQFT = 0.000075

# Fallback when the Atlas has no footprint (its `type=point` rows). 1.5 MW is a
# deliberately modest single-facility figure: guessing high would let unmeasured
# sites dominate the ranking, which is the opposite of what the score is for.
DEFAULT_DC_MW = 1.5

# --- sink demand estimation -----------------------------------------------
# Annual thermal intensity, kWh per m² of floor area (§3.3).
INTENSITY_KWH_PER_M2: dict[SinkCat, float] = {
    "pool": 400.0,
    "hospital": 250.0,
    "university": 150.0,
    "school": 120.0,
    "greenhouse": 350.0,
    "brewery": 200.0,
    "wwtp": 100.0,
    "office": 90.0,
    "residential_multifamily": 110.0,
    "hotel": 180.0,
}

# Used when OSM has no `building:levels`. Single-storey for the process/covered
# categories, mid-rise for the rest; these are guesses and flagged as such.
FLOORS_GUESS: dict[SinkCat, float] = {
    "pool": 1.0,
    "hospital": 5.0,
    "university": 4.0,
    "school": 3.0,
    "greenhouse": 1.0,
    "brewery": 2.0,
    "wwtp": 1.0,
    "office": 8.0,
    "residential_multifamily": 6.0,
    "hotel": 10.0,
}

# Minimum footprint area (m²) for a way/relation to count (§3.3). Categories
# absent from this map have no area gate.
MIN_AREA_M2: dict[SinkCat, float] = {
    "school": 5000.0,
    "office": 3000.0,
    "residential_multifamily": 2000.0,
}

# Annual thermal demand (kWh) for nodes, which have no footprint at all.
# Order-of-magnitude placeholders, flagged via demand_source="category_default".
CATEGORY_DEFAULT_KWH: dict[SinkCat, float] = {
    "pool": 500_000.0,
    "hospital": 8_000_000.0,
    "university": 5_000_000.0,
    "school": 800_000.0,
    "greenhouse": 1_000_000.0,
    "brewery": 600_000.0,
    "wwtp": 1_500_000.0,
    "office": 1_200_000.0,
    "residential_multifamily": 900_000.0,
    "hotel": 1_500_000.0,
}

# Sinks are kept only if within this multiple of a region's radius of some data
# center (§3.3); the 1.1 is slack so a later radius tweak in the UI does not
# immediately run out of data.
SINK_PREFILTER_SLACK = 1.1


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def region_for(lat: float, lon: float) -> RegionName | None:
    """Assign a point to a region, or None if it is in neither.

    Order matters and is not arbitrary: the upstate bbox fully contains the nyc
    one, so nyc must be tested first for "upstate = the rest of NYS" (§3.1) to
    hold. Callers still need the NYS boundary check separately; these are
    bounding boxes, and the nyc one reaches into New Jersey.
    """
    for name in ("nyc", "upstate"):
        if in_bbox(lat, lon, REGIONS[name]["bbox"]):
            return name  # type: ignore[return-value]
    return None
