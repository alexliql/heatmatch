// Application state.
//
// Ranking is synchronous: the engine ranks the real dataset in well under a
// millisecond, so there is no worker here. `lastRankMs` is recorded so that
// assumption stays visible if the dataset grows.

import { create } from "zustand";

import { loadEngine, type Engine, type LoadProgress } from "./engine";
import type { Contribution, Econ, Match, Region, Weights } from "./types";

interface State {
  engine: Engine | null;
  progress: LoadProgress | null;
  error: string | null;

  region: Region;
  weights: Weights | null;
  econ: Econ | null;

  results: Match[];
  selectedDc: string | null;
  explain: Contribution[];
  lastRankMs: number;

  init: () => Promise<void>;
  setRegion: (region: Region) => void;
  setWeights: (patch: Partial<Weights>) => void;
  setEcon: (patch: Partial<Econ>) => void;
  resetDefaults: () => void;
  select: (dcId: string | null) => void;
  recompute: () => void;
}

export const useStore = create<State>((set, get) => ({
  engine: null,
  progress: null,
  error: null,
  region: "nyc",
  weights: null,
  econ: null,
  results: [],
  selectedDc: null,
  explain: [],
  lastRankMs: 0,

  init: async () => {
    try {
      const engine = await loadEngine((progress) => set({ progress }));
      const region = get().region;
      set({
        engine,
        weights: engine.defaultWeights(region),
        econ: engine.defaultEcon(region),
        error: null,
      });
      get().recompute();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  // Switching region also resets the tuning: radius and pipe cost differ by an
  // order of magnitude between them, so carrying NYC's values upstate would
  // silently produce nonsense.
  setRegion: (region) => {
    const { engine } = get();
    if (!engine) return set({ region });
    set({
      region,
      weights: engine.defaultWeights(region),
      econ: engine.defaultEcon(region),
      selectedDc: null,
      explain: [],
    });
    get().recompute();
  },

  setWeights: (patch) => {
    const weights = get().weights;
    if (!weights) return;
    set({ weights: { ...weights, ...patch } });
    get().recompute();
  },

  setEcon: (patch) => {
    const econ = get().econ;
    if (!econ) return;
    set({ econ: { ...econ, ...patch } });
    get().recompute();
  },

  resetDefaults: () => {
    const { engine, region } = get();
    if (!engine) return;
    set({ weights: engine.defaultWeights(region), econ: engine.defaultEcon(region) });
    get().recompute();
  },

  select: (dcId) => {
    const { engine, weights } = get();
    set({ selectedDc: dcId });
    if (!engine || !weights || !dcId) return set({ explain: [] });
    try {
      set({ explain: engine.explain(dcId, weights) });
    } catch {
      set({ explain: [] });
    }
  },

  recompute: () => {
    const { engine, region, weights, econ, selectedDc } = get();
    if (!engine || !weights || !econ) return;
    try {
      const t0 = performance.now();
      const results = engine.rank(region, weights, econ);
      set({ results, lastRankMs: performance.now() - t0, error: null });
      // Keep the detail panel in step with the table it was opened from.
      if (selectedDc) get().select(selectedDc);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },
}));
