"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { useStore } from "@/lib/store";
import { BUCKET_COLORS, num, payback, paybackBucket, pct, score, usd } from "@/lib/format";
import type { Match } from "@/lib/types";

const col = createColumnHelper<Match>();

export function ResultsTable() {
  const results = useStore((s) => s.results);
  const selectedDc = useStore((s) => s.selectedDc);
  const select = useStore((s) => s.select);
  const engine = useStore((s) => s.engine);
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);

  // Match carries the data center's id, not its name; the names live in the
  // GeoJSON the map already holds.
  const names = useMemo(() => {
    const out = new Map<string, string>();
    const fc = engine?.geo.datacenters as
      | { features: { properties: { id: string; name: string } }[] }
      | undefined;
    for (const f of fc?.features ?? []) out.set(f.properties.id, f.properties.name);
    return out;
  }, [engine]);

  const columns = useMemo(
    () => [
      col.accessor((m) => names.get(m.dc) ?? m.dc, {
        id: "name",
        header: "Data center",
        cell: (c) => (
          <>
            <span
              className="dot"
              style={{ background: BUCKET_COLORS[paybackBucket(c.row.original.payback_yrs)] }}
            />
            {c.getValue()}
          </>
        ),
      }),
      col.accessor("score", { header: "Score", cell: (c) => score(c.getValue()) }),
      col.accessor("supply_mwh", {
        header: "Supply",
        cell: (c) => `${num(c.getValue())} MWh`,
      }),
      col.accessor("utilization", { header: "Util.", cell: (c) => pct(c.getValue()) }),
      col.accessor("delivered_mwh", { header: "Delivered", cell: (c) => num(c.getValue()) }),
      col.accessor("capex", { header: "Capex", cell: (c) => usd(c.getValue()) }),
      col.accessor("annual_savings", { header: "Savings/yr", cell: (c) => usd(c.getValue()) }),
      col.accessor((m) => m.payback_yrs ?? Number.POSITIVE_INFINITY, {
        id: "payback",
        header: "Payback",
        cell: (c) => payback(c.row.original.payback_yrs),
      }),
    ],
    [names],
  );

  const table = useReactTable({
    data: results,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!results.length) {
    return <p className="muted">No data centers in this region.</p>;
  }

  return (
    <table>
      <thead>
        {table.getHeaderGroups().map((hg) => (
          <tr key={hg.id}>
            {hg.headers.map((h) => (
              <th key={h.id} onClick={h.column.getToggleSortingHandler()}>
                {flexRender(h.column.columnDef.header, h.getContext())}
                {{ asc: " ▲", desc: " ▼" }[h.column.getIsSorted() as string] ?? ""}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            data-selected={row.original.dc === selectedDc}
            onClick={() => select(row.original.dc === selectedDc ? null : row.original.dc)}
          >
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className={cell.column.id === "name" ? undefined : "num"}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
