"""Output schema — the contract with heatmatch-core (HEATMATCH.md §3.2).

Property names here must match the serde field names in core/heatmatch-core's
types.rs exactly. Nothing checks that automatically; changing a name here is a
breaking change to the engine.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ingest.config import RegionName, SinkCat

# `pnnl` from §3.2 is deliberately absent: the Atlas publishes no capacity
# field, so a MW value can never be sourced directly from it. Area-derived
# estimates are `atlas_sqft`; footprint-less rows fall back to `atlas_default`.
MwSource = Literal["atlas_sqft", "atlas_default", "pluto_estimate", "parcel_estimate", "manual"]
DemandSource = Literal["ll84_fuel", "footprint_estimate", "category_default"]
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
    cooling: Cooling = "unknown"

    @field_validator("id")
    @classmethod
    def _id_prefix(cls, v: str) -> str:
        if not v.startswith("dc_"):
            raise ValueError(f"data center id must start with 'dc_': {v!r}")
        return v


class Sink(_Located):
    cat: SinkCat
    demand_kwh: float = Field(gt=0)
    demand_source: DemandSource
    # True when LL84 shows district steam as the primary heating fuel; such
    # sinks are dropped before output, since their heat is already supplied.
    steam_heated: bool = False

    @field_validator("id")
    @classmethod
    def _id_prefix(cls, v: str) -> str:
        if not v.startswith("s_"):
            raise ValueError(f"sink id must start with 's_': {v!r}")
        return v
