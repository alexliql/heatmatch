//! Shipped regions' results must not move.
//!
//! Adding a region changes ids and file hashes, so "byte-identical output" is
//! not a testable claim. This is the claim that matters instead: for every
//! data center in a region already shipped, the physics and the economics come
//! out exactly as they did before. If this fails, a change meant to be additive
//! was not — or it was meant to move numbers, in which case the fixture is
//! regenerated and the commit says which numbers and why.
//!
//! Rows are keyed by name rather than id, because region-prefixed ids renumber.
//! Regenerate deliberately, never reflexively:
//! `cargo run --release --example baseline -p heatmatch-core`

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

/// Regions the snapshot pins. Extended as regions ship; each addition is a
/// deliberate regeneration of the fixture.
const PINNED: [Region; 3] = [Region::Nyc, Region::Upstate, Region::Nova];

fn baseline() -> Map<String, Value> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/baseline.json");
    serde_json::from_str(&fs::read_to_string(path).expect("baseline.json")).unwrap()
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
fn shipped_regions_are_unchanged() {
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
    let mut failures: Vec<String> = Vec::new();

    for region in PINNED {
        let Some(rows) = expected.get(region.as_str()).and_then(Value::as_array) else {
            failures.push(format!(
                "{region:?}: not in the baseline (regenerate the fixture)"
            ));
            continue;
        };
        let want: Vec<Row> = sorted(
            rows.iter()
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

        // Every difference is collected before failing, per region, so a
        // change that was meant to touch one region shows at a glance
        // whether it touched the others.
        if got.len() != want.len() {
            failures.push(format!(
                "{region:?}: data center count {} -> {}",
                want.len(),
                got.len()
            ));
            continue;
        }
        let moved: Vec<String> = got
            .iter()
            .zip(&want)
            .filter_map(|(g, w)| {
                if g.0 != w.0 {
                    Some(format!("  order: expected {:?}, got {:?}", w.0, g.0))
                } else if g.1 != w.1 {
                    Some(format!("  {}: {:?} -> {:?}", g.0, w.1, g.1))
                } else {
                    None
                }
            })
            .collect();
        if !moved.is_empty() {
            failures.push(format!(
                "{region:?}: {} of {} sites moved (score, supply, demand, util, \
                 delivered, capex, savings, payback)\n{}",
                moved.len(),
                got.len(),
                moved.join("\n")
            ));
        }
    }

    assert!(
        failures.is_empty(),
        "results differ from the committed baseline:\n{}",
        failures.join("\n")
    );
}
