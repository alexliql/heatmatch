"""Assemble the data center layer from every source, reconciled."""

from ingest.config import RegionName
from ingest.merge.dedupe import merge
from ingest.schema import DataCenter
from ingest.sources import nys_parcels, pluto, pnnl, zones


def build(regions: list[RegionName], *, refresh: bool = False) -> list[DataCenter]:
    raw: list[dict] = []
    for region in regions:
        raw += list(pnnl.candidates(region, refresh=refresh))
        raw += list(pluto.candidates(region, refresh=refresh))
        raw += list(nys_parcels.candidates(region, refresh=refresh))

    rows = [zones.tag(r) for r in merge(raw)]
    # Source-only bookkeeping; the schema does not carry it.
    for r in rows:
        r.pop("_address", None)
    # Sorting on position-then-name (§3.2) is what makes ids reproducible: the
    # upstream file's row order is not guaranteed stable between releases.
    rows.sort(key=lambda r: (r["lat"], r["lon"], r["name"]))
    return [DataCenter(id=f"dc_{i:04d}", **r) for i, r in enumerate(rows)]
