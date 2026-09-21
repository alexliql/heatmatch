"""Heat sinks from OpenStreetMap via the Overpass API, queried around the
data centers rather than over the region bbox: a bbox query over NYC returned
~4400 sinks of which the pre-filter kept ~160, and over upstate it timed out.
Overpass returns 406 for a default User-Agent."""

import json
from collections.abc import Iterator, Sequence

from ingest.config import (
    CATEGORY_DEFAULT_KWH,
    FLOORS_GUESS,
    INTENSITY_KWH_PER_M2,
    MIN_AREA_M2,
    MULTIFAMILY_REGIONS,
    OVERPASS_FILTERS,
    OVERPASS_MAX_RETRIES,
    OVERPASS_SOURCE,
    OVERPASS_URL,
    RegionName,
    SinkCat,
    min_area_for,
)
from ingest.sources.boundary import in_region
from ingest.sources.fetch import cached_post, overpass_ql
from ingest.util import GEOD, distance_m, ring_polygon

# Same-category elements closer than this are one building tagged twice
# (commonly a node inside its own way).
_DEDUPE_M = 50.0


def _query(
    cat: SinkCat,
    anchors: Sequence[tuple[float, float]],
    radius_m: float,
    gates: dict[SinkCat, float] | None = None,
) -> str:
    """Overpass QL for one category. Area-gated categories skip nodes: a node
    has no footprint to clear the gate, and for `["office"]` the discarded
    nodes would dominate the response."""
    gates = gates if gates is not None else MIN_AREA_M2
    kinds = ("way", "relation") if cat in gates else ("node", "way", "relation")
    return overpass_ql(OVERPASS_FILTERS[cat], kinds, anchors, radius_m)


def _ring_area_m2(ring: list[dict]) -> float:
    """Geodesic area of a closed ring of {lat, lon} points."""
    if len(ring) < 3:
        return 0.0
    lons = [p["lon"] for p in ring]
    lats = [p["lat"] for p in ring]
    area, _ = GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def _footprint(el: dict) -> tuple[float | None, float, float] | None:
    """Return (area_m2 or None, lat, lon) for an element, or None if unusable."""
    if el["type"] == "node":
        return None, el["lat"], el["lon"]

    if el["type"] == "way":
        ring = el.get("geometry") or []
        poly = ring_polygon(ring)
        if poly is None:
            return None
        return _ring_area_m2(ring), poly.centroid.y, poly.centroid.x

    # Relations: sum the outer rings; courtyards are rare and ignored.
    outers = [m.get("geometry") or [] for m in el.get("members", []) if m.get("role") != "inner"]
    outers = [r for r in outers if len(r) >= 3]
    if not outers:
        return None
    area = sum(_ring_area_m2(r) for r in outers)
    poly = ring_polygon(max(outers, key=_ring_area_m2))
    if poly is None:
        return None
    return area, poly.centroid.y, poly.centroid.x


def _floors(tags: dict, cat: SinkCat) -> float:
    raw = tags.get("building:levels")
    try:
        levels = float(str(raw).split(";")[0])
        if levels > 0:
            return levels
    except (TypeError, ValueError):
        pass
    return FLOORS_GUESS[cat]


def _demand(cat: SinkCat, area_m2: float | None, tags: dict) -> tuple[float, str]:
    if area_m2 is None or area_m2 <= 0:
        return CATEGORY_DEFAULT_KWH[cat], "category_default"
    return area_m2 * _floors(tags, cat) * INTENSITY_KWH_PER_M2[cat], "footprint_estimate"


def _dedupe(rows: list[dict]) -> list[dict]:
    """Drop same-category near-duplicates, keeping the larger demand."""
    kept: list[dict] = []
    for row in sorted(rows, key=lambda r: -r["demand_kwh"]):
        dup = False
        for k in kept:
            if k["cat"] != row["cat"]:
                continue
            if distance_m(k["lat"], k["lon"], row["lat"], row["lon"]) < _DEDUPE_M:
                dup = True
                break
        if not dup:
            kept.append(row)
    return kept


def candidates(
    region: RegionName,
    anchors: Sequence[tuple[float, float]],
    radius_m: float,
    *,
    refresh: bool = False,
) -> Iterator[dict]:
    """Yield raw sink candidates near `anchors`, one Overpass query per category."""
    if not anchors:
        return
    rows: list[dict] = []

    gates = min_area_for(region)

    for cat in OVERPASS_FILTERS:
        if cat == "residential_multifamily" and region not in MULTIFAMILY_REGIONS:
            continue
        body = cached_post(
            OVERPASS_URL,
            {"data": _query(cat, anchors, radius_m, gates)},
            subdir=f"osm/{region}",
            max_retries=OVERPASS_MAX_RETRIES,
            refresh=refresh,
        )
        for el in json.loads(body).get("elements", []):
            place = _footprint(el)
            if place is None:
                continue
            area_m2, lat, lon = place

            gate = gates.get(cat)
            if gate is not None and (area_m2 is None or area_m2 < gate):
                continue
            if not in_region(lat, lon, region):
                continue

            tags = el.get("tags") or {}
            demand_kwh, demand_source = _demand(cat, area_m2, tags)
            floors = _floors(tags, cat) if area_m2 else None
            rows.append(
                {
                    "name": tags.get("name") or f"Unnamed {cat.replace('_', ' ')}",
                    "region": region,
                    "lat": lat,
                    "lon": lon,
                    "cat": cat,
                    "demand_kwh": demand_kwh,
                    "demand_source": demand_source,
                    # Footprint and floor area, for regions with a demand model.
                    "area_m2": area_m2,
                    "area_source": "osm" if area_m2 else "none",
                    "floor_area_m2": area_m2 * floors if area_m2 else None,
                    "steam_heated": False,  # set by the measured-demand joins
                    "sources": [OVERPASS_SOURCE["id"]],
                }
            )

    yield from _dedupe(rows)
