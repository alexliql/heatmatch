"""Assemble the sink layer, pre-filtered to those near a data center."""

from pyproj import Geod

from ingest.config import REGIONS, SINK_PREFILTER_SLACK, RegionName
from ingest.schema import DataCenter, Sink
from ingest.sources import ll84, osm, pluto, zones

_GEOD = Geod(ellps="WGS84")


def cutoff_m(region: RegionName) -> float:
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
    stats = {"fetched": 0, "dropped_far": 0, "dropped_steam_heated": 0, "ll84_joined": 0}
    rows: list[dict] = []

    for region in regions:
        cutoff = cutoff_m(region)
        # Query around the data centers themselves: anything further than the
        # pre-filter cutoff would be discarded below anyway.
        anchors = [(dc.lat, dc.lon) for dc in dcs if dc.region == region]

        near: list[dict] = []
        for row in osm.candidates(region, anchors, cutoff, refresh=refresh):
            stats["fetched"] += 1
            if not _near_any(row, dcs, cutoff):
                stats["dropped_far"] += 1
                continue
            near.append(row)

        # LL84 covers NYC only, and replaces the footprint guess with reported
        # fuel use wherever a tax lot matches.
        if region == "nyc" and near:
            lots = pluto.lots_near(anchors, cutoff, refresh=refresh)
            joined = ll84.attach(near, lots, refresh=refresh)
            stats["ll84_joined"] += joined["joined"]

        for row in near:
            # District-steam buildings already have their heat (§3.3).
            if row["steam_heated"]:
                stats["dropped_steam_heated"] += 1
                continue
            rows.append(zones.tag(row))

    rows.sort(key=lambda r: (r["lat"], r["lon"], r["name"]))
    return [Sink(id=f"s_{i:05d}", **r) for i, r in enumerate(rows)], stats
