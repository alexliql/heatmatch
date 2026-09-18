"""Jurisdiction clips: every bbox crosses a state or county line, so bbox
membership alone would pull in the wrong state. New York clips to the state,
the other regions to their counties."""

from functools import lru_cache

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep

from ingest.config import COUNTY_BOUNDARY_URL, NYS_BOUNDARY_URL, REGIONS, RegionName, region_for
from ingest.sources.fetch import cached_get


@lru_cache(maxsize=4)
def _state_prepared(fips: str):
    path = cached_get(NYS_BOUNDARY_URL, "tl_2024_us_state.zip")
    states = gpd.read_file(path)
    match = states.loc[states["STATEFP"] == fips, "geometry"]
    if match.empty:
        raise RuntimeError(f"no state with FIPS {fips} in the TIGER state file")
    # prep() indexes the ~100k edges; without it each point test is O(edges).
    return prep(match.union_all())


@lru_cache(maxsize=8)
def _counties_prepared(state_fips: str, county_fips: tuple[str, ...]):
    path = cached_get(COUNTY_BOUNDARY_URL, "tl_2024_us_county.zip")
    counties = gpd.read_file(path)
    in_state = counties.loc[counties["STATEFP"] == state_fips]
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


def in_region(lat: float, lon: float, region: RegionName) -> bool:
    """The guard every source applies: the point's bbox region is this one,
    and it is inside the clip. The bbox test runs first because the clip is
    the expensive step."""
    return region_for(lat, lon) == region and in_region_boundary(lat, lon, region)


def county_codes(region: RegionName) -> list[str]:
    """County FIPS codes a region's ComStock table is built from."""
    return sorted(REGIONS[region].get("county_fips", ()))
