//! R-tree over projected sink positions (HEATMATCH.md §4.3).

use rstar::{PointDistance, RTree, RTreeObject, AABB};

/// A sink's projected position plus its index into the region's sink vector.
#[derive(Clone, Copy, Debug)]
pub struct SinkPt {
    pub xy: [f32; 2],
    pub idx: u32,
}

impl RTreeObject for SinkPt {
    type Envelope = AABB<[f32; 2]>;

    fn envelope(&self) -> Self::Envelope {
        AABB::from_point(self.xy)
    }
}

impl PointDistance for SinkPt {
    fn distance_2(&self, point: &[f32; 2]) -> f32 {
        let dx = self.xy[0] - point[0];
        let dy = self.xy[1] - point[1];
        dx * dx + dy * dy
    }
}

pub fn build(points: Vec<SinkPt>) -> RTree<SinkPt> {
    // Bulk loading produces a better-balanced tree than repeated insertion,
    // and the point set is fully known up front.
    RTree::bulk_load(points)
}
