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

/** Payback is absent when a scheme does not save money; say so rather than
 *  printing a placeholder number. */
export const payback = (yrs: number | undefined | null) =>
  yrs == null ? "never" : yrs > 100 ? ">100 yr" : `${yrs.toFixed(1)} yr`;

/** Bucket used to colour data centers on the map and in the table. */
export type PaybackBucket = "fast" | "medium" | "slow" | "none";

export function paybackBucket(yrs: number | undefined | null): PaybackBucket {
  if (yrs == null) return "none";
  if (yrs < 5) return "fast";
  if (yrs <= 10) return "medium";
  return "slow";
}

export const BUCKET_COLORS: Record<PaybackBucket, string> = {
  fast: "#0f9d58",
  medium: "#f4b400",
  slow: "#db4437",
  none: "#9aa0a6",
};

export const BUCKET_LABELS: Record<PaybackBucket, string> = {
  fast: "< 5 yr",
  medium: "5–10 yr",
  slow: "> 10 yr",
  none: "no payback",
};

/** Colour per sink category. The single source of truth: the map builds its
 *  `match` expression from this and the legend reads the same table, so the
 *  two cannot drift apart. */
export const SINK_COLORS: Record<SinkCat, string> = {
  pool: "#00bcd4",
  wwtp: "#a1887f",
  greenhouse: "#4caf50",
  hospital: "#ef5350",
  hotel: "#ab47bc",
  residential_multifamily: "#5c6bc0",
  university: "#26a69a",
  brewery: "#ffa726",
  school: "#d4e157",
  office: "#90a4ae",
};

/** Fallback when a colour is somehow missing — also the "other" swatch. */
export const SINK_COLOR_FALLBACK = "#9e9e9e";
