"""Small helpers every source module wants: geodesic distance, the manual
data directory, and the commented-CSV format the hand-curated files use."""

import csv
from pathlib import Path

from pyproj import Geod
from shapely.geometry import Polygon

GEOD = Geod(ellps="WGS84")
MANUAL = Path(__file__).resolve().parents[2] / "manual"


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic distance in metres."""
    return GEOD.inv(lon1, lat1, lon2, lat2)[2]


def read_manual_csv(name: str) -> list[dict]:
    """Rows of `manual/<name>`, skipping blank and `#` comment lines, which
    DictReader has no support for. Missing file: no rows."""
    path = MANUAL / name
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def ring_polygon(ring: list[dict]) -> Polygon | None:
    """A polygon from an Overpass `geometry` ring of {lat, lon} points, repaired
    with buffer(0) if invalid; None if there is nothing usable."""
    if len(ring) < 3:
        return None
    poly = Polygon([(p["lon"], p["lat"]) for p in ring])
    if not poly.is_valid:
        poly = poly.buffer(0)
    return None if poly.is_empty else poly
