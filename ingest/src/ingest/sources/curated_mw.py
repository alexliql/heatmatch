"""Curated capacities from public statements and filings, one
`manual/<region>_mw.csv` per region.

Published figures are usually campus-level ("our Manassas campus is 190 MW"),
so a campus row is split across its matched buildings pro rata by their
footprint estimates. Rows whose note begins `UNVERIFIED` are used for their
value but emitted as `parcel_estimate` until a person has read the source.
"""

import re

from ingest.config import RegionName
from ingest.util import read_manual_csv

CURATED_MW_SOURCE = {
    "id": "manual_curated_mw",
    "url": "https://github.com/alexliql/heatmatch/tree/main/ingest/manual",
    "license": "CC0-1.0",
    "note": "Hand-curated capacities, one <region>_mw.csv per region; per-row provenance in each file.",
}

UNVERIFIED = "UNVERIFIED"


def normalize(name: str) -> str:
    """Casefold and strip punctuation, so 'Iron Mountain VA-1' matches 'va 1'."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _rows(region: RegionName) -> list[dict]:
    out = []
    for row in read_manual_csv(f"{region}_mw.csv"):
        if not row.get("match_key"):
            continue
        row["mw"] = float(row["mw"])
        row["scope"] = (row.get("scope") or "campus").strip()
        out.append(row)
    return out


def apply(dcs: list[dict], region: RegionName) -> dict[str, int]:
    """Overwrite `mw` in place where a curated figure covers a data center;
    returns counts for the CLI summary."""
    rows = _rows(region)
    stats = {"rows": len(rows), "buildings": 0, "unmatched": 0}
    if not rows:
        return stats

    targets = [d for d in dcs if d.get("region") == region]

    for row in rows:
        key = normalize(row["match_key"])
        verified = not (row.get("note") or "").lstrip().startswith(UNVERIFIED)
        source = row["mw_confidence"] if verified else "parcel_estimate"
        campus = f"camp_{re.sub(r'[^a-z0-9]+', '_', key).strip('_')}"

        matched = [d for d in targets if key in normalize(d["name"])]
        if not matched:
            stats["unmatched"] += 1
            continue

        if row["scope"] == "building":
            # One building's figure; a key matching several gives each the same.
            for d in matched:
                d.update(mw=row["mw"], mw_source=source, campus_id=campus)
        else:
            basis = sum(d["mw"] for d in matched)
            for d in matched:
                share = (d["mw"] / basis) if basis else 1.0 / len(matched)
                d.update(mw=row["mw"] * share, mw_source=source, campus_id=campus)

        for d in matched:
            d.setdefault("sources", []).append(CURATED_MW_SOURCE["id"])
        stats["buildings"] += len(matched)

    return stats
