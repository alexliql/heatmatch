"""Measured heating demand from Seattle's Building Energy Benchmarking.

Seattle requires buildings of 20,000 sq ft and up to report annual energy use
by fuel, and publishes it (`data.seattle.gov`, dataset `teqw-tu6e`). Unlike
New York's LL84 the rows carry their own coordinates, so the join is a plain
nearest-point one with no tax-lot step in between.

District steam is a real fuel here — Enwave Seattle serves downtown — and the
region keeps steam-heated sinks rather than dropping them, so a steam column
that would end a building's candidacy in New York only labels it here.
"""

import json
from functools import lru_cache
from urllib.parse import quote

from ingest.config import RegionName
from ingest.sources.fetch import cached_get
from ingest.sources.measured import attach_nearest, entry_from_kbtu, number

DATASET = "teqw-tu6e"
URL = f"https://data.seattle.gov/resource/{DATASET}.json"
SEATTLE_BENCH_SOURCE = {
    "id": "seattle_bench",
    "url": f"https://data.seattle.gov/d/{DATASET}",
    "license": "public-domain",
    "note": "City of Seattle Building Energy Benchmarking, latest reported year; buildings >= 20,000 sq ft.",
}

# The most recent year with a full reporting cycle behind it. The newest year
# in the dataset is still filling in when this runs.
DATA_YEAR = "2024"
# Benchmarking points are address geocodes; sink points are footprint
# centroids. Same as LL84's tax-lot join.
JOIN_M = 40.0

_FIELDS = (
    "latitude",
    "longitude",
    "naturalgas_kbtu",
    "steamuse_kbtu",
    "propertygfatotal",
)


@lru_cache(maxsize=1)
def _buildings_cached(refresh: bool) -> tuple[dict, ...]:
    select = ",".join(_FIELDS)
    where = quote(f"datayear='{DATA_YEAR}'")
    url = f"{URL}?$select={quote(select)}&$where={where}&$limit=50000"
    rows = json.loads(
        cached_get(url, f"seattle_bench_{DATA_YEAR}.json", refresh=refresh).read_text()
    )

    out = []
    for row in rows:
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = entry_from_kbtu(
            number(row.get("naturalgas_kbtu")), number(row.get("steamuse_kbtu"))
        )
        if entry is None:
            continue
        out.append({"lat": lat, "lon": lon, **entry})
    return tuple(out)


def buildings(*, refresh: bool = False) -> tuple[dict, ...]:
    return _buildings_cached(refresh)


def attach(rows: list[dict], region: RegionName, *, refresh: bool = False) -> dict[str, int]:
    """Replace estimates with disclosures for sinks inside Seattle's programme."""
    if region != "seattle":
        return {"joined": 0, "steam_heated": 0, "candidates": 0}
    return attach_nearest(
        rows, buildings(refresh=refresh), radius_m=JOIN_M, source=SEATTLE_BENCH_SOURCE["id"]
    )
