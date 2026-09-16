//! Golden ranking over hand-built fixtures (HEATMATCH.md §4.7).
//!
//! Expected values were computed independently in Python from the spec's
//! formulas, not captured from this implementation's output — a snapshot of
//! the code's own behaviour would pass no matter how wrong the model was.
//!
//! The four fixture data centers cover the cases that matter: a normal
//! catchment, one whose supply runs out before its neighbours are satisfied,
//! a small facility, and one with nothing in radius at all.

mod support;

use approx::assert_relative_eq;
use heatmatch_core::{Decay, DistanceModel, Region, Weights};

const EPS: f32 = 1e-4;

/// Euclidean distance and linear decay, so every expected value is reproducible
/// with a calculator.
fn weights() -> Weights {
    Weights {
        distance: DistanceModel::Euclid,
        decay: Decay::Linear,
        radius_m: 1000.0,
        ..Weights::default_for(Region::Nyc)
    }
}

#[test]
fn ranking_order_and_scores() {
    let engine = support::mini_engine();
    let ranked = engine.rank(Region::Nyc, &weights()).unwrap();

    let order: Vec<&str> = ranked.iter().map(|m| m.dc.as_str()).collect();
    assert_eq!(order, ["dc_a", "dc_c", "dc_b", "dc_d"]);

    let expected: [(f32, f32, f32, f32, f32); 4] = [
        // score,     supply,   demand_in_radius, delivered, utilization
        (4.673_994, 7884.0, 10_500.0, 7442.0, 0.943_937),
        (4.061_799, 3942.0, 2_500.0, 1985.5, 0.503_678),
        (1.274_431, 15_768.0, 240_000.0, 15_768.0, 1.0),
        (0.0, 7884.0, 0.0, 0.0, 0.0),
    ];

    for (m, (score, supply, demand, delivered, util)) in ranked.iter().zip(expected) {
        assert_relative_eq!(m.score, score, epsilon = EPS);
        assert_relative_eq!(m.supply_mwh, supply, epsilon = EPS);
        assert_relative_eq!(m.demand_mwh_in_radius, demand, epsilon = EPS);
        assert_relative_eq!(m.delivered_mwh, delivered, epsilon = EPS);
        assert_relative_eq!(m.utilization, util, epsilon = EPS);
    }
}

#[test]
fn supply_exhaustion_caps_delivery_and_truncates_top() {
    let engine = support::mini_engine();
    let ranked = engine.rank(Region::Nyc, &weights()).unwrap();
    let b = ranked.iter().find(|m| m.dc == "dc_b").unwrap();

    // Six sinks are in radius and each wants far more than the site can give,
    // so supply is fully used and only four sinks receive anything.
    assert_relative_eq!(m_util(b), 1.0, epsilon = EPS);
    assert_eq!(b.top.len(), 4);
    assert!(b.demand_mwh_in_radius > b.supply_mwh * 10.0);
}

fn m_util(m: &heatmatch_core::Match) -> f32 {
    m.utilization
}

#[test]
fn data_center_with_no_neighbours_scores_zero() {
    let engine = support::mini_engine();
    let ranked = engine.rank(Region::Nyc, &weights()).unwrap();
    let d = ranked.iter().find(|m| m.dc == "dc_d").unwrap();

    assert_eq!(d.score, 0.0);
    assert_eq!(d.delivered_mwh, 0.0);
    assert!(d.top.is_empty());
    // It still reports its supply: the heat exists, there is just nowhere for
    // it to go.
    assert_relative_eq!(d.supply_mwh, 7884.0, epsilon = EPS);
}

#[test]
fn explain_lists_every_in_radius_sink_best_first() {
    let engine = support::mini_engine();
    let contribs = engine.explain("dc_a", &weights()).unwrap();

    assert_eq!(
        contribs.len(),
        6,
        "one sink at 1200 m is outside the radius"
    );
    assert!(contribs.windows(2).all(|p| p[0].score >= p[1].score));
    assert_eq!(contribs[0].sink, "s_000");
    assert_relative_eq!(contribs[0].score, 2.400_347, epsilon = EPS);
    assert_relative_eq!(contribs[0].pipe_m, 200.0, epsilon = 0.5);
}

#[test]
fn explain_scores_sum_to_the_rank_score() {
    let engine = support::mini_engine();
    let w = weights();
    for m in engine.rank(Region::Nyc, &w).unwrap() {
        let summed: f32 = engine
            .explain(&m.dc, &w)
            .unwrap()
            .iter()
            .map(|c| c.score)
            .sum();
        assert_relative_eq!(summed, m.score, epsilon = EPS);
    }
}

#[test]
fn unknown_data_center_is_an_error() {
    let engine = support::mini_engine();
    assert!(engine.explain("dc_nope", &weights()).is_err());
}
