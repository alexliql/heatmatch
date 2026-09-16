//! Thermodynamics, seasonality, water crossing and the rotated-grid distance.

mod support;

use approx::assert_relative_eq;
use geo::{Coord, LineString, Polygon};
use heatmatch_core::{
    distance::pipe_length, season, thermo, Cooling, DistanceModel, Econ, Region, SinkCat,
    WaterPolicy, Weights,
};

// --- thermodynamics -------------------------------------------------------

#[test]
fn heat_is_used_directly_when_it_is_already_hot_enough() {
    // Liquid cooling supplies 55 °C; a pool needs 32 °C even after the 5 K
    // approach, so there is nothing to lift.
    let hp = thermo::heat_pump(Cooling::Liquid, SinkCat::Pool, 5.0, 0.5);
    assert!(!hp.required);
    assert!(
        hp.cop.is_infinite(),
        "no pump means no electricity: {}",
        hp.cop
    );
}

#[test]
fn air_cooled_to_hospital_matches_the_spec_worked_example() {
    // §4.7: cop ≈ 0.5 * 348.15 / 45 ≈ 3.87. The 45 K denominator is the full
    // lift including the approach, which is why the evaporator sees
    // supply - approach rather than supply.
    let hp = thermo::heat_pump(Cooling::Air, SinkCat::Hospital, 5.0, 0.5);
    assert!(hp.required);
    assert_relative_eq!(hp.cop, 0.5 * 348.15 / 45.0, max_relative = 1e-5);
}

#[test]
fn a_smaller_lift_gives_a_better_cop() {
    let easy = thermo::heat_pump(Cooling::RearDoor, SinkCat::Greenhouse, 5.0, 0.5);
    let hard = thermo::heat_pump(Cooling::Air, SinkCat::Office, 5.0, 0.5);
    assert!(easy.cop > hard.cop, "{} vs {}", easy.cop, hard.cop);
}

// --- seasonality ----------------------------------------------------------

#[test]
fn every_profile_sums_to_one_year() {
    for (cat, profile) in season::all_profiles() {
        let total: f32 = profile.iter().sum();
        assert_relative_eq!(total, 1.0, epsilon = 1e-6);
        assert!(
            profile.iter().all(|m| *m >= 0.0),
            "{cat:?} has a negative month"
        );
    }
}

#[test]
fn a_flat_sink_can_absorb_a_flat_supply_entirely() {
    // A pool wants the same heat every month, so a matched flat supply is
    // fully used.
    let (util, delivered) = season::utilization(1200.0, &[(SinkCat::Pool, 1200.0)]);
    assert_relative_eq!(util, 1.0, epsilon = 1e-5);
    assert_relative_eq!(delivered, 1200.0, max_relative = 1e-5);
}

#[test]
fn a_winter_peaked_sink_strands_summer_heat() {
    // An office wants nothing in July but the data center produces anyway.
    let (util, _) = season::utilization(1200.0, &[(SinkCat::Office, 1200.0)]);
    assert!(util < 1.0, "expected summer heat to be wasted, got {util}");
}

#[test]
fn no_demand_means_no_delivery() {
    let (util, delivered) = season::utilization(1000.0, &[]);
    assert_eq!((util, delivered), (0.0, 0.0));
}

// --- rotated-grid distance -----------------------------------------------

#[test]
fn rotated_l1_is_plain_manhattan_at_zero_rotation() {
    let model = DistanceModel::RotatedL1 { theta_deg: 0.0 };
    assert_relative_eq!(
        pipe_length([0.0, 0.0], [30.0, 40.0], &model),
        70.0,
        max_relative = 1e-5
    );
}

#[test]
fn rotated_l1_follows_the_grid_axes() {
    // A segment lying exactly along a 29°-rotated avenue costs its own length,
    // not the longer dog-leg an unrotated grid would charge.
    let theta = 29.0f32;
    let (sin, cos) = theta.to_radians().sin_cos();
    let along = [100.0 * cos, 100.0 * sin];
    let model = DistanceModel::RotatedL1 { theta_deg: theta };
    assert_relative_eq!(
        pipe_length([0.0, 0.0], along, &model),
        100.0,
        max_relative = 1e-4
    );
}

