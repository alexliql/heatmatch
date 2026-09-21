"use client";

import { useMemo, useState } from "react";

import { num } from "@/lib/format";
import { useSelectedMatch, useStore } from "@/lib/store";
import { CAT_LABELS, type SinkCat } from "@/lib/types";
import { useCoarsePointer } from "@/lib/useMedia";

const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const W = 360;
const H = 96;
const PAD_TOP = 4;
const PAD_BOTTOM = 16;
const PLOT_H = H - PAD_TOP - PAD_BOTTOM;
const GAP = 4;
const BAR_W = (W - GAP * 11) / 12;

/** Twelve bars comparing flat monthly supply against this site's seasonal
 *  demand — the clearest way to show why utilization is below 100%. Drawn as
 *  SVG so the supply line is clamped inside the plot whatever the ratio.
 *  Hover or arrow through a month to see which categories drive it. */
export function SeasonStrip() {
  const engine = useStore((s) => s.engine);
  const explain = useStore((s) => s.explain);
  const match = useSelectedMatch();
  const [month, setMonth] = useState<number | null>(null);
  const coarse = useCoarsePointer();

  const data = useMemo(() => {
    if (!engine || !match) return null;
    // Shapes are per region: Virginia models its own from ComStock.
    const profiles = engine.profiles(match.region);
    const connected = explain.filter((c) => c.delivered_mwh > 0);
    // Per category per month, so a hovered month can say who wants the heat.
    const byCat = new Map<SinkCat, number[]>();
    for (const c of connected) {
      const row = byCat.get(c.cat) ?? Array.from({ length: 12 }, () => 0);
      for (let m = 0; m < 12; m++) row[m] += c.delivered_mwh * (profiles[c.cat]?.[m] ?? 0);
      byCat.set(c.cat, row);
    }
    const monthly = Array.from({ length: 12 }, (_, m) =>
      [...byCat.values()].reduce((sum, row) => sum + row[m], 0),
    );
    const supply = match.supply_mwh / 12;
    const peak = Math.max(supply, ...monthly) || 1;
    return { monthly, byCat, supply, peak };
  }, [engine, explain, match]);

  if (!data) return null;

  const y = (v: number) => PAD_TOP + PLOT_H * (1 - v / data.peak);
  const supplyY = y(data.supply);

  const readout =
    month === null
      ? null
      : (() => {
          const demand = data.monthly[month];
          const top = [...data.byCat.entries()]
            .map(([cat, row]) => [cat, row[month]] as const)
            .filter(([, v]) => v > 0)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3);
          const gap = data.supply - demand;
          return { demand, top, gap };
        })();

  return (
    <figure className="season">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Monthly demand against flat supply"
        onMouseLeave={coarse ? undefined : () => setMonth(null)}
      >
        {data.monthly.map((v, i) => {
          const x = i * (BAR_W + GAP);
          const top = y(v);
          const wasted = v < data.supply;
          const dim = month !== null && month !== i;
          return (
            <g
              key={i}
              tabIndex={0}
              className="season-col"
              // Hover previews on a pointer; a tap toggles and sticks on touch.
              onMouseEnter={coarse ? undefined : () => setMonth(i)}
              onClick={coarse ? () => setMonth(month === i ? null : i) : undefined}
              onFocus={() => setMonth(i)}
              onBlur={coarse ? undefined : () => setMonth(null)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                  e.preventDefault();
                  const next = (i + (e.key === "ArrowRight" ? 1 : 11)) % 12;
                  (e.currentTarget.parentElement?.children[next] as SVGElement | undefined)?.focus();
                }
              }}
            >
              <title>{`${MONTH_NAMES[i]}: ${num(v)} MWh of demand`}</title>
              {/* Hit area for the whole column. */}
              <rect x={x} y={0} width={BAR_W} height={H} fill="transparent" />
              {/* The gap between demand and supply is heat with nowhere to
                  go; shading it makes the waste visible, not just the use. */}
              {wasted && (
                <rect
                  x={x}
                  y={supplyY}
                  width={BAR_W}
                  height={Math.max(0, top - supplyY)}
                  fill="var(--heat-none)"
                  opacity={dim ? 0.12 : 0.22}
                  rx={2}
                />
              )}
              <rect
                x={x}
                y={top}
                width={BAR_W}
                height={Math.max(0, PAD_TOP + PLOT_H - top)}
                fill="var(--accent)"
                opacity={dim ? 0.45 : month === i ? 1 : 0.8}
                rx={2}
              />
              <text
                x={x + BAR_W / 2}
                y={H - 3}
                textAnchor="middle"
                fontSize={9.5}
                fill={month === i ? "var(--fg-0)" : "var(--fg-2)"}
                fontFamily="var(--font-sans)"
              >
                {MONTHS[i]}
              </text>
            </g>
          );
        })}
        <line x1={0} x2={W} y1={supplyY} y2={supplyY} stroke="var(--fg-1)" strokeWidth={1.25} strokeDasharray="3 3" />
      </svg>
      <figcaption className="season-caption" aria-live="polite">
        {readout && month !== null ? (
          <>
            <b style={{ color: "var(--fg-0)" }}>{MONTH_NAMES[month]}</b>
            {" · "}
            <span className="num">{num(readout.demand)}</span> MWh demand vs{" "}
            <span className="num">{num(data.supply)}</span> supply
            {readout.gap > 0 ? (
              <>
                {" · "}
                <span className="num">{num(readout.gap)}</span> MWh unused
              </>
            ) : (
              " · fully used"
            )}
            {readout.top.length > 0 && (
              <>
                <br />
                {readout.top.map(([cat, v], i) => (
                  <span key={cat}>
                    {i > 0 && ", "}
                    {CAT_LABELS[cat]} <span className="num">{num(v)}</span>
                  </span>
                ))}
              </>
            )}
          </>
        ) : (
          <>
            <span className="season-key"><b />demand from connected sinks</span>
            <span className="season-key"><i />supply, {num(data.supply)} MWh every month</span>
            <br />
            Demand below the line is heat with nowhere to go. {coarse ? "Tap" : "Hover"} a month for detail.
          </>
        )}
      </figcaption>
    </figure>
  );
}
