"""Curated capacities for Northern Virginia, from public statements and filings.

Everything else in this pipeline infers capacity from building area. Where an
operator, a county approval or a utility filing states a real number, that is
strictly better information, and `mw_confidence` exists to say so.

Two things about the real world shaped this module:

**Published figures are usually campus-level.** Operators say "our Manassas
campus is 190 MW", not "DC5 is 42 MW". A campus row is therefore distributed
across the buildings matched to it, pro rata by the footprint estimate already
computed — which keeps the campus total honest and the relative sizes within it
as good as the footprints are.

**A number with a URL is not a verified number.** Rows whose note still begins
`UNVERIFIED` are used for their value but not for their confidence: they are
emitted as `parcel_estimate`, the same grade as an assessed-area inference,
until a person has read the source and removed the marker. That is the whole
difference between "someone found this on the internet" and "this is filed".
"""

import csv
import re
from pathlib import Path

from ingest.config import RegionName

MANUAL = Path(__file__).resolve().parents[3] / "manual" / "nova_mw.csv"

NOVA_MW_SOURCE = {
    "id": "manual_nova_mw",
    "url": "https://github.com/alexliql/heatmatch/blob/main/ingest/manual/nova_mw.csv",
    "license": "CC0-1.0",
    "note": "Hand-curated Northern Virginia capacities; per-row provenance in the file.",
}

# A row still carrying this marker has not been read by a person, so its value
# is used but its confidence is not.
UNVERIFIED = "UNVERIFIED"


def normalize(name: str) -> str:
    """Casefold and strip punctuation, so 'Iron Mountain VA-1' matches 'va 1'."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _rows() -> list[dict]:
    if not MANUAL.exists():
        return []
    with MANUAL.open(newline="") as fh:
        # The file is heavily commented; DictReader has no comment support, so
        # blank and '#' lines are dropped before it sees them.
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    out = []
    for row in csv.DictReader(lines):
        if not row.get("match_key"):
            continue
        row["mw"] = float(row["mw"])
        row["scope"] = (row.get("scope") or "campus").strip()
        out.append(row)
    return out


def apply(dcs: list[dict], region: RegionName = "nova") -> dict[str, int]:
    """Overwrite `mw` in place where a curated figure covers a data center.

    Returns counts for the CLI summary. Mutates `dcs` rather than returning a
    new list, matching how `ll84.attach` revises sink demand.
    """
    rows = _rows()
    stats = {"rows": len(rows), "buildings": 0, "unmatched": 0}
    if not rows:
        return stats

    targets = [d for d in dcs if d.get("region") == region]

    for row in rows:
        key = normalize(row["match_key"])
        verified = not (row.get("note") or "").lstrip().startswith(UNVERIFIED)
        # A curated figure nobody has read is worth using but not worth
        # claiming; see the module docstring.
        source = row["mw_confidence"] if verified else "parcel_estimate"
        campus = f"camp_{re.sub(r'[^a-z0-9]+', '_', key).strip('_')}"

        matched = [d for d in targets if key in normalize(d["name"])]
        if not matched:
            stats["unmatched"] += 1
            continue

        if row["scope"] == "building":
            # An exact figure for one building; if the key matched several,
            # each gets it, which is what a repeated name means.
            for d in matched:
                d.update(mw=row["mw"], mw_source=source, campus_id=campus)
        else:
            # Campus total, split by the footprint estimate so the total is the
            # published one and the split is as good as the footprints are.
            basis = sum(d["mw"] for d in matched)
            for d in matched:
                share = (d["mw"] / basis) if basis else 1.0 / len(matched)
                d.update(mw=row["mw"] * share, mw_source=source, campus_id=campus)

        for d in matched:
            d.setdefault("sources", []).append(NOVA_MW_SOURCE["id"])
        stats["buildings"] += len(matched)

    return stats
