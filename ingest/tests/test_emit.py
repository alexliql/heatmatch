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
        id=f"dc_nyc_{idx:04d}", name=name, region="nyc", lat=lat, lon=lon,
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
        "id", "name", "region", "in_steam", "in_uten", "sources",
        "mw", "mw_source", "mw_confidence", "campus_id", "cooling",
    }
    # Derived from mw_source, never passed in, so the two cannot disagree.
    assert props["mw_confidence"] == "footprint_estimate"


def _row(name: str, region: str, lat: float, lon: float) -> dict:
    return {"name": name, "region": region, "lat": lat, "lon": lon, "mw": 1.0,
            "mw_source": "atlas_default", "cooling": "unknown", "sources": ["t"]}


def _only_pnnl(monkeypatch, rows: list[dict]) -> None:
    from ingest.sources import nys_parcels, pluto, pnnl

    def none(region, refresh=False):
        return iter(())

    monkeypatch.setattr(pluto, "candidates", none)
    monkeypatch.setattr(nys_parcels, "candidates", none)
    monkeypatch.setattr(
        pnnl, "candidates", lambda region, refresh=False: iter([r for r in rows if r["region"] == region])
    )


def test_ids_are_assigned_by_position_not_source_order(monkeypatch) -> None:
    """Reordering the upstream rows must not renumber the ids."""
    rows = [_row("B", "nyc", 40.8, -73.9), _row("A", "nyc", 40.7, -74.0)]

    _only_pnnl(monkeypatch, rows)
    forward = {d.id: d.name for d in build_dcs(["nyc"])[0]}

    _only_pnnl(monkeypatch, list(rows[::-1]))
    reversed_ = {d.id: d.name for d in build_dcs(["nyc"])[0]}

    assert forward == reversed_ == {"dc_nyc_0000": "A", "dc_nyc_0001": "B"}


def test_adding_a_region_does_not_renumber_another(monkeypatch) -> None:
    """The reason ids carry their region.

    Virginia sorts south of every New York site, so a single global counter
    would have pushed every existing `dc_00NN` along by the Virginia count.
    """
    ny = [_row("B", "nyc", 40.8, -73.9), _row("A", "nyc", 40.7, -74.0)]

    _only_pnnl(monkeypatch, ny)
    before = {d.id: d.name for d in build_dcs(["nyc"])[0]}

    va = [_row("Ashburn", "nova", 39.04, -77.49), _row("Sterling", "nova", 39.00, -77.40)]
    _only_pnnl(monkeypatch, ny + va)
    after = {d.id: d.name for d in build_dcs(["nyc", "nova"])[0]}

    assert all(after[i] == name for i, name in before.items()), "New York ids moved"
    assert {"dc_nova_0000", "dc_nova_1000"} & set(after) == {"dc_nova_0000"}
    assert sorted(i for i in after if i.startswith("dc_nova")) == ["dc_nova_0000", "dc_nova_0001"]


def test_collection_bytes_are_stable_across_runs() -> None:
    dcs = [_dc(0, 40.7, -74.0, "A"), _dc(1, 40.8, -73.9, "B")]
    first = emit.canonical(
        {"type": "FeatureCollection", "features": [emit.to_feature(d) for d in dcs]}
    )
    second = emit.canonical(
        {"type": "FeatureCollection", "features": [emit.to_feature(d) for d in dcs]}
    )
    assert first == second
    assert json.loads(first)["features"][0]["properties"]["id"] == "dc_nyc_0000"
