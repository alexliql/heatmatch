//! Contract A: the committed data must deserialize into core's types.
//!
//! This is the only check that catches drift between
//! `ingest/src/ingest/schema.py` and `src/types.rs`. Nothing else would: a
//! renamed property or a new sink category compiles fine on both sides and
//! only shows up as an empty map in the browser.
//!
//! Note that `lat`/`lon` live in the GeoJSON *geometry*, not in `properties`,
//! so the test merges them in exactly as the wasm loader will have to.

mod support;

use heatmatch_core::{DataCenter, Econ, Engine, Region, Sink, Weights};
use serde_json::Value;
use support::{data_asset, features, flatten};

#[test]
fn committed_datacenters_deserialize() {
    let feats = features(&data_asset("datacenters."));
    assert!(!feats.is_empty(), "no data centers committed");

    for f in &feats {
        let dc: DataCenter =
            serde_json::from_value(Value::Object(flatten(f))).unwrap_or_else(|e| {
                panic!(
                    "data center {} failed Contract A: {e}",
                    f["properties"]["id"]
                )
            });
        assert!(dc.mw > 0.0, "{} has non-positive mw", dc.id);
        assert!(dc.id.starts_with("dc_"));
    }
}

#[test]
fn committed_sinks_deserialize() {
    let feats = features(&data_asset("sinks."));
    assert!(!feats.is_empty(), "no sinks committed");

    for f in &feats {
        let sink: Sink = serde_json::from_value(Value::Object(flatten(f)))
            .unwrap_or_else(|e| panic!("sink {} failed Contract A: {e}", f["properties"]["id"]));
        assert!(sink.demand_kwh > 0.0, "{} has non-positive demand", sink.id);
        assert!(sink.id.starts_with("s_"));
    }
}

/// Ingest drops steam-heated sinks before writing — except in Seattle, which
/// keeps Enwave's customers as candidate offtakers of a network-level swap.
/// Anywhere else, one reaching core means the drop rule broke.
#[test]
fn steam_heated_sinks_ship_only_where_the_region_keeps_them() {
    let mut kept_in_seattle = 0;
    for f in features(&data_asset("sinks.")) {
        if f["properties"]["steam_heated"] != Value::Bool(true) {
            continue;
        }
        assert_eq!(
            f["properties"]["region"],
            Value::String("seattle".into()),
            "steam-heated sink {} should have been filtered by ingest",
            f["properties"]["id"]
        );
        // And it must say so on the map as well as in the fuel data.
        assert_eq!(
            f["properties"]["in_steam"],
            Value::Bool(true),
            "{}",
            f["properties"]["id"]
        );
        kept_in_seattle += 1;
    }
    assert!(
        kept_in_seattle > 0,
        "Seattle ships no steam-heated sinks; the keep rule broke"
    );
}

/// End to end on the real data: the engine must build and rank it.
#[test]
fn engine_ranks_the_committed_dataset() {
    let (dcs, sinks) = support::committed();

    let expected: Vec<(Region, usize)> = Region::ALL
        .iter()
        .map(|r| (*r, dcs.iter().filter(|d| d.region == *r).count()))
        .collect();

    let engine = Engine::new(dcs, sinks, &[]).expect("engine build");

    for (region, count) in expected {
        let ranked = engine
            .rank(
                region,
                &Weights::default_for(region),
                &Econ::default_for(region),
            )
            .unwrap();

        assert_eq!(ranked.len(), count, "{region:?} data center count");
        assert!(
            ranked.windows(2).all(|p| p[0].score >= p[1].score),
            "{region:?} not sorted by score"
        );
        // The whole point of the dataset is that some site scores; an all-zero
        // ranking would mean the radius or the projection is wrong.
        if count > 0 {
            assert!(
                ranked[0].score > 0.0,
                "{region:?} top data center scored zero"
            );
        }
    }
}
