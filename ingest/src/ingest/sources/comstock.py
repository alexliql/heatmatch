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

Heating fuels only, matching the LL84 treatment in `ll84.py`: gas, oil and
propane for space heating and service hot water. Electricity is excluded
because it is not what a heat network would displace, and district heating is
excluded because that heat is already supplied.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from functools import lru_cache

import pandas as pd

from ingest.config import (
    COMSTOCK_BASE_URL,
    COMSTOCK_LARGE_OFFICE_M2,
    COMSTOCK_MIN_SAMPLES,
    COMSTOCK_PROFILE_TYPE_BY_CAT,
    COMSTOCK_RELEASE,
    COMSTOCK_SOURCE,
    COMSTOCK_TYPE_BY_CAT,
    REGIONS,
    RegionName,
    SinkCat,
)
from ingest.sources.fetch import cached_get

# Floor area arrives in square feet; the schema works in square metres.
SQFT_TO_M2 = 0.09290304

# Non-electric heating end uses. The two spellings are not a typo: the metadata
# parquet separates unit from name with two dots, the timeseries CSVs with one.
#
# Electric heating is deliberately excluded, matching how `ll84.py` treats New
# York: the economics downstream price delivered heat against a displaced gas
# boiler, so counting electrically heated floor area as demand would be costing
# a saving that is not there.
#
# The cost is real and Virginia-specific, which is why `electric_heating_share`
# is reported alongside every intensity: in this mild a climate much of the
# commercial stock runs heat pumps, so only 36% of large offices burn any fuel
# at all and the fuel-only intensity is correspondingly low. Those buildings
# still have thermal demand a heat network could serve; this model does not
# count it. See the README's Virginia limitations.
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
TIMESERIES_COLUMNS = _columns(".")

# Reported as a caveat, never added to demand.
ELECTRIC_HEATING_COLUMNS = [
    "out.electricity.heating.energy_consumption..kwh",
    "out.electricity.water_systems.energy_consumption..kwh",
]


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
        *METADATA_COLUMNS,
        *ELECTRIC_HEATING_COLUMNS,
    ]

    frames = []
    for county_fips in county_fips_for(region, refresh=refresh):
        gisjoin = _gisjoin(cfg["state_fips"], county_fips)
        path = cached_get(
            _county_metadata_url(state, gisjoin),
            f"comstock/{state}_{gisjoin}_upgrade0.parquet",
            refresh=refresh,
        )
        frames.append(pd.read_parquet(path, columns=wanted))

    df = pd.concat(frames, ignore_index=True)
    # `weight` scales each sampled building up to the stock it represents, so
    # both numerator and denominator must carry it or the ratio is a simple
    # sample mean of a deliberately non-uniform sample.
    heat = df[METADATA_COLUMNS].sum(axis=1) * df["weight"]
    area = df["in.sqft..ft2"] * SQFT_TO_M2 * df["weight"]

    electric = df[ELECTRIC_HEATING_COLUMNS].sum(axis=1) * df["weight"]
    burns_fuel = df[METADATA_COLUMNS].sum(axis=1) > 0

    out: dict[str, dict] = {}
    for building_type, group in df.groupby("in.comstock_building_type"):
        # Too few sampled buildings to publish a number from. ComStock samples
        # hospitals thinly — six across all seven jurisdictions — so hospitals
        # fall through to the category constant rather than being described by
        # half a dozen simulations.
        if len(group) < COMSTOCK_MIN_SAMPLES:
            continue
        area_sum = area.loc[group.index].sum()
        if area_sum <= 0:
            continue
        fuel_sum = heat.loc[group.index].sum()
        out[str(building_type)] = {
            "kwh_per_m2": float(fuel_sum / area_sum),
            "samples": len(group),
            # What this intensity leaves out, so the limitation is a number in
            # the file rather than a sentence in a README nobody reads.
            "fuel_heated_share": float(burns_fuel.loc[group.index].mean()),
            "kwh_per_m2_incl_electric": float(
                (fuel_sum + electric.loc[group.index].sum()) / area_sum
            ),
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


def county_fips_for(region: RegionName, *, refresh: bool = False) -> list[str]:
    """County FIPS codes for a region's named jurisdictions, from TIGER.

    Read from the boundary file rather than hardcoded: the same file already
    has to be downloaded for the clip, and a hand-written table of Virginia
    independent-city codes is exactly the kind of thing that rots silently.
    """
    from ingest.sources.boundary import county_codes

    return county_codes(region, refresh=refresh)


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
        "by_type": {
            t: {**v, "monthly": shapes[t]} for t, v in intensity.items() if t in shapes
        },
    }


def comstock_type(cat: SinkCat, area_m2: float | None) -> str | None:
    """The ComStock type standing in for a sink, or None if there is no match.

    Offices are split by size here rather than in the mapping table: ComStock
    models small, medium and large offices separately and they differ by more
    than a factor of two, so which one a building resembles depends on the
    building.
    """
    if cat == "office":
        if area_m2 is None:
            return None
        return "LargeOffice" if area_m2 > COMSTOCK_LARGE_OFFICE_M2 else "MediumOffice"
    return COMSTOCK_TYPE_BY_CAT.get(cat)


def demand_kwh(
    cat: SinkCat, area_m2: float | None, table: dict[str, dict]
) -> tuple[float, str] | None:
    """Modelled annual heating demand for one sink, or None if unmodellable.

    Returns `(kwh, "comstock_modeled")` so callers can fall through to the
    footprint or category estimate exactly as they do for an unjoined LL84 row.
    """
    if not area_m2 or area_m2 <= 0:
        return None
    building_type = comstock_type(cat, area_m2)
    entry = table.get(building_type) if building_type else None
    if entry is None:
        return None
    return area_m2 * entry["kwh_per_m2"], "comstock_modeled"


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
