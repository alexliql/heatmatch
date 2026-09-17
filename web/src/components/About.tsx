"use client";

import { useEffect, useRef } from "react";

import { useStore } from "@/lib/store";

import { CloseIcon } from "./icons";

/** Methodology and provenance, read once. Lives behind the (i) so the page
 *  itself can stay quiet. */
export function About({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const engine = useStore((s) => s.engine);
  const lastRankMs = useStore((s) => s.lastRankMs);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const manifest = engine?.manifest;

  return (
    <dialog ref={ref} className="about" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}>
      <div className="about-head">
        <h2 className="detail-title">About heatmatch</h2>
        <button className="icon-btn" aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="about-body">
        <p className="about-note">
          <b>Indicative, not a feasibility study.</b> Pipe routes are straight-line approximations,
          most capacity figures are estimates, and cooling type is unknown for nearly every site.
        </p>

        <div>
          <h3>What the score means</h3>
          <p>
            If this data center&rsquo;s waste heat were available, how much of it could usefully reach a
            neighbour, and how attractive would that be? It is a ranking signal, not a measurement.
          </p>
        </div>

        <div>
          <h3>How it is computed</h3>
          <ol>
            <li>Every sink within the search radius is a candidate.</li>
            <li>Straight-line distance becomes a pipe length under the chosen distance model.</li>
            <li>Each pairing is judged: category weight × demand × distance decay × heat-pump penalty × zone bonus.</li>
            <li>Supply is finite, so sinks compete for it, best first.</li>
            <li>Flat supply is overlaid on monthly demand; heat nobody needs is wasted.</li>
            <li>Pipe and heat-pump capital is set against displaced gas, electricity and avoided cooling.</li>
          </ol>
          <p style={{ marginTop: 8 }}>
            Everything in <b>Assumptions</b> is a starting point, not a finding. The model runs in your
            browser; there is no server.
          </p>
        </div>

        {manifest && (
          <div>
            <h3>Data</h3>
            <p>
              {manifest.datacenters.count} data centers · {manifest.sinks.count} heat sinks · built{" "}
              {manifest.built_at.slice(0, 10)} · engine v{engine?.version} · ranks in{" "}
              {lastRankMs.toFixed(1)} ms
            </p>
            <ul style={{ marginTop: 8 }}>
              {manifest.sources.map((s) => (
                <li key={s.id}>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    <code>{s.id}</code>
                  </a>{" "}
                  <span className="faint">({s.license})</span>
                  {s.note ? <> — {s.note}</> : null}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p>
          <a href="https://github.com/alexliql/heatmatch" target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
        </p>
      </div>
    </dialog>
  );
}
