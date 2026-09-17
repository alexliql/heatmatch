"""Steam-territory and thermal-network polygons (HEATMATCH.md §3.3).

Both come from hand-maintained GeoJSON in `ingest/manual/`, because neither is
published as geodata. They are approximations and say so in their own
properties; the README lists them among the known limitations.
"""

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep

MANUAL = Path(__file__).resolve().parents[3] / "manual"


@lru_cache(maxsize=4)
def _zone(name: str):
    path = MANUAL / name
    if not path.exists():
        return None
    features = json.loads(path.read_text()).get("features", [])
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        return None
    from shapely.ops import unary_union

    return prep(unary_union(geoms))


def in_steam(lat: float, lon: float) -> bool:
    """Inside the district-steam service area."""
    zone = _zone("steam_territory.geojson")
    return bool(zone and zone.contains(Point(lon, lat)))


def in_uten(lat: float, lon: float) -> bool:
    """Inside a utility thermal energy network pilot footprint."""
    zone = _zone("uten_pilots.geojson")
    return bool(zone and zone.contains(Point(lon, lat)))


def tag(row: dict) -> dict:
    """Add `in_steam`/`in_uten` to a candidate row."""
    row["in_steam"] = in_steam(row["lat"], row["lon"])
    row["in_uten"] = in_uten(row["lat"], row["lon"])
    return row
