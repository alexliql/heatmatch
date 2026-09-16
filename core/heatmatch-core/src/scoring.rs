//! Ranking engine (HEATMATCH.md §4.6).
//!
//! Scoring runs per data center against the sinks in its region. The supply a
//! facility has is finite, so sinks compete for it: the allocation step is what
//! stops a ranking from simply rewarding whoever has the most neighbours.

use std::collections::HashMap;

use rstar::RTree;
use smallvec::SmallVec;
use thiserror::Error;

use crate::distance::{euclid, pipe_length, search_radius};
use crate::econ::{self, Connection};
use crate::frame::LocalFrame;
use crate::index::{self, SinkPt};
use crate::season;
use crate::thermo::{self, HeatPump};
use crate::types::{Contribution, DataCenter, Match, Region, Sink};
use crate::water::WaterIndex;
use crate::weights::{Decay, Econ, WaterPolicy, Weights};

#[derive(Debug, Error, PartialEq)]
pub enum EngineError {
    #[error("unknown data center id: {0}")]
    UnknownDataCenter(String),
    #[error("duplicate id in input: {0}")]
    DuplicateId(String),
    #[error("invalid weights: {0}")]
    Weights(#[from] crate::weights::WeightsError),
}

struct RegionData {
    dcs: Vec<DataCenter>,
    sinks: Vec<Sink>,
    sink_xy: Vec<[f32; 2]>,
    tree: RTree<SinkPt>,
    frame: LocalFrame,
    water: WaterIndex,
}

pub struct Engine {
    regions: HashMap<Region, RegionData>,
    /// Maps a data center id to its region, so `explain` can find it without
    /// the caller having to say where it is.
    dc_region: HashMap<String, Region>,
}

/// Result of sharing one data center's supply across its in-radius sinks.
struct Allocation {
    contributions: Vec<Contribution>,
    supply_mwh: f32,
    demand_mwh_in_radius: f32,
}

/// A candidate sink with everything needed to allocate and score it.
struct Candidate {
    idx: usize,
    dist_m: f32,
    pipe_m: f32,
    crosses_water: bool,
    hp: HeatPump,
    raw: f32,
    demand_mwh: f32,
}

impl Engine {
    /// Build an engine. `water` polygons are in lon/lat and get projected into
    /// each region's frame; pass an empty slice when none are available.
    pub fn new(
        dcs: Vec<DataCenter>,
        sinks: Vec<Sink>,
        water: &[geo::Polygon<f64>],
    ) -> Result<Self, EngineError> {
        let mut seen = HashMap::new();
        for id in dcs.iter().map(|d| &d.id).chain(sinks.iter().map(|s| &s.id)) {
            if seen.insert(id.clone(), ()).is_some() {
                return Err(EngineError::DuplicateId(id.clone()));
            }
        }

        let mut regions: HashMap<Region, RegionData> = HashMap::new();
        for region in Region::ALL {
            let (lat0, lon0) = region.origin();
            let frame = LocalFrame::new(lat0, lon0);
            let region_sinks: Vec<Sink> = sinks
                .iter()
                .filter(|s| s.region == region)
                .cloned()
                .collect();
            let sink_xy: Vec<[f32; 2]> = region_sinks
                .iter()
                .map(|s| frame.to_xy(s.lat, s.lon))
                .collect();
            let pts = sink_xy
                .iter()
                .enumerate()
                .map(|(i, xy)| SinkPt {
                    xy: *xy,
                    idx: i as u32,
                })
                .collect();

            regions.insert(
                region,
                RegionData {
                    dcs: dcs.iter().filter(|d| d.region == region).cloned().collect(),
                    sinks: region_sinks,
                    sink_xy,
                    tree: index::build(pts),
                    water: WaterIndex::build(water, &frame),
                    frame,
                },
            );
        }

        let dc_region = dcs.into_iter().map(|d| (d.id, d.region)).collect();
        Ok(Self { regions, dc_region })
    }

