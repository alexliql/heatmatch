"""Curated Northern Virginia capacities: matching, splitting and trust.

The shipped CSV is read as a fixture too, because a row that matches nothing
is silently useless and a row claiming a confidence it has not earned is worse
than no row at all.
"""

import pytest

from ingest.sources import curated_mw as nova_mw


def _dc(name: str, mw: float, region: str = "nova") -> dict:
    return {
        "name": name,
        "region": region,
        "lat": 38.75,
        "lon": -77.47,
        "mw": mw,
        "mw_source": "atlas_sqft",
        "cooling": "unknown",
        "sources": ["im3_datacenter_atlas"],
    }


@pytest.fixture
def one_row(monkeypatch):
    def use(rows):
        monkeypatch.setattr(nova_mw, "_rows", lambda region: rows)

    return use


def _row(**kw) -> dict:
    return {
        "match_key": "QTS Manassas",
        "mw": 190.0,
        "scope": "campus",
        "mw_confidence": "reported",
        "source_url": "https://example.invalid/",
        "source_date": "2026-09-17",
        "note": "",
        **kw,
    }


def test_a_campus_total_is_split_pro_rata_by_footprint(one_row) -> None:
    """The published total is the total; footprints decide only the split."""
    one_row([_row()])
    dcs = [_dc("QTS Manassas DC1", 30.0), _dc("QTS Manassas DC5", 60.0)]
    nova_mw.apply(dcs, "nova")

    assert sum(d["mw"] for d in dcs) == pytest.approx(190.0)
    # 30:60 in, so 1:2 out.
    assert dcs[0]["mw"] == pytest.approx(190 / 3)
    assert dcs[1]["mw"] == pytest.approx(380 / 3)


def test_a_building_row_sets_that_building_outright(one_row) -> None:
    one_row([_row(match_key="Iron Mountain VA-1", mw=12.4, scope="building")])
    dcs = [_dc("Iron Mountain VA-1", 5.0), _dc("Iron Mountain VA-2", 40.0)]
    nova_mw.apply(dcs, "nova")

    assert dcs[0]["mw"] == pytest.approx(12.4)
    assert dcs[1]["mw"] == pytest.approx(40.0), "an unmatched building is untouched"


def test_matching_ignores_case_and_punctuation(one_row) -> None:
    one_row([_row(match_key="iron mountain va 1", mw=12.4, scope="building")])
    dcs = [_dc("Iron Mountain VA-1", 5.0)]
    nova_mw.apply(dcs, "nova")
    assert dcs[0]["mw"] == pytest.approx(12.4)


def test_a_curated_row_records_its_campus_and_its_source(one_row) -> None:
    one_row([_row()])
    dcs = [_dc("QTS Manassas DC1", 30.0)]
    nova_mw.apply(dcs, "nova")
    assert dcs[0]["campus_id"] == "camp_qts_manassas"
    assert nova_mw.CURATED_MW_SOURCE["id"] in dcs[0]["sources"]


def test_an_unverified_row_is_used_but_not_trusted(one_row) -> None:
    """The distinction the whole confidence model rests on.

    A figure found by an automated pass is better than a footprint guess, so
    its value is taken — but nobody has read the source, so it must not claim
    to be a reported capacity.
    """
    one_row([_row(note="UNVERIFIED — found by a research pass")])
    dcs = [_dc("QTS Manassas DC1", 30.0)]
    nova_mw.apply(dcs, "nova")

    assert dcs[0]["mw"] == pytest.approx(190.0), "the value is still used"
    assert dcs[0]["mw_source"] == "parcel_estimate", "but not as a reported one"


def test_a_verified_row_keeps_its_stated_confidence(one_row) -> None:
    one_row([_row(mw_confidence="filed", note="Read the PWC staff report, p14.")])
    dcs = [_dc("QTS Manassas DC1", 30.0)]
    nova_mw.apply(dcs, "nova")
    assert dcs[0]["mw_source"] == "filed"


def test_other_regions_are_never_touched(one_row) -> None:
    one_row([_row(match_key="Data Center")])
    dcs = [_dc("Some Data Center", 5.0, region="nyc")]
    nova_mw.apply(dcs, "nova")
    assert dcs[0]["mw"] == pytest.approx(5.0)
    assert dcs[0]["mw_source"] == "atlas_sqft"


def test_an_unmatched_row_is_counted_not_silently_dropped(one_row) -> None:
    one_row([_row(match_key="Nowhere Data Halls")])
    stats = nova_mw.apply([_dc("QTS Manassas DC1", 30.0)], "nova")
    assert stats == {"rows": 1, "buildings": 0, "unmatched": 1}


# --- the shipped file -----------------------------------------------------


def test_every_shipped_row_carries_a_source_url() -> None:
    """The file's own rule: no URL, no row."""
    for region in ("nova", "ca", "wa", "or", "seattle", "pdx", "svy", "la", "sac"):
        for row in nova_mw._rows(region):
            assert row["source_url"].startswith("http"), (region, row["match_key"])
            assert row["source_date"], (region, row["match_key"])
            assert row["mw"] > 0, (region, row["match_key"])
            assert row["mw_confidence"] in ("reported", "filed"), (region, row["match_key"])
