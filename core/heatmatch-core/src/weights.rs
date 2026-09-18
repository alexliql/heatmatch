//! Tunable model parameters (HEATMATCH.md §4.2).
//!
//! Everything the UI exposes as a slider lives here. Defaults are per-region
//! and must stay in step with `ingest/src/ingest/config.py`, which uses the
//! same radius and pipe-cost figures.

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::types::{MwConfidence, Region, SinkCat};

/// How a straight line between two points becomes a pipe length.
///
/// Internally tagged so the web layer round-trips it as plain JSON:
/// `{"kind": "detour", "k": 1.3}`.
#[derive(Clone, Copy, PartialEq, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum DistanceModel {
    /// Straight line.
    Euclid,
    /// Straight line inflated by a constant factor.
    Detour { k: f32 },
    /// Manhattan distance on a street grid rotated `theta_deg` from north.
    RotatedL1 { theta_deg: f32 },
}

/// How score falls off with pipe length.
#[derive(Clone, Copy, PartialEq, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum Decay {
    /// Reaches zero exactly at the radius.
    Linear,
    /// Never quite reaches zero; `k` sets the steepness.
    Exp { k: f32 },
}

/// What to do about a pipe that would cross open water.
#[derive(Clone, Copy, PartialEq, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub enum WaterPolicy {
    /// Treat the sink as unreachable.
    Exclude,
    /// Keep it, but multiply the pipe length by `factor`.
    Penalty { factor: f32 },
}

/// Per-category desirability weights.
///
/// An explicit struct rather than a map: `serde_wasm_bindgen` turns Rust maps
/// into a JS `Map`, which serializes to `{}` and is awkward to bind sliders to.
/// A struct crosses the boundary as a plain object and types exactly.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct CatWeights {
    pub pool: f32,
    pub hospital: f32,
    pub university: f32,
    pub school: f32,
    pub greenhouse: f32,
    pub brewery: f32,
    pub wwtp: f32,
    pub office: f32,
    pub residential_multifamily: f32,
    pub hotel: f32,
}

impl CatWeights {
    pub fn get(&self, cat: SinkCat) -> f32 {
        match cat {
            SinkCat::Pool => self.pool,
            SinkCat::Hospital => self.hospital,
            SinkCat::University => self.university,
            SinkCat::School => self.school,
            SinkCat::Greenhouse => self.greenhouse,
            SinkCat::Brewery => self.brewery,
            SinkCat::Wwtp => self.wwtp,
            SinkCat::Office => self.office,
            SinkCat::ResidentialMultifamily => self.residential_multifamily,
            SinkCat::Hotel => self.hotel,
        }
    }

    pub fn set(&mut self, cat: SinkCat, value: f32) {
        let slot = match cat {
            SinkCat::Pool => &mut self.pool,
            SinkCat::Hospital => &mut self.hospital,
            SinkCat::University => &mut self.university,
            SinkCat::School => &mut self.school,
            SinkCat::Greenhouse => &mut self.greenhouse,
            SinkCat::Brewery => &mut self.brewery,
            SinkCat::Wwtp => &mut self.wwtp,
            SinkCat::Office => &mut self.office,
            SinkCat::ResidentialMultifamily => &mut self.residential_multifamily,
            SinkCat::Hotel => &mut self.hotel,
        };
        *slot = value;
    }

    pub fn iter(&self) -> impl Iterator<Item = (SinkCat, f32)> + '_ {
        SinkCat::ALL.into_iter().map(|c| (c, self.get(c)))
    }
}

impl std::ops::Index<SinkCat> for CatWeights {
    type Output = f32;
    fn index(&self, cat: SinkCat) -> &f32 {
        match cat {
            SinkCat::Pool => &self.pool,
            SinkCat::Hospital => &self.hospital,
            SinkCat::University => &self.university,
            SinkCat::School => &self.school,
            SinkCat::Greenhouse => &self.greenhouse,
            SinkCat::Brewery => &self.brewery,
            SinkCat::Wwtp => &self.wwtp,
            SinkCat::Office => &self.office,
            SinkCat::ResidentialMultifamily => &self.residential_multifamily,
            SinkCat::Hotel => &self.hotel,
        }
    }
}

