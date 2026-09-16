"""Overpass element handling: query shape, geometry, gates, dedupe."""

import pytest

from ingest.config import MIN_AREA_M2
from ingest.sources.osm import _dedupe, _footprint, _query

# A ~100 m square near Times Square, as Overpass returns it under `out geom`.
_SQUARE = [
    {"lat": 40.7580, "lon": -73.9855},
    {"lat": 40.7580, "lon": -73.9843},
    {"lat": 40.7589, "lon": -73.9843},
    {"lat": 40.7589, "lon": -73.9855},
    {"lat": 40.7580, "lon": -73.9855},
]


def test_query_uses_out_geom_not_out_center() -> None:
    # `out center` omits the polygon, and without it neither the area gates nor
    # the footprint demand estimate can be computed.
    assert "out geom tags;" in _query("hospital", (-74.3, 40.45, -73.65, 40.95))


def test_query_orders_bbox_south_west_north_east() -> None:
    # Overpass takes (S,W,N,E) while config stores (min_lon,min_lat,max_lon,max_lat);
    # swapping them silently queries the wrong part of the planet.
    assert "(40.45,-74.3,40.95,-73.65)" in _query("hospital", (-74.3, 40.45, -73.65, 40.95))


@pytest.mark.parametrize("cat", sorted(MIN_AREA_M2))
def test_gated_categories_do_not_query_nodes(cat: str) -> None:
    # A node has no footprint and can never clear an area gate; for a selector
    # as broad as ["office"] the wasted nodes make the request time out.
    assert "node[" not in _query(cat, (-74.3, 40.45, -73.65, 40.95))


def test_ungated_categories_still_query_nodes() -> None:
    assert "node[" in _query("hospital", (-74.3, 40.45, -73.65, 40.95))


def test_way_footprint_area_and_centroid() -> None:
    area, lat, lon = _footprint({"type": "way", "geometry": _SQUARE})
    assert area == pytest.approx(10_000, rel=0.15)  # ~100 m x ~100 m
    assert lat == pytest.approx(40.7584, abs=1e-3)
    assert lon == pytest.approx(-73.9849, abs=1e-3)


def test_node_has_position_but_no_area() -> None:
    area, lat, lon = _footprint({"type": "node", "lat": 40.7, "lon": -74.0})
    assert area is None and (lat, lon) == (40.7, -74.0)


def test_degenerate_way_is_dropped() -> None:
    assert _footprint({"type": "way", "geometry": _SQUARE[:2]}) is None


def test_relation_sums_outer_rings_and_ignores_inner() -> None:
    rel = {
        "type": "relation",
        "members": [
            {"role": "outer", "geometry": _SQUARE},
            {"role": "inner", "geometry": _SQUARE},
        ],
    }
    area, _, _ = _footprint(rel)
    assert area == pytest.approx(10_000, rel=0.15)


def test_dedupe_keeps_larger_demand_of_colocated_pair() -> None:
    rows = [
        {"cat": "hospital", "lat": 40.75, "lon": -73.98, "demand_kwh": 100.0, "name": "node"},
        {"cat": "hospital", "lat": 40.7501, "lon": -73.98, "demand_kwh": 900.0, "name": "way"},
    ]
    kept = _dedupe(rows)
    assert [r["name"] for r in kept] == ["way"]


def test_dedupe_keeps_different_categories_at_one_location() -> None:
    rows = [
        {"cat": "hospital", "lat": 40.75, "lon": -73.98, "demand_kwh": 100.0, "name": "h"},
        {"cat": "office", "lat": 40.75, "lon": -73.98, "demand_kwh": 100.0, "name": "o"},
    ]
    assert len(_dedupe(rows)) == 2
