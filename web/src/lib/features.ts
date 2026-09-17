// Lookups over the raw GeoJSON the engine holds.
//
// The engine's results are deliberately lean: a Match names a data center by
// id and a Contribution names a sink by id, because the model has no use for
// a display name. The names live in the feature properties, so anything that
// shows them has to join the two back together here.

import { useMemo } from "react";

import type { Engine } from "./engine";
import type { MwConfidence, SinkCat } from "./types";

export interface SinkProps {
  name: string;
  cat: SinkCat;
  demand_kwh: number;
  /** How the annual demand was arrived at — measured, modelled or assumed. */
  demand_source: string;
  area_m2: number | null;
  lngLat: [number, number];
}

export interface DcProps {
  name: string;
  mw: number;
  cooling: string;
  region: string;
  /** How far to trust `mw`. Shown, never used to recompute anything here. */
  mw_confidence: MwConfidence;
  campus_id: string | null;
  lngLat: [number, number];
}

export interface FeatureIndex {
  dcNames: Map<string, string>;
  dcs: Map<string, DcProps>;
  sinks: Map<string, SinkProps>;
}

interface Collection<T> {
  features: { properties: T; geometry: { coordinates: [number, number] } }[];
}

/** Ingest writes this when OpenStreetMap has no name for a feature. */
export function isPlaceholderName(name: string): boolean {
  return name.startsWith("Unnamed");
}

export function buildIndex(engine: Engine | null): FeatureIndex {
  const dcNames = new Map<string, string>();
  const dcs = new Map<string, DcProps>();
  const sinks = new Map<string, SinkProps>();
  if (!engine) return { dcNames, dcs, sinks };

  const dcFc = engine.geo.datacenters as
    | Collection<{
        id: string;
        name: string;
        mw: number;
        cooling: string;
        region: string;
        mw_confidence?: MwConfidence;
        campus_id?: string | null;
      }>
    | undefined;
  for (const f of dcFc?.features ?? []) {
    const { id, name, mw, cooling, region } = f.properties;
    dcNames.set(id, name);
    dcs.set(id, {
      name,
      mw,
      cooling,
      region,
      // Optional in the properties so a bundle built before the field existed
      // still loads; the weakest grade is the safe reading of a missing one.
      mw_confidence: f.properties.mw_confidence ?? "footprint_estimate",
      campus_id: f.properties.campus_id ?? null,
      lngLat: f.geometry.coordinates,
    });
  }

  const sinkFc = engine.geo.sinks as
    | Collection<{
        id: string;
        name: string;
        cat: SinkCat;
        demand_kwh: number;
        demand_source?: string;
        area_m2?: number | null;
      }>
    | undefined;
  for (const f of sinkFc?.features ?? []) {
    const { id, name, cat, demand_kwh } = f.properties;
    sinks.set(id, {
      name,
      cat,
      demand_kwh,
      demand_source: f.properties.demand_source ?? "category_default",
      area_m2: f.properties.area_m2 ?? null,
      lngLat: f.geometry.coordinates,
    });
  }
  return { dcNames, dcs, sinks };
}

export function useFeatureIndex(engine: Engine | null): FeatureIndex {
  return useMemo(() => buildIndex(engine), [engine]);
}