/// How much a data center's score is discounted for an uncertain capacity.
///
/// A flat struct rather than an `EnumMap`, for the same reason as `CatWeights`:
/// `serde_wasm_bindgen` turns a Rust map into a JS `Map`, which serializes to
/// `{}` and cannot be bound to a slider.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct ConfidenceWeights {
    pub reported: f32,
    pub filed: f32,
    pub parcel_estimate: f32,
    pub footprint_estimate: f32,
}

impl ConfidenceWeights {
    /// No discount at all — every grade trusted equally.
    ///
    /// This is what New York gets, and it is what keeps adding the confidence
    /// model from moving a single existing number.
    pub const TRUSTING: Self = Self {
        reported: 1.0,
        filed: 1.0,
        parcel_estimate: 1.0,
        footprint_estimate: 1.0,
    };

    /// The default outside New York: a published figure ranks ahead of an
    /// inference of the same size.
    pub const GRADED: Self = Self {
        reported: 1.0,
        filed: 0.95,
        parcel_estimate: 0.7,
        footprint_estimate: 0.5,
    };

    pub fn get(&self, c: MwConfidence) -> f32 {
        match c {
            MwConfidence::Reported => self.reported,
            MwConfidence::Filed => self.filed,
            MwConfidence::ParcelEstimate => self.parcel_estimate,
            MwConfidence::FootprintEstimate => self.footprint_estimate,
        }
    }

    pub fn set(&mut self, c: MwConfidence, value: f32) {
        let slot = match c {
            MwConfidence::Reported => &mut self.reported,
            MwConfidence::Filed => &mut self.filed,
            MwConfidence::ParcelEstimate => &mut self.parcel_estimate,
            MwConfidence::FootprintEstimate => &mut self.footprint_estimate,
        };
        *slot = value;
    }

