"""Water polygons, for the pipe-crossing check. OpenStreetMap via Overpass
rather than NHD: fetched around the data centers like the sinks, one licence,
one fetch path."""

import json
from collections.abc import Sequence

from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from ingest.config import OVERPASS_MAX_RETRIES, OVERPASS_URL, RegionName
from ingest.sources.fetch import cached_post, overpass_ql
from ingest.util import GEOD, ring_polygon

# Smaller is a pond a pipe can route around.
MIN_WATER_AREA_M2 = 5000.0
# ~20 m; the file is downloaded by every visitor.
SIMPLIFY_DEG = 0.0002

_FILTERS = ['["natural"="water"]', '["waterway"="riverbank"]', '["landuse"="reservoir"]']


def _ring(geometry: list[dict]) -> Polygon | None:
    poly = ring_polygon(geometry)
    return poly if poly is not None and poly.geom_type == "Polygon" else None


def _area_m2(poly: Polygon) -> float:
    return abs(GEOD.geometry_area_perimeter(poly)[0])


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
        {"data": overpass_ql(_FILTERS, ("way", "relation"), anchors, radius_m)},
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

    # Merge first: a river arrives as many adjoining ways, each alone under
    # the area threshold.
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
        {"type": "Feature", "geometry": mapping(p), "properties": {"kind": "water"}} for p in polys
    ]
