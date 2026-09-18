//! Fixture and committed-data loading shared by the tests and examples.
//!
//! Each binary compiles this separately, so unused helpers look dead.
#![allow(dead_code)]

use std::fs;
use std::path::{Path, PathBuf};

use heatmatch_core::{DataCenter, Engine, Sink};
use serde::de::DeserializeOwned;
use serde_json::{Map, Value};

/// Flatten a GeoJSON point feature into the object core's types expect:
/// coordinates live in `geometry`, everything else in `properties`.
pub fn flatten(feature: &Value) -> Map<String, Value> {
    let mut props = feature["properties"]
        .as_object()
        .cloned()
        .expect("properties");
    let c = feature["geometry"]["coordinates"]
        .as_array()
        .expect("coordinates");
    props.insert("lon".into(), c[0].clone());
    props.insert("lat".into(), c[1].clone());
    props
}

pub fn features(path: &Path) -> Vec<Value> {
    let raw: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    raw["features"].as_array().cloned().unwrap()
}

pub fn load<T: DeserializeOwned>(path: &Path) -> Vec<T> {
    features(path)
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect()
}

pub fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

pub fn data_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data")
}

/// The single hash-named build of a committed asset, e.g. `datacenters.ab12cd34.geojson`.
pub fn data_asset(prefix: &str) -> PathBuf {
    let mut hits: Vec<PathBuf> = fs::read_dir(data_dir())
        .expect("data/ must exist")
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| {
            p.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with(prefix) && n.ends_with(".geojson"))
        })
        .collect();
    hits.sort();
    assert_eq!(
        hits.len(),
        1,
        "expected exactly one {prefix} asset, found {hits:?}"
    );
    hits.pop().unwrap()
}

pub fn mini_dcs() -> Vec<DataCenter> {
    load(&fixture("mini_dcs.geojson"))
}

pub fn mini_sinks() -> Vec<Sink> {
    load(&fixture("mini_sinks.geojson"))
}

pub fn mini_engine() -> Engine {
    mini_engine_with_water(&[])
}

pub fn mini_engine_with_water(water: &[geo::Polygon<f64>]) -> Engine {
    Engine::new(mini_dcs(), mini_sinks(), water).expect("fixture engine")
}

/// Every committed data center and sink.
pub fn committed() -> (Vec<DataCenter>, Vec<Sink>) {
    (
        load(&data_asset("datacenters.")),
        load(&data_asset("sinks.")),
    )
}
