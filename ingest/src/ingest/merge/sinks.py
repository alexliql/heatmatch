"""Assemble the sink layer, pre-filtered to those near a data center."""

from ingest.config import (
    COMSTOCK_FALLBACK_REGIONS,
    COMSTOCK_REGIONS,
    MEASURED_NEAR_ZERO_KWH_PER_M2,
    MODELLED_SUBSTANTIAL_KWH_PER_M2,
    REGIONS,
    SINK_PREFILTER_SLACK,
    RegionName,
    keep_steam_heated,
)
from ingest.merge.emit import assign_ids
from ingest.schema import DataCenter, Sink
from ingest.sources import ab802, comstock, ll84, osm, pluto, seattle_bench, zones
from ingest.util import distance_m


def cutoff_m(region: RegionName) -> float:
    r = REGIONS[region]
    return r["radius_m"] * r["detour"] * SINK_PREFILTER_SLACK


_MEASURED = frozenset({"ll84_fuel", "ab802", "seattle_bench"})


def _entry(row: dict, table: dict[str, dict]) -> dict | None:
    return comstock.intensity_for(row["cat"], row.get("floor_area_m2"), table)


def _measured_near_zero(row: dict, table: dict[str, dict]) -> bool:
    if row["demand_source"] not in _MEASURED or not row.get("floor_area_m2"):
        return False
    entry = _entry(row, table)
    if entry is None:
        return False
    measured = row["demand_kwh"] / row["floor_area_m2"]
    return (
        measured < MEASURED_NEAR_ZERO_KWH_PER_M2
        and entry["kwh_per_m2"] > MODELLED_SUBSTANTIAL_KWH_PER_M2
    )


def _counterfactual(row: dict, table: dict[str, dict]) -> str:
    """A modelled sink takes the stock majority for its type; a measured one
    burns fuel by observation, and an estimate says nothing, so both are gas."""
    if row["demand_source"] != "comstock_modeled":
        return "gas"
    entry = _entry(row, table)
    return entry["counterfactual"] if entry else "gas"


def _near_any(row: dict, dcs: list[DataCenter], cutoff: float) -> bool:
    return any(
        dc.region == row["region"] and distance_m(dc.lat, dc.lon, row["lat"], row["lon"]) <= cutoff
        for dc in dcs
    )


def build(
    regions: list[RegionName], dcs: list[DataCenter], *, refresh: bool = False
) -> tuple[list[Sink], dict[str, int]]:
    """Return (sinks, stats). Stats feed the CLI summary table."""
    stats = {
        "fetched": 0,
        "dropped_far": 0,
        "dropped_steam_heated": 0,
        "ll84_joined": 0,
        "bench_joined": 0,
        "comstock_modeled": 0,
        "measured_fuel_near_zero": 0,
    }
    rows: list[dict] = []

    for region in regions:
        cutoff = cutoff_m(region)
        anchors = [(dc.lat, dc.lon) for dc in dcs if dc.region == region]

        near: list[dict] = []
        for row in osm.candidates(region, anchors, cutoff, refresh=refresh):
            stats["fetched"] += 1
            if not _near_any(row, dcs, cutoff):
                stats["dropped_far"] += 1
                continue
            near.append(row)

        # Measured demand replaces the estimate wherever a disclosure matches;
        # each source answers only for its regions.
        if region == "nyc" and near:
            lots = pluto.lots_near(anchors, cutoff, refresh=refresh)
            joined = ll84.attach(near, lots, refresh=refresh)
            stats["ll84_joined"] += joined["joined"]

        if near:
            stats["bench_joined"] += seattle_bench.attach(near, region, refresh=refresh)["joined"]
            stats["bench_joined"] += ab802.attach(near, region, refresh=refresh)["joined"]

        # Model the demand where ComStock covers the category; a measurement
        # beats the model, and only the near-zero rule below may overturn one.
        if region in COMSTOCK_REGIONS and near:
            table = comstock.build(region, refresh=refresh)["by_type"]
            for row in near:
                if row["demand_source"] in _MEASURED:
                    continue
                modelled = comstock.demand_kwh(row["cat"], row.get("floor_area_m2"), table)
                if modelled is None:
                    continue
                row["demand_kwh"], row["demand_source"] = modelled
                stats["comstock_modeled"] += 1

        # A measured building reporting almost no thermal fuel is usually
        # heated electrically; see config.MEASURED_NEAR_ZERO_KWH_PER_M2.
        if region in COMSTOCK_FALLBACK_REGIONS and near:
            table = comstock.build(region, refresh=refresh)["by_type"]
            for row in near:
                if _measured_near_zero(row, table):
                    row["demand_kwh"] = row["floor_area_m2"] * _entry(row, table)["kwh_per_m2"]
                    row["demand_source"] = "comstock_modeled"
                    row["demand_note"] = "measured_fuel_near_zero"
                    stats["measured_fuel_near_zero"] += 1
            for row in near:
                row["counterfactual"] = _counterfactual(row, table)

        keep = keep_steam_heated(region)
        for row in near:
            if row["steam_heated"] and not keep:
                stats["dropped_steam_heated"] += 1
                continue
            rows.append(zones.tag(row))

    return [Sink(id=i, **r) for i, r in assign_ids(rows, "s", 5)], stats
