"""Modelled thermal demand from NREL ComStock, for regions with no
benchmarking disclosure to read.

Two products: an annual intensity (kWh/m2) per building type from the
per-county metadata, and a monthly shape from the state-level timeseries
(the county aggregates are ~770 MB for seven counties, and the shape barely
varies within a climate zone). The result is modelled, not measured, and
`demand_source="comstock_modeled"` says so.

Demand is delivered heat, per sampled building:

    delivered = (gas + oil + propane)[heating + hot water] × BOILER_EFF
              + district heat[heating + hot water]
              + electric heating × (COP if a heat pump else 1)
              + electric hot water

A fuel-only basis would miss most of the stock: Virginia's large offices are
52% electric resistance and 24% district heat. `kwh_per_m2_fuel_only` is
still reported so the difference stays visible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ingest.config import (
    BOILER_EFF,
    COMSTOCK_BASE_URL,
    COMSTOCK_FALLBACK_REGIONS,
    COMSTOCK_LARGE_OFFICE_M2,
    COMSTOCK_MIN_SAMPLES,
    COMSTOCK_PROFILE_TYPE_BY_CAT,
    COMSTOCK_RELEASE,
    COMSTOCK_SOURCE,
    COMSTOCK_TYPE_BY_CAT,
    EXISTING_HEAT_PUMP_COP,
    REGIONS,
    RegionName,
    SinkCat,
)
from ingest.sources.boundary import county_codes
from ingest.sources.fetch import cached_get

# Floor area arrives in square feet; the schema works in square metres.
SQFT_TO_M2 = 0.09290304

# Combustion heating end uses. The metadata parquet separates unit from name
# with two dots, the timeseries CSVs with one.
_HEATING_ENDUSES = [
    ("natural_gas", "heating"),
    ("natural_gas", "water_systems"),
    ("fuel_oil", "heating"),
    ("fuel_oil", "water_systems"),
    ("propane", "heating"),
    ("propane", "water_systems"),
]


def _columns(sep: str) -> list[str]:
    return [f"out.{fuel}.{use}.energy_consumption{sep}kwh" for fuel, use in _HEATING_ENDUSES]


METADATA_COLUMNS = _columns("..")
# The monthly shape spans every heating end-use. The timeseries is aggregated
# across buildings, so heat-pump electricity enters at unit weight here.
TIMESERIES_COLUMNS = _columns(".") + [
    "out.district_heating.heating.energy_consumption.kwh",
    "out.district_heating.water_systems.energy_consumption.kwh",
    "out.electricity.heating.energy_consumption.kwh",
    "out.electricity.water_systems.energy_consumption.kwh",
]

ELECTRIC_HEATING = "out.electricity.heating.energy_consumption..kwh"
ELECTRIC_WATER = "out.electricity.water_systems.energy_consumption..kwh"
DISTRICT_COLUMNS = [
    "out.district_heating.heating.energy_consumption..kwh",
    "out.district_heating.water_systems.energy_consumption..kwh",
]
# How the building heats. Values seen in the release: Furnace, Boiler,
# Electric Resistance, ASHP, WSHP, GSHP, District.
HEAT_TYPE = "in.hvac_heat_type"
HEAT_PUMP_TYPES = frozenset({"ASHP", "WSHP", "GSHP"})

# What each ComStock heating system would be displaced as. District heat is
# overwhelmingly gas-fired steam.
COUNTERFACTUAL_BY_HEAT_TYPE = {
    "Furnace": "gas",
    "Boiler": "gas",
    "District": "gas",
    "Electric Resistance": "electric_resistance",
    "ASHP": "heat_pump",
    "WSHP": "heat_pump",
    "GSHP": "heat_pump",
}

# Recorded in every derived file, next to the numbers computed on it.
BASIS = {
    "quantity": "delivered heat, kWh per m2 of floor area, weighted by ComStock `weight`",
    "combustion": f"{[f'{f}.{u}' for f, u in _HEATING_ENDUSES]} x BOILER_EFF={BOILER_EFF}",
    "district": "out.district_heating.{heating,water_systems} x 1.0",
    "electric_heating": f"{ELECTRIC_HEATING} x {EXISTING_HEAT_PUMP_COP} if {HEAT_TYPE} in "
    f"{sorted(HEAT_PUMP_TYPES)} else x 1.0",
    "electric_water": f"{ELECTRIC_WATER} x 1.0 (baseline stock has no heat-pump water heaters)",
    "counterfactual": f"weighted majority of {HEAT_TYPE} via {COUNTERFACTUAL_BY_HEAT_TYPE}",
    "monthly": "share by month of every heating end-use across all fuels, state-level "
    "aggregate; electric heating at unit weight (no per-building COP available)",
}


def _gisjoin(state_fips: str, county_fips: str) -> str:
    """NHGIS county id, ComStock's partition key: Loudoun (51107) is G5101070."""
    return f"G{state_fips}0{county_fips}0"


