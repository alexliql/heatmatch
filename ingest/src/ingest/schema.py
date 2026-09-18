"""Output schema: the contract with heatmatch-core. Property names must
match the serde field names in core/heatmatch-core/src/types.rs; its
tests/contract.rs checks the committed data against them."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ingest.config import MW_CONFIDENCE_BY_SOURCE, Counterfactual, RegionName, SinkCat

# Where `mw` came from: area-derived estimates, a hand-seeded floor area, or
# a real figure (an operator statement is "reported", a filing is "filed").
MwSource = Literal[
    "atlas_sqft",
    "atlas_default",
    "pluto_estimate",
    "parcel_estimate",
    "manual",
    "seed_sqft",
    "reported",
    "filed",
]
# Derived from `mw_source` via config.MW_CONFIDENCE_BY_SOURCE, never set alone.
MwConfidence = Literal["reported", "filed", "parcel_estimate", "footprint_estimate"]
# Measured (the first three), modelled, or estimated.
DemandSource = Literal[
    "ll84_fuel",
    "ab802",
    "seattle_bench",
    "comstock_modeled",
    "footprint_estimate",
    "category_default",
]
AreaSource = Literal["county_footprint", "osm", "microsoft_footprint", "none"]
Cooling = Literal["air", "rear_door", "liquid", "unknown"]


class _Located(BaseModel):
    """Shared position/provenance fields."""

    id: str
    name: str
    region: RegionName
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    in_steam: bool = False
    in_uten: bool = False
    sources: list[str] = Field(min_length=1)


class DataCenter(_Located):
    mw: float = Field(gt=0)
    mw_source: MwSource
    mw_confidence: MwConfidence
    cooling: Cooling = "unknown"
    # Buildings on one campus; carried for the UI, scoring stays per building.
    campus_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_confidence(cls, data: object) -> object:
        """Fill `mw_confidence` from `mw_source`; a supplied one must agree."""
        if not isinstance(data, dict) or "mw_source" not in data:
            return data
        expected = MW_CONFIDENCE_BY_SOURCE.get(data["mw_source"])
        if expected is None:
            return data  # unknown mw_source; the Literal below rejects it
        given = data.get("mw_confidence")
        if given is not None and given != expected:
            raise ValueError(
                f"mw_confidence {given!r} contradicts mw_source "
                f"{data['mw_source']!r} (expected {expected!r})"
            )
        return {**data, "mw_confidence": expected}

    @field_validator("id")
    @classmethod
    def _id_prefix(cls, v: str) -> str:
        if not v.startswith("dc_"):
            raise ValueError(f"data center id must start with 'dc_': {v!r}")
        return v


class Sink(_Located):
    cat: SinkCat
    # Annual *delivered* heat, kWh — see config.BOILER_EFF.
    demand_kwh: float = Field(gt=0)
    demand_source: DemandSource
    # Set when a measurement was overruled ("measured_fuel_near_zero").
    demand_note: str | None = None
    # What the building heats with today; gas unless something says otherwise.
    counterfactual: Counterfactual = "gas"
    # Ground footprint, and footprint × storeys, which is what a per-m2
    # intensity applies to.
    area_m2: float | None = Field(default=None, gt=0)
    area_source: AreaSource = "none"
    floor_area_m2: float | None = Field(default=None, gt=0)
    # District steam is the primary fuel; dropped before output unless the
    # region keeps them.
    steam_heated: bool = False

    @field_validator("id")
    @classmethod
    def _id_prefix(cls, v: str) -> str:
        if not v.startswith("s_"):
            raise ValueError(f"sink id must start with 's_': {v!r}")
        return v
