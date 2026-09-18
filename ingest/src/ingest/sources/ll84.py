"""NYC Local Law 84 energy disclosure, joined to sinks through PLUTO tax lots."""

import json
from collections.abc import Sequence
from functools import lru_cache
from urllib.parse import quote

from ingest.config import LL84_JOIN_M, LL84_URL
from ingest.sources.fetch import cached_get
from ingest.sources.measured import entry_from_kbtu, nearest
from ingest.sources.measured import number as _number

_FUEL_FIELDS = (
    "natural_gas_use_kbtu",
    "fuel_oil_1_use_kbtu",
    "fuel_oil_2_use_kbtu",
    "fuel_oil_4_use_kbtu",
    "fuel_oil_5_6_use_kbtu",
)
_STEAM_FIELD = "district_steam_use_kbtu"
_BBL_FIELD = "nyc_borough_block_and_lot"


def _normalise_bbl(raw: str) -> str:
    """BBLs appear as '1000160100' here and '1000160100.00000000' in PLUTO."""
    return str(raw).strip().split(".")[0].lstrip("0")


@lru_cache(maxsize=1)
def _by_bbl_cached(refresh: bool) -> dict[str, dict]:
    select = ",".join((_BBL_FIELD, _STEAM_FIELD, *_FUEL_FIELDS))
    url = f"{LL84_URL}?$select={quote(select)}&$limit=50000"
    rows = json.loads(cached_get(url, "ll84.json", refresh=refresh).read_text())

    out: dict[str, dict] = {}
    for row in rows:
        bbl = _normalise_bbl(row.get(_BBL_FIELD, ""))
        entry = _entry(row) if bbl else None
        if entry is None:
            continue
        # One BBL can appear several times (multiple buildings on a lot); keep
        # the largest reported consumption.
        if bbl not in out or entry["demand_kwh"] > out[bbl]["demand_kwh"]:
            out[bbl] = entry
    return out


def _entry(row: dict) -> dict | None:
    """One disclosure row as delivered heat, or None if it reports no heating."""
    return entry_from_kbtu(
        sum(_number(row.get(f)) for f in _FUEL_FIELDS), _number(row.get(_STEAM_FIELD))
    )


def by_bbl(*, refresh: bool = False) -> dict[str, dict]:
    return _by_bbl_cached(refresh)


def attach(rows: list[dict], lots: Sequence[dict], *, refresh: bool = False) -> dict[str, int]:
    """Replace estimates with LL84 fuel use where a tax lot matches within
    LL84_JOIN_M, in place; returns counts for the CLI summary."""
    stats = {"joined": 0, "steam_heated": 0, "candidates": len(rows)}
    fuels = by_bbl(refresh=refresh)
    if not lots or not fuels:
        return stats

    points = []
    for lot in lots:
        try:
            points.append(
                {
                    "lat": float(lot["latitude"]),
                    "lon": float(lot["longitude"]),
                    "bbl": str(lot["bbl"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    for row in rows:
        best = nearest(row, points, LL84_JOIN_M)
        entry = fuels.get(_normalise_bbl(best["bbl"])) if best else None
        if entry is None:
            continue

        row["steam_heated"] = entry["steam_heated"]
        if entry["steam_heated"]:
            stats["steam_heated"] += 1
            continue
        if entry["demand_kwh"] > 0:
            row["demand_kwh"] = entry["demand_kwh"]
            row["demand_source"] = "ll84_fuel"
            stats["joined"] += 1
    return stats
