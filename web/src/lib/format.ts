// Display formatting and the shared visual vocabulary. Kept in one place so
// the table, the map popups, the legend and the detail panel cannot disagree
// about how a number reads or what a colour means.

import type { SinkCat } from "./types";

const compactUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const usd = (n: number) => compactUsd.format(n);
export const num = (n: number) => compact.format(n);
export const pct = (n: number) => `${(n * 100).toFixed(0)}%`;
export const mw = (n: number) => `${n.toFixed(1)} MW`;
export const score = (n: number) => n.toFixed(2);
export const km = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m.toFixed(0)} m`);

/** Payback is absent when a scheme does not save money; say so rather than
 *  printing a placeholder number. */
export const payback = (yrs: number | undefined | null) =>
  yrs == null ? "never" : yrs > 100 ? ">100 yr" : `${yrs.toFixed(1)} yr`;

/** Bucket used to colour data centers on the map and in the table. */
type PaybackBucket = "fast" | "medium" | "slow" | "none";

export function paybackBucket(yrs: number | undefined | null): PaybackBucket {
  if (yrs == null) return "none";
  if (yrs < 5) return "fast";
  if (yrs <= 10) return "medium";
  return "slow";
}

export const BUCKET_LABELS: Record<PaybackBucket, string> = {
  fast: "< 5 yr",
  medium: "5–10 yr",
  slow: "> 10 yr",
  none: "no payback",
};

// Colours are CSS custom properties so the two themes can disagree about
// them. The DOM reads them directly; the map reads them through `palette()`
// below, because a WebGL layer cannot resolve `var()`.

/** Payback is ordinal, so it gets one warm ramp: the hotter the colour, the
 *  faster the money comes back. Ties the encoding to the subject and stays
 *  legible without red/green. */
export const BUCKET_VARS: Record<PaybackBucket, string> = {
  fast: "--heat-fast",
  medium: "--heat-medium",
  slow: "--heat-slow",
  none: "--heat-none",
};

/** Sink categories are coloured in five hue families (water, buildings,
 *  institutions, growing, industry); lightness separates members. */
export const SINK_VARS: Record<SinkCat, string> = {
  pool: "--cat-pool",
  wwtp: "--cat-wwtp",
  hotel: "--cat-hotel",
  residential_multifamily: "--cat-residential",
  office: "--cat-office",
  hospital: "--cat-hospital",
  school: "--cat-school",
  university: "--cat-university",
  greenhouse: "--cat-greenhouse",
  brewery: "--cat-brewery",
};

export const cssVar = (name: string) => `var(${name})`;

/** Everything the map needs to paint, resolved from the current theme. */
export interface Palette {
  bucket: Record<PaybackBucket, string>;
  sink: Record<SinkCat, string>;
  accent: string;
  fg: string;
  bg: string;
  line: string;
  zone: string;
}

export function palette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const read = (v: string) => cs.getPropertyValue(v).trim();
  const resolve = <K extends string>(vars: Record<K, string>) =>
    Object.fromEntries(Object.entries<string>(vars).map(([k, v]) => [k, read(v)])) as Record<K, string>;
  return {
    bucket: resolve(BUCKET_VARS),
    sink: resolve(SINK_VARS),
    accent: read("--accent"),
    fg: read("--fg-0"),
    bg: read("--bg-0"),
    line: read("--map-halo"),
    zone: read("--zone"),
  };
}