def _county_metadata_url(state: str, gisjoin: str) -> str:
    return (
        f"{COMSTOCK_BASE_URL}/{COMSTOCK_RELEASE}/metadata_and_annual_results/"
        f"by_state_and_county/full/parquet/state={state}/county={gisjoin}/"
        f"{state}_{gisjoin}_upgrade0.parquet"
    )


def _state_timeseries_url(state: str, building_type: str) -> str:
    slug = building_type.lower()
    return (
        f"{COMSTOCK_BASE_URL}/{COMSTOCK_RELEASE}/timeseries_aggregates/by_state/"
        f"upgrade=0/state={state}/up0-{state.lower()}-{slug}.csv"
    )


def annual_intensity(region: RegionName, *, refresh: bool = False) -> dict[str, dict]:
    """Weighted delivered kWh per m2 of floor area by ComStock type, pooled
    across the region's counties. Types under `COMSTOCK_MIN_SAMPLES` are left
    out; their sinks keep the category constant."""
    cfg = REGIONS[region]
    state = cfg["state_abb"]
    wanted = [
        "in.comstock_building_type",
        "in.sqft..ft2",
        "weight",
        HEAT_TYPE,
        *METADATA_COLUMNS,
        *DISTRICT_COLUMNS,
        ELECTRIC_HEATING,
        ELECTRIC_WATER,
    ]

    frames = []
    for county_fips in county_codes(region):
        gisjoin = _gisjoin(cfg["state_fips"], county_fips)
        path = cached_get(
            _county_metadata_url(state, gisjoin),
            f"comstock/{state}_{gisjoin}_upgrade0.parquet",
            refresh=refresh,
        )
        frames.append(pd.read_parquet(path, columns=wanted))

    df = pd.concat(frames, ignore_index=True)
    # `weight` scales each sample up to the stock it represents; numerator and
    # denominator both carry it.
    w = df["weight"]
    area = df["in.sqft..ft2"] * SQFT_TO_M2 * w

    # The release pads some values ("Boiler ").
    df[HEAT_TYPE] = df[HEAT_TYPE].astype(str).str.strip()

    fuel_in = df[METADATA_COLUMNS].sum(axis=1)
    is_heat_pump = df[HEAT_TYPE].isin(HEAT_PUMP_TYPES)
    electric_heat = df[ELECTRIC_HEATING] * is_heat_pump.map(
        {True: EXISTING_HEAT_PUMP_COP, False: 1.0}
    )
    delivered = (
        fuel_in * BOILER_EFF + df[DISTRICT_COLUMNS].sum(axis=1) + electric_heat + df[ELECTRIC_WATER]
    ) * w
    fuel_delivered = fuel_in * BOILER_EFF * w
    burns_fuel = fuel_in > 0

    out: dict[str, dict] = {}
    for building_type, group in df.groupby("in.comstock_building_type"):
        if len(group) < COMSTOCK_MIN_SAMPLES:
            continue
        idx = group.index
        area_sum = area.loc[idx].sum()
        if area_sum <= 0:
            continue
        # The stock's dominant heating system, by the floor area it heats.
        by_type = (w.loc[idx] * df["in.sqft..ft2"].loc[idx]).groupby(df[HEAT_TYPE].loc[idx]).sum()
        majority = str(by_type.idxmax()) if len(by_type) else "Furnace"
        out[str(building_type)] = {
            "kwh_per_m2": float(delivered.loc[idx].sum() / area_sum),
            "counterfactual": COUNTERFACTUAL_BY_HEAT_TYPE.get(majority, "gas"),
            "majority_heat_type": majority,
            "samples": len(group),
            "kwh_per_m2_fuel_only": float(fuel_delivered.loc[idx].sum() / area_sum),
            "fuel_heated_share": float(burns_fuel.loc[idx].mean()),
        }
    return out


