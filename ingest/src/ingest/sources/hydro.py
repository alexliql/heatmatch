"""Water polygons, used to detect pipes that would cross open water.

§3.3 names NYC Open Data hydrography and USGS NHD. This uses OpenStreetMap via
Overpass instead, for three reasons: water only matters where a pipe might run,
so it can be fetched around the data centers exactly as sinks are; NHD's
statewide extract is hundreds of megabytes of which almost none is relevant;
and it keeps every layer under one licence (ODbL) and one fetch path.
"""

import json
from collections.abc import Sequence

from pyproj import Geod
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from ingest.config import (
    OVERPASS_MAX_RETRIES,
    OVERPASS_TIMEOUT_S,
    OVERPASS_URL,
    RegionName,
)
from ingest.sources.fetch import cached_post

_GEOD = Geod(ellps="WGS84")

# Anything smaller is a pond a pipe can be routed around without it changing
# the economics; keeping them would bloat the file for no signal.
MIN_WATER_AREA_M2 = 5000.0
# ~20 m at this latitude. Coastlines carry far more detail than a crossing test
# needs, and the file is downloaded by every visitor.
SIMPLIFY_DEG = 0.0002

_FILTERS = ['["natural"="water"]', '["waterway"="riverbank"]', '["landuse"="reservoir"]']


def _query(anchors: Sequence[tuple[float, float]], radius_m: float) -> str:
    coords = ",".join(f"{lat:.6f},{lon:.6f}" for lat, lon in anchors)
    around = f"(around:{radius_m:.0f},{coords})"
    parts = [f"{kind}{sel}{around};" for sel in _FILTERS for kind in ("way", "relation")]
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];(" + "".join(parts) + ");out geom tags;"


def _ring(geometry: list[dict]) -> Polygon | None:
    if len(geometry) < 3:
        return None
    poly = Polygon([(p["lon"], p["lat"]) for p in geometry])
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if (not poly.is_empty and poly.geom_type == "Polygon") else None


def _area_m2(poly: Polygon) -> float:
    area, _ = _GEOD.geometry_area_perimeter(poly)
    return abs(area)


def polygons(
    region: RegionName,
    anchors: Sequence[tuple[float, float]],
    radius_m: float,
    *,
    refresh: bool = False,
) -> list[Polygon]:
    """Water polygons within `radius_m` of any anchor."""
    if not anchors:
        return []

    body = cached_post(
        OVERPASS_URL,
        {"data": _query(anchors, radius_m)},
        subdir=f"osm/{region}",
        max_retries=OVERPASS_MAX_RETRIES,
        refresh=refresh,
    )

    polys: list[Polygon] = []
    for el in json.loads(body).get("elements", []):
        if el["type"] == "way":
            poly = _ring(el.get("geometry") or [])
            if poly is not None:
                polys.append(poly)
        else:
            for member in el.get("members", []):
                if member.get("role") == "inner":
                    continue
                poly = _ring(member.get("geometry") or [])
                if poly is not None:
                    polys.append(poly)

    # Merge first: rivers arrive as many adjoining ways, and each one alone can
    # fall under the area threshold that the whole river clearly passes.
    merged = unary_union([p for p in polys if p.is_valid]) if polys else None
    if merged is None or merged.is_empty:
        return []
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]

    out = []
    for p in parts:
        simple = p.simplify(SIMPLIFY_DEG, preserve_topology=True)
        if not simple.is_empty and _area_m2(simple) >= MIN_WATER_AREA_M2:
            out.append(simple)
    return out


def to_features(polys: list[Polygon]) -> list[dict]:
    return [
        {"type": "Feature", "geometry": mapping(p), "properties": {"kind": "water"}}
        for p in polys
    ]
