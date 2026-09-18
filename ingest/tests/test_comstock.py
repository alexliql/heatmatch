"""ComStock-derived demand: the mapping rules and the sanity of the shipped table.

The download itself is never exercised — `conftest.py` fails any test that
tries the network. What is exercised is every decision made about the data
after it lands, plus a read of the committed `derived/va_intensity.json` so a
bad rebuild cannot be committed unnoticed.
"""

import json
from pathlib import Path

import pytest

from ingest.config import COMSTOCK_PROFILE_TYPE_BY_CAT, COMSTOCK_RELEASE
from ingest.sources import comstock

DERIVED = Path(__file__).resolve().parents[1] / "derived" / "va_intensity.json"

# A minimal stand-in for the real table.
TABLE = {
    "MediumOffice": {"kwh_per_m2": 20.0, "monthly": [1 / 12] * 12, "counterfactual": "gas"},
    "LargeOffice": {
        "kwh_per_m2": 40.0,
        "monthly": [1 / 12] * 12,
        "counterfactual": "electric_resistance",
    },
    "PrimarySchool": {"kwh_per_m2": 80.0, "monthly": [1 / 12] * 12, "counterfactual": "gas"},
}


def test_gisjoin_pads_the_way_nhgis_does() -> None:
    # Loudoun County is FIPS 51107, but NHGIS writes it G5101070.
    assert comstock._gisjoin("51", "107") == "G5101070"
    assert comstock._gisjoin("51", "013") == "G5100130"


@pytest.mark.parametrize(
    "area_m2,expected",
    [(20_000.0, "LargeOffice"), (10_000.0, "MediumOffice"), (3_000.0, "MediumOffice")],
)
def test_offices_are_split_by_floor_area(area_m2: float, expected: str) -> None:
    assert comstock.comstock_type("office", area_m2) == expected


def test_a_sink_with_no_area_cannot_be_modelled() -> None:
    # No area, no intensity to multiply: the caller must fall back.
    assert comstock.comstock_type("office", None) is None
    assert comstock.demand_kwh("office", None, TABLE) is None
    assert comstock.demand_kwh("school", 0.0, TABLE) is None


def test_a_category_comstock_does_not_model_falls_through() -> None:
    """A pool is not commercial floor space, and ComStock has no type for it."""
    assert comstock.comstock_type("pool", 500.0) is None
    assert comstock.demand_kwh("pool", 500.0, TABLE) is None
    # Hospital maps to a type, but that type is absent from a table built from
    # too few samples — the fall-through must handle that too.
    assert comstock.comstock_type("hospital", 5_000.0) == "Hospital"
    assert comstock.demand_kwh("hospital", 5_000.0, TABLE) is None


def test_demand_is_intensity_times_area_and_labelled_modelled() -> None:
    assert comstock.demand_kwh("school", 6_000.0, TABLE) == (480_000.0, "comstock_modeled")


def test_profiles_cover_only_modelled_categories() -> None:
    profiles = comstock.profiles_for_region(TABLE)
    assert sorted(profiles) == ["office", "school"]
    # Categories the table cannot speak to are absent, not zero-filled: the
    # engine fills them from its built-in shapes.
    assert "hotel" not in profiles and "pool" not in profiles


# --- the committed table --------------------------------------------------


@pytest.fixture(scope="module")
def shipped() -> dict:
    if not DERIVED.exists():
        pytest.skip("derived/va_intensity.json not built yet")
    return json.loads(DERIVED.read_text())


def test_shipped_table_matches_the_pinned_release(shipped: dict) -> None:
    """A silent release bump would move every Virginia demand figure."""
    assert shipped["release"] == COMSTOCK_RELEASE
    assert shipped["climate_zone"] == "4A"


def test_every_shipped_profile_is_a_distribution(shipped: dict) -> None:
    """The engine rejects a profile that is not, so catch it here instead."""
    for name, entry in shipped["by_type"].items():
        monthly = entry["monthly"]
        assert len(monthly) == 12, name
        assert all(v >= 0 for v in monthly), name
        assert abs(sum(monthly) - 1.0) <= 1e-6, f"{name} sums to {sum(monthly)}"


def test_every_category_needing_a_profile_has_one(shipped: dict) -> None:
    for cat, building_type in COMSTOCK_PROFILE_TYPE_BY_CAT.items():
        assert building_type in shipped["by_type"], f"{cat} -> {building_type} missing"


def test_shipped_intensities_are_physically_plausible(shipped: dict) -> None:
    """Loose bounds: this catches a unit error, not a modelling disagreement.

    Delivered heat, so the ceiling is generous — a restaurant delivers a lot of
    heat per square metre — and the floor is zero-exclusive because a type
    delivering nothing would mean the columns moved.
    """
    for name, entry in shipped["by_type"].items():
        kwh = entry["kwh_per_m2"]
        assert 1.0 < kwh < 600.0, f"{name} at {kwh} kWh/m2 looks like a unit error"
        assert entry["samples"] >= 30, name
        # Delivered heat includes everything fuel-only did and more, so it can
        # never be the smaller figure.
        assert kwh >= entry["kwh_per_m2_fuel_only"], name
        assert entry["counterfactual"] in ("gas", "electric_resistance", "heat_pump"), name


def test_shipped_table_records_its_basis(shipped: dict) -> None:
    """The basis a number was computed on belongs in the file next to it."""
    basis = shipped["basis"]
    for key in ("quantity", "combustion", "electric_heating", "counterfactual", "monthly"):
        assert basis[key], key
    assert "delivered heat" in basis["quantity"]


def test_office_intensity_in_4a_is_in_range(shipped: dict) -> None:
    """Delivered-heat sanity for the one region shipped so far. The fuel-only
    figure was 10 kWh/m2; delivered is roughly four times that, because half
    the stock is resistance-heated and the fuel columns never saw it."""
    if shipped["climate_zone"] != "4A":
        pytest.skip("range is for climate zone 4A")
    large = shipped["by_type"]["LargeOffice"]
    assert 30.0 <= large["kwh_per_m2"] <= 150.0, large["kwh_per_m2"]
    assert large["counterfactual"] == "electric_resistance"


def test_winter_outweighs_summer_in_every_shipped_profile(shipped: dict) -> None:
    """A heating profile that is not winter-peaked means the months are wrong."""
    for name, entry in shipped["by_type"].items():
        monthly = entry["monthly"]
        winter = monthly[0] + monthly[1] + monthly[10] + monthly[11]
        summer = monthly[5] + monthly[6] + monthly[7] + monthly[8]
        assert winter > summer, f"{name}: winter {winter:.3f} <= summer {summer:.3f}"
