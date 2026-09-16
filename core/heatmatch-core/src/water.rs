//! Water-crossing detection (HEATMATCH.md §4.3).
//!
//! A pipe that would cross open water is either impossible or far more
//! expensive than its length suggests, so the model needs to know. Polygons
//! arrive in lon/lat and are projected into each region's frame, because the
//! segments tested against them are already in metres.

use geo::{Contains, Intersects, Polygon};
use rstar::{RTree, RTreeObject, AABB};

use crate::frame::LocalFrame;

/// A water polygon in projected metres, with its bounding box for the index.
pub struct WaterPoly {
    poly: Polygon<f32>,
    envelope: AABB<[f32; 2]>,
}

impl RTreeObject for WaterPoly {
    type Envelope = AABB<[f32; 2]>;
    fn envelope(&self) -> Self::Envelope {
        self.envelope
    }
}

#[derive(Default)]
pub struct WaterIndex {
    tree: Option<RTree<WaterPoly>>,
}

impl WaterIndex {
    /// Project lon/lat polygons into `frame` and index them.
    pub fn build(polys: &[Polygon<f64>], frame: &LocalFrame) -> Self {
        let projected: Vec<WaterPoly> = polys
            .iter()
            .filter_map(|p| {
                let ring: Vec<(f32, f32)> = p
                    .exterior()
                    .points()
                    .map(|pt| {
                        let xy = frame.to_xy(pt.y(), pt.x());
                        (xy[0], xy[1])
                    })
                    .collect();
                if ring.len() < 4 {
                    return None;
                }
                let poly = Polygon::new(ring.into(), vec![]);
                let bbox = bounds(&poly)?;
                Some(WaterPoly {
                    poly,
                    envelope: bbox,
                })
            })
            .collect();

        Self {
            tree: (!projected.is_empty()).then(|| RTree::bulk_load(projected)),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.tree.is_none()
    }

    /// True if the straight segment `a`–`b` meets any water polygon.
    ///
    /// The r-tree narrows to candidates by bounding box first; exact polygon
    /// intersection is far too slow to run against every polygon in the state.
    pub fn crosses(&self, a: [f32; 2], b: [f32; 2]) -> bool {
        let Some(tree) = &self.tree else {
            return false;
        };
        let seg = geo::Line::new(
            geo::Coord { x: a[0], y: a[1] },
            geo::Coord { x: b[0], y: b[1] },
        );
        let query = AABB::from_corners(
            [a[0].min(b[0]), a[1].min(b[1])],
            [a[0].max(b[0]), a[1].max(b[1])],
        );
        tree.locate_in_envelope_intersecting(&query)
            .any(|w| w.poly.intersects(&seg) || w.poly.contains(&seg))
    }
}

fn bounds(poly: &Polygon<f32>) -> Option<AABB<[f32; 2]>> {
    let mut it = poly.exterior().points();
    let first = it.next()?;
    let (mut min_x, mut min_y) = (first.x(), first.y());
    let (mut max_x, mut max_y) = (first.x(), first.y());
    for p in it {
        min_x = min_x.min(p.x());
        min_y = min_y.min(p.y());
        max_x = max_x.max(p.x());
        max_y = max_y.max(p.y());
    }
    Some(AABB::from_corners([min_x, min_y], [max_x, max_y]))
}
