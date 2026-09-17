"""Steam and thermal-network zone tagging (§3.3)."""

from ingest.sources import zones


def test_manhattan_south_of_96th_is_in_the_steam_zone() -> None:
    # 33 Thomas Street and 60 Hudson Street, both well inside the approximation.
    assert zones.in_steam(40.7174, -74.0055)
    assert zones.in_steam(40.7205, -74.0075)


def test_outside_the_approximated_territory_is_not() -> None:
    assert not zones.in_steam(40.8100, -73.9450)  # Harlem, north of 96th
    assert not zones.in_steam(40.6782, -73.9442)  # Brooklyn
    assert not zones.in_steam(42.8864, -78.8784)  # Buffalo


def test_uten_is_empty_until_pilot_footprints_are_published() -> None:
    # The file ships as an empty FeatureCollection on purpose; nothing should
    # be tagged in_uten until real boundaries exist.
    assert not zones.in_uten(40.7174, -74.0055)


def test_tag_sets_both_flags() -> None:
    row = zones.tag({"lat": 40.7174, "lon": -74.0055})
    assert row["in_steam"] is True
    assert row["in_uten"] is False
