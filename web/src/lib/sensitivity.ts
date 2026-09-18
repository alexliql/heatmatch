// How a site's rank would move as one slider sweeps its range.
//
// The engine ranks in well under a millisecond, so trying a dozen values per
// slider is cheap enough to do on every change of assumptions.

import type { Engine } from "./engine";
import { REGIONS, byScore, type ByRegion, type Econ, type Match, type Region, type Weights } from "./types";

/** Which slider: a dotted path into `Weights`. */
export type Param =
  | `cat.${keyof Weights["cat"]}`
  | "radius_m"
  | "per_sink_cap"
  | "steam_bonus"
  | "uten_bonus"
  | "distance.k"
  | "distance.theta_deg";

function patched(w: Weights, param: Param, value: number): Weights {
  if (param.startsWith("cat.")) {
    const cat = param.slice(4) as keyof Weights["cat"];
    return { ...w, cat: { ...w.cat, [cat]: value } };
  }
  if (param === "distance.k") {
    return w.distance.kind === "detour" ? { ...w, distance: { kind: "detour", k: value } } : w;
  }
  if (param === "distance.theta_deg") {
    return w.distance.kind === "rotated_l1"
      ? { ...w, distance: { kind: "rotated_l1", theta_deg: value } }
      : w;
  }
  return { ...w, [param]: value };
}

export interface Sweep {
  values: number[];
  ranks: number[];
  /** Indices into `values` where the rank differs from the step before. */
  breaks: { at: number; from: number; to: number }[];
}

/** Rank of `dc` at each of `steps` values of `param` across [min, max],
 *  holding everything else — including the other region — fixed. */
export function sweep(
  engine: Engine,
  weights: ByRegion<Weights>,
  econ: ByRegion<Econ>,
  region: Region,
  dc: string,
  param: Param,
  min: number,
  max: number,
  steps = 12,
): Sweep {
  const others: Match[] = REGIONS.filter((r) => r !== region).flatMap((r) =>
    engine.rank(r, weights[r], econ[r]),
  );
  const values = Array.from({ length: steps + 1 }, (_, i) => min + ((max - min) * i) / steps);
  const ranks = values.map((v) => {
    const own = engine.rank(region, patched(weights[region], param, v), econ[region]);
    const all = [...own, ...others].sort(byScore);
    return all.findIndex((m) => m.dc === dc) + 1;
  });
  const breaks: Sweep["breaks"] = [];
  for (let i = 1; i < ranks.length; i++) {
    if (ranks[i] !== ranks[i - 1]) breaks.push({ at: i, from: ranks[i - 1], to: ranks[i] });
  }
  return { values, ranks, breaks };
}
