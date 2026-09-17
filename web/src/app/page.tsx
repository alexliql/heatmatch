"use client";

import { useEffect, useState } from "react";

import { DcDetail } from "@/components/DcDetail";
import { Footer } from "@/components/Footer";
import { Map } from "@/components/Map";
import { ResultsTable } from "@/components/ResultsTable";
import { WeightsPanel } from "@/components/WeightsPanel";
import { BUCKET_COLORS, BUCKET_LABELS, SINK_COLORS } from "@/lib/format";
import { CAT_LABELS, SINK_CATS } from "@/lib/types";
import { useStore } from "@/lib/store";

type Tab = "results" | "tuning" | "detail";

export default function Page() {
  const [tab, setTab] = useState<Tab>("results");
  const init = useStore((s) => s.init);
  const engine = useStore((s) => s.engine);
  const progress = useStore((s) => s.progress);
  const error = useStore((s) => s.error);

  // The engine is WebAssembly and must only load in the browser; the static
  // export has no wasm host.
  useEffect(() => {
    void init();
  }, [init]);

  // Selecting a site should show its detail rather than leaving the reader to
  // find the tab themselves.
  const selectedDc = useStore((s) => s.selectedDc);
  useEffect(() => {
    if (selectedDc) setTab("detail");
  }, [selectedDc]);


  if (error) {
    return (
      <main className="centered">
        <div className="error">
          <h1>heatmatch could not start</h1>
          <p className="muted">
            This tool runs its model in your browser using WebAssembly. If your browser blocks
            WebAssembly, or the data failed to load, nothing can be computed — there is no server
            to fall back to.
          </p>
          <code>{error}</code>
        </div>
      </main>
    );
  }

  if (!engine) {
    return (
      <main className="centered">
        <div>
          <h1>heatmatch</h1>
          <p className="muted">
            {progress?.message ?? "Starting…"}
            {progress?.bytes ? ` (${(progress.bytes / 1024).toFixed(0)} KB)` : ""}
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>heatmatch</h1>
        <span className="tagline">
          Which New York data centers could usefully heat their neighbours?
        </span>
        <span className="spacer" />
      </header>

      <div className="layout">
        <Map />
        <aside className="side">
          <div className="tabs">
            {(["results", "tuning", "detail"] as const).map((t) => (
              <button key={t} data-active={tab === t} onClick={() => setTab(t)}>
                {t === "results" ? "Ranking" : t === "tuning" ? "Assumptions" : "Detail"}
              </button>
            ))}
          </div>

          {tab === "results" && (
            <>
              <section className="section">
                {/* Swatch shapes mirror the map: data centers are circles,
                    sinks are squares. */}
                <h2>Data centers — payback</h2>
                <div className="legend">
                  {(["fast", "medium", "slow", "none"] as const).map((b) => (
                    <span key={b}>
                      <span className="dot" style={{ background: BUCKET_COLORS[b] }} />
                      {BUCKET_LABELS[b]}
                    </span>
                  ))}
                </div>

                <h2 style={{ marginTop: 12 }}>Heat sinks — type</h2>
                <div className="legend legend-grid">
                  {SINK_CATS.map((cat) => (
                    <span key={cat}>
                      <span className="swatch" style={{ background: SINK_COLORS[cat] }} />
                      {CAT_LABELS[cat]}
                    </span>
                  ))}
                </div>
              </section>
              <section className="section">
                <h2>Ranked data centers — all of New York State</h2>
                <ResultsTable />
              </section>
            </>
          )}
          {tab === "tuning" && <WeightsPanel />}
          {tab === "detail" && <DcDetail />}
        </aside>
      </div>

      <Footer />
    </div>
  );
}