    pub fn iter(&self) -> impl Iterator<Item = (MwConfidence, f32)> + '_ {
        MwConfidence::ALL.into_iter().map(|c| (c, self.get(c)))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct Weights {
    /// Per-category desirability. Pool ranks highest because a pool wants
    /// low-grade heat year-round, which is exactly what a data center has.
    pub cat: CatWeights,
    /// Score multiplier by how well established the data center's capacity is.
    /// Affects ranking only: `supply_mwh`, `delivered_mwh`, `capex` and
    /// `payback_yrs` are reported undiscounted.
    pub confidence: ConfidenceWeights,
    pub radius_m: f32,
    pub distance: DistanceModel,
    pub decay: Decay,
    /// Applied when data center and sink are both inside the steam territory.
    pub steam_bonus: f32,
    /// Applied when either is inside a thermal-network pilot footprint.
    pub uten_bonus: f32,
    /// Ceiling on the share of a data center's supply any single sink may take,
    /// so one large neighbour cannot claim the whole facility.
    pub per_sink_cap: f32,
    /// Base of the logarithm used to normalize demand.
    pub log_base: f32,
    pub water_crossing: WaterPolicy,
    /// Temperature margin a heat exchanger needs, in K.
    pub approach_c: f32,
    /// Fraction of the ideal Carnot COP a real heat pump achieves.
    pub hp_carnot_fraction: f32,
    /// Hours per year of usable output; `supply_mwh = mw * this`.
    pub utilization_hours: f32,
}

/// Cost and price assumptions consumed by `econ`. Planning-grade figures; see
/// the README's limitations before treating any output as a budget.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[cfg_attr(feature = "ts", derive(tsify_next::Tsify))]
#[cfg_attr(feature = "ts", tsify(into_wasm_abi, from_wasm_abi))]
pub struct Econ {
    pub pipe_cost_per_m: f32,
    pub hp_capex_per_mw_th: f32,
    pub gas_price_per_mwh_th: f32,
    pub boiler_eff: f32,
    pub elec_price_per_mwh: f32,
    pub dc_avoided_cooling_per_mwh: f32,
}

#[derive(Debug, Error, PartialEq)]
pub enum WeightsError {
    #[error("{field} must be finite, got {value}")]
    NotFinite { field: &'static str, value: f32 },
    #[error("{field} must be >= 0, got {value}")]
    Negative { field: &'static str, value: f32 },
    #[error("radius_m must be > 0, got {0}")]
    Radius(f32),
    #[error("boiler_eff must be in (0, 1], got {0}")]
    BoilerEff(f32),
}

fn finite(field: &'static str, value: f32) -> Result<(), WeightsError> {
    if value.is_finite() {
        Ok(())
    } else {
        Err(WeightsError::NotFinite { field, value })
    }
}

fn non_negative(field: &'static str, value: f32) -> Result<(), WeightsError> {
    finite(field, value)?;
    if value < 0.0 {
        return Err(WeightsError::Negative { field, value });
    }
    Ok(())
}

impl Weights {
    pub fn default_for(region: Region) -> Self {
        Self {
            cat: CatWeights {
                pool: 1.0,
                wwtp: 0.9,
                greenhouse: 0.9,
                hospital: 0.8,
                hotel: 0.7,
                residential_multifamily: 0.6,
                university: 0.5,
                brewery: 0.5,
                school: 0.3,
                office: 0.3,
            },
            // New York's capacities are uniformly area-derived, so grading them
            // against each other would be noise. Everywhere else some sites
            // publish real numbers, which is worth preferring over a guess.
            confidence: match region {
                Region::Nyc | Region::Upstate => ConfidenceWeights::TRUSTING,
                _ => ConfidenceWeights::GRADED,
            },
            radius_m: match region {
                Region::Nyc => 1000.0,
                Region::Upstate => 4000.0,
                Region::Nova => 3000.0,
                Region::Seattle => 1500.0,
                Region::Pdx => 2500.0,
                Region::Svy => 2000.0,
                Region::La => 1500.0,
                Region::Sac => 3000.0,
            },
            // Manhattan's street grid runs ~29° off true north, so pipes
            // there follow two axes rather than the diagonal. Upstate has no
            // single orientation to exploit and gets a plain detour factor,
            // matching ingest's per-region `detour` value.
            distance: match region {
                Region::Nyc => DistanceModel::RotatedL1 { theta_deg: 29.0 },
                Region::Upstate => DistanceModel::Detour { k: 1.20 },
                Region::Nova => DistanceModel::Detour { k: 1.25 },
                Region::Seattle => DistanceModel::Detour { k: 1.30 },
                Region::Pdx => DistanceModel::Detour { k: 1.25 },
                Region::Svy => DistanceModel::Detour { k: 1.25 },
                Region::La => DistanceModel::Detour { k: 1.30 },
                Region::Sac => DistanceModel::Detour { k: 1.20 },
            },
            decay: Decay::Linear,
            steam_bonus: 0.5,
            uten_bonus: 0.3,
            per_sink_cap: 0.25,
            log_base: 10.0,
            // Seattle's sinks sit across Lake Union, the Ship Canal and
            // Elliott Bay from its data centers; a penalty would still let a
            // pipe be drawn under Lake Washington, so there it is a hard no.
            water_crossing: match region {
                Region::Seattle => WaterPolicy::Exclude,
                _ => WaterPolicy::Penalty { factor: 2.0 },
            },
            approach_c: 5.0,
            hp_carnot_fraction: 0.5,
            utilization_hours: 0.9 * 8760.0,
        }
    }

    pub fn validate(&self) -> Result<(), WeightsError> {
        for (_, w) in self.cat.iter() {
            non_negative("cat weight", w)?;
        }
        for (_, c) in self.confidence.iter() {
            non_negative("confidence weight", c)?;
        }
        non_negative("steam_bonus", self.steam_bonus)?;
        non_negative("uten_bonus", self.uten_bonus)?;
        non_negative("per_sink_cap", self.per_sink_cap)?;
        non_negative("approach_c", self.approach_c)?;
        non_negative("hp_carnot_fraction", self.hp_carnot_fraction)?;
        non_negative("utilization_hours", self.utilization_hours)?;

        finite("radius_m", self.radius_m)?;
        if self.radius_m <= 0.0 {
            return Err(WeightsError::Radius(self.radius_m));
        }
        // A base of 1 would divide by ln(1) = 0; anything below 1 flips the
        // sign of every normalized demand.
        finite("log_base", self.log_base)?;
        if self.log_base <= 1.0 {
            return Err(WeightsError::Negative {
                field: "log_base (must exceed 1)",
                value: self.log_base,
            });
        }

        match self.distance {
            DistanceModel::Euclid => {}
            DistanceModel::Detour { k } => {
                non_negative("distance.k", k)?;
                if k <= 0.0 {
                    return Err(WeightsError::Negative {
                        field: "distance.k (must exceed 0)",
                        value: k,
                    });
                }
            }
            DistanceModel::RotatedL1 { theta_deg } => finite("distance.theta_deg", theta_deg)?,
        }
        match self.decay {
            Decay::Linear => {}
            Decay::Exp { k } => non_negative("decay.k", k)?,
        }
        match self.water_crossing {
            WaterPolicy::Exclude => {}
            WaterPolicy::Penalty { factor } => non_negative("water_crossing.factor", factor)?,
        }
        Ok(())
    }
}

impl Econ {
    pub fn default_for(region: Region) -> Self {
        Self {
            pipe_cost_per_m: match region {
                Region::Nyc => 3000.0,
                Region::Upstate => 800.0,
                Region::Nova => 1200.0,
                Region::Seattle => 2500.0,
                Region::Pdx => 1500.0,
                Region::Svy => 2500.0,
                Region::La => 3000.0,
                Region::Sac => 1200.0,
            },
            hp_capex_per_mw_th: 900_000.0,
            gas_price_per_mwh_th: match region {
                Region::Nyc | Region::Upstate | Region::Seattle | Region::Pdx => 45.0,
                Region::Nova => 40.0,
                Region::Svy | Region::La => 55.0,
                Region::Sac => 50.0,
            },
            boiler_eff: 0.85,
            // California is the highest-priced electricity on the map, and
            // SMUD's municipal rates in Sacramento are well under the
            // investor-owned utilities on the coast.
            elec_price_per_mwh: match region {
                Region::Nyc => 150.0,
                Region::Upstate => 90.0,
                Region::Nova => 80.0,
                Region::Seattle => 90.0,
                Region::Pdx => 85.0,
                Region::Svy => 200.0,
                Region::La => 210.0,
                Region::Sac => 140.0,
            },
            dc_avoided_cooling_per_mwh: 8.0,
        }
    }

    pub fn validate(&self) -> Result<(), WeightsError> {
        non_negative("pipe_cost_per_m", self.pipe_cost_per_m)?;
        non_negative("hp_capex_per_mw_th", self.hp_capex_per_mw_th)?;
        non_negative("gas_price_per_mwh_th", self.gas_price_per_mwh_th)?;
        non_negative("elec_price_per_mwh", self.elec_price_per_mwh)?;
        non_negative(
            "dc_avoided_cooling_per_mwh",
            self.dc_avoided_cooling_per_mwh,
        )?;
        finite("boiler_eff", self.boiler_eff)?;
        if self.boiler_eff <= 0.0 || self.boiler_eff > 1.0 {
            return Err(WeightsError::BoilerEff(self.boiler_eff));
        }
        Ok(())
    }
}
