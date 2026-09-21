"""Reconcile data center candidates across sources.

The Atlas and PLUTO describe the same buildings in different words — Telehouse
appears as "Telehouse Teleport" in one and "7 Teleport Drive" in the other — so
candidates are matched on position first and name second.
"""

from collections.abc import Iterable

from rapidfuzz import fuzz

from ingest.util import distance_m

# Two candidates this close are the same building; tax-lot centroids and OSM
# points for one facility rarely differ by more than a few tens of metres.
MATCH_M = 75.0
NAME_RATIO = 70

# The Atlas has real facility names where PLUTO has a lot owner. A seed ranks
# equal to the Atlas so the larger area estimate wins: a seed's stated floor
# area beats the Atlas footprint for a 34-storey carrier hotel.
_SOURCE_RANK = {
    "im3_datacenter_atlas": 0,
    "manual_seed_dcs": 0,
    "nyc_pluto": 1,
    "nys_parcels": 2,
}


def _rank(row: dict) -> int:
    return min((_SOURCE_RANK.get(s, 9) for s in row["sources"]), default=9)


def _same(a: dict, b: dict) -> bool:
    if distance_m(a["lat"], a["lon"], b["lat"], b["lon"]) > MATCH_M:
        return False
    name_a, name_b = a.get("name", "").strip(), b.get("name", "").strip()
    if not name_a or not name_b:
        return True
    return fuzz.token_set_ratio(name_a, name_b) >= NAME_RATIO


def merge(candidates: Iterable[dict]) -> list[dict]:
    """Collapse duplicates, keeping the best-ranked record and unioning sources."""
    # Best source first: the record kept is the preferred one.
    ordered = sorted(candidates, key=lambda r: (_rank(r), -r.get("mw", 0.0)))

    kept: list[dict] = []
    for row in ordered:
        for existing in kept:
            if _same(existing, row):
                for src in row["sources"]:
                    if src not in existing["sources"]:
                        existing["sources"].append(src)
                if _rank(row) == _rank(existing) and row.get("mw", 0) > existing.get("mw", 0):
                    existing["mw"] = row["mw"]
                    existing["mw_source"] = row["mw_source"]
                break
        else:
            kept.append(row)
    return kept
