// Lookups over the raw GeoJSON the engine holds.
//
// The engine's results are deliberately lean: a Match names a data center by
// id and a Contribution names a sink by id, because the model has no use for
// a display name. The names live in the feature properties, so anything that
// shows them has to join the two back together here.

import { useMemo } from "react";

import type { Engine } from "./engine";
import type { SinkCat } from "./types";

export interface SinkProps {
  name: string;
  cat: SinkCat;
  demand_kwh: number;
  lngLat: [number, number];
}

export interface DcProps {
  name: string;
  mw: number;
  cooling: string;
  region: string;
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
    | Collection<{ id: string; name: string; mw: number; cooling: string; region: string }>
    | undefined;
  for (const f of dcFc?.features ?? []) {
    const { id, name, mw, cooling, region } = f.properties;
    dcNames.set(id, name);
    dcs.set(id, { name, mw, cooling, region, lngLat: f.geometry.coordinates });
  }

  const sinkFc = engine.geo.sinks as
    | Collection<{ id: string; name: string; cat: SinkCat; demand_kwh: number }>
    | undefined;
  for (const f of sinkFc?.features ?? []) {
    const { id, name, cat, demand_kwh } = f.properties;
    sinks.set(id, { name, cat, demand_kwh, lngLat: f.geometry.coordinates });
  }
  return { dcNames, dcs, sinks };
}

export function useFeatureIndex(engine: Engine | null): FeatureIndex {
  return useMemo(() => buildIndex(engine), [engine]);
}
