// What differs from the engine's defaults.
//
// Used for the "modified" dots on controls, the badge on the Assumptions
// tab, and the URL scenario, which only carries what has changed.

import type { Engine } from "./engine";
import { REGIONS, type Econ, type Region, type Weights } from "./types";

type ByRegion<T> = Record<Region, T>;

/** Values come back from the engine as f32 widened to f64, so a stored 0.9
 *  reads as 0.8999999761581421. Compare at the control's own precision. */
export const roundTo = (v: number, step: number) => Math.round(v / step) * step;
export const modified = (a: number, b: number, step: number) => Math.abs(a - b) > step / 2;

/** Precision each field is compared at; anything not listed uses 1e-6. */
const STEP: Record<string, number> = {
  radius_m: 100,
  per_sink_cap: 0.05,
  steam_bonus: 0.1,
  uten_bonus: 0.1,
  k: 0.05,
  theta_deg: 1,
  factor: 0.05,
  pipe_cost_per_m: 10,
  hp_capex_per_mw_th: 1000,
  gas_price_per_mwh_th: 1,
  elec_price_per_mwh: 1,
  boiler_eff: 0.01,
  dc_avoided_cooling_per_mwh: 1,
};
const CAT_STEP = 0.1;

type Plain = Record<string, unknown>;

/** Leaf-by-leaf diff of `a` against `b`; returns the changed subtree of `a`
 *  or `null` when nothing differs. Tagged unions (`distance`, `decay`,
 *  `water_crossing`) are replaced whole when their `kind` differs. */
export function diffObject(a: Plain, b: Plain, path: string[] = []): Plain | null {
  const out: Plain = {};
  let any = false;
  if (typeof a.kind === "string" && a.kind !== b.kind) return a;
  for (const key of Object.keys(a)) {
    const av = a[key];
    const bv = b[key];
    if (typeof av === "number" && typeof bv === "number") {
      const step = path[path.length - 1] === "cat" ? CAT_STEP : (STEP[key] ?? 1e-6);
      if (modified(av, bv, step)) {
        out[key] = av;
        any = true;
      }
    } else if (av && typeof av === "object" && bv && typeof bv === "object") {
      const sub = diffObject(av as Plain, bv as Plain, [...path, key]);
      if (sub) {
        out[key] = sub;
        any = true;
      }
    } else if (av !== bv) {
      out[key] = av;
      any = true;
    }
  }
  return any ? out : null;
}

export function countLeaves(o: Plain | null): number {
  if (!o) return 0;
  let n = 0;
  for (const v of Object.values(o)) {
    if (v && typeof v === "object" && !("kind" in (v as Plain))) n += countLeaves(v as Plain);
    else n += 1;
  }
  return n;
}

export interface Diff {
  count: number;
  byRegion: ByRegion<number>;
  changes: ByRegion<{ w: Plain | null; e: Plain | null }>;
}

export function diffFromDefaults(
  engine: Engine,
  weights: ByRegion<Weights>,
  econ: ByRegion<Econ>,
): Diff {
  const changes = {} as Diff["changes"];
  const byRegion = {} as ByRegion<number>;
  let count = 0;
  for (const r of REGIONS) {
    const w = diffObject(weights[r] as unknown as Plain, engine.defaultWeights(r) as unknown as Plain);
    const e = diffObject(econ[r] as unknown as Plain, engine.defaultEcon(r) as unknown as Plain);
    changes[r] = { w, e };
    byRegion[r] = countLeaves(w) + countLeaves(e);
    count += byRegion[r];
  }
  return { count, byRegion, changes };
}
