//! Distance models and the query radius they imply (HEATMATCH.md §4.3).

use crate::weights::DistanceModel;

pub fn euclid(a: [f32; 2], b: [f32; 2]) -> f32 {
    let dx = a[0] - b[0];
    let dy = a[1] - b[1];
    (dx * dx + dy * dy).sqrt()
}

/// Length of pipe needed to connect `a` to `b` under `model`.
pub fn pipe_length(a: [f32; 2], b: [f32; 2], model: &DistanceModel) -> f32 {
    match model {
        DistanceModel::Euclid => euclid(a, b),
        DistanceModel::Detour { k } => euclid(a, b) * k,
        // Streets on a grid: a pipe runs along two axes, not the diagonal.
        // Rotate the offset back onto those axes, then take Manhattan distance.
        DistanceModel::RotatedL1 { theta_deg } => {
            let (sin, cos) = (-theta_deg.to_radians()).sin_cos();
            let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
            (dx * cos - dy * sin).abs() + (dx * sin + dy * cos).abs()
        }
    }
}

/// Straight-line radius that must be searched to find every sink whose pipe
/// length could come in under `radius_m`.
///
/// This is an exact bound, not a safety margin. Under Detour,
/// `pipe = d*k <= radius` implies `d <= radius/k`. Under Euclid the two are
/// the same. Searching less would silently drop candidates; searching more
/// just costs time.
pub fn search_radius(radius_m: f32, model: &DistanceModel) -> f32 {
    match model {
        DistanceModel::Euclid => radius_m,
        DistanceModel::Detour { k } => radius_m / k.min(1.0),
        // |dx| + |dy| >= sqrt(dx^2 + dy^2), so an L1 length within the radius
        // always implies a Euclidean distance within it too.
        DistanceModel::RotatedL1 { .. } => radius_m,
    }
}
