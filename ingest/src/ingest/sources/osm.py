"""Heat sinks from OpenStreetMap via the Overpass API (HEATMATCH.md §3.3).

Two details that are easy to get wrong and were verified against the live API:
the service returns 406 for a default requests/curl User-Agent, and `out geom`
is required rather than `out center` because the area gates and the footprint
demand estimate both need the polygon, not just its centre.

Queries are anchored on the data centers rather than on the region bbox. A bbox
query over NYC returned ~4400 sinks of which the pre-filter kept ~160, and the
same query over upstate — the rest of the state — did not return at all.
Overpass takes a list of coordinates in one `around` clause, so the whole
region costs one query per category regardless of how many sites it has.
"""

import json
from collections.abc import Iterator, Sequence

from pyproj import Geod
from shapely.geometry import Polygon

from ingest.config import (
    CATEGORY_DEFAULT_KWH,
    FLOORS_GUESS,
    INTENSITY_KWH_PER_M2,
    MIN_AREA_M2,
    NYC_ONLY_CATS,
    OVERPASS_FILTERS,
    OVERPASS_MAX_RETRIES,
    OVERPASS_SOURCE,
    OVERPASS_TIMEOUT_S,
    OVERPASS_URL,
    RegionName,
    SinkCat,
    region_for,
)
from ingest.sources.boundary import in_nys
from ingest.sources.fetch import cached_post

_GEOD = Geod(ellps="WGS84")

# Two OSM elements of the same category closer than this are treated as one
# building tagged twice (commonly a node inside its own way). Without this the
# same demand is counted more than once, which feeds straight into the score.
_DEDUPE_M = 50.0


def _query(cat: SinkCat, anchors: Sequence[tuple[float, float]], radius_m: float) -> str:
    """Build Overpass QL anchored on the data centers.

    `around` accepts a flat list of lat,lon pairs, so one clause covers every
    site in the region.

    Area-gated categories skip nodes entirely. A node has no footprint and so
    can never clear its gate, and for a selector as broad as `["office"]` the
    discarded nodes dominate the response — querying them turns a fast request
    into one that does not return.
    """
    coords = ",".join(f"{lat:.6f},{lon:.6f}" for lat, lon in anchors)
    around = f"(around:{radius_m:.0f},{coords})"
    kinds = ("way", "relation") if cat in MIN_AREA_M2 else ("node", "way", "relation")
    parts = [f"{kind}{sel}{around};" for sel in OVERPASS_FILTERS[cat] for kind in kinds]
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];(" + "".join(parts) + ");out geom tags;"


def _ring_area_m2(ring: list[dict]) -> float:
    """Geodesic area of a closed ring of {lat, lon} points."""
    if len(ring) < 3:
        return 0.0
    lons = [p["lon"] for p in ring]
    lats = [p["lat"] for p in ring]
    area, _ = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def _footprint(el: dict) -> tuple[float | None, float, float] | None:
    """Return (area_m2 or None, lat, lon) for an element, or None if unusable."""
    if el["type"] == "node":
        return None, el["lat"], el["lon"]

    if el["type"] == "way":
        ring = el.get("geometry") or []
        if len(ring) < 3:
            return None
        poly = Polygon([(p["lon"], p["lat"]) for p in ring])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        c = poly.centroid
        return _ring_area_m2(ring), c.y, c.x

    # Relations: sum the outer rings only. Inner rings (courtyards) are ignored
    # rather than subtracted — they are rare here and the demand estimate is
    # already an approximation.
    outers = [m.get("geometry") or [] for m in el.get("members", []) if m.get("role") != "inner"]
    outers = [r for r in outers if len(r) >= 3]
    if not outers:
        return None
    area = sum(_ring_area_m2(r) for r in outers)
    biggest = max(outers, key=_ring_area_m2)
    poly = Polygon([(p["lon"], p["lat"]) for p in biggest]).buffer(0)
    if poly.is_empty:
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
            _, _, dist = _GEOD.inv(k["lon"], k["lat"], row["lon"], row["lat"])
            if dist < _DEDUPE_M:
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

    for cat in OVERPASS_FILTERS:
        if region != "nyc" and cat in NYC_ONLY_CATS:
            continue
        body = cached_post(
            OVERPASS_URL,
            {"data": _query(cat, anchors, radius_m)},
            subdir=f"osm/{region}",
            max_retries=OVERPASS_MAX_RETRIES,
            refresh=refresh,
        )
        for el in json.loads(body).get("elements", []):
            place = _footprint(el)
            if place is None:
                continue
            area_m2, lat, lon = place

            # A gated category is defined on footprint area, so an element with
            # no footprint (a bare node) cannot qualify.
            gate = MIN_AREA_M2.get(cat)
            if gate is not None and (area_m2 is None or area_m2 < gate):
                continue
            if region_for(lat, lon) != region or not in_nys(lat, lon):
                continue

            tags = el.get("tags") or {}
            demand_kwh, demand_source = _demand(cat, area_m2, tags)
            rows.append(
                {
                    "name": tags.get("name") or f"Unnamed {cat.replace('_', ' ')}",
                    "region": region,
                    "lat": lat,
                    "lon": lon,
                    "cat": cat,
                    "demand_kwh": demand_kwh,
                    "demand_source": demand_source,
                    "steam_heated": False,  # needs LL84 (T8)
                    "sources": [OVERPASS_SOURCE["id"]],
                }
            )

    yield from _dedupe(rows)
