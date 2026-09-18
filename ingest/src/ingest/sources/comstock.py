"""Modelled thermal demand from NREL ComStock.

Virginia publishes no building energy benchmarking data — there is no LL84
equivalent — so a Northern Virginia sink has no measured fuel use to read.
ComStock fills that gap: a statistically representative sample of simulated
commercial buildings, from which an annual heating intensity per building type
and a monthly shape can be derived and applied to any building whose floor area
is known.

The result is *modelled, not measured*, and the schema says so:
`demand_source="comstock_modeled"`. It describes a typical building of its type
in this climate, not the specific building on the map.

Two products, from two different slices of the release:

- **Annual intensity** (kWh/m2) from the per-county building metadata, which
  carries one row per sampled building with its floor area and annual energy.
- **Monthly shape** from the state-level timeseries aggregates. State rather
  than county: the county aggregates are one ~11 MB file per county *per
  building type*, about 770 MB for seven counties, and the month-to-month shape
  barely varies across adjacent counties in one climate zone.

Demand is **delivered heat** — what the heating system put into the building —
not the fuel it bought. Per sampled building:

    delivered = (gas + oil + propane)[heating + hot water] × BOILER_EFF
              + district heat[heating + hot water]              (already heat)
              + electric heating × (COP if a heat pump else 1)
              + electric hot water × 1                          (no HPWH in baseline stock)

The fuel-only basis this replaced saw a quarter of the stock in Virginia: large
offices there are 52% electric resistance and 24% district heat. In hydro-
electric Seattle or heat-pump California it would have seen almost nothing.
Every intensity still reports `kwh_per_m2_fuel_only` so the difference stays
visible.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Iterator
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
from ingest.sources.fetch import cached_get

# Floor area arrives in square feet; the schema works in square metres.
SQFT_TO_M2 = 0.09290304

# Combustion heating end uses. The two spellings are not a typo: the metadata
# parquet separates unit from name with two dots, the timeseries CSVs with one.
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
# The monthly shape is taken over every heating end-use, whatever the fuel.
# The timeseries is aggregated across buildings, so a heat pump's electricity
# cannot be scaled by its COP here as it is in the annual figure; it enters at
# unit weight, which slightly flattens the shape for heat-pump-heavy stock.
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

# What each ComStock heating system would be displaced *as*. District heat is
# priced as gas: it is overwhelmingly gas-fired steam, and district-heated
# sinks are in any case the ones the steam rule drops.
COUNTERFACTUAL_BY_HEAT_TYPE = {
    "Furnace": "gas",
    "Boiler": "gas",
    "District": "gas",
    "Electric Resistance": "electric_resistance",
    "ASHP": "heat_pump",
    "WSHP": "heat_pump",
    "GSHP": "heat_pump",
}

# Recorded in every derived file, so the basis a number was computed on is in
# the file next to the number.
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
    """NHGIS county identifier, the key ComStock partitions counties by.

    The zero padding is NHGIS's own: a state gets a trailing 0 and so does a
    county, which is why Loudoun (51107) is G5101070 rather than G51107.
    """
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
    """Weighted kWh of heating fuel per m2 of floor area, by ComStock type.

    Pooled across the region's jurisdictions. A type sampled fewer than
    `COMSTOCK_MIN_SAMPLES` times is left out entirely rather than reported with
    a number nobody should rely on; its sinks fall back to the category
    constant in `config.INTENSITY_KWH_PER_M2`.
    """
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
    for county_fips in county_fips_for(region):
        gisjoin = _gisjoin(cfg["state_fips"], county_fips)
        path = cached_get(
            _county_metadata_url(state, gisjoin),
            f"comstock/{state}_{gisjoin}_upgrade0.parquet",
            refresh=refresh,
        )
        frames.append(pd.read_parquet(path, columns=wanted))

    df = pd.concat(frames, ignore_index=True)
    w = df["weight"]
    # `weight` scales each sampled building up to the stock it represents, so
    # both numerator and denominator must carry it or the ratio is a simple
    # sample mean of a deliberately non-uniform sample.
    area = df["in.sqft..ft2"] * SQFT_TO_M2 * w

    # The release pads some values ("Boiler "); an unstripped one would miss
    # the counterfactual table and default to gas, wrongly for a resistance
    # building.
    df[HEAT_TYPE] = df[HEAT_TYPE].astype(str).str.strip()

    fuel_in = df[METADATA_COLUMNS].sum(axis=1)
    is_heat_pump = df[HEAT_TYPE].isin(HEAT_PUMP_TYPES)
    # Electricity into a heat pump comes out as several times as much heat;
    # into a resistance element, as exactly as much.
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
        # Too few sampled buildings to publish a number from. ComStock samples
        # hospitals thinly — six across all of Northern Virginia — so hospitals
        # there fall through to the category constant rather than being
        # described by half a dozen simulations.
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
            # The basis this replaced, kept so the difference stays a number
            # in the file rather than a sentence in a README nobody reads.
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
        # Timestamps are interval-ending: the reading labelled 2019-01-01 00:00
        # is the last quarter hour of December. Shifting back by one interval
        # puts every reading in the month it was actually consumed in.
        month = (stamps - pd.Timedelta(minutes=15)).dt.month
        totals = df[TIMESERIES_COLUMNS].sum(axis=1).groupby(month).sum()

        year = float(totals.sum())
        if year <= 0:
            continue
        shares = [float(totals.get(m, 0.0)) / year for m in range(1, 13)]
        # Rounding twelve independent shares leaves the sum a hair off 1.0, and
        # the engine rejects a profile that is not a distribution. Absorb the
        # residual into the largest month, where it is proportionally smallest.
        shares = [round(s, 6) for s in shares]
        biggest = shares.index(max(shares))
        shares[biggest] = round(shares[biggest] + (1.0 - sum(shares)), 6)
        out[building_type] = shares
    return out


def county_fips_for(region: RegionName) -> list[str]:
    """County FIPS codes for a region's ComStock table, from config."""
    from ingest.sources.boundary import county_codes

    return county_codes(region)


