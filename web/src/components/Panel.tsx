"use client";

import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { diffFromDefaults } from "@/lib/defaults";
import { useFeatureIndex } from "@/lib/features";
import { payback, score } from "@/lib/format";
import { SHEET_SNAPS as SNAPS, useSelectedMatch, useStore, type SheetSnap } from "@/lib/store";
import { useLayoutMode } from "@/lib/useMedia";

import { ThemeButton } from "./TopBar";

export type Tab = "results" | "tuning" | "detail";

const TAB_LABELS: Record<Tab, string> = {
  results: "Ranking",
  tuning: "Assumptions",
  detail: "Detail",
};

const SNAP_ORDER: SheetSnap[] = ["peek", "half", "full"];
const stepFrom = (snap: SheetSnap, dir: 1 | -1) =>
  SNAP_ORDER[Math.max(0, Math.min(2, SNAP_ORDER.indexOf(snap) + dir))];
/** Faster than this (px/ms) and a drag is a fling: snap in its direction. */
const FLING = 0.5;

/** The one line worth reading while the sheet is down and the map is up. */
function PeekSummary({ onOpen }: { onOpen: () => void }) {
  const engine = useStore((s) => s.engine);
  const results = useStore((s) => s.results);
  const m = useSelectedMatch();
  const { dcName } = useFeatureIndex(engine);
  return (
    <button className="peek" onClick={onOpen} aria-label="Open panel">
      {m ? (
        <>
          <span className="faint num">#{results.indexOf(m) + 1}</span>
          <b>{dcName(m.dc)}</b>
          <span className="num">{score(m.score)}</span>
          <span className="num">{payback(m.payback_yrs)}</span>
        </>
      ) : (
        <>
          <b>{engine ? `${engine.manifest.datacenters.count} sites ranked` : "Loading…"}</b>
          <span className="faint">tap one on the map</span>
        </>
      )}
    </button>
  );
}

