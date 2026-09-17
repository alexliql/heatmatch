"use client";

import { useMemo } from "react";

import { useFeatureIndex } from "@/lib/features";
import { BUCKET_VARS, cssVar, paybackBucket, score } from "@/lib/format";
import { useStore } from "@/lib/store";

const W = 360;
const H = 22;
const PAD = 2;

/** Every site on one score axis. The list hides the gaps; this shows where
 *  the cliffs are. */
export function ScoreRail() {
  const results = useStore((s) => s.results);
  const selectedDc = useStore((s) => s.selectedDc);
  const hoveredDc = useStore((s) => s.hoveredDc);
  const hoverDc = useStore((s) => s.hoverDc);
  const select = useStore((s) => s.select);
  const engine = useStore((s) => s.engine);
  const { dcNames } = useFeatureIndex(engine);

  const max = useMemo(() => Math.max(0, ...results.map((r) => r.score)) || 1, [results]);
  if (!results.length) return null;

  const x = (s: number) => PAD + (s / max) * (W - PAD * 2);

  return (
    <div className="rail">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Distribution of scores" onMouseLeave={() => hoverDc(null)}>
        <line x1={PAD} x2={W - PAD} y1={H - 4} y2={H - 4} stroke="var(--line-strong)" strokeWidth={1} />
        {results.map((m) => {
          const sel = m.dc === selectedDc;
          const hov = m.dc === hoveredDc;
          const h = sel ? 14 : hov ? 12 : 9;
          const w = sel ? 3 : 2;
          return (
            <g
              key={m.dc}
              onMouseEnter={() => hoverDc(m.dc)}
              onClick={() => select(sel ? null : m.dc, "list")}
              style={{ cursor: "pointer" }}
            >
              <title>{`${dcNames.get(m.dc) ?? m.dc} · ${score(m.score)}`}</title>
              <rect x={x(m.score) - 4} y={0} width={8} height={H} fill="transparent" />
              <rect
                x={x(m.score) - w / 2}
                y={H - 4 - h}
                width={w}
                height={h}
                rx={1}
                fill={cssVar(BUCKET_VARS[paybackBucket(m.payback_yrs)])}
                stroke={sel ? "var(--accent)" : "none"}
                strokeWidth={sel ? 1.5 : 0}
                opacity={hoveredDc && !hov && !sel ? 0.45 : 1}
                style={{ transition: "x 240ms var(--ease), height 160ms var(--ease), opacity 160ms" }}
              />
            </g>
          );
        })}
      </svg>
      <div className="rail-axis num">
        <span>0</span>
        <span>score {score(max)}</span>
      </div>
    </div>
  );
}
