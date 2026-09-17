"""Output schema — the contract with heatmatch-core (HEATMATCH.md §3.2).

Property names here must match the serde field names in core/heatmatch-core's
types.rs exactly. Nothing checks that automatically; changing a name here is a
breaking change to the engine.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ingest.config import MW_CONFIDENCE_BY_SOURCE, RegionName, SinkCat

# `pnnl` from §3.2 is deliberately absent: the Atlas publishes no capacity
# field, so a MW value can never be sourced directly from it. Area-derived
# estimates are `atlas_sqft`; footprint-less rows fall back to `atlas_default`.
MwSource = Literal[
    "atlas_sqft",
    "atlas_default",
    "pluto_estimate",
    "parcel_estimate",
    "manual",
    # Virginia publishes real capacities for some sites: an operator statement
    # is "reported", a county approval or utility filing is "filed".
    "reported",
    "filed",
]
# How far to trust `mw`. Derived from `mw_source` via config.confidence_for,
# never set on its own, so the two cannot disagree.
MwConfidence = Literal["reported", "filed", "parcel_estimate", "footprint_estimate"]
DemandSource = Literal[
    "ll84_fuel",
    # Annual intensity from NREL ComStock times floor area. Modelled, not
    # measured — the only option in states with no benchmarking disclosure.
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
    # Groups buildings on one campus, where the parcel data supports it.
    # Carried for the UI; scoring stays per building.
    campus_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_confidence(cls, data: object) -> object:
        """Fill `mw_confidence` from `mw_source`.

        Derived rather than passed in, so no source module can state a
        confidence that its own provenance does not support. A caller that
        supplies one anyway must agree with the mapping.
        """
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
    demand_kwh: float = Field(gt=0)
    demand_source: DemandSource
    # Floor or footprint area behind a modelled demand, when one is known.
    area_m2: float | None = Field(default=None, gt=0)
    area_source: AreaSource = "none"
    # True when LL84 shows district steam as the primary heating fuel; such
    # sinks are dropped before output, since their heat is already supplied.
    steam_heated: bool = False

    @field_validator("id")
    @classmethod
    def _id_prefix(cls, v: str) -> str:
        if not v.startswith("s_"):
            raise ValueError(f"sink id must start with 's_': {v!r}")
        return v
