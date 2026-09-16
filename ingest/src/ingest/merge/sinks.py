"""Assemble the sink layer, pre-filtered to those near a data center."""

from pyproj import Geod

from ingest.config import REGIONS, SINK_PREFILTER_SLACK, RegionName
from ingest.schema import DataCenter, Sink
from ingest.sources import osm

_GEOD = Geod(ellps="WGS84")


def _cutoff_m(region: RegionName) -> float:
    r = REGIONS[region]
    return r["radius_m"] * r["detour"] * SINK_PREFILTER_SLACK


def _near_any(row: dict, dcs: list[DataCenter], cutoff: float) -> bool:
    for dc in dcs:
        if dc.region != row["region"]:
            continue
        _, _, dist = _GEOD.inv(dc.lon, dc.lat, row["lon"], row["lat"])
        if dist <= cutoff:
            return True
    return False


def build(
    regions: list[RegionName], dcs: list[DataCenter], *, refresh: bool = False
) -> tuple[list[Sink], dict[str, int]]:
    """Return (sinks, stats). Stats feed the CLI summary table."""
    stats = {"fetched": 0, "dropped_far": 0, "dropped_steam_heated": 0}
    rows: list[dict] = []

    for region in regions:
        cutoff = _cutoff_m(region)
        for row in osm.candidates(region, refresh=refresh):
            stats["fetched"] += 1
            # LL84 sets this in T8; district-steam buildings already have heat.
            if row["steam_heated"]:
                stats["dropped_steam_heated"] += 1
                continue
            if not _near_any(row, dcs, cutoff):
                stats["dropped_far"] += 1
                continue
            rows.append(row)

    rows.sort(key=lambda r: (r["lat"], r["lon"], r["name"]))
    return [Sink(id=f"s_{i:05d}", **r) for i, r in enumerate(rows)], stats
