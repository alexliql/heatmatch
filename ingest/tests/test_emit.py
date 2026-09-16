"""Output determinism and id stability (HEATMATCH.md §3.2).

The filename embeds a content hash and CI compares it against the bytes on
disk, so any nondeterminism here turns into a red build rather than a subtle
data drift.
"""

import json

from ingest.merge import emit
from ingest.merge.datacenters import build as build_dcs
from ingest.schema import DataCenter


def _dc(idx: int, lat: float, lon: float, name: str) -> DataCenter:
    return DataCenter(
        id=f"dc_{idx:04d}", name=name, region="nyc", lat=lat, lon=lon,
        mw=1.0, mw_source="atlas_default", sources=["test"],
    )


def test_canonical_is_key_order_independent() -> None:
    a = emit.canonical({"type": "FeatureCollection", "features": []})
    b = emit.canonical({"features": [], "type": "FeatureCollection"})
    assert a == b


def test_feature_has_lon_lat_order_and_six_decimals() -> None:
    feature = emit.to_feature(_dc(1, 40.71284999, -74.00601234, "X"))
    assert feature["geometry"]["coordinates"] == [-74.006012, 40.712850]
    # lat/lon live in geometry only; duplicating them into properties would let
    # the two disagree after rounding.
    assert "lat" not in feature["properties"] and "lon" not in feature["properties"]


def test_properties_match_the_schema_contract() -> None:
    props = emit.to_feature(_dc(1, 40.7, -74.0, "X"))["properties"]
    assert set(props) == {
        "id", "name", "region", "in_steam", "in_uten", "sources", "mw", "mw_source", "cooling",
    }


def test_ids_are_assigned_by_position_not_source_order(monkeypatch) -> None:
    """Reordering the upstream rows must not renumber the ids."""
    rows = [
        {"name": "B", "region": "nyc", "lat": 40.8, "lon": -73.9, "mw": 1.0,
         "mw_source": "atlas_default", "cooling": "unknown", "sources": ["t"]},
        {"name": "A", "region": "nyc", "lat": 40.7, "lon": -74.0, "mw": 2.0,
         "mw_source": "atlas_default", "cooling": "unknown", "sources": ["t"]},
    ]
    from ingest.sources import pnnl

    monkeypatch.setattr(pnnl, "candidates", lambda region, refresh=False: iter(rows))
    forward = {d.id: d.name for d in build_dcs(["nyc"])}

    monkeypatch.setattr(pnnl, "candidates", lambda region, refresh=False: iter(rows[::-1]))
    reversed_ = {d.id: d.name for d in build_dcs(["nyc"])}

    assert forward == reversed_ == {"dc_0000": "A", "dc_0001": "B"}


def test_collection_bytes_are_stable_across_runs() -> None:
    dcs = [_dc(0, 40.7, -74.0, "A"), _dc(1, 40.8, -73.9, "B")]
    first = emit.canonical(
        {"type": "FeatureCollection", "features": [emit.to_feature(d) for d in dcs]}
    )
    second = emit.canonical(
        {"type": "FeatureCollection", "features": [emit.to_feature(d) for d in dcs]}
    )
    assert first == second
    assert json.loads(first)["features"][0]["properties"]["id"] == "dc_0000"
