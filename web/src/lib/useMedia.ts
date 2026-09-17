// Layout is chosen by the shape of the screen, not the device.
//
// A phone held upright gets a bottom sheet; the same phone on its side is
// too short for a sheet and gets the side panel instead. Touch is detected
// from the pointer, never the user agent.

import { useEffect, useState } from "react";

export const SHEET_QUERY = "(max-width: 900px) and (orientation: portrait)";
export const LANDSCAPE_QUERY = "(max-height: 520px) and (max-width: 1100px)";
export const COARSE_QUERY = "(pointer: coarse)";

export type LayoutMode = "desktop" | "sheet" | "landscape";

export function layoutMode(): LayoutMode {
  if (typeof window === "undefined") return "desktop";
  if (window.matchMedia(SHEET_QUERY).matches) return "sheet";
  if (window.matchMedia(LANDSCAPE_QUERY).matches) return "landscape";
  return "desktop";
}

export function isCoarsePointer(): boolean {
  return typeof window !== "undefined" && window.matchMedia(COARSE_QUERY).matches;
}

export function useMediaQuery(q: string): boolean {
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

export function useCoarsePointer(): boolean {
  return useMediaQuery(COARSE_QUERY);
}

export function useLayoutMode(): LayoutMode {
  const sheet = useMediaQuery(SHEET_QUERY);
  const landscape = useMediaQuery(LANDSCAPE_QUERY);
  return sheet ? "sheet" : landscape ? "landscape" : "desktop";
}
