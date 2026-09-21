// Application state.
//
// Every region is ranked together and shown as one list, but each keeps its
// own parameters: a pipe costs $3,000/m in Manhattan and $800/m upstate, and
// one set of numbers across both would make one of them meaningless.
//
// Ranking is synchronous: the engine ranks the real dataset in well under a
// millisecond, so there is no worker. `lastRankMs` keeps that assumption
// visible if the dataset grows.

import { create } from "zustand";

import { loadEngine, type Engine, type LoadStage } from "./engine";
import {
  decodeScenario,
  encodeScenario,
  readRegionParam,
  readScenarioParam,
  writeRegionParam,
  writeScenarioParam,
} from "./scenario";
import {
  REGIONS,
  byScore,
  type ByRegion,
  type Contribution,
  type Econ,
  type Match,
  type Region,
  type RegionView,
  type Weights,
} from "./types";

export type Theme = "light" | "dark" | "system";
/** localStorage key; `layout.tsx` reads the same one before first paint. */
export const THEME_KEY = "heatmatch:theme";

/** Where a selection came from. The map flies to a site picked from the
 *  list, but not to one clicked on the map: it is already under the cursor. */
export type SelectionSource = "map" | "list";

/** Resting heights of the phone bottom sheet, as a share of the viewport.
 *  Full leaves a strip of map: the panel describes the map and should
 *  never replace it. */
export type SheetSnap = "peek" | "half" | "full";
export const SHEET_SNAPS: Record<SheetSnap, number> = { peek: 0.14, half: 0.52, full: 0.86 };

interface State {
  engine: Engine | null;
  stage: LoadStage | null;
  error: string | null;

  theme: Theme;

  weights: ByRegion<Weights> | null;
  econ: ByRegion<Econ> | null;
  /** Which region's parameters the assumptions panel edits. */
  tuningRegion: Region;
  /** Which region the map and ranking show. "all" is the cross-region view. */
  viewRegion: RegionView;

  results: Match[];
  /** Rank per site before the most recent recompute, for showing movement. */
  prevRanks: Map<string, number>;
  selectedDc: string | null;
  selectionSource: SelectionSource;
  hoveredDc: string | null;
  hoveredSink: string | null;
  explain: Contribution[];
  lastRankMs: number;

  /** Whether the reader has done anything yet; the onboarding hint waits. */
  interacted: boolean;
  /** Name filter on the ranking. */
  search: string;
  /** Site ids in the order the ranking currently shows them, for ↑/↓. */
  visibleOrder: string[];
  /** Where the phone bottom sheet is resting; the panel owns changes. */
  sheetSnap: SheetSnap;

  init: () => Promise<void>;
  setTheme: (theme: Theme) => void;
  setTuningRegion: (region: Region) => void;
  setViewRegion: (region: RegionView) => void;
  setWeights: (patch: Partial<Weights>) => void;
  setEcon: (patch: Partial<Econ>) => void;
  resetDefaults: () => void;
  resetRegion: (region: Region) => void;
  select: (dcId: string | null, source?: SelectionSource) => void;
  hoverDc: (dcId: string | null) => void;
  hoverSink: (sinkId: string | null) => void;
  markInteracted: () => void;
  setSearch: (search: string) => void;
  setVisibleOrder: (ids: string[]) => void;
  setSheetSnap: (snap: SheetSnap) => void;
  recompute: () => void;
}

// The URL follows the scenario, a beat behind the sliders.
let urlTimer: ReturnType<typeof setTimeout> | undefined;
function syncUrl(engine: Engine, weights: ByRegion<Weights>, econ: ByRegion<Econ>) {
  clearTimeout(urlTimer);
  urlTimer = setTimeout(() => writeScenarioParam(encodeScenario(engine, weights, econ)), 300);
}

/** The matches the current view shows: one region's, or every region's. */
export function inView(results: Match[], view: RegionView): Match[] {
  return view === "all" ? results : results.filter((m) => m.region === view);
}

export const useSelectedMatch = () =>
  useStore((s) => (s.selectedDc ? s.results.find((m) => m.dc === s.selectedDc) : undefined));

const defaults = <T,>(make: (region: Region) => T): ByRegion<T> =>
  Object.fromEntries(REGIONS.map((r) => [r, make(r)])) as ByRegion<T>;

function readTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  try {
    if (theme === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode; the choice just does not persist */
  }
}

