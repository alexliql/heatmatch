"""Seeded data centers: density, area, and the guard against a wrong coordinate."""

import pytest

from ingest.config import MAX_ESTIMATED_DC_MW, MW_PER_SQFT, NOVA_MW_PER_SQFT
from ingest.sources import boundary, seed_dcs


@pytest.fixture
def seeds(monkeypatch):
    def use(rows):
        monkeypatch.setattr(seed_dcs, "_rows", lambda region: rows)

    return use


@pytest.fixture(autouse=True)
def _inside_region(monkeypatch):
    # The clip needs TIGER; tests never fetch. Everything is "inside".
    monkeypatch.setattr(boundary, "in_region_boundary", lambda lat, lon, region: True)


def _row(**kw) -> dict:
    return {
        "name": "Westin Building Exchange",
        "lat": "47.6144",
        "lon": "-122.3389",
        "operator": "Clise",
        "density": "carrier_hotel",
        "sqft": "400400",
        "source_url": "https://example.invalid/",
        "source_date": "2026-09-17",
        "note": "",
        **kw,
    }


def test_density_selects_the_watts_per_square_foot(seeds) -> None:
    """A downtown tower is mostly offices; a purpose-built hall is mostly
    white space. Same area, half the capacity."""
    seeds([_row(density="carrier_hotel"), _row(name="Hall", density="purpose_built")])
    tower, hall = list(seed_dcs.candidates("seattle"))
    assert tower["mw"] == pytest.approx(400400 * MW_PER_SQFT)
    assert hall["mw"] == pytest.approx(400400 * NOVA_MW_PER_SQFT)
    assert hall["mw"] == pytest.approx(tower["mw"] * 2)


def test_a_seed_is_an_area_estimate_not_a_capacity(seeds) -> None:
    seeds([_row()])
    (row,) = seed_dcs.candidates("seattle")
    assert row["mw_source"] == "seed_sqft"
    assert row["sources"] == [seed_dcs.SEED_DCS_SOURCE["id"]]


def test_the_regional_ceiling_still_applies(seeds) -> None:
    seeds([_row(density="purpose_built", sqft="5000000")])
    (row,) = seed_dcs.candidates("seattle")
    assert row["mw"] == MAX_ESTIMATED_DC_MW["seattle"]


@pytest.mark.parametrize("bad", [{"sqft": "0"}, {"sqft": "abc"}, {"density": "shed"}, {"lat": ""}])
def test_a_malformed_row_is_skipped_not_fatal(seeds, bad) -> None:
    seeds([_row(**bad), _row(name="Good")])
    names = [r["name"] for r in seed_dcs.candidates("seattle")]
    assert names == ["Good"]


def test_a_seed_in_the_wrong_region_is_dropped(seeds) -> None:
    """A typo in a coordinate must not land a Seattle site in Portland."""
    seeds([_row(lat="45.52", lon="-122.90")])  # Portland
    assert list(seed_dcs.candidates("seattle")) == []


def test_regions_without_a_seed_file_yield_nothing() -> None:
    assert list(seed_dcs.candidates("upstate")) == []


def test_every_shipped_seed_has_a_source_and_an_area() -> None:
    for region in ("seattle", "la", "sac"):
        for row in seed_dcs._rows(region):
            assert row["source_url"].startswith("http"), (region, row["name"])
            assert float(row["sqft"]) > 0, (region, row["name"])
            assert row["density"] in ("purpose_built", "carrier_hotel"), (region, row["name"])
