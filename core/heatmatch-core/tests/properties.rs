//! Invariants that must hold for any inputs (HEATMATCH.md §4.7).
//!
//! These catch the failures a golden test cannot: a golden test pins one
//! scenario, while these assert the model's shape over the whole input space.

mod support;

use heatmatch_core::{
    distance::{euclid, pipe_length, search_radius},
    frame::LocalFrame,
    DataCenter, Decay, DistanceModel, Econ, Engine, Region, Sink, SinkCat, Weights,
};
use proptest::prelude::*;

fn base_weights() -> Weights {
    Weights {
        distance: DistanceModel::Euclid,
        decay: Decay::Linear,
        radius_m: 1000.0,
        ..Weights::default_for(Region::Nyc)
    }
}

/// Region defaults; the economics model is exercised in `econ_*` tests.
fn econ() -> Econ {
    Econ::default_for(Region::Nyc)
}

fn cat_of(i: usize) -> SinkCat {
    const CATS: [SinkCat; 10] = [
        SinkCat::Pool,
        SinkCat::Hospital,
        SinkCat::University,
        SinkCat::School,
        SinkCat::Greenhouse,
        SinkCat::Brewery,
        SinkCat::Wwtp,
        SinkCat::Office,
        SinkCat::ResidentialMultifamily,
        SinkCat::Hotel,
    ];
    CATS[i % CATS.len()]
}

proptest! {
    /// Supply is a budget: you cannot deliver more heat than you have.
    #[test]
    fn utilization_and_delivery_stay_within_supply(
        radius in 200.0f32..5000.0,
        per_sink_cap in 0.01f32..1.0,
        hours in 100.0f32..8760.0,
    ) {
        let w = Weights { radius_m: radius, per_sink_cap, utilization_hours: hours, ..base_weights() };
        let engine = support::mini_engine();
        for m in engine.rank(Region::Nyc, &w, &econ()).unwrap() {
            prop_assert!((0.0..=1.0).contains(&m.utilization), "utilization {} out of range", m.utilization);
            prop_assert!(m.delivered_mwh <= m.supply_mwh * 1.0001, "delivered exceeded supply");
            prop_assert!(m.score >= 0.0);
        }
    }

    /// `explain` must account for the whole of a data center's score, or the
    /// detail panel would contradict the table it was opened from.
    #[test]
    fn rank_score_equals_sum_of_explain_scores(radius in 200.0f32..5000.0) {
        let w = Weights { radius_m: radius, ..base_weights() };
        let engine = support::mini_engine();
        for m in engine.rank(Region::Nyc, &w, &econ()).unwrap() {
            let summed: f32 = engine.explain(&m.dc, &w).unwrap().iter().map(|c| c.score).sum();
            prop_assert!((summed - m.score).abs() <= 1e-3 * m.score.max(1.0),
                "explain sum {summed} != rank score {}", m.score);
        }
    }

    /// Raising a category's weight can only help the sites that use it.
    #[test]
    fn raising_a_category_weight_never_lowers_a_score(idx in 0usize..10, bump in 0.01f32..5.0) {
        let engine = support::mini_engine();
        let before = engine.rank(Region::Nyc, &base_weights(), &econ()).unwrap();

        let mut w = base_weights();
        let cat = cat_of(idx);
        w.cat.set(cat, w.cat.get(cat) + bump);
        let after = engine.rank(Region::Nyc, &w, &econ()).unwrap();

        for b in &before {
            let a = after.iter().find(|m| m.dc == b.dc).unwrap();
            prop_assert!(a.score >= b.score - 1e-3, "{} fell from {} to {}", b.dc, b.score, a.score);
        }
    }

    /// Moving a sink away can only reduce its contribution: decay is monotone
    /// in pipe length.
    #[test]
    fn moving_a_sink_further_never_raises_its_score(extra_m in 1.0f64..400.0) {
        let dc = DataCenter {
            id: "dc_0".into(), name: "dc".into(), region: Region::Nyc,
            lat: 40.7128, lon: -74.0060, mw: 1.0,
            cooling: Default::default(), mw_confidence: Default::default(),
            campus_id: None, in_steam: false, in_uten: false,
        };
        // 100 m north of the data center, then pushed further north.
        let frame_deg = |m: f64| m / 6_371_000.0f64.to_radians() / 1000.0 * 1000.0;
        let near = Sink {
            id: "s_0".into(), name: "s".into(), region: Region::Nyc,
            lat: 40.7128 + frame_deg(100.0), lon: -74.0060,
            cat: SinkCat::Pool, demand_kwh: 1_000_000.0, in_steam: false, in_uten: false,
        };
        let mut far = near.clone();
        far.lat = 40.7128 + frame_deg(100.0 + extra_m);

        let w = base_weights();
        let near_score = Engine::new(vec![dc.clone()], vec![near], &[]).unwrap()
            .explain("dc_0", &w).unwrap().first().map(|c| c.score).unwrap_or(0.0);
        let far_score = Engine::new(vec![dc], vec![far], &[]).unwrap()
            .explain("dc_0", &w).unwrap().first().map(|c| c.score).unwrap_or(0.0);

        prop_assert!(far_score <= near_score + 1e-4, "{far_score} > {near_score}");
    }

    /// The r-tree query radius must not exclude anything the distance model
    /// would have accepted. This is what justifies replacing the spec's
    /// `radius_m * 1.5` guess with an exact bound.
    #[test]
    fn search_radius_never_misses_an_in_radius_sink(
        radius in 100.0f32..5000.0,
        k in 0.2f32..3.0,
        theta in -180.0f32..180.0,
        dx in -8000.0f32..8000.0,
        dy in -8000.0f32..8000.0,
    ) {
        let models = [
            DistanceModel::Euclid,
            DistanceModel::Detour { k },
            DistanceModel::RotatedL1 { theta_deg: theta },
        ];
        for model in models {
            let pipe = pipe_length([0.0, 0.0], [dx, dy], &model);
            if pipe <= radius {
                let straight = euclid([0.0, 0.0], [dx, dy]);
                prop_assert!(straight <= search_radius(radius, &model) + 1e-3,
                    "{model:?}: sink at {straight} m qualifies (pipe {pipe}) but search radius is {}",
                    search_radius(radius, &model));
            }
        }
    }

    /// Projection round-trip: a known offset in metres must come back out.
    #[test]
    fn local_frame_preserves_distance(north_m in -20_000.0f64..20_000.0) {
        let frame = LocalFrame::new(40.7128, -74.0060);
        let deg = north_m / 111_194.9; // metres per degree of latitude at R = 6_371_000
        let xy = frame.to_xy(40.7128 + deg, -74.0060);
        prop_assert!((xy[1] as f64 - north_m).abs() < 1.0, "{} vs {north_m}", xy[1]);
    }
}
