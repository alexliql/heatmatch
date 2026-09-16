//! Local equirectangular projection (HEATMATCH.md §4.3).
//!
//! Distances here span at most a few kilometres, so a full map projection buys
//! nothing. Flattening around a per-region origin keeps every downstream
//! computation in plain metres.

/// Mean Earth radius, metres.
const R: f64 = 6_371_000.0;

#[derive(Clone, Copy, Debug)]
pub struct LocalFrame {
    lat0: f64,
    lon0: f64,
    cos_lat0: f64,
}

impl LocalFrame {
    pub fn new(lat0: f64, lon0: f64) -> Self {
        Self {
            lat0,
            lon0,
            cos_lat0: lat0.to_radians().cos(),
        }
    }

    /// Project to metres east/north of the origin.
    ///
    /// Computed in f64 and narrowed at the end: the subtraction of two similar
    /// degree values loses precision badly in f32.
    pub fn to_xy(&self, lat: f64, lon: f64) -> [f32; 2] {
        let x = R * (lon - self.lon0).to_radians() * self.cos_lat0;
        let y = R * (lat - self.lat0).to_radians();
        [x as f32, y as f32]
    }
}
