"""The NYS clip, exercised offline against a committed boundary fixture.

This matters more than it looks: the nyc bbox in §3.1 crosses the Hudson, so
without this filter Jersey City facilities enter the dataset as New York ones.
"""

import json
from pathlib import Path

import pytest
from shapely.geometry import shape
from shapely.prepared import prep

from ingest.sources import boundary

FIXTURE = Path(__file__).parent / "fixtures" / "nys_boundary_nyc_clip.geojson"


@pytest.fixture(autouse=True)
def _offline_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the real boundary from a fixture so tests never hit the network."""
    geom = shape(json.loads(FIXTURE.read_text())["features"][0]["geometry"])
    monkeypatch.setattr(boundary, "_nys_prepared", lambda: prep(geom))


@pytest.mark.parametrize(
    "name,lat,lon,expected",
    [
        ("33 Thomas Street, Manhattan", 40.7174, -74.0055, True),
        ("Telehouse Teleport, Staten Island", 40.6035, -74.1876, True),
        ("Jersey City, NJ", 40.7178, -74.0431, False),
        ("Hoboken, NJ", 40.7440, -74.0324, False),
        ("Newark, NJ", 40.7357, -74.1724, False),
    ],
)
def test_in_nys_separates_new_york_from_new_jersey(
    name: str, lat: float, lon: float, expected: bool
) -> None:
    assert boundary.in_nys(lat, lon) is expected, name
