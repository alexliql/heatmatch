//! The New York results must not move.
//!
//! Adding a region changes ids and file hashes, so "byte-identical output" is
//! not a testable claim. This is the claim that matters instead: for every New
//! York data center, the physics and the economics come out exactly as they did
//! before. If this fails, a change meant to be additive was not.
//!
//! Rows are keyed by name rather than id, because region-prefixed ids renumber.
//! Regenerate deliberately, never reflexively:
//! `cargo run --release --example ny_baseline -p heatmatch-core`

use std::fs;
use std::path::PathBuf;

use heatmatch_core::{DataCenter, Econ, Engine, Region, Sink, Weights};
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

/// Comparable row: the numbers a user actually reads, plus the name.
///
/// Held as `f32` because that is what the engine computes in. Widening to f64
/// for JSON and narrowing back is lossless; comparing as f64 is not, because
/// the shortest decimal that round-trips an f64 is not the one that round-trips
/// the f32 it came from.
type Row = (String, Vec<Option<f32>>);

fn number(v: &Value) -> Option<f32> {
    if v.is_null() {
        None
    } else {
        Some(v.as_f64().expect("numeric field") as f32)
    }
}

fn baseline() -> Map<String, Value> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/ny_baseline.json");
    serde_json::from_str(&fs::read_to_string(path).expect("ny_baseline.json")).unwrap()
}

fn sorted(mut rows: Vec<Row>) -> Vec<Row> {
    // Score descending is the engine's own order; name breaks exact ties, which
    // id-ascending would otherwise resolve differently after a renumber.
    rows.sort_by(|a, b| {
        b.1[0]
            .partial_cmp(&a.1[0])
            .unwrap()
            .then_with(|| a.0.cmp(&b.0))
    });
    rows
}

#[test]
fn new_york_results_are_unchanged() {
    let dcs: Vec<DataCenter> = features("datacenters.")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();
    let sinks: Vec<Sink> = features("sinks.")
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();
    let names: std::collections::HashMap<String, String> =
        dcs.iter().map(|d| (d.id.clone(), d.name.clone())).collect();
    let engine = Engine::new(dcs, sinks, &[]).unwrap();

    let expected = baseline();

    for region in [Region::Nyc, Region::Upstate] {
        let want: Vec<Row> = sorted(
            expected[region.as_str()]
                .as_array()
                .expect("region in baseline")
                .iter()
                .map(|r| {
                    (
                        r["name"].as_str().unwrap().to_string(),
                        vec![
                            number(&r["score"]),
                            number(&r["supply_mwh"]),
                            number(&r["demand_mwh_in_radius"]),
                            number(&r["utilization"]),
                            number(&r["delivered_mwh"]),
                            number(&r["capex"]),
                            number(&r["annual_savings"]),
                            number(&r["payback_yrs"]),
                        ],
                    )
                })
                .collect(),
        );

        let got: Vec<Row> = sorted(
            engine
                .rank(
                    region,
                    &Weights::default_for(region),
                    &Econ::default_for(region),
                )
                .unwrap()
                .iter()
                .map(|m| {
                    (
                        names[&m.dc].clone(),
                        vec![
                            Some(m.score),
                            Some(m.supply_mwh),
                            Some(m.demand_mwh_in_radius),
                            Some(m.utilization),
                            Some(m.delivered_mwh),
                            Some(m.capex),
                            Some(m.annual_savings),
                            m.payback_yrs,
                        ],
                    )
                })
                .collect(),
        );

        assert_eq!(
            got.len(),
            want.len(),
            "{region:?}: data center count changed"
        );
        for (g, w) in got.iter().zip(&want) {
            assert_eq!(g.0, w.0, "{region:?}: rank order changed");
            assert_eq!(
                g.1, w.1,
                "{region:?}: numbers changed for {} (score, supply, demand, util, \
                 delivered, capex, savings, payback)",
                g.0
            );
        }
    }
}
