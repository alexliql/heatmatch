//! Ad-hoc timing of `rank` over the committed dataset (budget: 50 ms in
//! release). Run with:
//! `cargo run --release --example bench_rank -p heatmatch-core`

#[path = "../tests/support/mod.rs"]
mod support;

use std::time::Instant;

use heatmatch_core::{Econ, Engine, Region, Weights};

fn main() {
    let (dcs, sinks) = support::committed();
    println!("dataset: {} data centers, {} sinks", dcs.len(), sinks.len());

    let build = Instant::now();
    let engine = Engine::new(dcs, sinks, &[]).unwrap();
    println!(
        "Engine::new  {:>8.3} ms",
        build.elapsed().as_secs_f64() * 1e3
    );

    let w = Weights::default_for(Region::Nyc);
    let e = Econ::default_for(Region::Nyc);
    engine.rank(Region::Nyc, &w, &e).unwrap(); // warm up

    let runs = 1000;
    let t = Instant::now();
    for _ in 0..runs {
        std::hint::black_box(engine.rank(Region::Nyc, &w, &e).unwrap());
    }
    let per = t.elapsed().as_secs_f64() * 1e3 / runs as f64;
    println!(
        "rank         {per:>8.3} ms/call  (budget 50 ms) -> {}",
        if per < 50.0 { "PASS" } else { "FAIL" }
    );
}