    pub fn datacenter(&self, id: &str) -> Option<&DataCenter> {
        let region = self.dc_region.get(id)?;
        self.regions[region].dcs.iter().find(|d| d.id == id)
    }

    /// Rank every data center in `region`, best first.
    pub fn rank(&self, region: Region, w: &Weights, e: &Econ) -> Result<Vec<Match>, EngineError> {
        w.validate()?;
        e.validate()?;
        let data = &self.regions[&region];
        let mut out: Vec<Match> = data
            .dcs
            .iter()
            .map(|dc| self.score_dc(data, dc, w, e))
            .collect();
        // Ties broken by id so the order never depends on input ordering.
        out.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.dc.cmp(&b.dc))
        });
        Ok(out)
    }

    /// Every in-radius sink for one data center, best first.
    ///
    /// Sinks that received no allocation are included with `score = 0`, so the
    /// sum of these scores equals the data center's `Match` score.
    pub fn explain(&self, dc_id: &str, w: &Weights) -> Result<Vec<Contribution>, EngineError> {
        w.validate()?;
        let region = *self
            .dc_region
            .get(dc_id)
            .ok_or_else(|| EngineError::UnknownDataCenter(dc_id.to_string()))?;
        let data = &self.regions[&region];
        let dc = data
            .dcs
            .iter()
            .find(|d| d.id == dc_id)
            .ok_or_else(|| EngineError::UnknownDataCenter(dc_id.to_string()))?;
        Ok(self.contributions(data, dc, w).contributions)
    }

    /// Collect in-radius sinks and score them by desirability, before any
    /// supply constraint is applied.
    fn candidates(&self, data: &RegionData, dc: &DataCenter, w: &Weights) -> Vec<Candidate> {
        let dc_xy = data.frame.to_xy(dc.lat, dc.lon);
        let r = search_radius(w.radius_m, &w.distance);
        let mut found: Vec<Candidate> = data
            .tree
            .locate_within_distance(dc_xy, r * r)
            .filter_map(|pt| {
                let idx = pt.idx as usize;
                let sink = &data.sinks[idx];
                let mut pipe_m = pipe_length(dc_xy, data.sink_xy[idx], &w.distance);

                let crosses_water =
                    !data.water.is_empty() && data.water.crosses(dc_xy, data.sink_xy[idx]);
                if crosses_water {
                    match w.water_crossing {
                        WaterPolicy::Exclude => return None,
                        WaterPolicy::Penalty { factor } => pipe_m *= factor,
                    }
                }
                // Checked after the penalty: a crossing that pushes the pipe
                // past the radius takes the sink out of range.
                if pipe_m > w.radius_m {
                    return None;
                }
                let decay = match w.decay {
                    Decay::Linear => 1.0 - pipe_m / w.radius_m,
                    Decay::Exp { k } => (-k * pipe_m / w.radius_m).exp(),
                };
                let demand_mwh = sink.demand_mwh();
                // log_base is the base of the logarithm, so a 1 GWh sink
                // normalizes to ~3 under the default base of 10.
                let demand_norm = (1.0 + demand_mwh).ln() / w.log_base.ln();
                let bonus =
                    1.0 + if dc.in_steam && sink.in_steam {
                        w.steam_bonus
                    } else {
                        0.0
                    } + if dc.in_uten || sink.in_uten {
                        w.uten_bonus
                    } else {
                        0.0
                    };

                // Heat that needs pumping is worth less: cop/(cop+1) is the
                // share of delivered energy that came from the waste heat
                // rather than from the electricity meter.
                let hp =
                    thermo::heat_pump(dc.cooling, sink.cat, w.approach_c, w.hp_carnot_fraction);
                let hp_factor = if hp.required {
                    hp.cop / (hp.cop + 1.0)
                } else {
                    1.0
                };

                Some(Candidate {
                    idx,
                    dist_m: euclid(dc_xy, data.sink_xy[idx]),
                    pipe_m,
                    crosses_water,
                    hp,
                    raw: w.cat[sink.cat] * demand_norm * decay.max(0.0) * hp_factor * bonus,
                    demand_mwh,
                })
            })
            .collect();

        // Descending desirability, ties by sink id: the allocation below is
        // greedy, so this ordering decides who gets heat first and must not
        // depend on the r-tree's traversal order.
        found.sort_by(|a, b| {
            b.raw
                .partial_cmp(&a.raw)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| data.sinks[a.idx].id.cmp(&data.sinks[b.idx].id))
        });
        found
    }

    /// Share the data center's supply out across its candidates, greediest
    /// first, and turn each allocation into a `Contribution`.
    fn contributions(&self, data: &RegionData, dc: &DataCenter, w: &Weights) -> Allocation {
        let supply_mwh = dc.mw * w.utilization_hours;
        let cap = w.per_sink_cap * supply_mwh;
        let mut remaining = supply_mwh;

        let candidates = self.candidates(data, dc, w);
        let demand_mwh_in_radius = candidates.iter().map(|c| c.demand_mwh).sum();

        let contributions = candidates
            .into_iter()
            .map(|c| {
                let delivered = c.demand_mwh.min(remaining).min(cap).max(0.0);
                remaining -= delivered;
                // A sink that gets nothing scores nothing, however attractive
                // it looked: there is no heat left to send it.
                let share = if c.demand_mwh > 0.0 {
                    delivered / c.demand_mwh
                } else {
                    0.0
                };
                Contribution {
                    sink: data.sinks[c.idx].id.clone(),
                    cat: data.sinks[c.idx].cat,
                    dist_m: c.dist_m,
                    pipe_m: c.pipe_m,
                    crosses_water: c.crosses_water,
                    hp_required: c.hp.required,
                    cop: c.hp.cop,
                    delivered_mwh: delivered,
                    score: c.raw * share,
                }
            })
            .collect::<Vec<_>>();

        // Allocation runs in desirability order, but a sink's final score is
        // scaled by the share it actually received, so that order is not the
        // score order. Re-sort before returning: callers, and `top`, are
        // promised best-scoring first.
        let mut contributions = contributions;
        contributions.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.sink.cmp(&b.sink))
        });

        Allocation {
            contributions,
            supply_mwh,
            demand_mwh_in_radius,
        }
    }

    fn score_dc(&self, data: &RegionData, dc: &DataCenter, w: &Weights, e: &Econ) -> Match {
        let Allocation {
            contributions,
            supply_mwh,
            demand_mwh_in_radius,
        } = self.contributions(data, dc, w);

        let score: f32 = contributions.iter().map(|c| c.score).sum();

        // Seasonality decides how much of the allocation can actually be used:
        // heat produced in a month nobody needs it is wasted.
        let allocated: Vec<(crate::types::SinkCat, f32)> = contributions
            .iter()
            .filter(|c| c.delivered_mwh > 0.0)
            .map(|c| (c.cat, c.delivered_mwh))
            .collect();
        let (utilization, delivered_mwh) = season::utilization(supply_mwh, &allocated);

        let connections: Vec<Connection> = contributions
            .iter()
            .filter(|c| c.delivered_mwh > 0.0)
            .map(|c| Connection {
                pipe_m: c.pipe_m,
                delivered_mwh: c.delivered_mwh,
                cop: c.hp_required.then_some(c.cop),
            })
            .collect();
        let economics = econ::evaluate(&connections, delivered_mwh, e, w.utilization_hours);

        let mut top: SmallVec<[Contribution; 5]> = SmallVec::new();
        top.extend(
            contributions
                .iter()
                .filter(|c| c.score > 0.0)
                .take(5)
                .cloned(),
        );

        Match {
            dc: dc.id.clone(),
            region: dc.region,
            score,
            supply_mwh,
            demand_mwh_in_radius,
            utilization,
            delivered_mwh,
            capex: economics.capex,
            annual_savings: economics.annual_savings,
            payback_yrs: economics.payback_yrs,
            top,
        }
    }
}
