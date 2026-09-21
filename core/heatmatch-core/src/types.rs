//! Core domain types.
//!
//! The serde field names here are a contract with the ingest pipeline: they
//! must match the GeoJSON `properties` keys that `ingest/src/ingest/schema.py`
//! emits. `tests/contract.rs` checks that against the committed data files,
//! because nothing else would catch a rename until the map came up empty.

use enum_map::Enum;
use serde::{Deserialize, Serialize};
use smallvec::SmallVec;

/// Stable feature identifier, e.g. `dc_0003` or `s_00142`.
pub type Id = String;

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Serialize, Deserialize, Enum)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
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

impl SinkCat {
    pub const ALL: [SinkCat; 10] = [
        SinkCat::Pool,
        SinkCat::Hospital,
        SinkCat::University,
        SinkCat::School,
        SinkCat::Greenhouse,
        SinkCat::Brewery,
        SinkCat::Wwtp,
        SinkCat::Office,
        SinkCat::ResidentialMultifamily,
        SinkCat::Hotel,
    ];
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum Cooling {
    Air,
    RearDoor,
    Liquid,
    /// What nearly every real site reports, since no public source carries it.
    #[default]
    Unknown,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Serialize, Deserialize, Enum)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum Region {
    Nyc,
    Upstate,
    /// Northern Virginia: Loudoun, Prince William, Fairfax, Arlington,
    /// Alexandria, Manassas and Manassas Park.
    Nova,
    /// King, Snohomish and Pierce counties.
    Seattle,
    /// Portland metro: Washington, Multnomah and Clackamas counties. The data
    /// centers are in Hillsboro.
    Pdx,
    /// Silicon Valley: Santa Clara, San Mateo and Alameda counties.
    Svy,
    /// Los Angeles and Orange counties.
    La,
    /// Sacramento and Placer counties — the inland control for California:
    /// same measured-data source as the coast, colder winters, cheaper power.
    Sac,
}

impl Region {
    pub const ALL: [Region; 8] = [
        Region::Nyc,
        Region::Upstate,
        Region::Nova,
        Region::Seattle,
        Region::Pdx,
        Region::Svy,
        Region::La,
        Region::Sac,
    ];

    /// Projection origin, matching the `origin` values in ingest's config.
    pub fn origin(self) -> (f64, f64) {
        match self {
            Region::Nyc => (40.7128, -74.0060),
            Region::Upstate => (42.90, -75.50),
            Region::Nova => (39.02, -77.45),
            Region::Seattle => (47.61, -122.33),
            Region::Pdx => (45.52, -122.90),
            Region::Svy => (37.38, -121.95),
            Region::La => (34.05, -118.25),
            Region::Sac => (38.58, -121.35),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Region::Nyc => "nyc",
            Region::Upstate => "upstate",
            Region::Nova => "nova",
            Region::Seattle => "seattle",
            Region::Pdx => "pdx",
            Region::Svy => "svy",
            Region::La => "la",
            Region::Sac => "sac",
        }
    }
}

/// How much to trust a data center's stated capacity.
///
/// New York's capacities are all derived from floor area, so the distinction
/// only starts to matter in Virginia, where county approvals and utility
/// filings publish real numbers for some sites and nothing at all for others.
/// Ranking discounts the weaker grades; the reported `supply_mwh` does not.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum MwConfidence {
    /// The operator published it.
    Reported,
    /// A county approval or utility filing states it.
    Filed,
    /// Derived from assessed building area on a matched parcel.
    ParcelEstimate,
    /// Derived from a footprint with no parcel match — the weakest grade, and
    /// the default, so an unlabelled feature is never flattered.
    #[default]
    FootprintEstimate,
}

impl MwConfidence {
    pub const ALL: [MwConfidence; 4] = [
        MwConfidence::Reported,
        MwConfidence::Filed,
        MwConfidence::ParcelEstimate,
        MwConfidence::FootprintEstimate,
    ];
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
    /// Defaults to the weakest grade, so a feature predating this field is
    /// treated as a guess rather than silently trusted.
    #[serde(default)]
    pub mw_confidence: MwConfidence,
    /// Groups buildings that share one campus, where ingest could establish it.
    /// Carried through for the UI; scoring stays per building.
    #[serde(default)]
    pub campus_id: Option<String>,
    #[serde(default)]
    pub in_steam: bool,
    #[serde(default)]
    pub in_uten: bool,
}

/// What a sink heats with today — and therefore what a heat network would
/// displace.
///
/// The economics price avoided cost per delivered MWh, and that depends
/// entirely on this: displacing a gas boiler saves gas at boiler efficiency,
/// displacing resistance heat saves a full MWh of electricity, and displacing
/// a heat pump saves only the third or so of a MWh the pump would have drawn.
/// In California and Seattle a resistance-heated building is the best sink on
/// the map; without this field the model would call it worthless.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum Counterfactual {
    /// A gas (or oil, or propane) boiler or furnace. The default, and what
    /// every New York sink is, so their economics do not move.
    #[default]
    Gas,
    ElectricResistance,
    HeatPump,
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
    /// Annual thermal demand in kWh, as *delivered heat*. Converted to MWh on
    /// the way into scoring.
    pub demand_kwh: f32,
    #[serde(default)]
    pub counterfactual: Counterfactual,
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
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct Contribution {
    #[cfg_attr(feature = "ts", tsify(type = "string"))]
    pub sink: Id,
    pub cat: SinkCat,
    /// What this sink heats with today, so the detail view can say what the
    /// connection would displace.
    pub counterfactual: Counterfactual,
    /// Straight-line distance.
    pub dist_m: f32,
    /// Distance the pipe actually runs, per the distance model, including any
    /// water-crossing penalty.
    pub pipe_m: f32,
    pub crosses_water: bool,
    pub hp_required: bool,
    /// Units of heat per unit of electricity; infinite when no heat pump is
    /// needed.
    pub cop: f32,
    /// Heat this sink is allocated, after the supply budget is shared out.
    pub delivered_mwh: f32,
    /// Zero when the sink is in radius but received no allocation, so that
    /// `rank` scores equal the sum of `explain` scores for the same data center.
    pub score: f32,
}

/// A ranked data center.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct Match {
    #[cfg_attr(feature = "ts", tsify(type = "string"))]
    pub dc: Id,
    pub region: Region,
    pub score: f32,
    pub supply_mwh: f32,
    pub demand_mwh_in_radius: f32,
    /// Share of the year's waste heat that finds a home, after seasonality.
    pub utilization: f32,
    pub delivered_mwh: f32,
    pub capex: f32,
    pub annual_savings: f32,
    /// `None` when annual savings are not positive, so payback never reports
    /// a negative or infinite number of years.
    pub payback_yrs: Option<f32>,
    #[cfg_attr(feature = "ts", tsify(type = "Contribution[]"))]
    pub top: SmallVec<[Contribution; 5]>,
}
