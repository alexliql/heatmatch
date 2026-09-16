//! wasm-bindgen surface for heatmatch-core. See HEATMATCH.md §5.
#![forbid(unsafe_code)]

use wasm_bindgen::prelude::*;

/// Engine version string, used by the web app's loading state to confirm the
/// wasm bundle and the data manifest were built from the same commit.
#[wasm_bindgen]
pub fn version() -> String {
    heatmatch_core::MODEL_VERSION.to_string()
}
