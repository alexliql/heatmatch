"""Delivered heat is one number that two codebases must agree on.

`config.BOILER_EFF` converts measured fuel into heat on the way in;
`Econ.boiler_eff` converts heat back into fuel avoided on the way out. If they
drift, every measured sink is silently mis-priced by the ratio.
"""

import json
from pathlib import Path

import pytest

from ingest.config import BOILER_EFF, EXISTING_HEAT_PUMP_COP
from ingest.merge import sinks

WEIGHTS_RS = Path(__file__).resolve().parents[2] / "core" / "heatmatch-core" / "src" / "weights.rs"
ECON_RS = Path(__file__).resolve().parents[2] / "core" / "heatmatch-core" / "src" / "econ.rs"


def test_boiler_efficiency_matches_the_engine_default() -> None:
    # Read the Rust source rather than the wasm package: the package is a
    # build artefact that may not exist, and the default is one literal.
    src = WEIGHTS_RS.read_text()
    assert f"boiler_eff: {BOILER_EFF}," in src, (
        f"config.BOILER_EFF={BOILER_EFF} but weights.rs sets a different default"
    )


def test_heat_pump_cop_matches_the_engine_constant() -> None:
    src = ECON_RS.read_text()
    assert f"EXISTING_HEAT_PUMP_COP: f32 = {EXISTING_HEAT_PUMP_COP};" in src


# --- near-zero fallback ----------------------------------------------------

TABLE = {"LargeOffice": {"kwh_per_m2": 40.0, "counterfactual": "electric_resistance"}}


def _measured(kwh_per_m2: float, area_m2: float = 20_000.0, source: str = "ll84_fuel") -> dict:
    return {
        "cat": "office",
        "area_m2": area_m2,
        "demand_kwh": kwh_per_m2 * area_m2,
        "demand_source": source,
    }


def test_a_measured_building_with_almost_no_fuel_is_handed_to_the_model() -> None:
    """Almost no gas usually means electric heat, not no heat."""
    row = _measured(2.0)
    assert sinks._measured_near_zero(row, TABLE)


def test_a_measured_building_that_burns_fuel_keeps_its_measurement() -> None:
    assert not sinks._measured_near_zero(_measured(60.0), TABLE)


@pytest.mark.parametrize("source", ["footprint_estimate", "category_default", "comstock_modeled"])
def test_only_measurements_are_second_guessed(source: str) -> None:
    assert not sinks._measured_near_zero(_measured(2.0, source=source), TABLE)


def test_fallback_needs_a_model_that_disagrees_substantially() -> None:
    # Near-zero measured, but the model says the type barely heats either.
    faint = {"LargeOffice": {"kwh_per_m2": 12.0, "counterfactual": "gas"}}
    assert not sinks._measured_near_zero(_measured(2.0), faint)


# --- counterfactual ----------------------------------------------------------


def test_a_measured_gas_burner_is_gas_whatever_the_stock_majority_says() -> None:
    assert sinks._counterfactual(_measured(60.0), TABLE) == "gas"


def test_an_overruled_measurement_takes_the_stock_majority() -> None:
    # As the fallback leaves it: the model's number, the model's source, and
    # a note saying a measurement was set aside.
    row = {
        **_measured(2.0, source="comstock_modeled"),
        "demand_note": "measured_fuel_near_zero",
    }
    assert sinks._counterfactual(row, TABLE) == "electric_resistance"


@pytest.mark.parametrize("source", ["footprint_estimate", "category_default"])
def test_an_estimate_says_nothing_about_the_heating_system(source: str) -> None:
    """So it stays gas — even where the stock majority for its type is not.

    This is what keeps New York's 170 footprint-estimated sinks priced exactly
    as they were: an estimate of demand is not an observation of equipment.
    """
    assert sinks._counterfactual(_measured(40.0, source=source), TABLE) == "gas"


def test_a_modelled_sink_takes_the_stock_majority() -> None:
    assert sinks._counterfactual(_measured(40.0, source="comstock_modeled"), TABLE) == (
        "electric_resistance"
    )


def test_a_sink_the_model_cannot_place_stays_gas() -> None:
    """Which is what New York's estimates have always implicitly been."""
    pool = {
        "cat": "pool",
        "area_m2": 400.0,
        "demand_kwh": 1.0,
        "demand_source": "footprint_estimate",
    }
    assert sinks._counterfactual(pool, TABLE) == "gas"


def test_the_shipped_new_york_bundle_is_all_gas_where_untouched() -> None:
    """Every New York sink prices as before unless the fallback fired on it."""
    data = Path(__file__).resolve().parents[2] / "data"
    files = sorted(data.glob("sinks.*.geojson"))
    if not files:
        pytest.skip("no bundle built")
    feats = json.loads(files[-1].read_text())["features"]
    for f in feats:
        p = f["properties"]
        if p["region"] in ("nyc", "upstate") and p.get("demand_note") != "measured_fuel_near_zero":
            assert p.get("counterfactual", "gas") == "gas", p["id"]
