//! Core domain types (HEATMATCH.md §4.1).
//!
//! The serde field names here are a contract with the ingest pipeline: they
//! must match the GeoJSON `properties` keys that `ingest/src/ingest/schema.py`
//! emits. `tests/contract.rs` checks that against the committed data files,
//! because nothing else would catch a rename until the map came up empty.

use enum_map::Enum;
use serde::{Deserialize, Serialize};
use smallvec::SmallVec;

pub type Id = String;

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Serialize, Deserialize, Enum)]
#[serde(rename_all = "snake_case")]
pub enum SinkCat {
    Pool,
    Hospital,
    University,
    School,
    Greenhouse,
    Brewery,
    Wwtp,
    Office,
    ResidentialMultifamily,
    Hotel,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Cooling {
    Air,
    RearDoor,
    Liquid,
    /// What nearly every real site reports, since no public source carries it.
    #[default]
    Unknown,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Region {
    Nyc,
    Upstate,
}

impl Region {
    pub const ALL: [Region; 2] = [Region::Nyc, Region::Upstate];

    /// Projection origin, matching the `origin` values in ingest's config.
    pub fn origin(self) -> (f64, f64) {
        match self {
            Region::Nyc => (40.7128, -74.0060),
            Region::Upstate => (42.90, -75.50),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Region::Nyc => "nyc",
            Region::Upstate => "upstate",
        }
    }
}

/// A waste-heat source. Extra ingest-only fields (`mw_source`, `sources`) are
/// ignored by serde rather than rejected.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DataCenter {
    pub id: Id,
    pub name: String,
    pub region: Region,
    pub lat: f64,
    pub lon: f64,
    pub mw: f32,
    #[serde(default)]
    pub cooling: Cooling,
    #[serde(default)]
    pub in_steam: bool,
    #[serde(default)]
    pub in_uten: bool,
}

/// A potential heat consumer.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Sink {
    pub id: Id,
    pub name: String,
    pub region: Region,
    pub lat: f64,
    pub lon: f64,
    pub cat: SinkCat,
    /// Annual thermal demand in kWh. Converted to MWh on the way into scoring.
    pub demand_kwh: f32,
    #[serde(default)]
    pub in_steam: bool,
    #[serde(default)]
    pub in_uten: bool,
}

impl Sink {
    /// Annual demand in MWh, the unit everything downstream works in.
    pub fn demand_mwh(&self) -> f32 {
        self.demand_kwh / 1000.0
    }
}

/// One data center → sink pairing, as reported by `explain`.
///
/// `crosses_water`, `hp_required` and `cop` arrive with the water and
/// thermodynamics models; they are omitted rather than stubbed so no caller
/// can read a value this phase does not actually compute.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct Contribution {
    pub sink: Id,
    pub cat: SinkCat,
    /// Straight-line distance.
    pub dist_m: f32,
    /// Distance the pipe actually runs, per the distance model.
    pub pipe_m: f32,
    /// Heat this sink is allocated, after the supply budget is shared out.
    pub delivered_mwh: f32,
    /// Zero when the sink is in radius but received no allocation, so that
    /// `rank` scores equal the sum of `explain` scores for the same data center.
    pub score: f32,
}

/// A ranked data center.
///
/// `capex`, `annual_savings` and `payback_yrs` arrive with the economics
/// model. `utilization` and `delivered_mwh` are annual here; seasonality
/// refines them to a monthly supply/demand overlap later.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct Match {
    pub dc: Id,
    pub region: Region,
    pub score: f32,
    pub supply_mwh: f32,
    pub demand_mwh_in_radius: f32,
    pub utilization: f32,
    pub delivered_mwh: f32,
    pub top: SmallVec<[Contribution; 5]>,
}
