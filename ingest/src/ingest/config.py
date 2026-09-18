"""Regions, source endpoints and estimation constants."""

from typing import Literal

RegionName = Literal["nyc", "upstate", "nova", "seattle", "pdx", "svy", "la", "sac"]
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

# --- regions -------------------------------------------------------
# bbox is (min_lon, min_lat, max_lon, max_lat); `region_for` tests them in this
# order, so nyc must precede the upstate bbox that contains it. Every region is
# also clipped to a state or county boundary, since bboxes cross state lines.
# `radius_m`, `detour`, `pipe_cost_per_m` and `origin` mirror the engine's
# per-region defaults in core/heatmatch-core/src/weights.rs.
REGIONS: dict[RegionName, dict] = {
    "nyc": {
        "bbox": (-74.30, 40.45, -73.65, 40.95),
        "origin": (40.7128, -74.0060),
        "radius_m": 1000.0,
        "detour": 1.30,
        "grid_rotation_deg": 29.0,
        "pipe_cost_per_m": 3000.0,
        "state_fips": "36",
        "state_abb": "NY",
        # The five boroughs: which ComStock counties the near-zero fallback
        # reads. The clip is still the state boundary.
        "county_fips": ("061", "047", "081", "005", "085"),
        "clip": "state",
    },
    "upstate": {
        "bbox": (-79.80, 40.45, -71.80, 45.05),
        "origin": (42.90, -75.50),
        "radius_m": 4000.0,
        "detour": 1.20,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 800.0,
        "state_fips": "36",
        "state_abb": "NY",
        "clip": "state",
    },
    # Northern Virginia: seven jurisdictions, since the bbox reaches into
    # Maryland and West Virginia.
    "nova": {
        "bbox": (-78.00, 38.55, -77.00, 39.35),
        "origin": (39.02, -77.45),
        "radius_m": 3000.0,
        "detour": 1.25,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 1200.0,
        "state_fips": "51",
        "state_abb": "VA",
        # FIPS, not names: "Fairfax" is both the county (059) and an
        # independent city (600). Loudoun, Prince William, Fairfax, Arlington,
        # Alexandria, Manassas, Manassas Park.
        "county_fips": ("107", "153", "059", "013", "510", "683", "685"),
        "clip": "counties",
        "climate_zone": "4A",
    },
    # Seattle keeps Enwave's steam-heated customers as sinks: a network-level
    # heat swap is exactly the case a data center next to a steam plant makes.
    "seattle": {
        "bbox": (-122.55, 47.20, -121.95, 47.85),
        "origin": (47.61, -122.33),
        "radius_m": 1500.0,
        "detour": 1.30,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 2500.0,
        "state_fips": "53",
        "state_abb": "WA",
        "county_fips": ("033", "061", "053"),  # King, Snohomish, Pierce
        "clip": "counties",
        "climate_zone": "4C",
        "keep_steam_heated": True,
    },
    # Portland metro; the data centers are in Hillsboro.
    "pdx": {
        "bbox": (-123.10, 45.30, -122.40, 45.75),
        "origin": (45.52, -122.90),
        "radius_m": 2500.0,
        "detour": 1.25,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 1500.0,
        "state_fips": "41",
        "state_abb": "OR",
        "county_fips": ("067", "051", "005"),  # Washington, Multnomah, Clackamas
        "clip": "counties",
        "climate_zone": "4C",
    },
    # California is three metro regions, not one state: different utilities,
    # climates and projection frames.
    "svy": {
        "bbox": (-122.20, 37.20, -121.70, 37.50),
        "origin": (37.38, -121.95),
        "radius_m": 2000.0,
        "detour": 1.25,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 2500.0,
        "state_fips": "06",
        "state_abb": "CA",
        "county_fips": ("085", "081", "001"),  # Santa Clara, San Mateo, Alameda
        "clip": "counties",
        "climate_zone": "3C",
    },
    # The bbox reaches to Irvine so Orange County survives the bbox test.
    "la": {
        "bbox": (-118.60, 33.50, -117.55, 34.30),
        "origin": (34.05, -118.25),
        "radius_m": 1500.0,
        "detour": 1.30,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 3000.0,
        "state_fips": "06",
        "state_abb": "CA",
        "county_fips": ("037", "059"),  # Los Angeles, Orange
        "clip": "counties",
        "climate_zone": "3B",
    },
    # The inland control: coastal data sources, real winters, cheap SMUD power.
    "sac": {
        "bbox": (-121.65, 38.35, -121.05, 38.80),
        "origin": (38.58, -121.35),
        "radius_m": 3000.0,
        "detour": 1.20,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 1200.0,
        "state_fips": "06",
        "state_abb": "CA",
        "county_fips": ("067", "061"),  # Sacramento, Placer
        "clip": "counties",
        "climate_zone": "3B",
    },
}

