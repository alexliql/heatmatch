"""Regions, source endpoints and estimation constants.

Every magic number the pipeline uses lives here.
"""

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
        "state_fips": "36",
        "state_abb": "NY",
        # The five boroughs. Not the clip — that stays the state boundary plus
        # the bbox — but which ComStock counties the near-zero fallback reads.
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
    # Northern Virginia. Clipped to seven jurisdictions rather than to the bbox:
    # the bbox reaches into Maryland and West Virginia, and the cluster this
    # region exists to describe stops at the county line.
    "nova": {
        "bbox": (-78.00, 38.55, -77.00, 39.35),
        "origin": (39.02, -77.45),
        "radius_m": 3000.0,
        "detour": 1.25,
        "grid_rotation_deg": None,
        "pipe_cost_per_m": 1200.0,
        "state_fips": "51",
        "state_abb": "VA",
        # County FIPS, not names: "Fairfax" alone would match both Fairfax
        # County (059) and the independent City of Fairfax (600), which is a
        # separate jurisdiction and not one of the seven. Loudoun, Prince
        # William, Fairfax, Arlington, Alexandria, Manassas, Manassas Park.
        "county_fips": ("107", "153", "059", "013", "510", "683", "685"),
        "clip": "counties",
        "climate_zone": "4A",
    },
    # --- West Coast -------------------------------------------------------
    # Seattle has the one thing no other region here has: a live precedent.
    # The Westin Building already exports its heat to Amazon's campus next
    # door, and Enwave runs district steam downtown. Its Enwave customers are
    # kept as sinks even where steam heats them today — a network-level heat
    # swap is exactly the case a data center next to a steam plant makes.
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
    # Portland metro. The data centers are in Hillsboro, in Washington County;
    # Portland's own benchmarking data stops at the city limits.
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
    # California is modelled as metro regions, not one state: each gets its
    # own projection frame, prices and water policy, and the Bay Area, Los
    # Angeles and Sacramento are different utilities in different climates.
    # San Diego and the Inland Empire are absent; each is a one-entry
    # addition here if it ever earns one.
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
    # The bbox reaches south-east to Irvine: Orange County is part of this
    # region, and `region_for` tests the bbox before the county clip ever
    # runs, so a bbox that stopped at the county line would drop it.
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
    # The inland control: the same measured-data source as the coast, real
    # winters, and SMUD's municipal power at well under coastal prices.
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

