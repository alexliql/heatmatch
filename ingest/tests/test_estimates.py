"""Estimation rules: MW from footprint, demand from footprint, area gates."""

import pytest

from ingest.config import (
    CATEGORY_DEFAULT_KWH,
    DEFAULT_DC_MW,
    FLOORS_GUESS,
    INTENSITY_KWH_PER_M2,
    MW_PER_SQFT,
    region_for,
)
from ingest.sources.osm import _demand, _floors


def test_region_for_prefers_nyc_over_containing_upstate_bbox() -> None:
    # The upstate bbox contains the nyc one; without ordering, every NYC
    # feature would be emitted twice.
    assert region_for(40.7128, -74.0060) == "nyc"
    assert region_for(42.8864, -78.8784) == "upstate"
    assert region_for(34.0522, -118.2437) is None


def test_mw_from_sqft_matches_75w_per_sqft() -> None:
    assert 70_000 * MW_PER_SQFT == pytest.approx(5.25)


def test_default_mw_used_when_footprint_missing() -> None:
    # The Atlas `type=point` rows have no sqft; they must still yield mw > 0,
    # since the schema rejects zero and the engine divides by supply.
    assert DEFAULT_DC_MW > 0


def test_demand_uses_footprint_when_area_known() -> None:
    demand, source = _demand("office", 1000.0, {"building:levels": "10"})
    assert source == "footprint_estimate"
    assert demand == pytest.approx(1000.0 * 10 * INTENSITY_KWH_PER_M2["office"])


def test_demand_falls_back_to_category_default_without_area() -> None:
    demand, source = _demand("hospital", None, {})
    assert source == "category_default"
    assert demand == CATEGORY_DEFAULT_KWH["hospital"]


def test_zero_area_does_not_produce_zero_demand() -> None:
    # demand_kwh has a gt=0 constraint; a degenerate polygon must not slip
    # through as a valid sink with no demand.
    demand, source = _demand("pool", 0.0, {})
    assert source == "category_default"
    assert demand > 0


@pytest.mark.parametrize("raw,expected", [("5", 5.0), ("3;4", 3.0), (None, None), ("abc", None), ("0", None)])
def test_floors_parsing(raw: str | None, expected: float | None) -> None:
    tags = {} if raw is None else {"building:levels": raw}
    assert _floors(tags, "office") == (expected if expected else FLOORS_GUESS["office"])
