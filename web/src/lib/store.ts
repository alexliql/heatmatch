// Application state.
//
// Both regions are ranked together and shown as one list. They keep separate
// parameters, though, because the differences are physical rather than
// cosmetic: a pipe costs $3,000/m in the city against $800/m upstate, and the
// city's default reach is 1 km against 4 km. Forcing one set of numbers across
// both would make one of them meaningless.
//
// Ranking is synchronous: the engine ranks the real dataset in well under a
// millisecond, so there is no worker here. `lastRankMs` is recorded so that
// assumption stays visible if the dataset grows.

import { create } from "zustand";

import { loadEngine, type Engine, type LoadProgress } from "./engine";
import { REGIONS, type Contribution, type Econ, type Match, type Region, type Weights } from "./types";

type ByRegion<T> = Record<Region, T>;

interface State {
  engine: Engine | null;
  progress: LoadProgress | null;
  error: string | null;

  weights: ByRegion<Weights> | null;
  econ: ByRegion<Econ> | null;
  /** Which region's parameters the assumptions panel edits. */
  tuningRegion: Region;

  results: Match[];
  selectedDc: string | null;
  explain: Contribution[];
  lastRankMs: number;

  init: () => Promise<void>;
  setTuningRegion: (region: Region) => void;
  setWeights: (patch: Partial<Weights>) => void;
  setEcon: (patch: Partial<Econ>) => void;
  resetDefaults: () => void;
  select: (dcId: string | null) => void;
  recompute: () => void;
}

const defaults = <T,>(make: (region: Region) => T): ByRegion<T> =>
  Object.fromEntries(REGIONS.map((r) => [r, make(r)])) as ByRegion<T>;

export const useStore = create<State>((set, get) => ({
  engine: null,
  progress: null,
  error: null,
  weights: null,
  econ: null,
  tuningRegion: "nyc",
  results: [],
  selectedDc: null,
  explain: [],
  lastRankMs: 0,

  init: async () => {
    try {
      const engine = await loadEngine((progress) => set({ progress }));
      set({
        engine,
        weights: defaults((r) => engine.defaultWeights(r)),
        econ: defaults((r) => engine.defaultEcon(r)),
        error: null,
      });
      get().recompute();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  setTuningRegion: (tuningRegion) => set({ tuningRegion }),

  setWeights: (patch) => {
    const { weights, tuningRegion } = get();
    if (!weights) return;
    set({ weights: { ...weights, [tuningRegion]: { ...weights[tuningRegion], ...patch } } });
    get().recompute();
  },

  setEcon: (patch) => {
    const { econ, tuningRegion } = get();
    if (!econ) return;
    set({ econ: { ...econ, [tuningRegion]: { ...econ[tuningRegion], ...patch } } });
    get().recompute();
  },

  resetDefaults: () => {
    const { engine } = get();
    if (!engine) return;
    set({
      weights: defaults((r) => engine.defaultWeights(r)),
      econ: defaults((r) => engine.defaultEcon(r)),
    });
    get().recompute();
  },

  select: (dcId) => {
    const { engine, weights, results } = get();
    set({ selectedDc: dcId });
    if (!engine || !weights || !dcId) return set({ explain: [] });

    // Explain with the parameters the site was actually ranked under, which
    // are its own region's.
    const region = results.find((m) => m.dc === dcId)?.region;
    if (!region) return set({ explain: [] });
    try {
      set({ explain: engine.explain(dcId, weights[region]) });
    } catch {
      set({ explain: [] });
    }
  },

  recompute: () => {
    const { engine, weights, econ, selectedDc } = get();
    if (!engine || !weights || !econ) return;
    try {
      const t0 = performance.now();
      // Ranked per region, then merged: scores are comparable because the
      // score itself is dimensionless, even though the inputs differ.
      const results = REGIONS.flatMap((r) => engine.rank(r, weights[r], econ[r])).sort(
        (a, b) => b.score - a.score || a.dc.localeCompare(b.dc),
      );
      set({ results, lastRankMs: performance.now() - t0, error: null });
      // Keep the detail panel in step with the table it was opened from.
      if (selectedDc) get().select(selectedDc);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },
}));
