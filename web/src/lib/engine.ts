// Loads the data assets and the wasm engine.
//
// Everything here runs in the browser only: the wasm module is imported
// dynamically so it never executes during the static export, which has no
// WebAssembly host.

import type { Econ, Manifest, Match, Contribution, Region, Weights } from "./types";

export interface LoadProgress {
  stage: "manifest" | "data" | "engine" | "ready";
  bytes: number;
  message: string;
}

export interface Engine {
  rank(region: Region, weights: Weights, econ: Econ): Match[];
  explain(dcId: string, weights: Weights): Contribution[];
  defaultWeights(region: Region): Weights;
  defaultEcon(region: Region): Econ;
  /** Monthly demand shapes for a region, after any bundle override. */
  profiles(region: Region): Record<string, number[]>;
  version: string;
  manifest: Manifest;
  /** Raw GeoJSON, reused as map sources so they are not fetched twice. */
  geo: {
    datacenters: unknown;
    sinks: unknown;
    water: unknown | null;
    zones: unknown | null;
  };
}

const BASE = "data";

async function fetchText(file: string): Promise<{ text: string; bytes: number }> {
  const res = await fetch(`${BASE}/${file}`);
  if (!res.ok) throw new Error(`could not load ${file}: ${res.status} ${res.statusText}`);
  const text = await res.text();
  return { text, bytes: text.length };
}

/**
 * Fetch the manifest, then the hash-named assets it points at, then construct
 * the engine. Assets are addressed through the manifest rather than by a fixed
 * name so a rebuilt dataset cannot be served from a stale cache.
 */
export async function loadEngine(onProgress?: (p: LoadProgress) => void): Promise<Engine> {
  onProgress?.({ stage: "manifest", bytes: 0, message: "Reading manifest…" });

  const manifestRes = await fetch(`${BASE}/manifest.json`);
  if (!manifestRes.ok) {
    throw new Error(
      `No data manifest found (${manifestRes.status}). Run \`make ingest\` to build the dataset.`,
    );
  }
  const manifest: Manifest = await manifestRes.json();

  onProgress?.({ stage: "data", bytes: 0, message: "Downloading data…" });
  const [dcs, sinks] = await Promise.all([
    fetchText(manifest.datacenters.file),
    fetchText(manifest.sinks.file),
  ]);
  // Hydrography is published in a later phase; the engine accepts an empty
  // string and simply never flags a crossing.
  const water = manifest.water ? await fetchText(manifest.water.file) : { text: "", bytes: 0 };
  // Zones are drawn but never modelled here; the engine reads in_steam/in_uten
  // from the features themselves, which ingest tagged.
  const zones = manifest.zones ? await fetchText(manifest.zones.file) : { text: "", bytes: 0 };
  // Seasonal shapes for regions that model them rather than using the built-in
  // table. Absent for a New York-only bundle.
  const profiles = manifest.profiles
    ? await fetchText(manifest.profiles.file)
    : { text: "", bytes: 0 };

  const bytes = dcs.bytes + sinks.bytes + water.bytes + zones.bytes + profiles.bytes;
  onProgress?.({ stage: "engine", bytes, message: "Starting engine…" });

  const wasm = await import("@/wasm/heatmatch_wasm");
  const inner = new wasm.WasmEngine(dcs.text, sinks.text, water.text, profiles.text);

  onProgress?.({ stage: "ready", bytes, message: "Ready" });

  return {
    rank: (region, weights, econ) => inner.rank(region, weights, econ) as Match[],
    explain: (dcId, weights) => inner.explain(dcId, weights) as Contribution[],
    defaultWeights: (region) => wasm.WasmEngine.default_weights(region) as Weights,
    defaultEcon: (region) => wasm.WasmEngine.default_econ(region) as Econ,
    profiles: (region) => inner.profiles(region) as Record<string, number[]>,
    version: wasm.WasmEngine.version(),
    manifest,
    geo: {
      datacenters: JSON.parse(dcs.text),
      sinks: JSON.parse(sinks.text),
      water: water.text ? JSON.parse(water.text) : null,
      zones: zones.text ? JSON.parse(zones.text) : null,
    },
  };
}
