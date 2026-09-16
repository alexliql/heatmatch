"""Assemble the data center layer.

T2 has a single source, so there is nothing to reconcile yet; merge/dedupe.py
arrives with PLUTO and the parcel sources in T8.
"""

from ingest.config import RegionName
from ingest.schema import DataCenter
from ingest.sources import pnnl


def build(regions: list[RegionName], *, refresh: bool = False) -> list[DataCenter]:
    rows = [c for region in regions for c in pnnl.candidates(region, refresh=refresh)]
    # Sorting on position-then-name (§3.2) is what makes ids reproducible: the
    # upstream file's row order is not guaranteed stable between releases.
    rows.sort(key=lambda r: (r["lat"], r["lon"], r["name"]))
    return [DataCenter(id=f"dc_{i:04d}", **r) for i, r in enumerate(rows)]
