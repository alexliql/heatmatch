//! Monthly demand shapes (HEATMATCH.md §4.5).
//!
//! A data center's waste heat is flat across the year; most heating demand is
//! not. Matching them month by month rather than annually is what stops a
//! winter-peaked sink from appearing fully served by a supply that is only
//! there in July.
//!
//! The built-in table is hand-set from the spec. A region may override it with
//! measured or modelled shapes — Virginia's come from NREL ComStock — which is
//! why `utilization` takes a table rather than reaching for a constant.

use enum_map::{enum_map, EnumMap};
use serde::{Deserialize, Serialize};

use crate::types::SinkCat;

/// Share of annual demand falling in each month, January first.
pub type Profiles = EnumMap<SinkCat, [f32; 12]>;

/// Largest deviation from 1.0 tolerated in a profile row.
const SUM_TOLERANCE: f32 = 1e-6;

/// Share of annual demand falling in each month, January first. Every row sums
/// to 1.0; `profiles_sum_to_one` enforces it.
pub fn profile(cat: SinkCat) -> [f32; 12] {
    const FLAT: [f32; 12] = [1.0 / 12.0; 12];
    const GREENHOUSE: [f32; 12] = [
        0.14, 0.13, 0.11, 0.08, 0.05, 0.03, 0.02, 0.02, 0.04, 0.08, 0.13, 0.17,
    ];
    const RESIDENTIAL: [f32; 12] = [
        0.14, 0.13, 0.11, 0.08, 0.05, 0.04, 0.03, 0.03, 0.04, 0.08, 0.12, 0.15,
    ];
    const TERM: [f32; 12] = [
        0.17, 0.15, 0.12, 0.07, 0.03, 0.01, 0.00, 0.00, 0.02, 0.08, 0.15, 0.20,
    ];

    match cat {
        // Process and hot-water loads run all year.
        SinkCat::Pool | SinkCat::Wwtp | SinkCat::Brewery | SinkCat::Hotel => FLAT,
        SinkCat::Greenhouse => GREENHOUSE,
        SinkCat::Hospital | SinkCat::ResidentialMultifamily => RESIDENTIAL,
        // Buildings that empty out over the summer.
        SinkCat::University | SinkCat::School | SinkCat::Office => TERM,
    }
}

/// All twelve profiles, for callers that want to hand the whole table out.
pub fn all_profiles() -> Profiles {
    enum_map! { cat => profile(cat) }
}

/// A profile table as it arrives from a data bundle.
///
/// Partial by design: a region supplies shapes only for the categories it has
/// modelled, and the rest fall back to the built-in table. That is also why
/// this is not an `EnumMap` — `EnumMap`'s `Deserialize` demands every key.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ProfileOverrides(pub std::collections::HashMap<SinkCat, [f32; 12]>);

#[derive(Debug, thiserror::Error, PartialEq)]
pub enum ProfileError {
    #[error("{cat:?} profile has a negative share in month {month}: {value}")]
    Negative {
        cat: SinkCat,
        month: usize,
        value: f32,
    },
    #[error("{cat:?} profile sums to {sum}, not 1.0")]
    NotNormalized { cat: SinkCat, sum: f32 },
}

impl ProfileOverrides {
    /// Merge onto the built-in table, rejecting anything that is not a
    /// distribution. Validated here rather than in a test, because unlike the
    /// built-in table these numbers arrive at runtime.
    pub fn resolve(&self) -> Result<Profiles, ProfileError> {
        let mut out = all_profiles();
        for (cat, row) in &self.0 {
            let mut sum = 0.0f32;
            for (month, &v) in row.iter().enumerate() {
                // NaN checked explicitly: it would slip past `v < 0.0` and
                // then poison every month of the overlap.
                if v.is_nan() || v < 0.0 {
                    return Err(ProfileError::Negative {
                        cat: *cat,
                        month,
                        value: v,
                    });
                }
                sum += v;
            }
            if (sum - 1.0).abs() > SUM_TOLERANCE {
                return Err(ProfileError::NotNormalized { cat: *cat, sum });
            }
            out[*cat] = *row;
        }
        Ok(out)
    }
}

/// Overlap a flat monthly supply with seasonal demand.
///
/// Returns `(utilization, delivered_mwh)`. Heat that has no demand in the month
/// it is produced is simply wasted — there is no inter-seasonal storage in this
/// model.
pub fn utilization(supply_mwh: f32, demands: &[(SinkCat, f32)], profiles: &Profiles) -> (f32, f32) {
    if supply_mwh <= 0.0 {
        return (0.0, 0.0);
    }
    let monthly_supply = supply_mwh / 12.0;

    let mut delivered = 0.0f32;
    for month in 0..12 {
        let demand: f32 = demands
            .iter()
            .map(|(cat, mwh)| mwh * profiles[*cat][month])
            .sum();
        delivered += demand.min(monthly_supply);
    }
    ((delivered / supply_mwh).clamp(0.0, 1.0), delivered)
}