# County and independent-city boundaries, for regions defined by jurisdiction
# rather than by state. Virginia's independent cities (Alexandria, Manassas,
# Manassas Park) are county-equivalents in TIGER and appear in this same file.
COUNTY_BOUNDARY_URL = "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip"
COUNTY_BOUNDARY_SOURCE = {
    "id": "census_tiger_county",
    "url": COUNTY_BOUNDARY_URL,
    "license": "public-domain",
    "note": "US Census Bureau TIGER/Line 2024 county and county-equivalent boundaries.",
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
# warehouse, I utility, Y public facility.
PLUTO_BLDG_CLASS_PREFIXES = ("E", "F", "I", "Y")

# Owner-name fragments for known colocation and carrier operators. Matched
# case-insensitively as substrings; deliberately broad, then narrowed by the
# building-class and address filters.
# "COLO" alone was tried and removed: it matches Colonna, Colossal and similar
# ordinary owner names. Only whole words or distinctive brands belong here.
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

# Ceiling on an area-derived capacity estimate, MW, per region.
#
# New York: the 75 W/sq ft figure assumes a whole building is white space,
# which is false for the mixed-use towers this catches: 111 8th Avenue came out
# at 162 MW, far more than any facility in the state and enough to dominate
# every ranking on its own. Capping keeps a plausibly-large site large without
# letting a floor-area artefact outrank real measurements.
#
# Northern Virginia needs a far higher ceiling, because there the inference is
# sound: these are purpose-built halls, not offices with a server room, and the
# largest genuinely are tens of megawatts. A 25 MW cap would clip most of the
# cluster to the same value and flatten the ranking it exists to produce. At
# the footprint density below nothing reaches 150 MW, so this ceiling is a
# guard against bad geometry rather than a routine correction.
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
# Every sink's `demand_kwh` is *delivered heat*: what the building's heating
# system put into its spaces and hot water, not the fuel it bought to do so.
# That is the quantity a heat network would replace, and it is what the engine
# prices — `econ.rs` divides delivered heat by boiler efficiency to recover the
# fuel avoided. A measured source reporting fuel input therefore has to be
# scaled down by this on the way in, or the fuel is counted twice.
#
# Must equal `Econ::default_for(*).boiler_eff` in core/heatmatch-core; a test
# reads the wasm default and checks.
BOILER_EFF = 0.85

# Heat delivered per unit of electricity by an existing heat pump, for turning
# a ComStock building's heat-pump electricity back into the heat it produced.
# Must equal `econ::EXISTING_HEAT_PUMP_COP`.
EXISTING_HEAT_PUMP_COP = 3.0

# What a sink heats with today. Decides what a connection would displace, and
# so what a delivered MWh is worth to it. Derived per ComStock building type
# from the weighted majority of `in.hvac_heat_type`; measured buildings whose
# thermal fuels dominate are `gas` regardless.
Counterfactual = Literal["gas", "electric_resistance", "heat_pump"]

# A measured building reporting almost no thermal fuel is usually not a
# building with no heating demand — it is one heated electrically, which the
# fuel columns cannot see. Below the first threshold, where ComStock says a
# typical building of that type wants more than the second, the measurement is
# set aside for the model and the sink says so via `demand_note`.
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

# Tag filters per sink category. Each entry is a list of Overpass tag
# selectors; every selector is queried across node, way and relation.
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

# Where apartment buildings are collected as sinks. Dense enough to matter in
# New York City and Los Angeles; elsewhere the category is mostly suburban
# garden apartments with little to gain from a heat network.
MULTIFAMILY_REGIONS: frozenset[str] = frozenset({"nyc", "la"})


def keep_steam_heated(region: str) -> bool:
    """Whether steam-heated sinks stay in the dataset.

    Dropped everywhere by default — a district-steam building already has its
    heat. Seattle keeps them: Enwave's customers are the natural offtakers of a
    network-level swap, which is a commercial question this model does not
    evaluate but should not pre-empt.
    """
    return bool(REGIONS[region].get("keep_steam_heated", False))


# How far to trust a capacity figure, given where it came from. Kept here, in
# one mapping, so `mw_source` and `mw_confidence` can never contradict each
# other: the second is derived from the first, never set independently.
#
# Everything New York has is area-derived, which is why the engine's New York
# defaults apply no discount at all — grading guesses against guesses is noise.
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
# Modelled thermal demand, for regions with no benchmarking disclosure to read.
#
# Release pinned deliberately: ComStock re-runs the whole stock each year and
# the intensities move, so an unpinned "latest" would silently change every
# Virginia demand figure between builds. Bump it on purpose, and rerun.
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

# Regions whose sink demand is modelled from ComStock rather than read from a
# disclosure filing. New York has LL84; Virginia has nothing equivalent.
COMSTOCK_REGIONS: frozenset[str] = frozenset({"nova", "seattle", "pdx", "svy", "la", "sac"})

# Regions that download a ComStock table at all. A superset of the above: New
# York City fetches its five counties *only* so that the near-zero fallback
# has something to compare a measured building against. Its footprint and
# category estimates are never replaced — that would rewrite New York
# wholesale, which is a different decision from catching a few all-electric
# towers.
COMSTOCK_FALLBACK_REGIONS: frozenset[str] = COMSTOCK_REGIONS | {"nyc"}

# Below this many sampled buildings an intensity is not reported at all, and
# the category constant is used instead. Pooled across a region's jurisdictions
# this is rarely close: Loudoun alone samples ~6,300 buildings.
COMSTOCK_MIN_SAMPLES = 30

# ComStock building type per sink category. Categories absent from this map
# have no ComStock equivalent — a pool, greenhouse, brewery or treatment works
# is not commercial floor space — and keep INTENSITY_KWH_PER_M2 below.
#
# `office` is resolved by area at use time, not here: ComStock separates small,
# medium and large offices and they differ substantially.
COMSTOCK_TYPE_BY_CAT: dict[str, str] = {
    "hospital": "Hospital",
    "hotel": "LargeHotel",
    "school": "PrimarySchool",
    "university": "SecondarySchool",
}

# Floor area above which an office is modelled as a large one, m2.
COMSTOCK_LARGE_OFFICE_M2 = 10_000.0

# Which ComStock type supplies the *monthly shape* for a category. Intensity is
# chosen per building (an office's size decides it); a profile is one curve per
# category, so offices take the medium-office shape — the large and medium
# curves differ by about a point a month, and most qualifying office sinks sit
# nearer the medium end of the range.
#
# `hospital` is absent on purpose: ComStock samples only six hospitals across
# the seven jurisdictions, below COMSTOCK_MIN_SAMPLES, so hospitals keep the
# built-in shape and the category demand constant.
COMSTOCK_PROFILE_TYPE_BY_CAT: dict[str, str] = {
    "school": "PrimarySchool",
    "university": "SecondarySchool",
    "office": "MediumOffice",
    "hotel": "LargeHotel",
}

# --- data center capacity estimation --------------------------------------
# The Atlas carries no capacity field, so MW is always an estimate here.
# 75 W/sq ft is a low colo density.
MW_PER_SQFT = 0.000075

# Northern Virginia's purpose-built halls are far denser than the mixed-use
# colo space the NYC figure describes: 150 W/sq ft against assessed floor area.
NOVA_MW_PER_SQFT = 0.00015

# Applied when only a building *footprint* is known, as in the Atlas, whose
# `sqft` is an OpenStreetMap polygon area. A footprint understates a two-storey
# hall but overstates how much of the ground area is white space rather than
# mechanical yard, loading and office; the two errors do not cancel, so the
# lower figure is the honest one. Across the seven jurisdictions it totals
# ~4 GW, which is the right order for the cluster; 150 W/sq ft would say 6 GW.
NOVA_MW_PER_SQFT_FOOTPRINT = 0.0001

# Area-derived capacity density per region, W/sq ft of the area that source
# actually reports.
MW_PER_SQFT_BY_REGION: dict[str, float] = {
    "nyc": MW_PER_SQFT,
    "upstate": MW_PER_SQFT,
    "nova": NOVA_MW_PER_SQFT_FOOTPRINT,
    # Purpose-built halls, same as Virginia. A downtown carrier hotel is the
    # exception and is seeded with its own density; see seed_dcs.py.
    "seattle": NOVA_MW_PER_SQFT_FOOTPRINT,
    "pdx": NOVA_MW_PER_SQFT_FOOTPRINT,
    "svy": NOVA_MW_PER_SQFT_FOOTPRINT,
    "la": NOVA_MW_PER_SQFT_FOOTPRINT,
    "sac": NOVA_MW_PER_SQFT_FOOTPRINT,
}

# Seeded sites: W per square foot of stated floor area, by what kind of
# building it is. A purpose-built hall is mostly white space; a downtown
# carrier hotel is an office tower with some floors of it.
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

# Fallback when the Atlas has no footprint (its `type=point` rows). 1.5 MW is a
# deliberately modest single-facility figure: guessing high would let unmeasured
# sites dominate the ranking, which is the opposite of what the score is for.
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

# Minimum footprint area (m²) for a way/relation to count. Categories
# absent from this map have no area gate.
MIN_AREA_M2: dict[SinkCat, float] = {
    "school": 5000.0,
    "office": 3000.0,
    "residential_multifamily": 2000.0,
}

# Per-region overrides, merged over MIN_AREA_M2.
#
# Northern Virginia gates pools at 250 m². Suburban OpenStreetMap coverage
# there is thorough enough to include back-garden pools: 544 of 588 matches
# were unnamed with a median area of 81 m², which is a domestic pool, while the
# named community pools start around 330 m². Pool carries the highest category
# weight in the model, so without this gate the Virginia ranking is decided by
# back gardens.
#
# The same gate is *not* applied to New York, where the identical problem
# exists (76% of NYC pool matches are under 250 m², median 21 m²) — fixing it
# there would move published New York results, which is a separate decision.
# See the README's known limitations.
#
# Every region added since gets it: suburban Washington, Oregon and California
# are mapped the same way, and the first Silicon Valley ranking put 41 m² and
# 69 m² "pools" among the top contributions.
_POOL_GATED = {**MIN_AREA_M2, "pool": 250.0}
MIN_AREA_M2_BY_REGION: dict[str, dict[SinkCat, float]] = {
    region: _POOL_GATED for region in ("nova", "seattle", "pdx", "svy", "la", "sac")
}


def min_area_for(region: str) -> dict[SinkCat, float]:
    """Area gates in force for a region."""
    return MIN_AREA_M2_BY_REGION.get(region, MIN_AREA_M2)


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
# center; the 1.1 is slack so a later radius tweak in the UI does not
# immediately run out of data.
SINK_PREFILTER_SLACK = 1.1


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def region_for(lat: float, lon: float) -> RegionName | None:
    """Assign a point to a region, or None if it is in neither.

    Order matters and is not arbitrary: the upstate bbox fully contains the nyc
    one, so nyc must be tested first for "upstate = the rest of NYS" to
    hold. No other bbox overlaps any other, so their order is free. Callers
    still need the boundary check separately; these are bounding boxes, and
    the nyc one reaches into New Jersey, the nova one into Maryland and West
    Virginia, and the West Coast ones across county lines.
    """
    for name in ("nyc", "upstate", "nova", "seattle", "pdx", "svy", "la", "sac"):
        if in_bbox(lat, lon, REGIONS[name]["bbox"]):
            return name  # type: ignore[return-value]
    return None
