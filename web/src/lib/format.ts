// Display formatting. Kept in one place so the table, the map popups and the
// detail panel cannot disagree about how a number reads.

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
