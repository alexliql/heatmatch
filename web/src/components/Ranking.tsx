"use client";

import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useFeatureIndex, type DcProps } from "@/lib/features";
import { BUCKET_VARS, cssVar, payback, paybackBucket, pct, score } from "@/lib/format";
import { useStore } from "@/lib/store";
import {
  CONFIDENCE_LABELS,
  CONFIDENCE_MARKS,
  REGION_SHORT_LABELS,
  REGION_VIEWS,
  REGION_VIEW_LABELS,
  REGION_LABELS,
  type Match,
} from "@/lib/types";
import { useCoarsePointer, useLayoutMode } from "@/lib/useMedia";

import { SearchIcon } from "./icons";
import { ScoreRail } from "./ScoreRail";

const col = createColumnHelper<Match>();

const SORTS = [
  { id: "score", label: "Score" },
  { id: "payback", label: "Payback" },
  { id: "utilization", label: "Util." },
] as const;

/** One row per site: rank, name, score as a bar, payback, utilization. The
 *  numbers that explain the rank and nothing else; everything further lives
 *  in the detail. */
/** Which region the map and ranking show. "All" keeps the cross-region view
 *  the app opens with; picking one narrows both, and points the assumption
 *  sliders at it. */
function RegionTabs() {
  const viewRegion = useStore((s) => s.viewRegion);
  const setViewRegion = useStore((s) => s.setViewRegion);
  const results = useStore((s) => s.results);

  // A region with nothing in it is shown but not offered: its absence is
  // information, and a dead tab is better than a tab that silently empties.
  const counts = useMemo(() => {
    const by = new Map<string, number>();
    for (const m of results) by.set(m.region, (by.get(m.region) ?? 0) + 1);
    return by;
  }, [results]);

  return (
    <div className="seg seg-full region-tabs" role="tablist" aria-label="Region to show">
      {REGION_VIEWS.map((r) => {
        const n = r === "all" ? results.length : (counts.get(r) ?? 0);
        return (
          <button
            key={r}
            role="tab"
            aria-selected={viewRegion === r}
            data-active={viewRegion === r}
            disabled={n === 0}
            title={`${REGION_VIEW_LABELS[r]} — ${n} site${n === 1 ? "" : "s"}`}
            onClick={() => setViewRegion(r)}
          >
            {REGION_SHORT_LABELS[r]}
          </button>
        );
      })}
    </div>
  );
}

/** The same reading as the map's markers: a solid disc is a stated capacity,
 *  an outline is inferred from a building's size. Silent for a region where
 *  every figure is an estimate, since a mark every row carries says nothing. */
function ConfidenceMark({ dc }: { dc: DcProps | undefined }) {
  if (!dc || dc.mw_confidence === "footprint_estimate") return null;
  return (
    <span className="conf-mark" title={CONFIDENCE_LABELS[dc.mw_confidence]}>
      {CONFIDENCE_MARKS[dc.mw_confidence]}
    </span>
  );
}

