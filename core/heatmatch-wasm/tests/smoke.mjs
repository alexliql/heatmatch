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

// The bundler target emits ESM with a wasm import, which Node resolves through
// the nodejs-flavoured build; wasm-pack writes both into the same package.
const { WasmEngine } = await import(join(here, "../../../web/src/wasm/heatmatch_wasm.js"));

const dcs = readFileSync(join(fixtures, "mini_dcs.geojson"), "utf8");
const sinks = readFileSync(join(fixtures, "mini_sinks.geojson"), "utf8");

const engine = new WasmEngine(dcs, sinks, "");
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

const profiles = WasmEngine.profiles();
assert.equal(Object.keys(profiles).length, 10, "ten sink categories");
assert.equal(profiles.pool.length, 12, "twelve months");

// Errors must arrive as real exceptions, not silent nulls.
assert.throws(() => engine.rank("atlantis", weights, econ), /unknown region/);
assert.throws(() => engine.explain("dc_nope", weights), /unknown data center/i);
assert.throws(() => new WasmEngine("{not json", sinks, ""), /parsing/);

console.log(`smoke ok: ${ranked.length} ranked, top ${ranked[0].dc} score ${ranked[0].score.toFixed(4)}`);
