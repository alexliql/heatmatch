"use client";

import { useMemo } from "react";

import { SINK_VARS, cssVar, num, pct } from "@/lib/format";
import { useStore } from "@/lib/store";
import { CAT_LABELS, type SinkCat } from "@/lib/types";
import { useCoarsePointer } from "@/lib/useMedia";

const TOP = 4;

/** One stacked bar of delivered heat by sink category: the answer to "who
 *  takes it?" before the reader scrolls a forty-row table. */
export function DeliveredByCategory({
  hoveredCat,
  onHoverCat,
}: {
  hoveredCat: SinkCat | null;
  onHoverCat: (cat: SinkCat | null) => void;
}) {
  const explain = useStore((s) => s.explain);
  const coarse = useCoarsePointer();
  // Hover previews on a pointer; a tap toggles on touch.
  const enter = (cat: SinkCat) => (coarse ? undefined : () => onHoverCat(cat));
  const leave = coarse ? undefined : () => onHoverCat(null);
  const tap = (cat: SinkCat) => (coarse ? () => onHoverCat(hoveredCat === cat ? null : cat) : undefined);

  const parts = useMemo(() => {
    const byCat = new Map<SinkCat, number>();
    for (const c of explain) {
      if (c.delivered_mwh <= 0) continue;
      byCat.set(c.cat, (byCat.get(c.cat) ?? 0) + c.delivered_mwh);
    }
    const total = [...byCat.values()].reduce((a, b) => a + b, 0);
    const rows = [...byCat.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([cat, mwh]) => ({ cat, mwh, share: total ? mwh / total : 0 }));
    return { rows, total };
  }, [explain]);

  if (parts.rows.length === 0) return null;
  const shown = parts.rows.slice(0, TOP);
  const rest = parts.rows.length - shown.length;

  return (
    <div className="bycat">
      <div className="section-head" style={{ marginBottom: 8 }}>
        <span className="label">Where the heat goes</span>
        <span className="faint num" style={{ fontSize: "var(--t-xs)" }}>
          {num(parts.total)} MWh/yr delivered
        </span>
      </div>
      <div className="bycat-bar" onMouseLeave={leave}>
        {parts.rows.map((r) => (
          <i
            key={r.cat}
            style={{ flex: r.share, background: cssVar(SINK_VARS[r.cat]) }}
            data-dim={hoveredCat !== null && hoveredCat !== r.cat}
            title={`${CAT_LABELS[r.cat]} · ${num(r.mwh)} MWh · ${pct(r.share)}`}
            onMouseEnter={enter(r.cat)}
            onClick={tap(r.cat)}
          />
        ))}
      </div>
      <ul className="bycat-list" onMouseLeave={leave}>
        {shown.map((r) => (
          <li
            key={r.cat}
            data-dim={hoveredCat !== null && hoveredCat !== r.cat}
            onMouseEnter={enter(r.cat)}
            onClick={tap(r.cat)}
          >
            <i style={{ background: cssVar(SINK_VARS[r.cat]) }} />
            <span>{CAT_LABELS[r.cat]}</span>
            <b className="num">{num(r.mwh)}</b>
            <span className="num faint">{pct(r.share)}</span>
          </li>
        ))}
        {rest > 0 && (
          <li className="faint">
            <i style={{ visibility: "hidden" }} />
            <span>+{rest} more</span>
          </li>
        )}
      </ul>
    </div>
  );
}
