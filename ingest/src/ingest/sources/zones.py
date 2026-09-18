"""Steam-territory and thermal-network polygons: hand-drawn GeoJSON in
`ingest/manual/`, since neither is published as geodata."""

import json
from functools import lru_cache

from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from ingest.util import MANUAL

# Every manual zone layer with its `kind`; one list so tagging and drawing
# cannot disagree. "steam" and "uten" affect scoring; the rest are only drawn.
# A region with no district heating still ships an empty file.
ZONE_FILES: tuple[tuple[str, str], ...] = (
    ("steam_territory.geojson", "steam"),  # Con Edison, Manhattan
    ("uten_pilots.geojson", "uten"),
    ("seattle_zones.geojson", "steam"),  # Enwave Seattle
    ("nova_zones.geojson", "nova"),
    ("pdx_zones.geojson", "pdx"),
    ("svy_zones.geojson", "svy"),
    ("la_zones.geojson", "la"),
    ("sac_zones.geojson", "sac"),
)


def _geoms(name: str) -> list:
    path = MANUAL / name
    if not path.exists():
        return []
    features = json.loads(path.read_text()).get("features", [])
    return [shape(f["geometry"]) for f in features if f.get("geometry")]


@lru_cache(maxsize=4)
def _zone_of_kind(kind: str):
    """The union of every zone file of one kind, prepared for point tests."""
    geoms = [g for name, k in ZONE_FILES if k == kind for g in _geoms(name)]
    return prep(unary_union(geoms)) if geoms else None


def in_steam(lat: float, lon: float) -> bool:
    """Inside any district-steam service area."""
    zone = _zone_of_kind("steam")
    return bool(zone and zone.contains(Point(lon, lat)))


def in_uten(lat: float, lon: float) -> bool:
    """Inside a utility thermal energy network pilot footprint."""
    zone = _zone_of_kind("uten")
    return bool(zone and zone.contains(Point(lon, lat)))


def tag(row: dict) -> dict:
    """Add `in_steam`/`in_uten` to a candidate row."""
    row["in_steam"] = in_steam(row["lat"], row["lon"])
    row["in_uten"] = in_uten(row["lat"], row["lon"])
    return row
