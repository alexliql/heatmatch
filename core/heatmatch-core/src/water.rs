//! Water-crossing detection.
//!
//! A pipe that would cross open water is either impossible or far more
//! expensive than its length suggests. Polygons arrive in lon/lat and are
//! projected into each region's frame, where the tested segments live.

use geo::{Contains, Intersects, Polygon};
use rstar::{primitives::CachedEnvelope, RTree, AABB};

use crate::frame::LocalFrame;

#[derive(Default)]
pub struct WaterIndex {
    tree: RTree<CachedEnvelope<Polygon<f32>>>,
}

impl WaterIndex {
    /// Project lon/lat polygons into `frame` and index them.
    pub fn build(polys: &[Polygon<f64>], frame: &LocalFrame) -> Self {
        let projected: Vec<_> = polys
            .iter()
            .filter_map(|p| {
                let ring: Vec<(f32, f32)> = p
                    .exterior()
                    .points()
                    .map(|pt| frame.to_xy(pt.y(), pt.x()).into())
                    .collect();
                (ring.len() >= 4).then(|| CachedEnvelope::new(Polygon::new(ring.into(), vec![])))
            })
            .collect();
        Self {
            tree: RTree::bulk_load(projected),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.tree.size() == 0
    }

    /// True if the straight segment `a`–`b` meets any water polygon. The
    /// r-tree narrows to candidates by bounding box first.
    pub fn crosses(&self, a: [f32; 2], b: [f32; 2]) -> bool {
        let seg = geo::Line::new((a[0], a[1]), (b[0], b[1]));
        let query = AABB::from_corners(
            geo::Point::new(a[0].min(b[0]), a[1].min(b[1])),
            geo::Point::new(a[0].max(b[0]), a[1].max(b[1])),
        );
        self.tree
            .locate_in_envelope_intersecting(&query)
            .any(|w| w.intersects(&seg) || w.contains(&seg))
    }
}
