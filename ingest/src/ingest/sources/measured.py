"""What every benchmarking source has in common: thermal fuels become
delivered heat, district steam decides `steam_heated`, and the result is
attached to the nearest sink."""

from __future__ import annotations

from collections.abc import Sequence

from ingest.config import BOILER_EFF, KBTU_TO_KWH
from ingest.util import distance_m


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
    """One disclosure as delivered heat, or None if it reports none. Fuel is
    scaled by boiler efficiency here because the engine divides it back out;
    district steam is not demand at all, the building already has its heat."""
    total = fuel_kbtu + steam_kbtu
    if total <= 0:
        return None
    return {
        "demand_kwh": fuel_kbtu * KBTU_TO_KWH * BOILER_EFF,
        "steam_heated": steam_kbtu > 0.5 * total,
    }


def nearest(row: dict, points: Sequence[dict], radius_m: float) -> dict | None:
    """The closest of `points` (each with `lat`/`lon`) within `radius_m` of a sink."""
    best: dict | None = None
    best_m = radius_m
    for p in points:
        # Cheap rejection before the geodesic: a degree is ~111 km.
        if abs(p["lat"] - row["lat"]) > 0.01 or abs(p["lon"] - row["lon"]) > 0.015:
            continue
        dist = distance_m(row["lat"], row["lon"], p["lat"], p["lon"])
        if dist <= best_m:
            best, best_m = p, dist
    return best


def attach_nearest(
    rows: list[dict],
    buildings: Sequence[dict],
    *,
    radius_m: float,
    source: str,
) -> dict[str, int]:
    """Give each sink the nearest disclosed building within `radius_m`, in
    place. A disclosure of zero heat still marks steam heating but does not
    zero the demand."""
    stats = {"joined": 0, "steam_heated": 0, "candidates": len(rows)}
    if not buildings:
        return stats
    for row in rows:
        best = nearest(row, buildings, radius_m)
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
