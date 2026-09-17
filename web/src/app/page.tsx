"use client";

import { useEffect, useState } from "react";

import { About } from "@/components/About";
import { DcDetail } from "@/components/DcDetail";
import { Hint } from "@/components/Hint";
import { Legend } from "@/components/Legend";
import { Map } from "@/components/Map";
import { Panel, type Tab } from "@/components/Panel";
import { Ranking } from "@/components/Ranking";
import { TopBar } from "@/components/TopBar";
import { WeightsPanel } from "@/components/WeightsPanel";
import { useStore } from "@/lib/store";

export default function Page() {
  const [tab, setTab] = useState<Tab>("results");
  const [about, setAbout] = useState(false);
  const init = useStore((s) => s.init);
  const engine = useStore((s) => s.engine);
  const error = useStore((s) => s.error);

  // The engine is WebAssembly and must only load in the browser; the static
  // export has no wasm host.
  useEffect(() => {
    void init();
  }, [init]);

  // Selecting a site should show its detail rather than leaving the reader to
  // find the tab themselves. Clearing the selection returns to the ranking.
  const selectedDc = useStore((s) => s.selectedDc);
  useEffect(() => {
    setTab((t) => (selectedDc ? "detail" : t === "detail" ? "results" : t));
  }, [selectedDc]);

  // Keyboard: "/" filters, ↑/↓ walk the ranking, Esc clears. Typing in a
  // field is left alone, except Esc which always works.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName);
      const st = useStore.getState();
      if (e.key === "Escape") {
        if (typing) (t as HTMLElement).blur();
        if (st.search) st.setSearch("");
        else if (st.selectedDc) st.select(null);
        return;
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") {
        e.preventDefault();
        setTab("results");
        requestAnimationFrame(() => document.querySelector<HTMLInputElement>(".rank-search")?.focus());
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const order = st.visibleOrder;
        if (!order.length) return;
        e.preventDefault();
        const i = st.selectedDc ? order.indexOf(st.selectedDc) : -1;
        const next = e.key === "ArrowDown" ? Math.min(order.length - 1, i + 1) : Math.max(0, i - 1);
        if (order[next] !== st.selectedDc) st.select(order[next], "list");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) {
    return (
      <main className="centered">
        <div className="error">
          <h1>heatmatch could not start</h1>
          <p className="muted">
            This tool runs its model in your browser using WebAssembly. If your browser blocks
            WebAssembly, or the data failed to load, nothing can be computed — there is no server to
            fall back to.
          </p>
          <code>{error}</code>
        </div>
      </main>
    );
  }

  return (
    <div className="shell">
      <Map />
      <TopBar onAbout={() => setAbout(true)} />
      <Legend />
      <Hint />
      <Panel tab={tab} onTab={setTab} onAbout={() => setAbout(true)}>
        {!engine ? (
          <ol className="rank-list skel" aria-busy="true" aria-label="Loading ranking">
            {Array.from({ length: 9 }, (_, i) => (
              <li key={i} className="skel-row" style={{ animationDelay: `${i * 60}ms` }}>
                <i /><i /><i /><i /><i />
              </li>
            ))}
          </ol>
        ) : (
          <div className="tabpane" key={tab}>
            {tab === "results" && <Ranking />}
            {tab === "tuning" && <WeightsPanel />}
            {tab === "detail" && <DcDetail onBack={() => setTab("results")} />}
          </div>
        )}
      </Panel>
      <About open={about} onClose={() => setAbout(false)} />
    </div>
  );
}
