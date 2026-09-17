"""Upstate data center candidates from NYS parcel data (HEATMATCH.md §3.3).

The NYS GIS Clearinghouse publishes statewide parcels as a multi-gigabyte
download with no public query API, which is more than this pipeline can justify
for a handful of sites. Upstate coverage therefore rests on the Atlas, which
already carries 14 New York facilities outside the city, plus the curated list
below for sites it misses.

Each entry is a real facility with a published location; `manual/` is the place
to add more without touching code.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from ingest.config import RegionName, region_for
from ingest.sources.boundary import in_nys

MANUAL = Path(__file__).resolve().parents[3] / "manual"
PARCELS_SOURCE = {
    "id": "manual_upstate",
    "url": "https://github.com/alexliql/heatmatch/blob/main/ingest/manual/upstate_sites.csv",
    "license": "CC0-1.0",
    "note": "Hand-curated upstate data center sites; see the file for per-row provenance.",
}


def candidates(region: RegionName, *, refresh: bool = False) -> Iterator[dict]:
    """Yield curated upstate sites. NYC is covered by PLUTO and the Atlas."""
    del refresh  # nothing is downloaded
    if region != "upstate":
        return

    path = MANUAL / "upstate_sites.csv"
    if not path.exists():
        return

    for row in csv.DictReader(path.open()):
        if row.get("name", "").startswith("#") or not row.get("lat"):
            continue
        try:
            lat, lon, mw = float(row["lat"]), float(row["lon"]), float(row["mw"])
        except (KeyError, ValueError):
            continue
        if mw <= 0 or region_for(lat, lon) != "upstate" or not in_nys(lat, lon):
            continue

        yield {
            "name": row["name"].strip(),
            "region": "upstate",
            "lat": lat,
            "lon": lon,
            "mw": mw,
            "mw_source": "manual",
            "cooling": (row.get("cooling") or "unknown").strip() or "unknown",
            "sources": [PARCELS_SOURCE["id"]],
        }
