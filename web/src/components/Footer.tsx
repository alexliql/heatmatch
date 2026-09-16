"use client";

import { useStore } from "@/lib/store";

export function Footer() {
  const engine = useStore((s) => s.engine);
  const lastRankMs = useStore((s) => s.lastRankMs);
  if (!engine) return null;

  const { manifest, version } = engine;
  return (
    <footer className="footer">
      <span>
        <strong>Indicative, not a feasibility study.</strong> Straight-line pipe routes, estimated
        capacities, unknown cooling types.
      </span>
      <span className="spacer" />
      <span>
        {manifest.datacenters.count} data centers · {manifest.sinks.count} sinks · built{" "}
        {manifest.built_at.slice(0, 10)}
      </span>
      <span>
        {manifest.sources.map((s, i) => (
          <span key={s.id}>
            {i > 0 && ", "}
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.id}
            </a>{" "}
            ({s.license})
          </span>
        ))}
      </span>
      <span>
        engine v{version} · rank {lastRankMs.toFixed(1)} ms
      </span>
      <a href="https://github.com/alexliql/heatmatch" target="_blank" rel="noreferrer">
        source
      </a>
    </footer>
  );
}
