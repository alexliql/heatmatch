"use client";

import { useMemo } from "react";

import { isPlaceholderName, useFeatureIndex } from "@/lib/features";
import { useStore } from "@/lib/store";
import { CAT_LABELS } from "@/lib/types";
import { num, payback, pct, score, usd } from "@/lib/format";

/** Twelve bars comparing flat monthly supply against this site's seasonal
 *  demand — the clearest way to show why utilization is below 100%. */
function SeasonStrip({ dcId }: { dcId: string }) {
  const engine = useStore((s) => s.engine);
  const explain = useStore((s) => s.explain);
  const results = useStore((s) => s.results);

  const bars = useMemo(() => {
    const match = results.find((r) => r.dc === dcId);
    if (!engine || !match) return null;
    const profiles = engine.profiles();
    const monthly = Array.from({ length: 12 }, (_, m) =>
      explain
        .filter((c) => c.delivered_mwh > 0)
        .reduce((sum, c) => sum + c.delivered_mwh * (profiles[c.cat]?.[m] ?? 0), 0),
    );
    const supply = match.supply_mwh / 12;
    const peak = Math.max(supply, ...monthly) || 1;
    return { monthly, supply, peak };
  }, [engine, explain, results, dcId]);

  if (!bars) return null;
  const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

  return (
    <div className="season">
      <div className="season-bars">
        {bars.monthly.map((v, i) => (
          <div key={i} className="season-col" title={`${months[i]}: ${num(v)} MWh of demand`}>
            <div className="season-bar" style={{ height: `${(v / bars.peak) * 100}%` }} />
            <span
              className="season-supply"
              style={{ bottom: `${(bars.supply / bars.peak) * 100}%` }}
            />
            <span className="season-label">{months[i]}</span>
          </div>
        ))}
      </div>
      <p className="muted">
        Bars are monthly demand from connected sinks; the line is the flat monthly supply. Demand
        below the line is heat with nowhere to go.
      </p>
    </div>
  );
}

export function DcDetail() {
  const selectedDc = useStore((s) => s.selectedDc);
  const explain = useStore((s) => s.explain);
  const results = useStore((s) => s.results);
  const engine = useStore((s) => s.engine);
  // Above the early returns: hooks must run in the same order every render.
  const { sinks } = useFeatureIndex(engine);

  if (!selectedDc) {
    return (
      <section className="section">
        <h2>Detail</h2>
        <p className="muted">Select a data center on the map or in the table.</p>
      </section>
    );
  }

  const match = results.find((r) => r.dc === selectedDc);
  const fc = engine?.geo.datacenters as
    | { features: { properties: Record<string, unknown> }[] }
    | undefined;
  const props = fc?.features.find((f) => f.properties.id === selectedDc)?.properties;
  if (!match) return null;

  const connected = explain.filter((c) => c.delivered_mwh > 0).length;

  return (
    <section className="section">
      <h2>{String(props?.name ?? selectedDc)}</h2>
      <dl className="facts">
        <div><dt>Region</dt><dd>{match.region === "nyc" ? "New York City" : "Upstate"}</dd></div>
        <div><dt>Capacity</dt><dd className="num">{Number(props?.mw ?? 0).toFixed(1)} MW</dd></div>
        <div><dt>Cooling</dt><dd>{String(props?.cooling ?? "unknown")}</dd></div>
        <div><dt>Score</dt><dd className="num">{score(match.score)}</dd></div>
        <div><dt>Utilization</dt><dd className="num">{pct(match.utilization)}</dd></div>
        <div><dt>Delivered</dt><dd className="num">{num(match.delivered_mwh)} MWh</dd></div>
        <div><dt>Capex</dt><dd className="num">{usd(match.capex)}</dd></div>
        <div><dt>Savings</dt><dd className="num">{usd(match.annual_savings)}/yr</dd></div>
        <div><dt>Payback</dt><dd className="num">{payback(match.payback_yrs)}</dd></div>
      </dl>

      <SeasonStrip dcId={selectedDc} />

      <h2 style={{ marginTop: 14 }}>
        Sinks in range ({connected} connected of {explain.length})
      </h2>
      <table>
        <thead>
          <tr>
            <th>Sink</th>
            <th>Pipe</th>
            <th>COP</th>
            <th>Delivered</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {explain.slice(0, 40).map((c) => (
            <tr key={c.sink}>
              <td>
                {/* The name where OpenStreetMap has one, with the category
                    underneath so the type is never lost. */}
                {(() => {
                  const name = sinks.get(c.sink)?.name;
                  const named = name && !isPlaceholderName(name);
                  return named ? (
                    <>
                      {name}
                      <br />
                      <span className="muted">
                        {CAT_LABELS[c.cat]}
                        {c.crosses_water ? " · crosses water" : ""}
                      </span>
                    </>
                  ) : (
                    <>
                      {CAT_LABELS[c.cat]}
                      {c.crosses_water ? " · crosses water" : ""}
                    </>
                  );
                })()}
              </td>
              <td className="num">{c.pipe_m.toFixed(0)} m</td>
              <td className="num">{c.hp_required ? c.cop.toFixed(1) : "direct"}</td>
              <td className="num">{c.delivered_mwh > 0 ? num(c.delivered_mwh) : "—"}</td>
              <td className="num">{score(c.score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {explain.length > 40 && (
        <p className="muted">Showing the 40 highest-scoring of {explain.length}.</p>
      )}
    </section>
  );
}
