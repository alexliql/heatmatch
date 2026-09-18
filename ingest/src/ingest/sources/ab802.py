"""California's AB 802 benchmarking disclosure (buildings >= 50,000 sq ft,
statewide). The workbook carries fuels as separate kBtu fields and a geocode
per building. Its dated URL is pinned: a moved file is a build failure to
look at, not a silently different year."""

import math
from functools import lru_cache

import pandas as pd

from ingest.config import RegionName
from ingest.sources.fetch import cached_get
from ingest.sources.measured import attach_nearest, entry_from_kbtu, number

REPORTING_YEAR = "2024"
# The link on the programme page (energy.ca.gov/media/12019) resolves to this.
URL = "https://www.energy.ca.gov/sites/default/files/2025-10/2024_Download_ADA.xlsx"
AB802_SOURCE = {
    "id": "ab802",
    "url": "https://www.energy.ca.gov/programs-and-topics/programs/building-energy-benchmarking-program",
    "license": "public-domain",
    "note": (
        f"California Energy Commission, AB 802 Building Energy Benchmarking public disclosure, "
        f"reporting year {REPORTING_YEAR}; buildings >= 50,000 sq ft."
    ),
}

# The header is the third row; the first is a title and the second is blank.
HEADER_ROW = 2
LAT, LON = "Latitude", "Longitude"
FUEL_COLUMNS = ("Natural Gas Use (kBtu)", "Fuel Oil #2 Use (kBtu)", "Propane Use (kBtu)")
DISTRICT_COLUMNS = ("District Steam Use (kBtu)", "District Hot Water Use (kBtu)")
JOIN_M = 40.0

# California regions the file serves. Anything else gets nothing from here.
REGIONS_SERVED = frozenset({"svy", "la", "sac"})


@lru_cache(maxsize=1)
def buildings(*, refresh: bool = False) -> tuple[dict, ...]:
    path = cached_get(URL, f"ab802_{REPORTING_YEAR}.xlsx", refresh=refresh)
    df = pd.read_excel(path, header=HEADER_ROW)
    out = []
    for row in df.to_dict("records"):
        try:
            lat, lon = float(row[LAT]), float(row[LON])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isnan(lat) or math.isnan(lon):
            continue
        entry = entry_from_kbtu(
            sum(number(row.get(c)) for c in FUEL_COLUMNS),
            sum(number(row.get(c)) for c in DISTRICT_COLUMNS),
        )
        if entry is None:
            continue
        out.append({"lat": lat, "lon": lon, **entry})
    return tuple(out)


def attach(rows: list[dict], region: RegionName, *, refresh: bool = False) -> dict[str, int]:
    """Replace estimates with disclosures for sinks in a California region."""
    if region not in REGIONS_SERVED:
        return {"joined": 0, "steam_heated": 0, "candidates": 0}
    return attach_nearest(
        rows, buildings(refresh=refresh), radius_m=JOIN_M, source=AB802_SOURCE["id"]
    )
