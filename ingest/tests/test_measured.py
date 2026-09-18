"""The arithmetic and the join every benchmarking source shares."""

import pytest

from ingest.config import BOILER_EFF, KBTU_TO_KWH
from ingest.sources import measured, seattle_bench


def test_fuel_bought_becomes_heat_delivered() -> None:
    entry = measured.entry_from_kbtu(1000.0, 0.0)
    assert entry == {"demand_kwh": 1000 * KBTU_TO_KWH * BOILER_EFF, "steam_heated": False}


def test_steam_marks_but_does_not_add() -> None:
    """District steam is already heat, and a building it heats has its heat."""
    entry = measured.entry_from_kbtu(1000.0, 3000.0)
    assert entry["steam_heated"] is True
    assert entry["demand_kwh"] == 1000 * KBTU_TO_KWH * BOILER_EFF


def test_a_building_reporting_nothing_is_none() -> None:
    assert measured.entry_from_kbtu(0.0, 0.0) is None


@pytest.mark.parametrize(
    "raw,want", [("1,234.5", 1234.5), ("", 0.0), (None, 0.0), ("-5", 0.0), ("abc", 0.0)]
)
def test_cells_are_read_leniently(raw, want) -> None:
    assert measured.number(raw) == want


def _sink(lat: float, lon: float) -> dict:
    return {
        "lat": lat,
        "lon": lon,
        "demand_kwh": 1.0,
        "demand_source": "footprint_estimate",
        "steam_heated": False,
    }


def test_the_nearest_building_within_radius_wins() -> None:
    sink = _sink(47.6144, -122.3389)
    # ~30 m east and ~200 m north.
    near = {"lat": 47.6144, "lon": -122.3385, "demand_kwh": 500.0, "steam_heated": False}
    far = {"lat": 47.6162, "lon": -122.3389, "demand_kwh": 900.0, "steam_heated": True}
    stats = measured.attach_nearest([sink], [far, near], radius_m=40.0, source="seattle_bench")
    assert stats["joined"] == 1
    assert sink["demand_kwh"] == 500.0 and sink["demand_source"] == "seattle_bench"
    assert sink["steam_heated"] is False


def test_nothing_within_radius_leaves_the_estimate_alone() -> None:
    sink = _sink(47.6144, -122.3389)
    far = {"lat": 47.6162, "lon": -122.3389, "demand_kwh": 900.0, "steam_heated": False}
    stats = measured.attach_nearest([sink], [far], radius_m=40.0, source="seattle_bench")
    assert stats["joined"] == 0
    assert sink["demand_source"] == "footprint_estimate"


def test_seattle_bench_only_serves_seattle() -> None:
    assert seattle_bench.attach([_sink(47.6, -122.3)], "pdx") == {
        "joined": 0,
        "steam_heated": 0,
        "candidates": 0,
    }