export function Ranking() {
  const results = useStore((s) => s.results);
  const selectedDc = useStore((s) => s.selectedDc);
  const hoveredDc = useStore((s) => s.hoveredDc);
  const select = useStore((s) => s.select);
  const hoverDc = useStore((s) => s.hoverDc);
  const engine = useStore((s) => s.engine);
  const prevRanks = useStore((s) => s.prevRanks);
  const lastRankMs = useStore((s) => s.lastRankMs);
  const search = useStore((s) => s.search);
  const viewRegion = useStore((s) => s.viewRegion);
  const setSearch = useStore((s) => s.setSearch);
  const setVisibleOrder = useStore((s) => s.setVisibleOrder);
  const sheetSnap = useStore((s) => s.sheetSnap);
  const mode = useLayoutMode();
  const coarse = useCoarsePointer();
  const compact = mode !== "desktop";
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  // On a phone the filter box is folded behind an icon until wanted.
  const [searchOpen, setSearchOpen] = useState(false);

  // Match carries the data center's id, not its name.
  const { dcNames, dcs } = useFeatureIndex(engine);

  const columns = useMemo(
    () => [
      col.accessor((m) => dcNames.get(m.dc) ?? m.dc, { id: "name" }),
      col.accessor("score", { id: "score" }),
      col.accessor("utilization", { id: "utilization" }),
      // Sorting by payback ascending is "best first"; "never" sorts last.
      col.accessor((m) => m.payback_yrs ?? Number.POSITIVE_INFINITY, { id: "payback" }),
    ],
    [dcNames],
  );

  // The region is a choice of *which* list to rank, so it applies before the
  // numbering: in a single-region view the best site there is #1, not #7. The
  // name filter below is a find-within-the-list and deliberately does not
  // renumber.
  const inView = useMemo(
    () => (viewRegion === "all" ? results : results.filter((m) => m.region === viewRegion)),
    [results, viewRegion],
  );

  const table = useReactTable({
    data: inView,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const maxScore = useMemo(() => Math.max(0, ...inView.map((r) => r.score)) || 1, [inView]);

  // Keep the selected row in view when the selection came from the map.
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    if (!selectedDc) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-dc="${selectedDc}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedDc]);

  // Rank by the true position in the sorted list, then filter, so a filtered
  // view still says "#7" rather than renumbering.
  const rows = table.getRowModel().rows;
  const needle = search.trim().toLowerCase();
  const visible = rows
    .map((row, i) => ({ row, rank: i + 1 }))
    .filter(({ row }) => !needle || (dcNames.get(row.original.dc) ?? "").toLowerCase().includes(needle));

  useEffect(() => {
    setVisibleOrder(visible.map((v) => v.row.original.dc));
  });

  // FLIP: when the order changes, rows slide from where they were to where
  // they are, so a slider drag reads as movement rather than a redraw.
  const lastRects = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const items = list.querySelectorAll<HTMLElement>("[data-dc]");
    const next = new Map<string, number>();
    for (const el of items) {
      const dc = el.dataset.dc!;
      // Use offsetTop of the parent <li> instead of getBoundingClientRect().top 
      // so the coordinate is independent of scroll position.
      const top = el.parentElement!.offsetTop;
      next.set(dc, top);
      const was = lastRects.current.get(dc);
      if (!reduce && was !== undefined && Math.abs(was - top) > 1) {
        el.style.transition = "none";
        el.style.transform = `translateY(${was - top}px)`;
        void el.offsetHeight;
        el.style.transition = "transform 240ms var(--ease)";
        el.style.transform = "";
      }
    }
    lastRects.current = next;
  });

  if (!results.length) {
    return (
      <div className="empty">
        <b>Nothing to rank</b>
        No data centers in the dataset.
      </div>
    );
  }

  if (!inView.length) {
    return (
      <>
        <RegionTabs />
        <div className="empty">
          <b>Nothing to rank here</b>
          No data centers in {REGION_VIEW_LABELS[viewRegion]}.
        </div>
      </>
    );
  }

  const active = sorting[0]?.id ?? "score";
  const setSort = (id: string) =>
    setSorting([{ id, desc: id !== "payback" && id !== "name" }]);

  const showSearch = !compact || searchOpen || search.length > 0;

  return (
    <>
      <RegionTabs />
      <div className="rank-tools">
        {!(compact && showSearch) && <span className="label">Ranked data centers</span>}
        <span className="rank-tools-right">
          {compact && (
            <select
              className="sort-select"
              aria-label="Sort by"
              value={active}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="score">Score</option>
              <option value="payback">Payback</option>
              <option value="utilization">Utilization</option>
              <option value="name">Name</option>
            </select>
          )}
          <input
            className="rank-search input"
            data-open={showSearch}
            type="search"
            placeholder={coarse ? "Filter sites…" : "Filter sites…  /"}
            aria-label="Filter sites by name"
            value={search}
            autoFocus={compact && searchOpen}
            onChange={(e) => setSearch(e.target.value)}
            onBlur={() => search.length === 0 && setSearchOpen(false)}
          />
          {compact && !showSearch && (
            <button className="icon-btn" aria-label="Filter sites" onClick={() => setSearchOpen(true)}>
              <SearchIcon />
            </button>
          )}
        </span>
      </div>
      <ScoreRail sheet={mode === "sheet" ? sheetSnap : undefined} />
      <div className="rank-head" aria-hidden>
        <span>#</span>
        <button onClick={() => setSort("name")} data-active={active === "name"}>Site</button>
        {SORTS.map((s) => (
          <button key={s.id} onClick={() => setSort(s.id)} data-active={active === s.id}>
            {s.label}
          </button>
        ))}
      </div>
      <ol className="rank-list" ref={listRef}>
        {visible.length === 0 && (
          <li className="empty" style={{ padding: "var(--s-4)" }}>
            No site matches “{search}”.
          </li>
        )}
        {visible.map(({ row, rank }) => {
          const m = row.original;
          const bucket = paybackBucket(m.payback_yrs);
          const heat = cssVar(BUCKET_VARS[bucket]);
          const isSelected = m.dc === selectedDc;
          // Movement since the last recompute, in true (score) rank.
          const trueRank = results.findIndex((r) => r.dc === m.dc) + 1;
          const was = prevRanks.get(m.dc);
          const delta = was === undefined ? 0 : was - trueRank;
          return (
            <li key={m.dc}>
              <button
                className="rank-row"
                data-dc={m.dc}
                data-selected={isSelected}
                data-hover={m.dc === hoveredDc}
                onClick={() => select(isSelected ? null : m.dc, "list")}
                onMouseEnter={() => hoverDc(m.dc)}
                onMouseLeave={() => hoverDc(null)}
              >
                <span className="rank-n">
                  {rank}
                  {delta !== 0 && (
                    <span key={`${m.dc}-${lastRankMs}`} className="delta" data-dir={delta > 0 ? "up" : "down"}>
                      {delta > 0 ? "↑" : "↓"}{Math.abs(delta)}
                    </span>
                  )}
                </span>
                <span className="rank-name">
                  <b>{dcNames.get(m.dc) ?? m.dc}</b>
                  <span>
                    {REGION_LABELS[m.region]}
                    <ConfidenceMark dc={dcs.get(m.dc)} />
                  </span>
                </span>
                <span className="bar-cell">
                  <span>{score(m.score)}</span>
                  <span className="bar">
                    <i style={{ width: `${(m.score / maxScore) * 100}%`, background: heat }} />
                  </span>
                </span>
                <span className="rank-num" style={{ color: isSelected ? undefined : heat }}>
                  {payback(m.payback_yrs)}
                </span>
                <span className="rank-num">{pct(m.utilization)}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}
