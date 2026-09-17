"use client";

import { useState } from "react";

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
import { CAT_LABELS, type SinkCat } from "@/lib/types";

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
  // Above the early returns: hooks must run in the same order every render.
  const { dcs, sinks } = useFeatureIndex(engine);
  const [hoveredCat, setHoveredCat] = useState<SinkCat | null>(null);

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

  const rank = results.findIndex((r) => r.dc === selectedDc) + 1;
  const connected = explain.filter((c) => c.delivered_mwh > 0).length;
  const heat = cssVar(BUCKET_VARS[paybackBucket(match.payback_yrs)]);

  return (
    <>
      <section className="section">
        <div className="detail-head">
          <div style={{ minWidth: 0 }}>
            <div className="label" style={{ marginBottom: 4 }}>
              #{rank} of {results.length}
            </div>
            <h2 className="detail-title">{props?.name ?? selectedDc}</h2>
            <div className="detail-meta">
              <span>{match.region === "nyc" ? "New York City" : "Upstate"}</span>
              <span>
                <span className="num">{Number(props?.mw ?? 0).toFixed(1)}</span> MW
              </span>
              <span>{props?.cooling ?? "unknown"} cooling</span>
            </div>
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
                    style={connectedRow ? undefined : { opacity: 0.55 }}
                    onMouseEnter={() => hoverSink(c.sink)}
                    onMouseLeave={() => hoverSink(null)}
                  >
                    <td>
                      <div className="sink-name">
                        <i style={{ background: cssVar(SINK_VARS[c.cat]) }} />
                        <div>
                          {/* The name where OpenStreetMap has one, with the
                              category underneath so the type is never lost. */}
                          <b>{named ? name : label}</b>
                          <span>
                            {named ? label : "unnamed"}
                            {c.crosses_water ? " · crosses water" : ""}
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
