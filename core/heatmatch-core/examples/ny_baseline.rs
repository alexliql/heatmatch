//! Regenerate `tests/fixtures/ny_baseline.json` — the New York results that
//! `tests/regression.rs` pins. Run only when a change to the NY numbers is
//! intended and understood:
//! `cargo run --release --example ny_baseline -p heatmatch-core`

use std::fs;
use std::path::PathBuf;

use heatmatch_core::{DataCenter, Econ, Engine, Region, Sink, Weights};
use serde_json::{json, Map, Value};

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

    // Keyed by name, not id: region-prefixed ids renumber, the physics does not.
    let names: std::collections::HashMap<String, String> =
        dcs.iter().map(|d| (d.id.clone(), d.name.clone())).collect();
    let engine = Engine::new(dcs, sinks, &[]).unwrap();

    let mut out = Map::new();
    for region in [Region::Nyc, Region::Upstate] {
        let ranked = engine
            .rank(
                region,
                &Weights::default_for(region),
                &Econ::default_for(region),
            )
            .unwrap();
        let rows: Vec<Value> = ranked
            .iter()
            .map(|m| {
                json!({
                    "name": names[&m.dc],
                    "score": m.score,
                    "supply_mwh": m.supply_mwh,
                    "demand_mwh_in_radius": m.demand_mwh_in_radius,
                    "utilization": m.utilization,
                    "delivered_mwh": m.delivered_mwh,
                    "capex": m.capex,
                    "annual_savings": m.annual_savings,
                    "payback_yrs": m.payback_yrs,
                })
            })
            .collect();
        out.insert(region.as_str().to_string(), Value::Array(rows));
    }

    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/ny_baseline.json");
    fs::write(
        &path,
        serde_json::to_string_pretty(&Value::Object(out)).unwrap() + "\n",
    )
    .unwrap();
    println!("wrote {}", path.display());
}
