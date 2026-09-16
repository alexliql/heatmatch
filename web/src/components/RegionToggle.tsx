"use client";

import { useStore } from "@/lib/store";
import { REGIONS } from "@/lib/types";

const LABELS: Record<string, string> = { nyc: "New York City", upstate: "Upstate" };

export function RegionToggle() {
  const region = useStore((s) => s.region);
  const setRegion = useStore((s) => s.setRegion);

  return (
    <select
      value={region}
      onChange={(e) => setRegion(e.target.value as (typeof REGIONS)[number])}
      aria-label="Region"
    >
      {REGIONS.map((r) => (
        <option key={r} value={r}>
          {LABELS[r]}
        </option>
      ))}
    </select>
  );
}
