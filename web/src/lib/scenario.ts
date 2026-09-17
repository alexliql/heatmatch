// A tuned scenario as a URL parameter, so "look at this" is a link.
//
// Only what differs from the defaults is encoded, so the default view has no
// parameter at all and a small tweak is a short string.

import { diffFromDefaults } from "./defaults";
import type { Engine } from "./engine";
import { REGIONS, type Econ, type Region, type Weights } from "./types";

type ByRegion<T> = Record<Region, T>;
type Plain = Record<string, unknown>;

export const PARAM = "s";

function toBase64Url(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(s: string): string {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function encodeScenario(
  engine: Engine,
  weights: ByRegion<Weights>,
  econ: ByRegion<Econ>,
): string | null {
  const d = diffFromDefaults(engine, weights, econ);
  if (d.count === 0) return null;
  const out: Plain = {};
  for (const r of REGIONS) {
    const { w, e } = d.changes[r];
    if (w || e) out[r] = { ...(w ? { w } : {}), ...(e ? { e } : {}) };
  }
  return toBase64Url(JSON.stringify(out));
}

/** Deep merge of a partial onto defaults. A tagged union is taken whole if
 *  the partial carries a `kind`; unknown keys are ignored. */
function merge<T extends Plain>(base: T, patch: Plain): T {
  const out: Plain = { ...base };
  if (typeof patch.kind === "string") return patch as T;
  for (const [k, v] of Object.entries(patch)) {
    if (!(k in base)) continue;
    const bv = base[k];
    if (v && typeof v === "object" && bv && typeof bv === "object") {
      out[k] = merge(bv as Plain, v as Plain);
    } else if (typeof v === typeof bv) {
      out[k] = v;
    }
  }
  return out as T;
}

export function decodeScenario(
  engine: Engine,
  param: string,
): { weights: ByRegion<Weights>; econ: ByRegion<Econ> } | null {
  try {
    const parsed = JSON.parse(fromBase64Url(param)) as Plain;
    const weights = {} as ByRegion<Weights>;
    const econ = {} as ByRegion<Econ>;
    for (const r of REGIONS) {
      const part = (parsed[r] ?? {}) as { w?: Plain; e?: Plain };
      weights[r] = merge(engine.defaultWeights(r) as unknown as Plain, part.w ?? {}) as unknown as Weights;
      econ[r] = merge(engine.defaultEcon(r) as unknown as Plain, part.e ?? {}) as unknown as Econ;
    }
    return { weights, econ };
  } catch {
    return null;
  }
}

export function readScenarioParam(): string | null {
  try {
    return new URLSearchParams(window.location.search).get(PARAM);
  } catch {
    return null;
  }
}

export function writeScenarioParam(value: string | null) {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(PARAM, value);
  else url.searchParams.delete(PARAM);
  window.history.replaceState(null, "", url.toString());
}
