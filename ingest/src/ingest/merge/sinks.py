"""Assemble the sink layer, pre-filtered to those near a data center."""

from pyproj import Geod

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

_GEOD = Geod(ellps="WGS84")


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
    # Per square metre of floor, the basis the threshold and the intensity
    # share. Per footprint, a measured tower reads as hundreds of kWh/m2.
    measured = row["demand_kwh"] / row["floor_area_m2"]
    return (
        measured < MEASURED_NEAR_ZERO_KWH_PER_M2
        and entry["kwh_per_m2"] > MODELLED_SUBSTANTIAL_KWH_PER_M2
    )


def _counterfactual(row: dict, table: dict[str, dict]) -> str:
    """What the building heats with today.

    A measured building whose thermal fuels dominate is gas by observation. A
    modelled one — including a measurement the fallback overruled — takes the
    stock majority for its type. Everything else stays gas: a footprint or
    category estimate says nothing about the heating system, and gas is what
    those estimates have always implicitly assumed. That is also what keeps
    New York's untouched sinks priced exactly as before.
    """
    if row["demand_source"] != "comstock_modeled":
        return "gas"
    entry = _entry(row, table)
    return entry["counterfactual"] if entry else "gas"


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

        # Seattle publishes its own benchmarking, with coordinates; so does
        # California, statewide. Each module answers only for its regions.
        if near:
            stats["bench_joined"] += seattle_bench.attach(near, region, refresh=refresh)["joined"]
            stats["bench_joined"] += ab802.attach(near, region, refresh=refresh)["joined"]

        # Where there is no disclosure to read, model the demand instead. This
        # replaces the footprint guess for the categories ComStock covers; the
        # rest keep their category constants and say so via `demand_source`.
        if region in COMSTOCK_REGIONS and near:
            table = comstock.build(region, refresh=refresh)["by_type"]
            for row in near:
                # A measurement beats the model. Only the near-zero rule below
                # may overturn one, and it says so when it does.
                if row["demand_source"] in _MEASURED:
                    continue
                modelled = comstock.demand_kwh(row["cat"], row.get("floor_area_m2"), table)
                if modelled is None:
                    continue
                row["demand_kwh"], row["demand_source"] = modelled
                stats["comstock_modeled"] += 1

        # A measured building reporting almost no thermal fuel is usually not a
        # building without heating — it is one heated electrically, which the
        # fuel columns cannot see. Where ComStock says a typical building of
        # its type wants substantially more, the model wins and the sink says
        # why. New York reads its ComStock table for this alone.
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
            # District-steam buildings already have their heat (§3.3) — unless
            # the region says its steam customers are exactly who to keep.
            if row["steam_heated"] and not keep:
                stats["dropped_steam_heated"] += 1
                continue
            rows.append(zones.tag(row))

    return [Sink(id=i, **r) for i, r in assign_ids(rows, "s", 5)], stats
