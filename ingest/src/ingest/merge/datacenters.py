"""Assemble the data center layer from every source, reconciled."""

from ingest.config import RegionName
from ingest.merge.dedupe import merge
from ingest.merge.emit import assign_ids
from ingest.schema import DataCenter
from ingest.sources import nova_mw, nys_parcels, pluto, pnnl, zones


def build(
    regions: list[RegionName], *, refresh: bool = False
) -> tuple[list[DataCenter], dict[str, int]]:
    """Return (data centers, curated-capacity stats for the CLI summary)."""
    raw: list[dict] = []
    for region in regions:
        raw += list(pnnl.candidates(region, refresh=refresh))
        raw += list(pluto.candidates(region, refresh=refresh))
        raw += list(nys_parcels.candidates(region, refresh=refresh))

    rows = [zones.tag(r) for r in merge(raw)]
    # Applied after dedupe: a curated figure covers a facility, and which rows
    # are one facility is only settled once duplicates have been merged.
    curated = nova_mw.apply(rows) if "nova" in regions else {"rows": 0, "buildings": 0, "unmatched": 0}
    # Source-only bookkeeping; the schema does not carry it.
    for r in rows:
        r.pop("_address", None)
    return [DataCenter(id=i, **r) for i, r in assign_ids(rows, "dc", 4)], curated
