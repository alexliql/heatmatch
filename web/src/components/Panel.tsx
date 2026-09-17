"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { diffFromDefaults } from "@/lib/defaults";
import { useStore } from "@/lib/store";

export type Tab = "results" | "tuning" | "detail";

const TAB_LABELS: Record<Tab, string> = {
  results: "Ranking",
  tuning: "Assumptions",
  detail: "Detail",
};

/** Resting heights for the bottom sheet, as a share of the viewport. */
const SNAPS = { peek: 0.16, half: 0.46, full: 0.92 } as const;
type Snap = keyof typeof SNAPS;

function useMediaQuery(q: string): boolean {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return match;
}

/** The floating card on wide screens; a draggable bottom sheet on narrow
 *  ones. Owns the tab strip and the status line; the tabs' content is
 *  passed in. */
export function Panel({
  tab,
  onTab,
  onAbout,
  children,
}: {
  tab: Tab;
  onTab: (t: Tab) => void;
  onAbout: () => void;
  children: ReactNode;
}) {
  const engine = useStore((s) => s.engine);
  const weights = useStore((s) => s.weights);
  const econ = useStore((s) => s.econ);
  const narrow = useMediaQuery("(max-width: 900px)");
  const modifiedCount = engine && weights && econ ? diffFromDefaults(engine, weights, econ).count : 0;

  const [snap, setSnap] = useState<Snap>("half");
  const [dragH, setDragH] = useState<number | null>(null);
  const drag = useRef<{ y: number; h: number } | null>(null);

  // Selecting something on the map should bring the sheet up to show it.
  const selectedDc = useStore((s) => s.selectedDc);
  useEffect(() => {
    if (narrow && selectedDc) setSnap((s) => (s === "peek" ? "half" : s));
  }, [narrow, selectedDc]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const panel = (e.currentTarget as HTMLElement).parentElement;
    if (!panel) return;
    drag.current = { y: e.clientY, h: panel.getBoundingClientRect().height };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag.current) return;
    const h = drag.current.h + (drag.current.y - e.clientY);
    setDragH(Math.max(60, Math.min(window.innerHeight * 0.95, h)));
  }, []);

  const onPointerUp = useCallback(() => {
    if (!drag.current) return;
    drag.current = null;
    setDragH((h) => {
      if (h != null) {
        const share = h / window.innerHeight;
        const nearest = (Object.keys(SNAPS) as Snap[]).reduce((best, k) =>
          Math.abs(SNAPS[k] - share) < Math.abs(SNAPS[best] - share) ? k : best,
        );
        setSnap(nearest);
      }
      return null;
    });
  }, []);

  const height = narrow ? (dragH != null ? `${dragH}px` : `${SNAPS[snap] * 100}dvh`) : undefined;

  const SNAP_ORDER: Snap[] = ["peek", "half", "full"];
  const step = (dir: 1 | -1) =>
    setSnap((s) => SNAP_ORDER[Math.max(0, Math.min(2, SNAP_ORDER.indexOf(s) + dir))]);

  const tabs = Object.keys(TAB_LABELS) as Tab[];
  const onTabKey = (e: React.KeyboardEvent) => {
    const i = tabs.indexOf(tab);
    if (e.key === "ArrowRight") onTab(tabs[(i + 1) % tabs.length]);
    else if (e.key === "ArrowLeft") onTab(tabs[(i + tabs.length - 1) % tabs.length]);
    else return;
    e.preventDefault();
  };

  // The legend and map controls sit above the sheet, so they need its height.
  useEffect(() => {
    const root = document.documentElement;
    if (narrow && height) root.style.setProperty("--sheet-h", height);
    else root.style.removeProperty("--sheet-h");
  }, [narrow, height]);

  return (
    <aside
      className="panel float"
      data-dragging={dragH != null}
      style={height ? { height } : undefined}
    >
      <button
        className="sheet-handle"
        aria-label="Resize panel"
        aria-expanded={snap === "full"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={() => setSnap((s) => (s === "peek" ? "half" : s === "half" ? "full" : "peek"))}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp") step(1);
          else if (e.key === "ArrowDown") step(-1);
          else return;
          e.preventDefault();
        }}
      />
      <div className="panel-head">
        <div className="seg seg-full" role="tablist" onKeyDown={onTabKey}>
          {tabs.map((t) => (
            <button
              key={t}
              id={`tab-${t}`}
              role="tab"
              aria-selected={tab === t}
              aria-controls={`pane-${t}`}
              tabIndex={tab === t ? 0 : -1}
              data-active={tab === t}
              onClick={() => onTab(t)}
            >
              {TAB_LABELS[t]}
              {t === "tuning" && modifiedCount > 0 && (
                <span className="tab-badge" title={`${modifiedCount} assumptions changed from default`}>
                  {modifiedCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
      <div className="panel-body" id={`pane-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {children}
      </div>
      {engine && (
        <div className="panel-foot">
          <span className="num">
            {engine.manifest.datacenters.count} sites · {engine.manifest.sinks.count} sinks · built{" "}
            {engine.manifest.built_at.slice(0, 10)}
          </span>
          <button onClick={onAbout}>Methods &amp; sources</button>
        </div>
      )}
    </aside>
  );
}
