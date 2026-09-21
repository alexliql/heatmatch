"""LL84 fuel arithmetic and the tax-lot join."""

from ingest.config import KBTU_TO_KWH
from ingest.sources import ll84


def test_only_heating_fuels_count() -> None:
    # Electricity is not what a heat network displaces, so it is not in the
    # field list at all; gas and every fuel-oil grade are.
    assert "natural_gas_use_kbtu" in ll84._FUEL_FIELDS
    assert all(f"fuel_oil_{g}_use_kbtu" in ll84._FUEL_FIELDS for g in ("1", "2", "4"))
    assert not any("electricity" in f for f in ll84._FUEL_FIELDS)


def test_missing_readings_are_zero_not_errors() -> None:
    # LL84 writes "Not Available", blanks and negatives for missing readings.
    for bad in ("Not Available", "", None, "-5", "abc"):
        assert ll84._number(bad) == 0.0
    assert ll84._number("1,234.5") == 1234.5


def test_bbl_normalisation_matches_pluto_spelling() -> None:
    # LL84 writes 1000160100; PLUTO writes 1000160100.00000000.
    assert ll84._normalise_bbl("1000160100") == ll84._normalise_bbl("1000160100.00000000")


def test_kbtu_conversion() -> None:
    assert abs(1000 * KBTU_TO_KWH - 293.071) < 1e-3


def test_join_replaces_the_footprint_guess(monkeypatch) -> None:
    monkeypatch.setattr(
        ll84,
        "by_bbl",
        lambda refresh=False: {"1234": {"demand_kwh": 500_000.0, "steam_heated": False}},
    )
    rows = [
        {
            "lat": 40.7000,
            "lon": -74.0000,
            "demand_kwh": 1.0,
            "demand_source": "footprint_estimate",
            "steam_heated": False,
        }
    ]
    lots = [{"bbl": "1234", "latitude": "40.70001", "longitude": "-74.00001"}]

    stats = ll84.attach(rows, lots)
    assert stats["joined"] == 1
    assert rows[0]["demand_kwh"] == 500_000.0
    assert rows[0]["demand_source"] == "ll84_fuel"


def test_a_lot_beyond_the_join_radius_is_ignored(monkeypatch) -> None:
    monkeypatch.setattr(
        ll84,
        "by_bbl",
        lambda refresh=False: {"1234": {"demand_kwh": 500_000.0, "steam_heated": False}},
    )
    rows = [
        {
            "lat": 40.7000,
            "lon": -74.0000,
            "demand_kwh": 1.0,
            "demand_source": "footprint_estimate",
            "steam_heated": False,
        }
    ]
    # ~110 m north, well beyond the 40 m join.
    lots = [{"bbl": "1234", "latitude": "40.7010", "longitude": "-74.0000"}]

    assert ll84.attach(rows, lots)["joined"] == 0
    assert rows[0]["demand_source"] == "footprint_estimate"


def test_steam_heated_buildings_are_flagged_not_rewritten(monkeypatch) -> None:
    monkeypatch.setattr(
        ll84, "by_bbl", lambda refresh=False: {"1234": {"demand_kwh": 9.0, "steam_heated": True}}
    )
    rows = [
        {
            "lat": 40.7,
            "lon": -74.0,
            "demand_kwh": 1.0,
            "demand_source": "footprint_estimate",
            "steam_heated": False,
        }
    ]
    lots = [{"bbl": "1234", "latitude": "40.70001", "longitude": "-74.00001"}]

    stats = ll84.attach(rows, lots)
    # Flagged for the caller to drop; its demand is left alone because the
    # building's heat already comes from the steam system.
    assert rows[0]["steam_heated"] is True
    assert stats["steam_heated"] == 1
    assert stats["joined"] == 0


def test_fuel_bought_becomes_heat_delivered() -> None:
    """LL84 reports fuel input; the engine prices heat and divides by boiler
    efficiency itself. Converting here is what stops the 1/0.85 being applied
    twice — which it was, before this factor existed."""
    from ingest.config import BOILER_EFF

    entry = ll84._entry({"natural_gas_use_kbtu": "1000", "district_steam_use_kbtu": "0"})
    assert entry is not None
    assert entry["demand_kwh"] == 1000 * KBTU_TO_KWH * BOILER_EFF
    assert entry["demand_kwh"] < 1000 * KBTU_TO_KWH, "must be less than the fuel bought"
    assert entry["steam_heated"] is False


def test_a_row_with_no_heating_at_all_is_skipped() -> None:
    assert ll84._entry({"natural_gas_use_kbtu": "0", "district_steam_use_kbtu": ""}) is None
