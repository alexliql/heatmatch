"""Data centers seeded by hand from operator pages, for regions the
OpenStreetMap-derived Atlas barely covers (10 buildings in Los Angeles, 5 in
Sacramento). `manual/<region>_dcs.csv` columns:

    name, lat, lon, operator, density, sqft, source_url, source_date, note

`density` (purpose_built | carrier_hotel) sets the W/sq ft applied to `sqft`.
The result is `mw_source="seed_sqft"`, graded `footprint_estimate`: a stated
area is still an area, not a capacity. A curated MW row can lift it.
"""

from collections.abc import Iterator

from ingest.config import MAX_ESTIMATED_DC_MW, SEED_MW_PER_SQFT, RegionName
from ingest.sources.boundary import in_region
from ingest.util import read_manual_csv

SEED_DCS_SOURCE = {
    "id": "manual_seed_dcs",
    "url": "https://github.com/alexliql/heatmatch/tree/main/ingest/manual",
    "license": "CC0-1.0",
    "note": "Hand-seeded data center sites from operator pages; per-row provenance in each file.",
}


def _rows(region: RegionName) -> list[dict]:
    return read_manual_csv(f"{region}_dcs.csv")


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
        # A seeded coordinate can be wrong, and must not land in another region.
        if not in_region(lat, lon, region):
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