/** The theme actually in effect, after "system" is resolved. */
export function resolvedTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export const useStore = create<State>((set, get) => ({
  engine: null,
  stage: null,
  error: null,
  theme: "system",
  weights: null,
  econ: null,
  tuningRegion: "nyc",
  viewRegion: "all",
  results: [],
  prevRanks: new Map(),
  selectedDc: null,
  selectionSource: "list",
  hoveredDc: null,
  hoveredSink: null,
  explain: [],
  lastRankMs: 0,
  interacted: false,
  search: "",
  visibleOrder: [],
  sheetSnap: "half",

  init: async () => {
    set({ theme: readTheme() });
    try {
      const engine = await loadEngine((stage) => set({ stage }));
      // A shared link carries its scenario; otherwise the defaults.
      const param = readScenarioParam();
      const fromUrl = param ? decodeScenario(engine, param) : null;
      // A link may also pin a region. Anything not a known region is "all".
      const region = readRegionParam();
      const viewRegion: RegionView = (REGIONS as readonly string[]).includes(region ?? "")
        ? (region as Region)
        : "all";
      set({
        engine,
        weights: fromUrl?.weights ?? defaults((r) => engine.defaultWeights(r)),
        econ: fromUrl?.econ ?? defaults((r) => engine.defaultEcon(r)),
        viewRegion,
        tuningRegion: viewRegion === "all" ? get().tuningRegion : viewRegion,
        error: null,
      });
      get().recompute();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  setTheme: (theme) => {
    applyTheme(theme);
    set({ theme });
  },

  setTuningRegion: (tuningRegion) => set({ tuningRegion }),

  // Choosing a single region also points the sliders at it: editing New York's
  // assumptions while looking only at Virginia is never what was meant. "All"
  // leaves the tuning target alone, since there is no one region to pick.
  setViewRegion: (viewRegion) => {
    set(viewRegion === "all" ? { viewRegion } : { viewRegion, tuningRegion: viewRegion });
    writeRegionParam(viewRegion);
  },

  setWeights: (patch) => {
    const { weights, tuningRegion } = get();
    if (!weights) return;
    set({
      weights: { ...weights, [tuningRegion]: { ...weights[tuningRegion], ...patch } },
      interacted: true,
    });
    get().recompute();
  },

  setEcon: (patch) => {
    const { econ, tuningRegion } = get();
    if (!econ) return;
    set({ econ: { ...econ, [tuningRegion]: { ...econ[tuningRegion], ...patch } }, interacted: true });
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

  resetRegion: (region) => {
    const { engine, weights, econ } = get();
    if (!engine || !weights || !econ) return;
    set({
      weights: { ...weights, [region]: engine.defaultWeights(region) },
      econ: { ...econ, [region]: engine.defaultEcon(region) },
    });
    get().recompute();
  },

  select: (dcId, source = "list") => {
    const { engine, weights, results } = get();
    set({ selectedDc: dcId, selectionSource: source, hoveredSink: null, interacted: true });
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

  hoverDc: (hoveredDc) => {
    if (get().hoveredDc !== hoveredDc) set({ hoveredDc });
  },

  hoverSink: (hoveredSink) => {
    if (get().hoveredSink !== hoveredSink) set({ hoveredSink });
  },

  markInteracted: () => {
    if (!get().interacted) set({ interacted: true });
  },

  setSearch: (search) => set({ search }),

  setVisibleOrder: (ids) => {
    const cur = get().visibleOrder;
    if (cur.length === ids.length && cur.every((id, i) => id === ids[i])) return;
    set({ visibleOrder: ids });
  },

  setSheetSnap: (sheetSnap) => {
    if (get().sheetSnap !== sheetSnap) set({ sheetSnap });
  },

  /** Re-rank every region and keep the URL in step. */
  recompute: () => {
    const { engine, weights, econ, selectedDc, selectionSource, results: before } = get();
    if (!engine || !weights || !econ) return;
    try {
      const t0 = performance.now();
      const prevRanks = new Map(before.map((m, i) => [m.dc, i + 1]));
      // Ranked per region, then merged: scores are comparable because the
      // score itself is dimensionless, even though the inputs differ.
      const results = REGIONS.flatMap((r) => engine.rank(r, weights[r], econ[r])).sort(byScore);
      set({ results, prevRanks, lastRankMs: performance.now() - t0, error: null });
      syncUrl(engine, weights, econ);
      // Keep the detail panel in step with the table it was opened from,
      // without flying the map again.
      if (selectedDc) get().select(selectedDc, selectionSource);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },
}));