#[test]
fn rotated_l1_never_undercuts_the_straight_line() {
    let model = DistanceModel::RotatedL1 { theta_deg: 29.0 };
    for (dx, dy) in [(10.0, 0.0), (0.0, 10.0), (30.0, 40.0), (-70.0, 15.0)] {
        let l1 = pipe_length([0.0, 0.0], [dx, dy], &model);
        let straight = (dx * dx + dy * dy).sqrt();
        assert!(l1 >= straight - 1e-3, "L1 {l1} < euclid {straight}");
    }
}

// --- water crossing -------------------------------------------------------

/// A river band across the fixture area, in lon/lat, between the data center
/// at the frame origin and the sinks east of it.
fn river() -> Vec<Polygon<f64>> {
    let ring = LineString::from(vec![
        Coord {
            x: -74.0050,
            y: 40.70,
        },
        Coord {
            x: -74.0040,
            y: 40.70,
        },
        Coord {
            x: -74.0040,
            y: 40.73,
        },
        Coord {
            x: -74.0050,
            y: 40.73,
        },
        Coord {
            x: -74.0050,
            y: 40.70,
        },
    ]);
    vec![Polygon::new(ring, vec![])]
}

fn weights_with(policy: WaterPolicy) -> Weights {
    Weights {
        distance: DistanceModel::Euclid,
        radius_m: 1000.0,
        water_crossing: policy,
        ..Weights::default_for(Region::Nyc)
    }
}

#[test]
fn no_water_means_nothing_is_flagged() {
    let engine = support::mini_engine();
    let contribs = engine
        .explain("dc_a", &weights_with(WaterPolicy::Penalty { factor: 2.0 }))
        .unwrap();
    assert!(contribs.iter().all(|c| !c.crosses_water));
}

#[test]
fn a_crossing_is_detected_and_penalised() {
    let engine = support::mini_engine_with_water(&river());
    let contribs = engine
        .explain("dc_a", &weights_with(WaterPolicy::Penalty { factor: 2.0 }))
        .unwrap();

    let crossing: Vec<_> = contribs.iter().filter(|c| c.crosses_water).collect();
    assert!(!crossing.is_empty(), "river should block at least one sink");
    // The penalty doubles pipe length, so it must exceed the straight line.
    for c in crossing {
        assert!(
            c.pipe_m > c.dist_m,
            "{}: pipe {} <= dist {}",
            c.sink,
            c.pipe_m,
            c.dist_m
        );
    }
}

#[test]
fn exclude_policy_drops_sinks_across_the_water() {
    let engine = support::mini_engine_with_water(&river());
    let penalised = engine
        .explain("dc_a", &weights_with(WaterPolicy::Penalty { factor: 2.0 }))
        .unwrap();
    let excluded = engine
        .explain("dc_a", &weights_with(WaterPolicy::Exclude))
        .unwrap();

    assert!(
        excluded.len() < penalised.len(),
        "Exclude should drop the crossings"
    );
    assert!(excluded.iter().all(|c| !c.crosses_water));
}

#[test]
fn water_lowers_the_score_it_does_not_raise_it() {
    let w = weights_with(WaterPolicy::Penalty { factor: 2.0 });
    let e = Econ::default_for(Region::Nyc);
    let dry = support::mini_engine().rank(Region::Nyc, &w, &e).unwrap();
    let wet = support::mini_engine_with_water(&river())
        .rank(Region::Nyc, &w, &e)
        .unwrap();

    for d in &dry {
        let x = wet.iter().find(|m| m.dc == d.dc).unwrap();
        assert!(
            x.score <= d.score + 1e-4,
            "{} rose from {} to {}",
            d.dc,
            d.score,
            x.score
        );
    }
}