# --- sources --------------------------------------------------------------
USER_AGENT = "heatmatch/0.1 (https://github.com/alexliql/heatmatch)"

# The IM3 Open Source Data Center Atlas, from its GitHub repo: the MSD-LIVE
# record's file endpoint holds only a placeholder.
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

# Full-resolution TIGER/Line: a generalized boundary misplaces Hudson
# waterfront points onto the New Jersey side.
NYS_BOUNDARY_URL = "https://www2.census.gov/geo/tiger/TIGER2024/STATE/tl_2024_us_state.zip"
NYS_BOUNDARY_SOURCE = {
    "id": "census_tiger_state",
    "url": NYS_BOUNDARY_URL,
    "license": "public-domain",
    "note": "US Census Bureau TIGER/Line 2024 state boundaries.",
}

# County and county-equivalent (Virginia's independent cities) boundaries.
COUNTY_BOUNDARY_URL = "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip"
COUNTY_BOUNDARY_SOURCE = {
    "id": "census_tiger_county",
    "url": COUNTY_BOUNDARY_URL,
    "license": "public-domain",
    "note": "US Census Bureau TIGER/Line 2024 county and county-equivalent boundaries.",
}

# --- NYC Open Data (Socrata) ----------------------------------------------
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

# Building classes that could house a data center: E/F industrial and
# warehouse, I utility, Y public facility.
PLUTO_BLDG_CLASS_PREFIXES = ("E", "F", "I", "Y")

# Owner-name substrings for known operators, matched case-insensitively. Whole
# words or distinctive brands only: "COLO" matched Colonna and Colossal.
DC_OPERATOR_NAMES = (
    "EQUINIX",
    "DIGITAL REALTY",
    "TELX",
    "TELEHOUSE",
    "SABEY",
    "CORESITE",
    "DATABANK",
    "CYXTERA",
    "ZAYO",
    "VERIZON",
    "AT&T",
    "DATA CENTER",
    "COLOCATION",
    "INTERNAP",
    "CENTURYLINK",
    "LUMEN",
    "IRON MOUNTAIN",
    # Northern Virginia
    "AMAZON DATA SERVICES",
    "VADATA",
    "MICROSOFT",
    "GOOGLE",
    "META",
    "DUPONT FABROS",
    "CYRUSONE",
    "QTS",
    "VANTAGE",
    "ALIGNED",
    "COMPASS",
    "CLOUDHQ",
    "STACK INFRASTRUCTURE",
    "NTT",
    "COLOGIX",
    "COPT",
    "YONDR",
    "EDGECORE",
    "NOVVA",
    "CHIRISA",
    # West Coast
    "YAHOO",
    "OATH",
    "DELL",
    "INTUIT",
    "H5",
    "WESTIN BUILDING",
    "CLISE",
    "T5",
    "WAVE",
    "APPLE",
    "FLEXENTIAL",
    "EDGECONNEX",
    "INFOMART",
    "PRIME DATA",
    "EVOCATIVE",
    "COLOVORE",
    "HURRICANE ELECTRIC",
)

# Carrier hotels sit in ordinary office classes and would miss the class
# filter. Spelled as PLUTO files them: 60 Hudson Street is "56 HUDSON STREET".
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

# Ceiling on an area-derived capacity estimate, MW. New York's mixed-use
# towers are not all white space (111 8th Avenue came out at 162 MW); the
# purpose-built halls elsewhere genuinely reach tens of MW, so their ceiling
# only guards against bad geometry.
MAX_ESTIMATED_DC_MW: dict[str, float] = {
    "nyc": 25.0,
    "upstate": 25.0,
    "nova": 150.0,
    "seattle": 150.0,
    "pdx": 150.0,
    "svy": 150.0,
    "la": 150.0,
    "sac": 150.0,
}