/** The floating card on wide screens and short landscapes; a draggable
 *  bottom sheet in portrait. Owns the tab strip and the status line; the
 *  tabs' content is passed in. */
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
  const mode = useLayoutMode();
  const sheet = mode === "sheet";
  const modifiedCount = engine && weights && econ ? diffFromDefaults(engine, weights, econ).count : 0;

  const snap = useStore((s) => s.sheetSnap);
  const setSnap = useStore((s) => s.setSheetSnap);
  const panelRef = useRef<HTMLElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  // A drag writes the height straight to the element; React only hears
  // about the snap it settles on.
  const drag = useRef<{ y: number; h: number; lastY: number; lastT: number; v: number } | null>(null);

  const settle = useCallback(
    (h: number, v: number) => {
      const share = h / window.innerHeight;
      const nearest = SNAP_ORDER.reduce((b, k) =>
        Math.abs(SNAPS[k] - share) < Math.abs(SNAPS[b] - share) ? k : b,
      );
      // A fling steps one snap in its direction (up = taller).
      const next = Math.abs(v) > FLING ? stepFrom(nearest, v < 0 ? 1 : -1) : nearest;
      const el = panelRef.current;
      if (el) {
        el.style.height = "";
        el.dataset.dragging = "false";
      }
      setSnap(next);
    },
    [setSnap],
  );

  const startDrag = useCallback((y: number) => {
    const el = panelRef.current;
    if (!el) return;
    const t = performance.now();
    drag.current = { y, h: el.getBoundingClientRect().height, lastY: y, lastT: t, v: 0 };
    el.dataset.dragging = "true";
  }, []);

  const moveDrag = useCallback((y: number) => {
    const d = drag.current;
    const el = panelRef.current;
    if (!d || !el) return;
    const t = performance.now();
    if (t > d.lastT) d.v = (y - d.lastY) / (t - d.lastT);
    d.lastY = y;
    d.lastT = t;
    const h = Math.max(48, Math.min(window.innerHeight * 0.92, d.h + (d.y - y)));
    el.style.height = `${h}px`;
  }, []);

  const endDrag = useCallback(() => {
    const d = drag.current;
    const el = panelRef.current;
    drag.current = null;
    if (!d || !el) return;
    settle(el.getBoundingClientRect().height, d.v);
  }, [settle]);

  // Grip: the handle and the tab strip both drag. No pointer capture, so a
  // tap still reaches the tab underneath; a real drag swallows the click.
  const moved = useRef(false);
  const onGripDown = useCallback(
    (e: React.PointerEvent) => {
      if (!sheet || e.button !== 0) return;
      const y0 = e.clientY;
      moved.current = false;
      let started = false;
      const onMove = (ev: PointerEvent) => {
        if (!started) {
          if (Math.abs(ev.clientY - y0) < 6) return;
          started = true;
          moved.current = true;
          startDrag(y0);
        }
        moveDrag(ev.clientY);
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        if (started) endDrag();
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [sheet, startDrag, moveDrag, endDrag],
  );
  const onGripClickCapture = useCallback((e: React.MouseEvent) => {
    if (moved.current) {
      e.preventDefault();
      e.stopPropagation();
      moved.current = false;
    }
  }, []);

  // Body: a downward pull when already at the top of its scroll collapses
  // the sheet, the way a native sheet does.
  useEffect(() => {
    const body = bodyRef.current;
    if (!body || !sheet) return;
    let startY = 0;
    let armed = false;
    let taken = false;
    const onStart = (e: TouchEvent) => {
      startY = e.touches[0].clientY;
      // Not from a control: a slider must keep its own touches.
      const onControl = (e.target as HTMLElement | null)?.closest("input, select, textarea, svg");
      armed = body.scrollTop <= 0 && !onControl;
      taken = false;
    };
    const onMove = (e: TouchEvent) => {
      if (!armed) return;
      const y = e.touches[0].clientY;
      if (!taken) {
        if (y - startY < 8) return;
        taken = true;
        startDrag(startY);
      }
      e.preventDefault();
      moveDrag(y);
    };
    const onEnd = () => {
      if (taken) endDrag();
      armed = false;
      taken = false;
    };
    body.addEventListener("touchstart", onStart, { passive: true });
    body.addEventListener("touchmove", onMove, { passive: false });
    body.addEventListener("touchend", onEnd);
    body.addEventListener("touchcancel", onEnd);
    return () => {
      body.removeEventListener("touchstart", onStart);
      body.removeEventListener("touchmove", onMove);
      body.removeEventListener("touchend", onEnd);
      body.removeEventListener("touchcancel", onEnd);
    };
  }, [sheet, startDrag, moveDrag, endDrag]);

  // Where the sheet rests follows what the reader just did: a pick from the
  // list needs the map visible, a pick on the map needs the detail visible,
  // and a tap on the map while the sheet is full means "let me see".
  const selectedDc = useStore((s) => s.selectedDc);
  useEffect(() => {
    if (!sheet || !selectedDc) return;
    const src = useStore.getState().selectionSource;
    setSnap(src === "list" ? "half" : useStore.getState().sheetSnap === "peek" ? "half" : useStore.getState().sheetSnap);
  }, [sheet, selectedDc, setSnap]);

  useEffect(() => {
    if (!sheet) return;
    const map = document.querySelector<HTMLElement>(".map-wrap");
    if (!map) return;
    const onDown = () => {
      if (useStore.getState().sheetSnap === "full") setSnap("half");
    };
    map.addEventListener("pointerdown", onDown);
    return () => map.removeEventListener("pointerdown", onDown);
  }, [sheet, setSnap]);

  // The legend, hint and map controls sit above the sheet and need its
  // height; the map reads the panel's rect directly.
  useEffect(() => {
    const root = document.documentElement;
    if (sheet) root.style.setProperty("--sheet-h", `${SNAPS[snap] * 100}dvh`);
    else root.style.removeProperty("--sheet-h");
  }, [sheet, snap]);

  // Read the current snap from the store, not the render: two quick taps
  // must step twice.
  const step = (dir: 1 | -1) => setSnap(stepFrom(useStore.getState().sheetSnap, dir));
  const cycle = () => {
    const cur = useStore.getState().sheetSnap;
    setSnap(cur === "full" ? "peek" : stepFrom(cur, 1));
  };

  const tabs = Object.keys(TAB_LABELS) as Tab[];
  const onTabKey = (e: React.KeyboardEvent) => {
    const i = tabs.indexOf(tab);
    if (e.key === "ArrowRight") onTab(tabs[(i + 1) % tabs.length]);
    else if (e.key === "ArrowLeft") onTab(tabs[(i + tabs.length - 1) % tabs.length]);
    else return;
    e.preventDefault();
  };

  return (
    <aside ref={panelRef} className="panel float" data-mode={mode}>
      <div className="sheet-grip" onPointerDown={onGripDown} onClickCapture={onGripClickCapture}>
        {sheet && (
          <button
            className="sheet-handle"
            aria-label="Resize panel"
            aria-expanded={snap === "full"}
            onClick={cycle}
            onKeyDown={(e) => {
              if (e.key === "ArrowUp") step(1);
              else if (e.key === "ArrowDown") step(-1);
              else return;
              e.preventDefault();
            }}
          />
        )}
        {sheet && snap === "peek" ? (
          <PeekSummary onOpen={() => setSnap("half")} />
        ) : (
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
        )}
      </div>
      <div ref={bodyRef} className="panel-body" id={`pane-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {children}
      </div>
      {engine && (
        <div className="panel-foot">
          <span className="num">
            {engine.manifest.datacenters.count} sites · {engine.manifest.sinks.count} sinks · built{" "}
            {engine.manifest.built_at.slice(0, 10)}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button onClick={onAbout}>Methods &amp; sources</button>
            {mode !== "desktop" && <ThemeButton />}
          </span>
        </div>
      )}
    </aside>
  );
}
