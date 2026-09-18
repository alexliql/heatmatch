//! Regenerate `tests/fixtures/baseline.json` — the results `tests/regression.rs`
//! pins for every shipped region. Run only when a change to those numbers is
//! intended and understood, and say which moved and why in the commit:
//! `cargo run --release --example baseline -p heatmatch-core`

#[path = "../tests/support/mod.rs"]
mod support;

use std::fs;

use heatmatch_core::{Econ, Engine, Region, Weights};
use serde_json::{json, Map, Value};

fn main() {
    let (dcs, sinks) = support::committed();

    // Keyed by name, not id: region-prefixed ids renumber, the physics does not.
    let names: std::collections::HashMap<String, String> =
        dcs.iter().map(|d| (d.id.clone(), d.name.clone())).collect();
    let engine = Engine::new(dcs, sinks, &[]).unwrap();

    let mut out = Map::new();
    // Every shipped region. Keep in step with `PINNED` in tests/regression.rs.
    for region in Region::ALL {
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

    let path = support::fixture("baseline.json");
    fs::write(
        &path,
        serde_json::to_string_pretty(&Value::Object(out)).unwrap() + "\n",
    )
    .unwrap();
    println!("wrote {}", path.display());
}
