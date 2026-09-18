"""Cross-source reconciliation of data center candidates (§3.3)."""

from ingest.merge.dedupe import merge


def _row(name, lat, lon, mw, source, mw_source="atlas_sqft"):
    return {
        "name": name,
        "region": "nyc",
        "lat": lat,
        "lon": lon,
        "mw": mw,
        "mw_source": mw_source,
        "cooling": "unknown",
        "sources": [source],
    }


def test_same_site_from_two_sources_collapses_and_unions_provenance() -> None:
    rows = merge(
        [
            _row("Telehouse Teleport", 40.6068, -74.1754, 5.2, "im3_datacenter_atlas"),
            _row("Telehouse", 40.6068, -74.1755, 12.0, "nyc_pluto", "pluto_estimate"),
        ]
    )
    assert len(rows) == 1
    assert sorted(rows[0]["sources"]) == ["im3_datacenter_atlas", "nyc_pluto"]


def test_the_curated_source_wins_identity_and_capacity() -> None:
    # PLUTO's floor-area estimate is larger, but the Atlas is a real
    # measurement of a real facility; a bigger guess must not displace it.
    rows = merge(
        [
            _row("Telehouse Teleport", 40.6068, -74.1754, 5.2, "im3_datacenter_atlas"),
            _row("SOME HOLDINGS LLC", 40.6068, -74.1755, 25.0, "nyc_pluto", "pluto_estimate"),
        ]
    )
    assert rows[0]["name"] == "Telehouse Teleport"
    assert rows[0]["mw"] == 5.2
    assert rows[0]["mw_source"] == "atlas_sqft"


def test_distant_sites_are_kept_apart_even_with_identical_names() -> None:
    rows = merge(
        [
            _row("Verizon New York Inc.", 40.70, -74.00, 2.0, "nyc_pluto"),
            _row("Verizon New York Inc.", 40.75, -73.90, 1.0, "nyc_pluto"),
        ]
    )
    assert len(rows) == 2


def test_nearby_sites_with_unrelated_names_are_not_merged() -> None:
    # Within 75 m but plainly different buildings.
    rows = merge(
        [
            _row("Equinix NY9", 40.7000, -74.0000, 3.0, "im3_datacenter_atlas"),
            _row("Brooklyn Friends School", 40.7001, -74.0001, 3.0, "nyc_pluto"),
        ]
    )
    assert len(rows) == 2


def test_an_unnamed_neighbour_is_assumed_to_be_the_same_site() -> None:
    # §3.3: an empty name cannot contradict, so position decides.
    rows = merge(
        [
            _row("Equinix NY9", 40.7000, -74.0000, 3.0, "im3_datacenter_atlas"),
            _row("", 40.7001, -74.0000, 1.0, "nyc_pluto"),
        ]
    )
    assert len(rows) == 1


def test_merge_is_order_independent() -> None:
    a = _row("Telehouse Teleport", 40.6068, -74.1754, 5.2, "im3_datacenter_atlas")
    b = _row("Telehouse", 40.6068, -74.1755, 12.0, "nyc_pluto", "pluto_estimate")
    assert merge([a, b])[0]["name"] == merge([b, a])[0]["name"]
