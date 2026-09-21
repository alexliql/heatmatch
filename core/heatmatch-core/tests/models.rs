//! Thermodynamics, seasonality, water crossing and the rotated-grid distance.

mod support;

use approx::assert_relative_eq;
use geo::{Coord, LineString, Polygon};
use heatmatch_core::{
    distance::pipe_length, season, season::ProfileError, thermo, ConfidenceWeights, Cooling,
    Counterfactual, DataCenter, DistanceModel, Econ, Engine, MwConfidence, ProfileOverrides,
    Region, Sink, SinkCat, WaterPolicy, Weights,
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
    // Reference: cop ≈ 0.5 * 348.15 / 45 ≈ 3.87. The 45 K denominator is the full
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
    let (util, delivered) =
        season::utilization(1200.0, &[(SinkCat::Pool, 1200.0)], &season::all_profiles());
    assert_relative_eq!(util, 1.0, epsilon = 1e-5);
    assert_relative_eq!(delivered, 1200.0, max_relative = 1e-5);
}

#[test]
fn a_winter_peaked_sink_strands_summer_heat() {
    // An office wants nothing in July but the data center produces anyway.
    let (util, _) = season::utilization(
        1200.0,
        &[(SinkCat::Office, 1200.0)],
        &season::all_profiles(),
    );
    assert!(util < 1.0, "expected summer heat to be wasted, got {util}");
}

