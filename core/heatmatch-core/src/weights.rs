//! Tunable model parameters (HEATMATCH.md §4.2).
//!
//! Everything the UI exposes as a slider lives here. Defaults are per-region
//! and must stay in step with `ingest/src/ingest/config.py`, which uses the
//! same radius and pipe-cost figures.

use enum_map::{enum_map, EnumMap};
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::types::{Region, SinkCat};

/// How a straight line between two points becomes a pipe length.
///
/// Internally tagged so the web layer round-trips it as plain JSON:
/// `{"kind": "detour", "k": 1.3}`.
#[derive(Clone, Copy, PartialEq, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
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
pub enum Decay {
    /// Reaches zero exactly at the radius.
    Linear,
    /// Never quite reaches zero; `k` sets the steepness.
    Exp { k: f32 },
}

/// What to do about a pipe that would cross open water.
#[derive(Clone, Copy, PartialEq, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum WaterPolicy {
    /// Treat the sink as unreachable.
    Exclude,
    /// Keep it, but multiply the pipe length by `factor`.
    Penalty { factor: f32 },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Weights {
    /// Per-category desirability. Pool ranks highest because a pool wants
    /// low-grade heat year-round, which is exactly what a data center has.
    pub cat: EnumMap<SinkCat, f32>,
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

/// Cost and price assumptions. Defined now as configuration; the economics
/// model that consumes it arrives with `econ.rs`.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
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
            cat: enum_map! {
                SinkCat::Pool => 1.0,
                SinkCat::Wwtp => 0.9,
                SinkCat::Greenhouse => 0.9,
                SinkCat::Hospital => 0.8,
                SinkCat::Hotel => 0.7,
                SinkCat::ResidentialMultifamily => 0.6,
                SinkCat::University => 0.5,
                SinkCat::Brewery => 0.5,
                SinkCat::School => 0.3,
                SinkCat::Office => 0.3,
            },
            radius_m: match region {
                Region::Nyc => 1000.0,
                Region::Upstate => 4000.0,
            },
            // Detour factors match ingest's per-region `detour` values, so the
            // sink pre-filter and the engine agree on what "in radius" means.
            // NYC moves to RotatedL1 { theta_deg: 29.0 } once that model is
            // implemented; defaulting to it now would select unreachable code.
            distance: match region {
                Region::Nyc => DistanceModel::Detour { k: 1.30 },
                Region::Upstate => DistanceModel::Detour { k: 1.20 },
            },
            decay: Decay::Linear,
            steam_bonus: 0.5,
            uten_bonus: 0.3,
            per_sink_cap: 0.25,
            log_base: 10.0,
            water_crossing: WaterPolicy::Penalty { factor: 2.0 },
            approach_c: 5.0,
            hp_carnot_fraction: 0.5,
            utilization_hours: 0.9 * 8760.0,
        }
    }

    pub fn validate(&self) -> Result<(), WeightsError> {
        for (_, w) in &self.cat {
            non_negative("cat weight", *w)?;
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
            },
            hp_capex_per_mw_th: 900_000.0,
            gas_price_per_mwh_th: 45.0,
            boiler_eff: 0.85,
            elec_price_per_mwh: match region {
                Region::Nyc => 150.0,
                Region::Upstate => 90.0,
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
