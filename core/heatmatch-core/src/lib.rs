//! heatmatch scoring engine.
//!
//! Pure computation: given data centers and heat sinks, rank the data centers
//! by how usefully their waste heat could be delivered to nearby sinks. No
//! I/O, no globals, no randomness — the same inputs always produce the same
//! ranking (ties broken by id ascending).
//!
//! The model runs in layers: project to metres, index the sinks, pick the ones
//! a pipe could reach, judge each pairing on category, demand, distance and the
//! heat-pump lift it needs, share the data center's finite supply across them,
//! then overlay seasonality and cost it out.
#![forbid(unsafe_code)]

pub mod distance;
pub mod econ;
pub mod frame;
pub mod scoring;
pub mod season;
pub mod thermo;
pub mod types;
pub mod water;
pub mod weights;

pub use scoring::{Engine, EngineError};
pub use season::{ProfileOverrides, Profiles};
pub use thermo::{heat_pump, required_temp_c, supply_temp_c, HeatPump};
pub use types::{
    Contribution, Cooling, Counterfactual, DataCenter, Id, Match, MwConfidence, Region, Sink,
    SinkCat,
};
pub use weights::{
    CatWeights, ConfidenceWeights, Decay, DistanceModel, Econ, WaterPolicy, Weights, WeightsError,
};

/// Version of the scoring model, surfaced through wasm so the UI can show
/// which engine produced a result.
pub const MODEL_VERSION: &str = env!("CARGO_PKG_VERSION");
