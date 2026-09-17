//! wasm-bindgen surface for heatmatch-core (HEATMATCH.md §5).
//!
//! GeoJSON is parsed once, in the constructor: the browser holds the engine for
//! the life of the page and every slider move re-ranks from the parsed data,
//! so parsing per call would dominate the cost of ranking.
#![forbid(unsafe_code)]

use geo::{Coord, LineString, Polygon};
use geojson::{GeoJson, Value as GeoValue};
use heatmatch_core::{DataCenter, Econ, Engine, ProfileOverrides, Region, Sink, Weights};
use serde::de::DeserializeOwned;
use serde_json::{Map, Value};
use std::collections::HashMap;
use wasm_bindgen::prelude::*;

/// Turn a JS error into something a user can act on.
fn err(context: &str, e: impl std::fmt::Display) -> JsError {
    JsError::new(&format!("{context}: {e}"))
}

fn parse_region(s: &str) -> Result<Region, JsError> {
    Region::ALL
        .into_iter()
        .find(|r| r.as_str() == s)
        .ok_or_else(|| {
            let known: Vec<String> = Region::ALL
                .iter()
                .map(|r| format!("{:?}", r.as_str()))
                .collect();
            JsError::new(&format!(
                "unknown region {s:?}; expected one of {}",
                known.join(", ")
            ))
        })
}

/// Per-region seasonal profiles, as the `profiles` bundle asset carries them:
/// `{"nova": {"hospital": [...12 shares...], ...}}`. Regions and categories it
/// omits keep the built-in shapes.
fn parse_profiles(raw: &str) -> Result<HashMap<Region, ProfileOverrides>, JsError> {
    if raw.trim().is_empty() {
        return Ok(HashMap::new());
    }
    let by_name: HashMap<String, ProfileOverrides> =
        serde_json::from_str(raw).map_err(|e| err("parsing profiles", e))?;
    by_name
        .into_iter()
        .map(|(name, p)| parse_region(&name).map(|r| (r, p)))
        .collect()
}

/// Flatten a point feature into the shape core's types deserialize from.
///
/// Coordinates live in the geometry while everything else lives in properties,
/// so the two have to be merged before serde sees them.
fn point_features<T: DeserializeOwned>(raw: &str, what: &str) -> Result<Vec<T>, JsError> {
    let parsed: GeoJson = raw
        .parse()
        .map_err(|e| err(&format!("parsing {what}"), e))?;
    let GeoJson::FeatureCollection(fc) = parsed else {
        return Err(JsError::new(&format!("{what} must be a FeatureCollection")));
    };

    let mut out = Vec::with_capacity(fc.features.len());
    for feature in fc.features {
        let Some(geometry) = feature.geometry.as_ref() else {
            continue;
        };
        let GeoValue::Point(coords) = &geometry.value else {
            continue;
        };
        let mut props: Map<String, Value> = feature.properties.unwrap_or_default();
        props.insert("lon".into(), coords[0].into());
        props.insert("lat".into(), coords[1].into());
        out.push(
            serde_json::from_value(Value::Object(props))
                .map_err(|e| err(&format!("reading {what}"), e))?,
        );
    }
    Ok(out)
}

/// Exterior rings of every polygon in a collection, in lon/lat.
fn water_polygons(raw: &str) -> Result<Vec<Polygon<f64>>, JsError> {
    if raw.trim().is_empty() {
        return Ok(Vec::new());
    }
    let parsed: GeoJson = raw.parse().map_err(|e| err("parsing water", e))?;
    let GeoJson::FeatureCollection(fc) = parsed else {
        return Err(JsError::new("water must be a FeatureCollection"));
    };

    let ring = |r: &Vec<Vec<f64>>| {
        LineString::from(
            r.iter()
                .map(|p| Coord { x: p[0], y: p[1] })
                .collect::<Vec<_>>(),
        )
    };

    let mut out = Vec::new();
    for feature in fc.features {
        let Some(geometry) = feature.geometry else {
            continue;
        };
        match geometry.value {
            GeoValue::Polygon(rings) => {
                if let Some(first) = rings.first() {
                    out.push(Polygon::new(ring(first), vec![]));
                }
            }
            GeoValue::MultiPolygon(polys) => {
                for rings in polys {
                    if let Some(first) = rings.first() {
                        out.push(Polygon::new(ring(first), vec![]));
                    }
                }
            }
            _ => {}
        }
    }
    Ok(out)
}

#[wasm_bindgen]
pub struct WasmEngine {
    inner: Engine,
}

#[wasm_bindgen]
impl WasmEngine {
    /// Build the engine from the data assets. `water_geojson` and
    /// `profiles_json` may be empty strings when those assets are not published.
    #[wasm_bindgen(constructor)]
    pub fn new(
        dcs_geojson: &str,
        sinks_geojson: &str,
        water_geojson: &str,
        profiles_json: &str,
    ) -> Result<WasmEngine, JsError> {
        // Without this a Rust panic surfaces in the console as "unreachable".
        console_error_panic_hook::set_once();

        let dcs: Vec<DataCenter> = point_features(dcs_geojson, "data centers")?;
        let sinks: Vec<Sink> = point_features(sinks_geojson, "sinks")?;
        let water = water_polygons(water_geojson)?;
        let profiles = parse_profiles(profiles_json)?;

        Ok(Self {
            inner: Engine::with_profiles(dcs, sinks, &water, &profiles)
                .map_err(|e| err("building engine", e))?,
        })
    }

    /// Rank every data center in a region. `weights` and `econ` are the
    /// generated `Weights`/`Econ` shapes, not loose objects.
    pub fn rank(&self, region: &str, weights: Weights, econ: Econ) -> Result<JsValue, JsError> {
        let ranked = self
            .inner
            .rank(parse_region(region)?, &weights, &econ)
            .map_err(|e| err("rank", e))?;
        to_js(&ranked)
    }

    pub fn explain(&self, dc_id: &str, weights: Weights) -> Result<JsValue, JsError> {
        let contribs = self
            .inner
            .explain(dc_id, &weights)
            .map_err(|e| err("explain", e))?;
        to_js(&contribs)
    }

    /// Monthly demand shape per sink category for one region, so the UI can
    /// draw the supply-vs-demand strip without duplicating the table.
    ///
    /// An instance method, not a static one: a region may override the shapes
    /// from the data bundle, so the answer depends on what was loaded.
    pub fn profiles(&self, region: &str) -> Result<JsValue, JsError> {
        let map: std::collections::BTreeMap<String, [f32; 12]> = self
            .inner
            .profiles(parse_region(region)?)
            .into_iter()
            .map(|(cat, p)| {
                let key = serde_json::to_value(cat)
                    .ok()
                    .and_then(|v| v.as_str().map(str::to_owned))
                    .unwrap_or_default();
                (key, p)
            })
            .collect();
        to_js(&map)
    }

    pub fn default_weights(region: &str) -> Result<Weights, JsError> {
        Ok(Weights::default_for(parse_region(region)?))
    }

    pub fn default_econ(region: &str) -> Result<Econ, JsError> {
        Ok(Econ::default_for(parse_region(region)?))
    }

    pub fn version() -> String {
        heatmatch_core::MODEL_VERSION.to_string()
    }
}

/// Serialize with maps as plain objects, which is what JS callers expect for
/// the per-category weight table.
fn to_js<T: serde::Serialize>(value: &T) -> Result<JsValue, JsError> {
    let ser = serde_wasm_bindgen::Serializer::new().serialize_maps_as_objects(true);
    value
        .serialize(&ser)
        .map_err(|e| err("serializing result", e))
}
