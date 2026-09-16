//! heatmatch scoring engine.
//!
//! Pure computation: given data centers and heat sinks, rank the data centers
//! by how usefully their waste heat could be delivered to nearby sinks. No
//! I/O, no globals, no randomness — the same inputs always produce the same
//! ranking (ties broken by id ascending).
//!
//! The model is built in layers. Present: projection, spatial indexing,
//! distance models and supply-constrained scoring. Still to come:
//! thermodynamics (heat-pump lift and COP), seasonality, economics and
//! water-crossing detection. Types carry only the fields the current model
//! actually computes.
#![forbid(unsafe_code)]

pub mod distance;
pub mod frame;
pub mod index;
pub mod scoring;
pub mod types;
pub mod weights;

pub use scoring::{Engine, EngineError};
pub use types::{Contribution, Cooling, DataCenter, Id, Match, Region, Sink, SinkCat};
pub use weights::{Decay, DistanceModel, Econ, WaterPolicy, Weights, WeightsError};

/// Version of the scoring model, surfaced through wasm so the UI can show
/// which engine produced a result.
pub const MODEL_VERSION: &str = env!("CARGO_PKG_VERSION");
