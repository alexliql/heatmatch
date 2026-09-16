//! Capital cost, savings and payback (HEATMATCH.md §4.6 step 5).
//!
//! Indicative only. Every figure here is a planning-grade estimate; see the
//! README's limitations before treating any of it as a number to spend money
//! against.

use crate::weights::Econ;

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

    // Gas displaced at the boiler, less the electricity the heat pumps draw,
    // plus the cooling the data center no longer has to run.
    let gas_saved = delivered_mwh * e.gas_price_per_mwh_th / e.boiler_eff;
    let elec_cost = hp_elec_mwh * e.elec_price_per_mwh;
    let cooling_saved = delivered_mwh * e.dc_avoided_cooling_per_mwh;
    let annual_savings = gas_saved - elec_cost + cooling_saved;

    Economics {
        capex,
        annual_savings,
        // A scheme that does not save money has no payback period; reporting
        // one would invite a negative or infinite number of years.
        payback_yrs: (annual_savings > 0.0).then(|| capex / annual_savings),
    }
}
