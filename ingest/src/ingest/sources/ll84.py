"""NYC Local Law 84 energy disclosure (HEATMATCH.md §3.3).

Replaces the footprint guess with reported fuel use for buildings large enough
to be covered. Only heating fuels count: electricity is not what a heat network
displaces, and district steam means the building already has one.
"""

import json
from collections.abc import Sequence
from functools import lru_cache
from urllib.parse import quote

from pyproj import Geod

from ingest.config import KBTU_TO_KWH, LL84_JOIN_M, LL84_URL
from ingest.sources.fetch import cached_get

_GEOD = Geod(ellps="WGS84")

_FUEL_FIELDS = (
    "natural_gas_use_kbtu",
    "fuel_oil_1_use_kbtu",
    "fuel_oil_2_use_kbtu",
    "fuel_oil_4_use_kbtu",
    "fuel_oil_5_6_use_kbtu",
)
_STEAM_FIELD = "district_steam_use_kbtu"
_BBL_FIELD = "nyc_borough_block_and_lot"


def _number(value) -> float:
    """LL84 uses 'Not Available' and blanks for missing readings."""
    try:
        n = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
    return n if n > 0 else 0.0


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
        if not bbl:
            continue
        fuel_kbtu = sum(_number(row.get(f)) for f in _FUEL_FIELDS)
        steam_kbtu = _number(row.get(_STEAM_FIELD))
        total = fuel_kbtu + steam_kbtu
        if total <= 0:
            continue
        # A building heated mostly by district steam already has its heat; §3.3
        # drops these from the dataset entirely.
        entry = {
            "demand_kwh": fuel_kbtu * KBTU_TO_KWH,
            "steam_heated": steam_kbtu > 0.5 * total,
        }
        # One BBL can appear several times (multiple buildings on a lot); keep
        # the largest reported consumption.
        if bbl not in out or entry["demand_kwh"] > out[bbl]["demand_kwh"]:
            out[bbl] = entry
    return out


def by_bbl(*, refresh: bool = False) -> dict[str, dict]:
    return _by_bbl_cached(refresh)


def attach(rows: list[dict], lots: Sequence[dict], *, refresh: bool = False) -> dict[str, int]:
    """Replace footprint estimates with LL84 fuel use where a lot matches.

    Mutates `rows` in place and returns counts for the CLI summary. A sink is
    matched to the nearest tax-lot centroid within LL84_JOIN_M (§3.3).
    """
    stats = {"joined": 0, "steam_heated": 0, "candidates": len(rows)}
    fuels = by_bbl(refresh=refresh)
    if not lots or not fuels:
        return stats

    points = []
    for lot in lots:
        try:
            points.append((float(lot["latitude"]), float(lot["longitude"]), str(lot["bbl"])))
        except (KeyError, TypeError, ValueError):
            continue

    for row in rows:
        best: tuple[float, str] | None = None
        for lat, lon, bbl in points:
            # Cheap degree-box reject before the geodesic call; at this latitude
            # 0.0006° is comfortably more than 40 m in both axes.
            if abs(lat - row["lat"]) > 0.0006 or abs(lon - row["lon"]) > 0.0008:
                continue
            _, _, dist = _GEOD.inv(lon, lat, row["lon"], row["lat"])
            if dist <= LL84_JOIN_M and (best is None or dist < best[0]):
                best = (dist, bbl)

        if best is None:
            continue
        entry = fuels.get(_normalise_bbl(best[1]))
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
