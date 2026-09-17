//! Contract A: the committed data must deserialize into core's types.
//!
//! This is the only check that catches drift between
//! `ingest/src/ingest/schema.py` and `src/types.rs`. Nothing else would: a
//! renamed property or a new sink category compiles fine on both sides and
//! only shows up as an empty map in the browser.
//!
//! Note that `lat`/`lon` live in the GeoJSON *geometry*, not in `properties`,
//! so the test merges them in exactly as the wasm loader will have to.

use std::fs;
use std::path::PathBuf;

use heatmatch_core::{DataCenter, Econ, Engine, Region, Sink, Weights};
use serde_json::{Map, Value};

fn data_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data")
}

/// Find the single hash-named build of an asset, e.g. `datacenters.ab12cd34.geojson`.
fn find_asset(prefix: &str) -> PathBuf {
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

/// Flatten a GeoJSON point feature into the object core's types expect.
fn flatten(feature: &Value) -> Map<String, Value> {
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

fn features(path: PathBuf) -> Vec<Value> {
    let raw: Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    raw["features"].as_array().cloned().unwrap()
}

#[test]
fn committed_datacenters_deserialize() {
    let feats = features(find_asset("datacenters."));
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
    let feats = features(find_asset("sinks."));
    assert!(!feats.is_empty(), "no sinks committed");

    for f in &feats {
        let sink: Sink = serde_json::from_value(Value::Object(flatten(f)))
            .unwrap_or_else(|e| panic!("sink {} failed Contract A: {e}", f["properties"]["id"]));
        assert!(sink.demand_kwh > 0.0, "{} has non-positive demand", sink.id);
        assert!(sink.id.starts_with("s_"));
    }
}

/// Ingest drops steam-heated sinks before writing, so none should reach core.
#[test]
fn no_steam_heated_sinks_were_shipped() {
    for f in features(find_asset("sinks.")) {
        assert_ne!(
            f["properties"]["steam_heated"],
            Value::Bool(true),
            "steam-heated sink {} should have been filtered by ingest",
            f["properties"]["id"]
        );
    }
}

/// End to end on the real data: the engine must build and rank it.
#[test]
fn engine_ranks_the_committed_dataset() {
    let dcs: Vec<DataCenter> = features(find_asset("datacenters."))
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();
    let sinks: Vec<Sink> = features(find_asset("sinks."))
        .iter()
        .map(|f| serde_json::from_value(Value::Object(flatten(f))).unwrap())
        .collect();

    // Counted per region: `rank` covers one region at a time, and the dataset
    // now spans both.
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
