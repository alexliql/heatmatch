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


@lru_cache(maxsize=4)
def _counties_prepared(fips: str, names: tuple[str, ...]):
    path = cached_get(COUNTY_BOUNDARY_URL, "tl_2024_us_county.zip")
    counties = gpd.read_file(path)
    in_state = counties.loc[counties["STATEFP"] == fips]
    # NAMELSAD, not NAME: Virginia's independent cities share their names with
    # the counties around them, so "Fairfax" matches both Fairfax County and
    # the City of Fairfax. Only the suffixed form is unambiguous.
    wanted = in_state.loc[in_state["NAMELSAD"].isin(names)]
    missing = set(names) - set(wanted["NAMELSAD"])
    if missing:
        raise RuntimeError(f"no county named {sorted(missing)} in state {fips}")
    return prep(wanted.union_all())


@lru_cache(maxsize=8)
def _clip(region: RegionName):
    cfg = REGIONS[region]
    names = cfg.get("jurisdictions")
    if names:
        return _counties_prepared(cfg["state_fips"], tuple(names))
    return _state_prepared(cfg["state_fips"])


def in_region_boundary(lat: float, lon: float, region: RegionName) -> bool:
    """True if the point lies inside the region's clip polygon."""
    return _clip(region).contains(Point(lon, lat))


def county_codes(region: RegionName, *, refresh: bool = False) -> list[str]:
    """County FIPS codes for a region's named jurisdictions.

    Read from TIGER rather than hardcoded: the file is already downloaded for
    the clip, and a hand-written table of Virginia independent-city codes is
    exactly the kind of thing that rots without anyone noticing.
    """
    cfg = REGIONS[region]
    names = cfg.get("jurisdictions")
    if not names:
        return []
    path = cached_get(COUNTY_BOUNDARY_URL, "tl_2024_us_county.zip", refresh=refresh)
    counties = gpd.read_file(path)
    match = counties.loc[
        (counties["STATEFP"] == cfg["state_fips"]) & (counties["NAMELSAD"].isin(names))
    ]
    missing = set(names) - set(match["NAMELSAD"])
    if missing:
        raise RuntimeError(f"no county named {sorted(missing)} in state {cfg['state_fips']}")
    return sorted(match["COUNTYFP"])