#[test]
fn no_demand_means_no_delivery() {
    let (util, delivered) = season::utilization(1000.0, &[], &season::all_profiles());
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

// --- seasonal profile overrides -------------------------------------------

/// A bundle may replace the built-in shapes for the categories it has modelled.
#[test]
fn an_override_replaces_only_the_categories_it_names() {
    let mut given = std::collections::HashMap::new();
    // Virginia's hospitals, were they perfectly flat.
    given.insert(SinkCat::Hospital, [1.0 / 12.0; 12]);
    let resolved = ProfileOverrides(given).resolve().expect("valid override");

    assert_eq!(resolved[SinkCat::Hospital], [1.0 / 12.0; 12]);
    // Untouched categories keep the built-in table.
    assert_eq!(resolved[SinkCat::Office], season::profile(SinkCat::Office));
}

#[test]
fn an_override_that_is_not_a_distribution_is_rejected() {
    let bad = |row: [f32; 12]| {
        let mut m = std::collections::HashMap::new();
        m.insert(SinkCat::Pool, row);
        ProfileOverrides(m).resolve()
    };

    // Sums to 2.0, which would hand the sink twice its annual demand.
    assert!(matches!(
        bad([1.0 / 6.0; 12]),
        Err(ProfileError::NotNormalized { .. })
    ));

    let mut negative = [1.0 / 12.0; 12];
    negative[0] = -0.5;
    negative[1] = 1.0 / 12.0 + 0.5;
    assert!(matches!(
        bad(negative),
        Err(ProfileError::Negative { month: 0, .. })
    ));

    let mut nan = [1.0 / 12.0; 12];
    nan[3] = f32::NAN;
    assert!(matches!(bad(nan), Err(ProfileError::Negative { .. })));
}

// --- capacity confidence ---------------------------------------------------

/// The discount changes the ranking without touching the physics: a site whose
/// capacity is a guess should look less attractive, not smaller.
#[test]
fn the_confidence_discount_moves_score_but_not_energy_or_cost() {
    let dc = |id: &str, confidence| DataCenter {
        id: id.into(),
        name: id.into(),
        region: Region::Nyc,
        lat: 40.7128,
        lon: -74.0060,
        mw: 1.0,
        cooling: Default::default(),
        mw_confidence: confidence,
        campus_id: None,
        in_steam: false,
        in_uten: false,
    };
    let sink = Sink {
        id: "s_0".into(),
        name: "pool".into(),
        region: Region::Nyc,
        // ~200 m north, comfortably inside the 1000 m radius.
        lat: 40.7146,
        lon: -74.0060,
        cat: SinkCat::Pool,
        demand_kwh: 5_000_000.0,
        counterfactual: Default::default(),
        in_steam: false,
        in_uten: false,
    };

    let engine = Engine::new(
        vec![
            dc("dc_sure", MwConfidence::Reported),
            dc("dc_guess", MwConfidence::FootprintEstimate),
        ],
        vec![sink],
        &[],
    )
    .unwrap();

    let mut w = Weights::default_for(Region::Nyc);
    w.confidence = ConfidenceWeights {
        reported: 1.0,
        filed: 0.95,
        parcel_estimate: 0.7,
        footprint_estimate: 0.5,
    };
    let ranked = engine
        .rank(Region::Nyc, &w, &Econ::default_for(Region::Nyc))
        .unwrap();

    let sure = ranked.iter().find(|m| m.dc == "dc_sure").unwrap();
    let guess = ranked.iter().find(|m| m.dc == "dc_guess").unwrap();

    // Same facility twice over, so everything physical must agree exactly.
    assert_relative_eq!(guess.supply_mwh, sure.supply_mwh);
    assert_relative_eq!(guess.delivered_mwh, sure.delivered_mwh);
    assert_relative_eq!(guess.utilization, sure.utilization);
    assert_relative_eq!(guess.capex, sure.capex);
    assert_relative_eq!(guess.annual_savings, sure.annual_savings);
    // Only the ranking signal differs, by exactly the discount.
    assert_relative_eq!(guess.score, sure.score * 0.5, max_relative = 1e-5);
    assert!(sure.score > 0.0, "fixture must actually score");
}

/// New York's defaults must not discount anything, or every committed number
/// would move.
#[test]
fn new_york_defaults_trust_every_capacity_grade() {
    for region in [Region::Nyc, Region::Upstate] {
        for (grade, weight) in Weights::default_for(region).confidence.iter() {
            assert_eq!(weight, 1.0, "{region:?} discounts {grade:?}");
        }
    }
    // Virginia is the region the grading exists for.
    let nova = Weights::default_for(Region::Nova).confidence;
    assert_eq!(nova.reported, 1.0);
    assert!(nova.footprint_estimate < nova.parcel_estimate);
    assert!(nova.parcel_estimate < nova.filed);
}

// --- counterfactual economics -----------------------------------------------

/// The claim the whole change rests on: a connection set with no counterfactual
/// information prices exactly — bit for bit — as it did before the field
/// existed. Not "within tolerance": the regression snapshot compares exact
/// f32s, and an ulp here would fail every New York site.
#[test]
fn an_all_gas_connection_set_prices_exactly_as_before() {
    use heatmatch_core::econ::{evaluate, Connection};
    let e = Econ::default_for(Region::Nyc);
    let hours = 0.9 * 8760.0;
    let connections: Vec<Connection> = [
        (1200.0f32, 3_100.0f32),
        (800.0, 1_950.0),
        (2_500.0, 4_210.5),
    ]
    .iter()
    .map(|&(pipe_m, delivered_mwh)| Connection {
        pipe_m,
        delivered_mwh,
        cop: None,
        counterfactual: Counterfactual::Gas,
    })
    .collect();
    let seasonal = 7_000.25f32;
    let got = evaluate(&connections, seasonal, &e, hours);

    // The pre-counterfactual formula, verbatim, in the same operation order.
    let pipe_capex: f32 = connections
        .iter()
        .map(|c| c.pipe_m * e.pipe_cost_per_m)
        .sum();
    let gas_saved = seasonal * e.gas_price_per_mwh_th / e.boiler_eff;
    let cooling_saved = seasonal * e.dc_avoided_cooling_per_mwh;
    let expected_savings = gas_saved - 0.0 + cooling_saved;

    assert_eq!(got.capex, pipe_capex);
    assert_eq!(
        got.annual_savings, expected_savings,
        "must be bit-identical, not merely close"
    );
    assert_eq!(got.payback_yrs, Some(pipe_capex / expected_savings));
}

/// Displacing resistance heat is worth a full MWh of electricity; displacing a
/// heat pump only what the pump would have drawn. In a place where electricity
/// costs more than gas, resistance-heated buildings become the best sinks on
/// the map — which is the whole reason the field exists.
///
/// Gas versus heat pump is *not* asserted either way: at a 3.6:1 electricity-
/// to-gas price ratio a COP-3 pump costs slightly more per MWh of heat than a
/// boiler, at 2:1 slightly less. That ordering is a finding about prices, not
/// a property of the model.
#[test]
fn the_counterfactual_orders_avoided_cost_the_right_way() {
    use heatmatch_core::econ::{avoided_cost, EXISTING_HEAT_PUMP_COP};
    // California-like prices: electricity dear, gas cheap.
    let mut e = Econ::default_for(Region::Nyc);
    e.elec_price_per_mwh = 200.0;
    e.gas_price_per_mwh_th = 55.0;

    let gas = avoided_cost(100.0, Counterfactual::Gas, &e);
    let resistance = avoided_cost(100.0, Counterfactual::ElectricResistance, &e);
    let heat_pump = avoided_cost(100.0, Counterfactual::HeatPump, &e);

    assert!(
        resistance > gas,
        "resistance {resistance} should beat gas {gas}"
    );
    // Always, whatever the prices: a pump with COP > 1 draws less than a
    // resistance element delivering the same heat.
    assert!(
        resistance > heat_pump,
        "resistance {resistance} should beat heat pump {heat_pump}"
    );
    assert_relative_eq!(resistance, 100.0 * 200.0);
    assert_relative_eq!(gas, 100.0 * 55.0 / e.boiler_eff);
    assert_relative_eq!(heat_pump, 100.0 * 200.0 / EXISTING_HEAT_PUMP_COP);
}

/// A mixed set is priced per allocation and scaled to the seasonal total.
#[test]
fn a_mixed_connection_set_is_priced_by_allocation() {
    use heatmatch_core::econ::{evaluate, Connection};
    let e = Econ::default_for(Region::Nyc);
    let mk = |delivered_mwh: f32, counterfactual| Connection {
        pipe_m: 0.0,
        delivered_mwh,
        cop: None,
        counterfactual,
    };
    // 3:1 allocation between a gas sink and a resistance sink, no seasonal loss.
    let connections = vec![
        mk(300.0, Counterfactual::Gas),
        mk(100.0, Counterfactual::ElectricResistance),
    ];
    let got = evaluate(&connections, 400.0, &e, 8760.0);

    let gas_part = 300.0 * e.gas_price_per_mwh_th / e.boiler_eff;
    let res_part = 100.0 * e.elec_price_per_mwh;
    let expected = gas_part + res_part + 400.0 * e.dc_avoided_cooling_per_mwh;
    assert_relative_eq!(got.annual_savings, expected, max_relative = 1e-6);
}
