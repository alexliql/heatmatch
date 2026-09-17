"use client";

import {
  createColumnHelper,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useFeatureIndex } from "@/lib/features";
import { BUCKET_VARS, cssVar, payback, paybackBucket, pct, score } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Match } from "@/lib/types";
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
  const { dcNames } = useFeatureIndex(engine);

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

  const table = useReactTable({
    data: results,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const maxScore = useMemo(() => Math.max(0, ...results.map((r) => r.score)) || 1, [results]);

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

  const active = sorting[0]?.id ?? "score";
  const setSort = (id: string) =>
    setSorting([{ id, desc: id !== "payback" && id !== "name" }]);

  const showSearch = !compact || searchOpen || search.length > 0;

  return (
    <>
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
                  <span>{m.region === "nyc" ? "New York City" : "Upstate"}</span>
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
