"use client";

import { useEffect, useState } from "react";

import { DcDetail } from "@/components/DcDetail";
import { Footer } from "@/components/Footer";
import { Map } from "@/components/Map";
import { RegionToggle } from "@/components/RegionToggle";
import { ResultsTable } from "@/components/ResultsTable";
import { WeightsPanel } from "@/components/WeightsPanel";
import { BUCKET_COLORS, BUCKET_LABELS } from "@/lib/format";
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
        <RegionToggle />
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
                <h2>Payback</h2>
                <div className="legend">
                  {(["fast", "medium", "slow", "none"] as const).map((b) => (
                    <span key={b}>
                      <span className="dot" style={{ background: BUCKET_COLORS[b] }} />
                      {BUCKET_LABELS[b]}
                    </span>
                  ))}
                </div>
              </section>
              <section className="section">
                <h2>Ranked data centers</h2>
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
