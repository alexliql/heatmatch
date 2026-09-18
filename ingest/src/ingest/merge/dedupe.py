"""Reconcile data center candidates across sources.

The Atlas and PLUTO describe the same buildings in different words — Telehouse
appears as "Telehouse Teleport" in one and "7 Teleport Drive" in the other — so
candidates are matched on position first and name second.
"""

from collections.abc import Iterable

from pyproj import Geod
from rapidfuzz import fuzz

_GEOD = Geod(ellps="WGS84")

# Two candidates this close are the same building; tax-lot centroids and OSM
# points for one facility rarely differ by more than a few tens of metres.
MATCH_M = 75.0
NAME_RATIO = 70

# The Atlas is a curated dataset with real facility names, while PLUTO gives a
# lot's owner. Prefer the Atlas for identity and capacity where both describe
# the same site.
# A seed ranks with the Atlas, not below it. Both are area-derived estimates,
# and when they describe the same building the seed's *stated floor area* is
# the better one: the Atlas maps a footprint, which for a 34-storey carrier
# hotel like the Westin Building is a thirtieth of the floor space. Equal rank
# lets the larger estimate win, per the rule below.
_SOURCE_RANK = {
    "im3_datacenter_atlas": 0,
    "manual_seed_dcs": 0,
    "nyc_pluto": 1,
    "nys_parcels": 2,
}


def _rank(row: dict) -> int:
    return min((_SOURCE_RANK.get(s, 9) for s in row["sources"]), default=9)


def _same(a: dict, b: dict) -> bool:
    _, _, dist = _GEOD.inv(a["lon"], a["lat"], b["lon"], b["lat"])
    if dist > MATCH_M:
        return False
    name_a, name_b = a.get("name", "").strip(), b.get("name", "").strip()
    if not name_a or not name_b:
        return True
    return fuzz.token_set_ratio(name_a, name_b) >= NAME_RATIO


def merge(candidates: Iterable[dict]) -> list[dict]:
    """Collapse duplicates, keeping the best-ranked record and unioning sources."""
    # Best source first, so the record kept for each cluster is the preferred
    # one and later matches only contribute provenance.
    ordered = sorted(candidates, key=lambda r: (_rank(r), -r.get("mw", 0.0)))

    kept: list[dict] = []
    for row in ordered:
        for existing in kept:
            if _same(existing, row):
                for src in row["sources"]:
                    if src not in existing["sources"]:
                        existing["sources"].append(src)
                # A site measured by a better source keeps that measurement;
                # take the larger estimate only among equals.
                if _rank(row) == _rank(existing) and row.get("mw", 0) > existing.get("mw", 0):
                    existing["mw"] = row["mw"]
                    existing["mw_source"] = row["mw_source"]
                break
        else:
            kept.append(row)
    return kept
