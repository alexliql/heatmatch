// Lookups over the raw GeoJSON the engine holds.
//
// The engine's results name data centers and sinks by id only; the display
// properties live in the feature collections and are joined back here.

import { useMemo } from "react";

import type { Engine } from "./engine";
import type { DcFeature, MwConfidence, SinkCat } from "./types";

interface SinkProps {
  name: string;
  cat: SinkCat;
  demand_kwh: number;
  /** How the annual demand was arrived at — measured, modelled or assumed. */
  demand_source: string;
  lngLat: [number, number];
}

export interface DcProps {
  name: string;
  mw: number;
  cooling: string;
  region: DcFeature["region"];
  /** How far to trust `mw`. Shown, never used to recompute anything here. */
  mw_confidence: MwConfidence;
  lngLat: [number, number];
}

interface FeatureIndex {
  dcs: Map<string, DcProps>;
  sinks: Map<string, SinkProps>;
  /** Display name for a data center id; the id itself when unknown. */
  dcName: (id: string) => string;
}

/** Ingest writes this when OpenStreetMap has no name for a feature. */
export function isPlaceholderName(name: string): boolean {
  return name.startsWith("Unnamed");
}

export function useFeatureIndex(engine: Engine | null): FeatureIndex {
  return useMemo(() => {
    const dcs = new Map<string, DcProps>();
    const sinks = new Map<string, SinkProps>();
    for (const f of engine?.geo.datacenters.features ?? []) {
      const { id, name, mw, cooling, region } = f.properties;
      dcs.set(id, {
        name,
        mw,
        cooling,
        region,
        // Optional in older bundles; the weakest grade is the safe reading.
        mw_confidence: f.properties.mw_confidence ?? "footprint_estimate",
        lngLat: f.geometry.coordinates,
      });
    }
    for (const f of engine?.geo.sinks.features ?? []) {
      const { id, name, cat, demand_kwh } = f.properties;
      sinks.set(id, {
        name,
        cat,
        demand_kwh,
        demand_source: f.properties.demand_source ?? "category_default",
        lngLat: f.geometry.coordinates,
      });
    }
    return { dcs, sinks, dcName: (id) => dcs.get(id)?.name ?? id };
  }, [engine]);
}
