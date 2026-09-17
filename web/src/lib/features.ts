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
}

export interface FeatureIndex {
  dcNames: Map<string, string>;
  sinks: Map<string, SinkProps>;
}

interface Collection<T> {
  features: { properties: T }[];
}

/** Ingest writes this when OpenStreetMap has no name for a feature. */
export function isPlaceholderName(name: string): boolean {
  return name.startsWith("Unnamed");
}

export function buildIndex(engine: Engine | null): FeatureIndex {
  const dcNames = new Map<string, string>();
  const sinks = new Map<string, SinkProps>();
  if (!engine) return { dcNames, sinks };

  const dcs = engine.geo.datacenters as Collection<{ id: string; name: string }> | undefined;
  for (const f of dcs?.features ?? []) dcNames.set(f.properties.id, f.properties.name);

  const sinkFc = engine.geo.sinks as Collection<{ id: string } & SinkProps> | undefined;
  for (const f of sinkFc?.features ?? []) {
    const { id, name, cat, demand_kwh } = f.properties;
    sinks.set(id, { name, cat, demand_kwh });
  }
  return { dcNames, sinks };
}

export function useFeatureIndex(engine: Engine | null): FeatureIndex {
  return useMemo(() => buildIndex(engine), [engine]);
}
