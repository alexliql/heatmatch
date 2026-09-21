// Loads the data assets and the wasm engine.
//
// Everything here runs in the browser only: the wasm module is imported
// dynamically so it never executes during the static export, which has no
// WebAssembly host.

import type {
  Contribution,
  DcFeature,
  Econ,
  Manifest,
  Match,
  PointCollection,
  Region,
  SinkFeature,
  Weights,
} from "./types";

export type LoadStage = "manifest" | "data" | "engine" | "ready";

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
    datacenters: PointCollection<DcFeature>;
    sinks: PointCollection<SinkFeature>;
    zones: unknown | null;
  };
}

const BASE = "data";

async function fetchText(file: string | undefined): Promise<string> {
  if (!file) return "";
  const res = await fetch(`${BASE}/${file}`);
  if (!res.ok) throw new Error(`could not load ${file}: ${res.status} ${res.statusText}`);
  return res.text();
}

/**
 * Fetch the manifest, then the hash-named assets it points at, then construct
 * the engine. Assets are addressed through the manifest rather than by a fixed
 * name so a rebuilt dataset cannot be served from a stale cache.
 */
export async function loadEngine(onProgress?: (stage: LoadStage) => void): Promise<Engine> {
  onProgress?.("manifest");

  const manifestRes = await fetch(`${BASE}/manifest.json`);
  if (!manifestRes.ok) {
    throw new Error(
      `No data manifest found (${manifestRes.status}). Run \`make ingest\` to build the dataset.`,
    );
  }
  const manifest: Manifest = await manifestRes.json();

  onProgress?.("data");
  // Water, zones and profiles are optional; the engine takes an empty string
  // for the ones a bundle does not publish. Zones are drawn, never modelled:
  // ingest already tagged every feature with in_steam/in_uten.
  const [dcs, sinks, water, zones, profiles] = await Promise.all(
    [manifest.datacenters, manifest.sinks, manifest.water, manifest.zones, manifest.profiles].map(
      (a) => fetchText(a?.file),
    ),
  );
  onProgress?.("engine");

  const wasm = await import("@/wasm/heatmatch_wasm");
  const inner = new wasm.WasmEngine(dcs, sinks, water, profiles);
  onProgress?.("ready");

  return {
    rank: (region, weights, econ) => inner.rank(region, weights, econ) as Match[],
    explain: (dcId, weights) => inner.explain(dcId, weights) as Contribution[],
    defaultWeights: (region) => wasm.WasmEngine.default_weights(region) as Weights,
    defaultEcon: (region) => wasm.WasmEngine.default_econ(region) as Econ,
    profiles: (region) => inner.profiles(region) as Record<string, number[]>,
    version: wasm.WasmEngine.version(),
    manifest,
    geo: {
      datacenters: JSON.parse(dcs),
      sinks: JSON.parse(sinks),
      zones: zones ? JSON.parse(zones) : null,
    },
  };
}
