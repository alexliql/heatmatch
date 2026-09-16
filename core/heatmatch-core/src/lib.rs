//! heatmatch scoring engine.
//!
//! Pure computation: given data centers, heat sinks and water polygons, rank
//! the data centers by how usefully their waste heat could be delivered to
//! nearby sinks. No I/O, no globals, no randomness — the same inputs always
//! produce the same ranking (ties broken by id ascending).
//!
//! Modules land in phase order; see HEATMATCH.md §8.
#![forbid(unsafe_code)]

/// Version of the scoring model, surfaced through wasm so the UI can show
/// which engine produced a result.
pub const MODEL_VERSION: &str = env!("CARGO_PKG_VERSION");
