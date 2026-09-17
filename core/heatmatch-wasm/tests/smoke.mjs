// Node smoke test for the built wasm package (HEATMATCH.md §5).
//
// Loads the core crate's fixtures through the real wasm boundary and checks the
// engine both ranks them and reports the JSON shapes the web app expects. This
// is the only test that exercises GeoJSON parsing, serde-wasm-bindgen
// conversion and the generated types together.
//
// Run with: node core/heatmatch-wasm/tests/smoke.mjs

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "../../heatmatch-core/tests/fixtures");

// Loaded from a nodejs-target build, not the bundler one the web app uses:
// the bundler output imports the .wasm file directly, which only a bundler (or
// a very new Node with experimental flags) can resolve. Build it with
// `make wasm-node`, or run the whole thing via `make wasm-test`.
const pkg = join(here, "../pkg-node/heatmatch_wasm.js");
const { WasmEngine } = await import(pkg);

const dcs = readFileSync(join(fixtures, "mini_dcs.geojson"), "utf8");
const sinks = readFileSync(join(fixtures, "mini_sinks.geojson"), "utf8");

const engine = new WasmEngine(dcs, sinks, "", "");
assert.match(WasmEngine.version(), /^\d+\.\d+\.\d+$/, "version should be semver");

const weights = WasmEngine.default_weights("nyc");
const econ = WasmEngine.default_econ("nyc");
assert.equal(weights.radius_m, 1000, "nyc radius default");
assert.equal(weights.distance.kind, "rotated_l1", "nyc uses the rotated grid");
assert.equal(typeof weights.cat.pool, "number", "cat weights serialize as an object");
assert.equal(econ.pipe_cost_per_m, 3000, "nyc pipe cost default");

const ranked = engine.rank("nyc", weights, econ);
assert.equal(ranked.length, 4, "four fixture data centers");
assert.ok(ranked[0].score >= ranked[1].score, "sorted by score");

for (const key of ["dc", "region", "score", "supply_mwh", "utilization",
                   "delivered_mwh", "capex", "annual_savings", "top"]) {
  assert.ok(key in ranked[0], `Match is missing ${key}`);
}
assert.ok(Array.isArray(ranked[0].top), "top must be a plain array, not a SmallVec");

const contribs = engine.explain(ranked[0].dc, weights);
assert.ok(contribs.length > 0, "top-ranked site should explain to something");
for (const key of ["sink", "cat", "dist_m", "pipe_m", "crosses_water",
                   "hp_required", "cop", "delivered_mwh", "score"]) {
  assert.ok(key in contribs[0], `Contribution is missing ${key}`);
}

// explain must account for the whole score, or the detail view contradicts the
// table it was opened from.
const summed = contribs.reduce((a, c) => a + c.score, 0);
assert.ok(Math.abs(summed - ranked[0].score) < 1e-3,
  `explain sum ${summed} != rank score ${ranked[0].score}`);

const profiles = engine.profiles("nyc");
assert.equal(Object.keys(profiles).length, 10, "ten sink categories");
assert.equal(profiles.pool.length, 12, "twelve months");

// A region the bundle does not override falls back to the built-in shapes.
assert.deepEqual(engine.profiles("nova").pool, profiles.pool, "nova falls back");

// Bundle-supplied profiles replace only what they name, and must be a
// distribution — this is the check that a bad ingest run cannot get past.
const withProfiles = new WasmEngine(dcs, sinks, "",
  JSON.stringify({ nova: { hospital: Array(12).fill(1 / 12) } }));
// Tolerance, not equality: the engine holds these as f32.
assert.ok(Math.abs(withProfiles.profiles("nova").hospital[6] - 1 / 12) < 1e-6,
  "override applied");
assert.deepEqual(withProfiles.profiles("nyc").hospital, profiles.hospital,
  "override must not leak into another region");
assert.throws(
  () => new WasmEngine(dcs, sinks, "", JSON.stringify({ nova: { pool: Array(12).fill(1) } })),
  /sums to/, "a profile that is not a distribution must be rejected");

// Virginia defaults, including the capacity-confidence discount.
const novaWeights = WasmEngine.default_weights("nova");
assert.equal(novaWeights.radius_m, 3000, "nova radius default");
assert.equal(novaWeights.confidence.reported, 1, "reported capacity is not discounted");
assert.equal(novaWeights.confidence.footprint_estimate, 0.5, "footprint guesses are");
assert.equal(weights.confidence.footprint_estimate, 1, "nyc discounts nothing");

// Errors must arrive as real exceptions, not silent nulls.
assert.throws(() => engine.rank("atlantis", weights, econ), /unknown region/);
assert.throws(() => engine.explain("dc_nope", weights), /unknown data center/i);
assert.throws(() => new WasmEngine("{not json", sinks, "", ""), /parsing/);

console.log(`smoke ok: ${ranked.length} ranked, top ${ranked[0].dc} score ${ranked[0].score.toFixed(4)}`);
