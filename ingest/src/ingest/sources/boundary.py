"""New York State boundary, used to clip both sources.

Required, not optional: the nyc bbox in §3.1 extends across the Hudson into
New Jersey, so bbox membership alone would pull in Jersey City facilities.
"""

from functools import lru_cache

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep

from ingest.config import NYS_BOUNDARY_URL
from ingest.sources.fetch import cached_get


@lru_cache(maxsize=1)
def _nys_prepared():
    path = cached_get(NYS_BOUNDARY_URL, "tl_2024_us_state.zip")
    states = gpd.read_file(path)
    ny = states.loc[states["STUSPS"] == "NY", "geometry"]
    if ny.empty:
        raise RuntimeError("no NY feature in the TIGER state file")
    # prep() builds a spatial index over the polygon's edges; without it the
    # per-point test is O(edges) and this boundary has ~100k of them.
    return prep(ny.union_all())


def in_nys(lat: float, lon: float) -> bool:
    """True if the point lies inside New York State."""
    return _nys_prepared().contains(Point(lon, lat))