# kBtu -> kWh.
KBTU_TO_KWH = 0.293071

# --- demand basis ---------------------------------------------------------
# Every sink's `demand_kwh` is *delivered heat*, not fuel bought: the engine
# divides by boiler efficiency itself, so fuel-reporting sources are scaled by
# this on the way in. Both constants must equal the engine's (`boiler_eff`,
# `econ::EXISTING_HEAT_PUMP_COP`); tests check.
BOILER_EFF = 0.85
EXISTING_HEAT_PUMP_COP = 3.0

# What a sink heats with today, and so what a connection would displace.
Counterfactual = Literal["gas", "electric_resistance", "heat_pump"]

# A measured building reporting almost no thermal fuel is usually heated
# electrically, which the fuel columns cannot see. Below the first threshold,
# where ComStock says its type wants more than the second, the model wins and
# the sink says so via `demand_note`.
MEASURED_NEAR_ZERO_KWH_PER_M2 = 10.0
MODELLED_SUBSTANTIAL_KWH_PER_M2 = 30.0

# A sink is matched to a tax lot within this distance of its centroid.
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

# Overpass tag selectors per sink category.
OVERPASS_FILTERS: dict[SinkCat, list[str]] = {
    "pool": [
        '["leisure"="swimming_pool"]["access"!="private"]',
        '["leisure"="sports_centre"]["sport"="swimming"]',
    ],
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

# Where apartment buildings are dense enough to collect as sinks.
MULTIFAMILY_REGIONS: frozenset[str] = frozenset({"nyc", "la"})


def keep_steam_heated(region: str) -> bool:
    """Steam-heated sinks are dropped (they have their heat) unless the region
    keeps them as offtakers of a network-level swap."""
    return bool(REGIONS[region].get("keep_steam_heated", False))


# `mw_confidence` is derived from `mw_source` through this, never set
# independently, so the two cannot disagree.
MW_CONFIDENCE_BY_SOURCE: dict[str, str] = {
    "reported": "reported",
    "filed": "filed",
    "manual": "filed",
    "parcel_estimate": "parcel_estimate",
    "pluto_estimate": "parcel_estimate",
    "atlas_sqft": "footprint_estimate",
    "atlas_default": "footprint_estimate",
    "seed_sqft": "footprint_estimate",
}


# --- NREL ComStock --------------------------------------------------------
# Modelled thermal demand where there is no benchmarking disclosure. The
# release is pinned: intensities move between releases.
COMSTOCK_RELEASE = "2025/comstock_amy2018_release_3"
COMSTOCK_BASE_URL = (
    "https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/"
    "end-use-load-profiles-for-us-building-stock"
)
COMSTOCK_SOURCE = {
    "id": "nrel_comstock",
    "url": "https://registry.opendata.aws/nrel-pds-building-stock/",
    "license": "CC-BY-4.0",
    "note": (
        f"NREL ComStock {COMSTOCK_RELEASE}, baseline (upgrade 0); "
        "annual heating-fuel intensity and monthly shape by building type."
    ),
}

# Regions whose sink demand is modelled from ComStock. New York City reads its
# table only for the near-zero fallback; its estimates are never replaced.
COMSTOCK_REGIONS: frozenset[str] = frozenset({"nova", "seattle", "pdx", "svy", "la", "sac"})
COMSTOCK_FALLBACK_REGIONS: frozenset[str] = COMSTOCK_REGIONS | {"nyc"}

# Fewer sampled buildings than this and the category constant is used instead.
COMSTOCK_MIN_SAMPLES = 30

# ComStock building type per sink category. Absent categories (pool,
# greenhouse, brewery, wwtp) keep INTENSITY_KWH_PER_M2; `office` is resolved
# by floor area in `comstock.comstock_type`.
COMSTOCK_TYPE_BY_CAT: dict[str, str] = {
    "hospital": "Hospital",
    "hotel": "LargeHotel",
    "school": "PrimarySchool",
    "university": "SecondarySchool",
}

# Floor area above which an office is modelled as a large one, m2.
COMSTOCK_LARGE_OFFICE_M2 = 10_000.0

# Which ComStock type supplies a category's monthly shape. One curve per
# category, so offices take the medium-office shape. `hospital` is absent:
# too few samples, so it keeps the engine's built-in shape.
COMSTOCK_PROFILE_TYPE_BY_CAT: dict[str, str] = {
    "school": "PrimarySchool",
    "university": "SecondarySchool",
    "office": "MediumOffice",
    "hotel": "LargeHotel",
}

# --- data center capacity estimation --------------------------------------
# W/sq ft: 75 for mixed-use colo space (New York), 150 for a purpose-built
# hall's assessed floor area, 100 against a bare footprint, which overstates
# how much ground area is white space.
MW_PER_SQFT = 0.000075
NOVA_MW_PER_SQFT = 0.00015
NOVA_MW_PER_SQFT_FOOTPRINT = 0.0001

# Density per region, against the area that region's source reports.
MW_PER_SQFT_BY_REGION: dict[str, float] = {
    "nyc": MW_PER_SQFT,
    "upstate": MW_PER_SQFT,
    "nova": NOVA_MW_PER_SQFT_FOOTPRINT,
    "seattle": NOVA_MW_PER_SQFT_FOOTPRINT,
    "pdx": NOVA_MW_PER_SQFT_FOOTPRINT,
    "svy": NOVA_MW_PER_SQFT_FOOTPRINT,
    "la": NOVA_MW_PER_SQFT_FOOTPRINT,
    "sac": NOVA_MW_PER_SQFT_FOOTPRINT,
}

# Seeded sites, by kind of building: a carrier hotel is an office tower with
# some floors of white space.
SEED_MW_PER_SQFT: dict[str, float] = {
    "purpose_built": NOVA_MW_PER_SQFT,
    "carrier_hotel": MW_PER_SQFT,
}

# Two parcels belong to the same campus if their boundaries are no further
# apart than this and the normalized owner name matches.
CAMPUS_ADJACENCY_M = 30.0

# A Loudoun parcel with no operator-name match still counts as a candidate if
# its buildings cover at least this much ground.
NOVA_MIN_DC_FOOTPRINT_M2 = 4000.0

# Fallback when the Atlas has no footprint; modest so unmeasured sites cannot
# dominate the ranking.
DEFAULT_DC_MW = 1.5

# --- sink demand estimation -----------------------------------------------
# Annual thermal intensity, kWh per m² of floor area.
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

# Storeys when OSM has no `building:levels`.
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

# Minimum footprint area (m²) for a way/relation to count. Categories
# absent from this map have no area gate.
MIN_AREA_M2: dict[SinkCat, float] = {
    "school": 5000.0,
    "office": 3000.0,
    "residential_multifamily": 2000.0,
}

# Every region after New York gates pools at 250 m²: suburban OpenStreetMap
# includes back-garden pools (median 81 m² in Virginia), and pool carries the
# highest category weight. New York has the same problem, but applying the
# gate there would move published results; see the README's limitations.
_POOL_GATED = {**MIN_AREA_M2, "pool": 250.0}
MIN_AREA_M2_BY_REGION: dict[str, dict[SinkCat, float]] = {
    region: _POOL_GATED for region in ("nova", "seattle", "pdx", "svy", "la", "sac")
}


def min_area_for(region: str) -> dict[SinkCat, float]:
    """Area gates in force for a region."""
    return MIN_AREA_M2_BY_REGION.get(region, MIN_AREA_M2)


# Annual demand (kWh) for nodes, which have no footprint; order-of-magnitude
# placeholders flagged as demand_source="category_default".
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

# Sinks are kept within radius × detour × this of some data center; the slack
# is so a radius tweak in the UI does not immediately run out of data.
SINK_PREFILTER_SLACK = 1.1


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def region_for(lat: float, lon: float) -> RegionName | None:
    """The region whose bbox contains the point, in REGIONS order, or None.
    A bbox test only; `boundary.in_region` adds the clip."""
    for name, cfg in REGIONS.items():
        if in_bbox(lat, lon, cfg["bbox"]):
            return name
    return None
