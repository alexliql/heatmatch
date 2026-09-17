"use client";

import { useEffect, useState } from "react";

import { useStore } from "@/lib/store";

const KEY = "heatmatch:hinted";

/** One line over the map for a first visit, gone on the first interaction.
 *  The legend explains the encoding; this invites the click. */
export function Hint() {
  const engine = useStore((s) => s.engine);
  const interacted = useStore((s) => s.interacted);
  const [seen, setSeen] = useState(true);

  useEffect(() => {
    try {
      setSeen(localStorage.getItem(KEY) === "1");
    } catch {
      setSeen(false);
    }
  }, []);

  useEffect(() => {
    if (!interacted) return;
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* ignore */
    }
  }, [interacted]);

  if (!engine || seen) return null;
  return (
    <div className="hint float" data-hidden={interacted} aria-live="polite">
      Circles are data centers — sized by capacity, coloured by payback. Click one to see who
      could use its heat.
    </div>
  );
}
