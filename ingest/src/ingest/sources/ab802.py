"""Measured heating demand from California's AB 802 benchmarking disclosure.

Assembly Bill 802 requires every commercial and multifamily building of
50,000 sq ft and up, statewide, to report annual energy use to the California
Energy Commission, which publishes it. One file covers the whole state, so one
module serves every California region; each is filtered to its own clip.

The published workbook carries fuels as separate fields — natural gas, fuel
oil, propane, district steam and district hot water, all in kBtu — and a
geocoded coordinate per building, so nothing has to be derived from an EUI and
no tax-lot join is needed. That was the open question when this was planned;
the answer is in the column list below.

The download is an ADA-formatted xlsx behind a dated path that changes with
each release. It is pinned here on purpose: a moved file is a build failure
to look at, not a silently different year.
"""

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

# Column headings as the workbook prints them. The header row is the third
# row; the first is a title and the second is blank.
HEADER_ROW = 2
LAT, LON = "Latitude", "Longitude"
FUEL_COLUMNS = ("Natural Gas Use (kBtu)", "Fuel Oil #2 Use (kBtu)", "Propane Use (kBtu)")
# Both are heat that arrives already made; either dominating means the
# building has its heat.
DISTRICT_COLUMNS = ("District Steam Use (kBtu)", "District Hot Water Use (kBtu)")
JOIN_M = 40.0

# California regions the file serves. Anything else gets nothing from here.
REGIONS_SERVED = frozenset({"svy", "la", "sac"})


@lru_cache(maxsize=1)
def _buildings_cached(refresh: bool) -> tuple[dict, ...]:
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


def buildings(*, refresh: bool = False) -> tuple[dict, ...]:
    return _buildings_cached(refresh)


def attach(rows: list[dict], region: RegionName, *, refresh: bool = False) -> dict[str, int]:
    """Replace estimates with disclosures for sinks in a California region.

    The statewide list is not pre-filtered by region: `attach_nearest`'s
    bounding-box rejection makes the whole-state scan cheap, and the sinks are
    already clipped to the region.
    """
    if region not in REGIONS_SERVED:
        return {"joined": 0, "steam_heated": 0, "candidates": 0}
    return attach_nearest(
        rows, buildings(refresh=refresh), radius_m=JOIN_M, source=AB802_SOURCE["id"]
    )