@lru_cache(maxsize=4)
def build(region: RegionName, *, refresh: bool = False) -> dict:
    """Annual intensities and monthly shapes for one region.

    Memoized: the sink builder and the profile writer both want this, and
    re-reading seven county parquets to answer the same question twice is
    several seconds of nothing.
    """
    intensity = annual_intensity(region, refresh=refresh)
    shapes = monthly_shape(region, sorted(intensity), refresh=refresh)
    return {
        "release": COMSTOCK_RELEASE,
        "climate_zone": REGIONS[region].get("climate_zone"),
        "basis": BASIS,
        "by_type": {t: {**v, "monthly": shapes[t]} for t, v in intensity.items() if t in shapes},
    }


def comstock_type(cat: SinkCat, floor_area_m2: float | None) -> str | None:
    """The ComStock type standing in for a sink, or None if there is no match.

    Offices are split by size here rather than in the mapping table: ComStock
    models small, medium and large offices separately and they differ by more
    than a factor of two, so which one a building resembles depends on the
    building. Size means floor area — a 3,000 m2 footprint is a medium office
    at one storey and a large one at ten.
    """
    if cat == "office":
        if floor_area_m2 is None:
            return None
        return "LargeOffice" if floor_area_m2 > COMSTOCK_LARGE_OFFICE_M2 else "MediumOffice"
    return COMSTOCK_TYPE_BY_CAT.get(cat)


def demand_kwh(
    cat: SinkCat, floor_area_m2: float | None, table: dict[str, dict]
) -> tuple[float, str] | None:
    """Modelled annual heating demand for one sink, or None if unmodellable.

    `floor_area_m2`, not the footprint: the intensity is per square metre of
    floor. Applying it to the ground area put a 28-storey Seattle tower at
    96 MWh a year, which is how this was caught.

    Returns `(kwh, "comstock_modeled")` so callers can fall through to the
    footprint or category estimate exactly as they do for an unjoined LL84 row.
    """
    if not floor_area_m2 or floor_area_m2 <= 0:
        return None
    building_type = comstock_type(cat, floor_area_m2)
    entry = table.get(building_type) if building_type else None
    if entry is None:
        return None
    return floor_area_m2 * entry["kwh_per_m2"], "comstock_modeled"


def intensity_for(cat: SinkCat, floor_area_m2: float | None, table: dict[str, dict]) -> dict | None:
    """The ComStock entry standing in for a sink, or None if there is none."""
    building_type = comstock_type(cat, floor_area_m2)
    return table.get(building_type) if building_type else None


def profiles_for_region(table: dict[str, dict]) -> dict[str, list[float]]:
    """Monthly shapes keyed by sink category, as the profiles asset carries them.

    Categories with no ComStock equivalent are simply absent; the engine fills
    them from its built-in table.
    """
    out: dict[str, list[float]] = {}
    for cat, building_type in COMSTOCK_PROFILE_TYPE_BY_CAT.items():
        entry = table.get(building_type)
        if entry and entry.get("monthly"):
            out[cat] = entry["monthly"]
    return out


DERIVED = Path(__file__).resolve().parents[3] / "derived"


def write_derived(regions: list[RegionName], *, refresh: bool = False) -> list[Path]:
    """Write `derived/<state>_intensity.json`, one file per state, keyed by region.

    Committed for reproducibility: the parquet inputs are ~75 MB a region and
    are not, but the fourteen numbers per building type that come out of them
    are what every modelled demand rests on, and they belong in the diff.
    """
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


def months() -> Iterator[str]:
    """Month abbreviations, for the summary table."""
    return (calendar.month_abbr[m] for m in range(1, 13))


__all__ = [
    "COMSTOCK_SOURCE",
    "annual_intensity",
    "build",
    "comstock_type",
    "demand_kwh",
    "monthly_shape",
    "profiles_for_region",
]
