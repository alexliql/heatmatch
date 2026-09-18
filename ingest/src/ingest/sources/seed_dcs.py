"""Data centers seeded by hand, for regions the Atlas barely covers.

The IM3 Atlas is OpenStreetMap-derived, and OpenStreetMap's coverage of data
centers is uneven: 79 buildings in Silicon Valley, 10 in Los Angeles, 5 in
Sacramento. Where it is thin, building a county-parcel ingest to find the
missing sites is a data-collection project wearing an ingest module's clothes.
A cited list is the honest tool: each row is a real facility whose operator
publishes its location and floor area, with the URL that says so.

`manual/<region>_dcs.csv`, one file per region that needs one, columns:

    name, lat, lon, operator, density, sqft, source_url, source_date, note

`density` is what kind of building it is, and sets the W/sq ft applied to
`sqft`: a purpose-built hall is mostly white space; a downtown carrier hotel is
an office tower with a few floors of it. The result is `mw_source="seed_sqft"`,
graded `footprint_estimate` — a stated floor area is better than an
OpenStreetMap polygon, but it is still an area, not a capacity. A curated MW
row can lift it from there.

Seeds are also the supplement for Atlas-first regions where a spot-check
fails: Seattle's downtown carrier hotels are seeded because the Atlas maps the
Westin Building as an office, which it mostly is.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from ingest.config import (
    MAX_ESTIMATED_DC_MW,
    SEED_MW_PER_SQFT,
    RegionName,
    region_for,
)
from ingest.sources.boundary import in_region_boundary

MANUAL = Path(__file__).resolve().parents[3] / "manual"
SEED_DCS_SOURCE = {
    "id": "manual_seed_dcs",
    "url": "https://github.com/alexliql/heatmatch/tree/main/ingest/manual",
    "license": "CC0-1.0",
    "note": "Hand-seeded data center sites from operator pages; per-row provenance in each file.",
}


def _rows(region: RegionName) -> list[dict]:
    path = MANUAL / f"{region}_dcs.csv"
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def candidates(region: RegionName, *, refresh: bool = False) -> Iterator[dict]:
    """Yield seeded sites for `region`; nothing for regions without a file."""
    del refresh  # offline source
    for row in _rows(region):
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
            sqft = float(row["sqft"])
            per_sqft = SEED_MW_PER_SQFT[row["density"].strip()]
        except (KeyError, TypeError, ValueError):
            continue
        if sqft <= 0:
            continue
        # The same guard every source applies: a seeded coordinate can be
        # wrong, and a wrong one must not land in another region.
        if region_for(lat, lon) != region or not in_region_boundary(lat, lon, region):
            continue
        yield {
            "name": row["name"].strip(),
            "region": region,
            "lat": lat,
            "lon": lon,
            "mw": min(sqft * per_sqft, MAX_ESTIMATED_DC_MW[region]),
            "mw_source": "seed_sqft",
            "cooling": "unknown",
            "sources": [SEED_DCS_SOURCE["id"]],
        }
