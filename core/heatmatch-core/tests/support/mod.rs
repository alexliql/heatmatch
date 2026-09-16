//! Shared fixture loading for the integration tests.

use std::fs;
use std::path::PathBuf;

use heatmatch_core::{DataCenter, Engine, Sink};
use serde_json::{Map, Value};

/// Flatten a GeoJSON point feature into the object core's types expect:
/// coordinates live in `geometry`, everything else in `properties`.
pub fn flatten(feature: &Value) -> Map<String, Value> {
    let mut props = feature["properties"]
        .as_object()
        .cloned()
        .expect("properties");
    let coords = feature["geometry"]["coordinates"]
        .as_array()
        .expect("coordinates");
    props.insert("lon".into(), coords[0].clone());
    props.insert("lat".into(), coords[1].clone());
    props
}

fn load(name: &str) -> Vec<Value> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    let raw: Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    raw["features"].as_array().cloned().unwrap()
}

pub fn mini_dcs() -> Vec<DataCenter> {
    load("mini_dcs.geojson")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect()
}

pub fn mini_sinks() -> Vec<Sink> {
    load("mini_sinks.geojson")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect()
}

pub fn mini_engine() -> Engine {
    Engine::new(mini_dcs(), mini_sinks()).expect("fixture engine")
}
