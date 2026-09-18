//! Capital cost, savings and payback.
//!
//! Indicative only. Every figure here is a planning-grade estimate; see the
//! README's limitations before treating any of it as a number to spend money
//! against.

use crate::types::Counterfactual;
use crate::weights::Econ;

/// Heat a heat pump delivers per unit of electricity it draws, for a building
/// that already has one. Displacing it saves only the electricity, not the
/// heat, so the avoided cost per delivered MWh is `elec_price / this`.
pub const EXISTING_HEAT_PUMP_COP: f32 = 3.0;

#[derive(Clone, Copy, Debug, Default)]
pub struct Economics {
    pub capex: f32,
    pub annual_savings: f32,
    pub payback_yrs: Option<f32>,
}

/// One connected sink, as the economics model sees it.
pub struct Connection {
    pub pipe_m: f32,
    pub delivered_mwh: f32,
    /// `None` when the heat is hot enough to use directly.
    pub cop: Option<f32>,
    /// What the sink heats with today, which is what the connection displaces.
    pub counterfactual: Counterfactual,
}

/// What `delivered_mwh` of heat is worth to a sink, given what it would
/// otherwise have paid for it. Operation order is deliberate: the regression
/// fixture compares exact f32s.
pub fn avoided_cost(delivered_mwh: f32, c: Counterfactual, e: &Econ) -> f32 {
    match c {
        // Gas bought at the meter, burnt at boiler efficiency.
        Counterfactual::Gas => delivered_mwh * e.gas_price_per_mwh_th / e.boiler_eff,
        // A full MWh of electricity per MWh of heat.
        Counterfactual::ElectricResistance => delivered_mwh * e.elec_price_per_mwh,
        // Only the electricity the pump would have drawn.
        Counterfactual::HeatPump => delivered_mwh * e.elec_price_per_mwh / EXISTING_HEAT_PUMP_COP,
    }
}

/// Cost out a set of connections.
///
/// `delivered_mwh` is the seasonally-adjusted total, which is less than the
/// sum of the per-connection allocations: heat produced in a month with no
/// demand cannot be sold. Savings use the seasonal figure, while plant is
/// sized from the allocations, so equipment is not undersized.
pub fn evaluate(connections: &[Connection], delivered_mwh: f32, e: &Econ, hours: f32) -> Economics {
    // Each connection is priced its own full trench. Shared trunk lines would
    // be cheaper, so this over-counts — deliberately, to stay conservative.
    let pipe_capex: f32 = connections
        .iter()
        .map(|c| c.pipe_m * e.pipe_cost_per_m)
        .sum();

    let hp_capacity_mw_th: f32 = if hours > 0.0 {
        connections
            .iter()
            .filter(|c| c.cop.is_some())
            .map(|c| c.delivered_mwh / hours)
            .sum()
    } else {
        0.0
    };
    let capex = pipe_capex + hp_capacity_mw_th * e.hp_capex_per_mw_th;

    let hp_elec_mwh: f32 = connections
        .iter()
        .filter_map(|c| {
            c.cop.map(|cop| {
                if cop > 0.0 {
                    c.delivered_mwh / cop
                } else {
                    0.0
                }
            })
        })
        .sum();

    // Heat displaced at whatever each sink would otherwise have paid, priced
    // on the seasonal total. A uniform counterfactual is one call; a mixed
    // set is priced per allocation and scaled. The uniform path is not an
    // optimisation: a weighted mean of identical values can differ by an ulp,
    // which the regression snapshot refuses.
    let heat_saved = match connections.first().map(|c| c.counterfactual) {
        None => 0.0,
        Some(first) if connections.iter().all(|c| c.counterfactual == first) => {
            avoided_cost(delivered_mwh, first, e)
        }
        Some(_) => {
            let allocated: f32 = connections.iter().map(|c| c.delivered_mwh).sum();
            let per_allocation: f32 = connections
                .iter()
                .map(|c| avoided_cost(c.delivered_mwh, c.counterfactual, e))
                .sum();
            per_allocation / allocated * delivered_mwh
        }
    };
    let elec_cost = hp_elec_mwh * e.elec_price_per_mwh;
    let cooling_saved = delivered_mwh * e.dc_avoided_cooling_per_mwh;
    let annual_savings = heat_saved - elec_cost + cooling_saved;

    Economics {
        capex,
        annual_savings,
        // A scheme that does not save money has no payback period; reporting
        // one would invite a negative or infinite number of years.
        payback_yrs: (annual_savings > 0.0).then(|| capex / annual_savings),
    }
}
