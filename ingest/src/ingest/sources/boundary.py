"""Jurisdiction clips, used to narrow every source to its region.

Required, not optional: the nyc bbox in §3.1 extends across the Hudson into New
Jersey, and the nova bbox reaches into Maryland and West Virginia, so bbox
membership alone would pull in facilities from the wrong state entirely.

New York's regions clip to the state. Northern Virginia clips to seven named
jurisdictions instead: the cluster this region describes stops at the county
line, and half of Virginia is nowhere near it.
"""

from functools import lru_cache

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep

from ingest.config import (
    COUNTY_BOUNDARY_URL,
    NYS_BOUNDARY_URL,
    REGIONS,
    RegionName,
)
from ingest.sources.fetch import cached_get


@lru_cache(maxsize=4)
def _state_prepared(fips: str):
    path = cached_get(NYS_BOUNDARY_URL, "tl_2024_us_state.zip")
    states = gpd.read_file(path)
    match = states.loc[states["STATEFP"] == fips, "geometry"]
    if match.empty:
        raise RuntimeError(f"no state with FIPS {fips} in the TIGER state file")
    # prep() builds a spatial index over the polygon's edges; without it the
    # per-point test is O(edges) and these boundaries have ~100k of them.
    return prep(match.union_all())


@lru_cache(maxsize=8)
def _counties_prepared(state_fips: str, county_fips: tuple[str, ...]):
    path = cached_get(COUNTY_BOUNDARY_URL, "tl_2024_us_county.zip")
    counties = gpd.read_file(path)
    in_state = counties.loc[counties["STATEFP"] == state_fips]
    # FIPS codes, not names: Virginia's independent cities share their names
    # with the counties around them, so "Fairfax" is both 059 and 600.
    wanted = in_state.loc[in_state["COUNTYFP"].isin(county_fips)]
    missing = set(county_fips) - set(wanted["COUNTYFP"])
    if missing:
        raise RuntimeError(f"no county {sorted(missing)} in state {state_fips}")
    return prep(wanted.union_all())


@lru_cache(maxsize=16)
def _clip(region: RegionName):
    cfg = REGIONS[region]
    if cfg.get("clip") == "counties":
        return _counties_prepared(cfg["state_fips"], tuple(cfg["county_fips"]))
    return _state_prepared(cfg["state_fips"])


def in_region_boundary(lat: float, lon: float, region: RegionName) -> bool:
    """True if the point lies inside the region's clip polygon."""
    return _clip(region).contains(Point(lon, lat))


def county_codes(region: RegionName) -> list[str]:
    """County FIPS codes a region's ComStock table is built from."""
    return sorted(REGIONS[region].get("county_fips", ()))
