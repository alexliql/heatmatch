"""What every measured-demand source has in common.

Four cities and one state publish building energy benchmarking. They differ in
field names, units and how a building is located, but not in what is done
with the numbers once they are read: thermal fuels become delivered heat,
district steam decides `steam_heated`, and the result is attached to the
nearest sink. That part lives here so each source module is only the part
that differs.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyproj import Geod

from ingest.config import BOILER_EFF, KBTU_TO_KWH

_GEOD = Geod(ellps="WGS84")


def number(raw: object) -> float:
    """A benchmarking cell as a float; blanks, text and negatives are zero."""
    if raw is None:
        return 0.0
    try:
        value = float(str(raw).replace(",", "").strip())
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0


def entry_from_kbtu(fuel_kbtu: float, steam_kbtu: float) -> dict | None:
    """One building's disclosure as delivered heat, or None if it reports none.

    Benchmarking reports fuel bought, not heat delivered. The engine prices
    heat and divides by boiler efficiency itself, so the fuel becomes heat
    here or the 1/0.85 is applied twice. District steam is already heat and
    is not added to demand at all: a building it heats has its heat, and
    `steam_heated` says so.
    """
    total = fuel_kbtu + steam_kbtu
    if total <= 0:
        return None
    return {
        "demand_kwh": fuel_kbtu * KBTU_TO_KWH * BOILER_EFF,
        "steam_heated": steam_kbtu > 0.5 * total,
    }


def attach_nearest(
    rows: list[dict],
    buildings: Sequence[dict],
    *,
    radius_m: float,
    source: str,
) -> dict[str, int]:
    """Give each sink the nearest disclosed building within `radius_m`.

    `buildings` carry `lat`, `lon`, `demand_kwh`, `steam_heated`. Mutates
    `rows` in place, as `ll84.attach` does. Where a sink is matched, the
    disclosure replaces whatever estimate it had; a disclosure of zero heat
    still marks steam heating but does not zero the demand.
    """
    stats = {"joined": 0, "steam_heated": 0, "candidates": len(rows)}
    if not buildings:
        return stats
    for row in rows:
        best: dict | None = None
        best_m = radius_m
        for b in buildings:
            # Cheap rejection before the geodesic: a degree is ~111 km.
            if abs(b["lat"] - row["lat"]) > 0.01 or abs(b["lon"] - row["lon"]) > 0.015:
                continue
            _, _, dist = _GEOD.inv(row["lon"], row["lat"], b["lon"], b["lat"])
            if dist <= best_m:
                best, best_m = b, dist
        if best is None:
            continue
        stats["joined"] += 1
        row["steam_heated"] = best["steam_heated"]
        if best["steam_heated"]:
            stats["steam_heated"] += 1
        if best["demand_kwh"] > 0:
            row["demand_kwh"] = best["demand_kwh"]
            row["demand_source"] = source
    return stats
