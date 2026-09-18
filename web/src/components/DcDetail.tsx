"use client";

import { useMemo, useState } from "react";

import { isPlaceholderName, useFeatureIndex } from "@/lib/features";
import {
  BUCKET_VARS,
  SINK_VARS,
  cssVar,
  km,
  num,
  payback,
  paybackBucket,
  pct,
  score,
  usd,
} from "@/lib/format";
import { useStore } from "@/lib/store";
import {
  CAT_LABELS,
  CONFIDENCE_LABELS,
  CONFIDENCE_MARKS,
  COUNTERFACTUAL_LABELS,
  DEMAND_SOURCE_LABELS,
  REGION_LABELS,
  type SinkCat,
} from "@/lib/types";
import { useCoarsePointer } from "@/lib/useMedia";

import { DeliveredByCategory } from "./DeliveredByCategory";
import { BackIcon, CloseIcon } from "./icons";
import { SeasonStrip } from "./SeasonStrip";

const SHOW = 40;

export function DcDetail({ onBack }: { onBack: () => void }) {
  const selectedDc = useStore((s) => s.selectedDc);
  const explain = useStore((s) => s.explain);
  const results = useStore((s) => s.results);
  const engine = useStore((s) => s.engine);
  const select = useStore((s) => s.select);
  const hoverSink = useStore((s) => s.hoverSink);
  const hoveredSink = useStore((s) => s.hoveredSink);
  const coarse = useCoarsePointer();
  const viewRegion = useStore((s) => s.viewRegion);
  // Above the early returns: hooks must run in the same order every render.
  const { dcs, sinks } = useFeatureIndex(engine);
  const [hoveredCat, setHoveredCat] = useState<SinkCat | null>(null);

  // Sinks another highly-ranked site also wants. The model allocates each data
  // center's supply independently, so in a cluster like Ashburn the same pool
  // can be counted as served by several neighbours at once. Nothing here
  // resolves that — it just stops the detail view from implying otherwise.
  const contested = useMemo(() => {
    const claims = new Map<string, number>();
    for (const m of results.slice(0, 20)) {
      for (const c of m.top) {
        if (c.delivered_mwh > 0) claims.set(c.sink, (claims.get(c.sink) ?? 0) + 1);
      }
    }
    return new Set([...claims].filter(([, n]) => n > 1).map(([sink]) => sink));
  }, [results]);

  if (!selectedDc) {
    return (
      <div className="empty">
        <b>No site selected</b>
        Pick a data center on the map or in the ranking.
      </div>
    );
  }

  const match = results.find((r) => r.dc === selectedDc);
  const props = dcs.get(selectedDc);
  if (!match) return null;

  // Ranked within the region on show, not globally: the reader arrived from a
  // list where this site was #1, and "#8 of 303" contradicts it.
  const inView =
    viewRegion === "all" ? results : results.filter((r) => r.region === viewRegion);
  const rank = inView.findIndex((r) => r.dc === selectedDc) + 1;
  const connected = explain.filter((c) => c.delivered_mwh > 0).length;

  const heat = cssVar(BUCKET_VARS[paybackBucket(match.payback_yrs)]);

  return (
    <>
      <section className="section">
        <div className="detail-head">
          <div style={{ minWidth: 0 }}>
            <div className="label" style={{ marginBottom: 4 }}>
              #{rank} of {inView.length}
            </div>
            <h2 className="detail-title">{props?.name ?? selectedDc}</h2>
            <div className="detail-meta">
              <span>{REGION_LABELS[match.region]}</span>
              <span title={props ? CONFIDENCE_LABELS[props.mw_confidence] : undefined}>
                <span className="num">{Number(props?.mw ?? 0).toFixed(1)}</span> MW
                {props && (
                  <span className="conf-mark">{CONFIDENCE_MARKS[props.mw_confidence]}</span>
                )}
              </span>
              <span>{props?.cooling ?? "unknown"} cooling</span>
            </div>
            {props && props.mw_confidence !== "reported" && props.mw_confidence !== "filed" && (
              <p className="faint" style={{ fontSize: "var(--t-xs)", marginTop: 6 }}>
                {CONFIDENCE_LABELS[props.mw_confidence]}, not a stated capacity.
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 2, flex: "0 0 auto" }}>
            <button className="icon-btn" title="Back to ranking" aria-label="Back to ranking" onClick={onBack}>
              <BackIcon />
            </button>
            <button className="icon-btn" title="Clear selection" aria-label="Clear selection" onClick={() => select(null)}>
              <CloseIcon />
            </button>
          </div>
        </div>

        <div className="stats">
          <div className="stat" style={{ "--stat-color": heat } as React.CSSProperties}>
            <div className="stat-v">{score(match.score)}</div>
            <div className="stat-k">Score</div>
          </div>
          <div className="stat" style={{ "--stat-color": heat } as React.CSSProperties}>
            <div className="stat-v">{payback(match.payback_yrs)}</div>
            <div className="stat-k">Payback</div>
          </div>
          <div className="stat">
            <div className="stat-v">{pct(match.utilization)}</div>
            <div className="stat-k">Utilization</div>
          </div>
        </div>

        <dl className="facts">
          <div>
            <dt>Delivered</dt>
            <dd>{num(match.delivered_mwh)} MWh/yr</dd>
          </div>
          <div>
            <dt>Capex</dt>
            <dd>{usd(match.capex)}</dd>
          </div>
          <div>
            <dt>Savings</dt>
            <dd>{usd(match.annual_savings)}/yr</dd>
          </div>
        </dl>

        <DeliveredByCategory hoveredCat={hoveredCat} onHoverCat={setHoveredCat} />

        <SeasonStrip dcId={selectedDc} />
      </section>

      <section className="section">
        <div className="section-head">
          <span className="label">Sinks in range</span>
          <span className="faint num" style={{ fontSize: "var(--t-xs)" }}>
            {connected} connected of {explain.length}
          </span>
        </div>
        {explain.length === 0 ? (
          <p className="muted" style={{ fontSize: "var(--t-sm)" }}>
            Nothing within reach under the current assumptions.
          </p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Sink</th>
                <th className="w-pipe">Pipe</th>
                <th className="w-cop">COP</th>
                <th className="w-mwh">MWh/yr</th>
              </tr>
            </thead>
            <tbody>
              {explain.slice(0, SHOW).map((c) => {
                const name = sinks.get(c.sink)?.name;
                const named = name && !isPlaceholderName(name);
                const label = CAT_LABELS[c.cat];
                const connectedRow = c.delivered_mwh > 0;
                return (
                  <tr
                    key={c.sink}
                    data-hover
                    data-dim={hoveredCat !== null && hoveredCat !== c.cat}
                    data-active={hoveredSink === c.sink}
                    style={connectedRow ? undefined : { opacity: 0.55 }}
                    // Hover previews on a pointer; a tap toggles on touch.
                    onMouseEnter={coarse ? undefined : () => hoverSink(c.sink)}
                    onMouseLeave={coarse ? undefined : () => hoverSink(null)}
                    onClick={coarse ? () => hoverSink(hoveredSink === c.sink ? null : c.sink) : undefined}
                  >
                    <td>
                      <div className="sink-name">
                        <i style={{ background: cssVar(SINK_VARS[c.cat]) }} />
                        <div>
                          {/* The name where OpenStreetMap has one, with the
                              category underneath so the type is never lost. */}
                          <b>{named ? name : label}</b>
                          <span>
                            {[
                              named ? label : "unnamed",
                              DEMAND_SOURCE_LABELS[sinks.get(c.sink)?.demand_source ?? ""],
                              // Gas is the default and the common case; only
                              // say so when the building is something else.
                              c.counterfactual !== "gas" ? COUNTERFACTUAL_LABELS[c.counterfactual] : "",
                              c.crosses_water ? "crosses water" : "",
                              contested.has(c.sink) ? "also claimed nearby" : "",
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="num">{km(c.pipe_m)}</td>
                    <td className="num">{c.hp_required ? c.cop.toFixed(1) : "direct"}</td>
                    <td className="num strong">{connectedRow ? num(c.delivered_mwh) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {explain.length > SHOW && (
          <p className="faint" style={{ marginTop: 8, fontSize: "var(--t-xs)" }}>
            Showing the {SHOW} highest-scoring of {explain.length}.
          </p>
        )}
      </section>
    </>
  );
}
