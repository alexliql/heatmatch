"""Overpass element handling: query shape, geometry, gates, dedupe."""

import pytest

from ingest.config import FLOORS_GUESS, MIN_AREA_M2, min_area_for
from ingest.sources.osm import _dedupe, _footprint, _query

ANCHORS = [(40.7128, -74.0060), (40.75, -73.99)]

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
    assert "out geom tags;" in _query("hospital", ANCHORS, 1430.0)


def test_query_is_anchored_on_the_data_centers() -> None:
    # One `around` clause carries every site, so a region costs one query per
    # category however many data centers it has.
    q = _query("hospital", ANCHORS, 1430.0)
    assert "(around:1430,40.712800,-74.006000,40.750000,-73.990000)" in q
    assert q.count("around:") == 3  # node, way, relation — one selector


def test_query_with_no_anchors_is_not_sent() -> None:
    from ingest.sources.osm import candidates

    assert list(candidates("upstate", [], 1000.0)) == []


@pytest.mark.parametrize("cat", sorted(MIN_AREA_M2))
def test_gated_categories_do_not_query_nodes(cat: str) -> None:
    # A node has no footprint and can never clear an area gate; for a selector
    # as broad as ["office"] the wasted nodes make the request time out.
    assert "node[" not in _query(cat, ANCHORS, 1430.0)


def test_ungated_categories_still_query_nodes() -> None:
    assert "node[" in _query("hospital", ANCHORS, 1430.0)


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


def test_virginia_gates_out_back_garden_pools() -> None:
    """Pool carries the highest category weight, so junk there decides the map.

    Suburban OpenStreetMap coverage in Northern Virginia includes domestic
    pools — 544 of 588 matches were unnamed with a median area of 81 m2, while
    the named community pools start around 330 m2.
    """
    for region in ("nova", "seattle", "pdx", "svy", "la", "sac"):
        assert min_area_for(region)["pool"] == 250.0, region
    # New York has the same problem but is deliberately left alone: changing it
    # would move already-published results.
    assert "pool" not in min_area_for("nyc")
    assert "pool" not in min_area_for("upstate")
    # The other gates carry over rather than being replaced wholesale.
    assert min_area_for("nova")["office"] == min_area_for("nyc")["office"]


def test_a_gated_category_does_not_ask_overpass_for_nodes() -> None:
    """A node has no footprint, so it can never clear a gate — and for a broad
    selector the discarded nodes are most of the response."""
    anchors = [(39.0, -77.4)]
    assert "node" not in _query("pool", anchors, 3000.0, min_area_for("nova"))
    # Ungated elsewhere, where a pool mapped as a point is still worth having.
    assert "node" in _query("pool", anchors, 3000.0, min_area_for("nyc"))


def test_a_polygon_sink_carries_its_floor_area() -> None:
    """`area_m2` is the footprint OpenStreetMap draws; `floor_area_m2` is what
    a per-square-metre intensity wants. Storeys come from `building:levels`."""
    from ingest.sources.osm import _floors

    assert _floors({"building:levels": "28"}, "office") == 28.0
    # No tag: the category's guess, which for an office is several storeys.
    assert _floors({}, "office") == FLOORS_GUESS["office"] > 1.0
    # A malformed tag falls back rather than failing.
    assert _floors({"building:levels": "many"}, "school") == FLOORS_GUESS["school"]