def monthly_shape(
    region: RegionName, building_types: list[str], *, refresh: bool = False
) -> dict[str, list[float]]:
    """Share of annual heating fuel falling in each month, January first."""
    state = REGIONS[region]["state_abb"]
    out: dict[str, list[float]] = {}

    for building_type in building_types:
        path = cached_get(
            _state_timeseries_url(state, building_type),
            f"comstock/up0-{state.lower()}-{building_type.lower()}.csv",
            refresh=refresh,
        )
        df = pd.read_csv(path, usecols=["timestamp", *TIMESERIES_COLUMNS])
        stamps = pd.to_datetime(df["timestamp"])
        # Timestamps are interval-ending: 2019-01-01 00:00 is December's last
        # quarter hour.
        month = (stamps - pd.Timedelta(minutes=15)).dt.month
        totals = df[TIMESERIES_COLUMNS].sum(axis=1).groupby(month).sum()

        year = float(totals.sum())
        if year <= 0:
            continue
        shares = [float(totals.get(m, 0.0)) / year for m in range(1, 13)]
        # The engine rejects a profile that does not sum to 1.0; the rounding
        # residual goes into the largest month.
        shares = [round(s, 6) for s in shares]
        biggest = shares.index(max(shares))
        shares[biggest] = round(shares[biggest] + (1.0 - sum(shares)), 6)
        out[building_type] = shares
    return out


@lru_cache(maxsize=4)
def build(region: RegionName, *, refresh: bool = False) -> dict:
    """Annual intensities and monthly shapes for one region. Memoized: the
    sink builder and the profile writer both want it."""
    intensity = annual_intensity(region, refresh=refresh)
    shapes = monthly_shape(region, sorted(intensity), refresh=refresh)
    return {
        "release": COMSTOCK_RELEASE,
        "climate_zone": REGIONS[region].get("climate_zone"),
        "basis": BASIS,
        "by_type": {t: {**v, "monthly": shapes[t]} for t, v in intensity.items() if t in shapes},
    }


def comstock_type(cat: SinkCat, floor_area_m2: float | None) -> str | None:
    """The ComStock type standing in for a sink, or None. Offices are split by
    floor area: ComStock's medium and large offices differ by over 2×."""
    if cat == "office":
        if floor_area_m2 is None:
            return None
        return "LargeOffice" if floor_area_m2 > COMSTOCK_LARGE_OFFICE_M2 else "MediumOffice"
    return COMSTOCK_TYPE_BY_CAT.get(cat)


def demand_kwh(
    cat: SinkCat, floor_area_m2: float | None, table: dict[str, dict]
) -> tuple[float, str] | None:
    """`(kwh, "comstock_modeled")` for one sink, or None if unmodellable. The
    intensity is per m2 of *floor*, not footprint."""
    if not floor_area_m2 or floor_area_m2 <= 0:
        return None
    entry = intensity_for(cat, floor_area_m2, table)
    if entry is None:
        return None
    return floor_area_m2 * entry["kwh_per_m2"], "comstock_modeled"


def intensity_for(cat: SinkCat, floor_area_m2: float | None, table: dict[str, dict]) -> dict | None:
    """The ComStock entry standing in for a sink, or None if there is none."""
    building_type = comstock_type(cat, floor_area_m2)
    return table.get(building_type) if building_type else None


def profiles_for_region(table: dict[str, dict]) -> dict[str, list[float]]:
    """Monthly shapes keyed by sink category; absent categories keep the
    engine's built-in table."""
    out: dict[str, list[float]] = {}
    for cat, building_type in COMSTOCK_PROFILE_TYPE_BY_CAT.items():
        entry = table.get(building_type)
        if entry and entry.get("monthly"):
            out[cat] = entry["monthly"]
    return out


DERIVED = Path(__file__).resolve().parents[3] / "derived"


def write_derived(regions: list[RegionName], *, refresh: bool = False) -> list[Path]:
    """Write `derived/<state>_intensity.json`, keyed by region. Committed so
    the numbers every modelled demand rests on are in the diff."""
    by_state: dict[str, dict] = {}
    for region in regions:
        if region not in COMSTOCK_FALLBACK_REGIONS:
            continue
        state = str(REGIONS[region]["state_abb"]).lower()
        by_state.setdefault(state, {})[region] = build(region, refresh=refresh)
    DERIVED.mkdir(exist_ok=True)
    out = []
    for state, tables in sorted(by_state.items()):
        path = DERIVED / f"{state}_intensity.json"
        path.write_text(json.dumps(tables, indent=2, sort_keys=True) + "\n")
        out.append(path)
    return out


__all__ = [
    "COMSTOCK_SOURCE",
    "annual_intensity",
    "build",
    "comstock_type",
    "demand_kwh",
    "monthly_shape",
    "profiles_for_region",
]
