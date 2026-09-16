//! Ad-hoc timing of `rank` over the committed dataset (HEATMATCH.md §4.7
//! budgets 50 ms in release). Run with:
//! `cargo run --release --example bench_rank -p heatmatch-core`

use std::fs;
use std::path::PathBuf;
use std::time::Instant;

use heatmatch_core::{DataCenter, Engine, Region, Sink, Weights};
use serde_json::{Map, Value};

fn flatten(feature: &Value) -> Map<String, Value> {
    let mut props = feature["properties"].as_object().cloned().unwrap();
    let c = feature["geometry"]["coordinates"].as_array().unwrap();
    props.insert("lon".into(), c[0].clone());
    props.insert("lat".into(), c[1].clone());
    props
}

fn features(prefix: &str) -> Vec<Value> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data");
    let path = fs::read_dir(dir)
        .unwrap()
        .filter_map(Result::ok)
        .map(|e| e.path())
        .find(|p| p.file_name().unwrap().to_str().unwrap().starts_with(prefix))
        .expect("asset");
    let raw: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    raw["features"].as_array().cloned().unwrap()
}

fn main() {
    let dcs: Vec<DataCenter> = features("datacenters.")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();
    let sinks: Vec<Sink> = features("sinks.")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();
    println!("dataset: {} data centers, {} sinks", dcs.len(), sinks.len());

    let build = Instant::now();
    let engine = Engine::new(dcs, sinks).unwrap();
    println!(
        "Engine::new  {:>8.3} ms",
        build.elapsed().as_secs_f64() * 1e3
    );

    let w = Weights::default_for(Region::Nyc);
    engine.rank(Region::Nyc, &w).unwrap(); // warm up

    let runs = 1000;
    let t = Instant::now();
    for _ in 0..runs {
        std::hint::black_box(engine.rank(Region::Nyc, &w).unwrap());
    }
    let per = t.elapsed().as_secs_f64() * 1e3 / runs as f64;
    println!(
        "rank         {per:>8.3} ms/call  (budget 50 ms) -> {}",
        if per < 50.0 { "PASS" } else { "FAIL" }
    );
}
