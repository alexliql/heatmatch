"use client";

import { useStore, type Theme } from "@/lib/store";
import { useLayoutMode } from "@/lib/useMedia";

import { InfoIcon, ThemeIcon } from "./icons";

const NEXT_THEME: Record<Theme, Theme> = { system: "dark", dark: "light", light: "system" };
const THEME_LABEL: Record<Theme, string> = {
  system: "Theme: follows your system",
  dark: "Theme: dark",
  light: "Theme: light",
};

/** Cycles system → dark → light. In the top bar on wide screens, in the
 *  panel foot on phones. */
export function ThemeButton() {
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);
  return (
    <button
      className="icon-btn"
      title={THEME_LABEL[theme]}
      aria-label={THEME_LABEL[theme]}
      onClick={() => setTheme(NEXT_THEME[theme])}
    >
      <ThemeIcon theme={theme} />
    </button>
  );
}

const STAGE_PROGRESS = { manifest: 0.15, data: 0.55, engine: 0.85, ready: 1 };

export function TopBar({ onAbout }: { onAbout: () => void }) {
  const engine = useStore((s) => s.engine);
  const compact = useLayoutMode() !== "desktop";
  const stage = useStore((s) => s.stage);
  const progress = engine ? 1 : stage ? STAGE_PROGRESS[stage] : 0.05;

  return (
    <header className="topbar float" data-compact={compact}>
      <h1 className="wordmark">heatmatch</h1>
      <span className="tagline">Which data centers could usefully heat their neighbours?</span>
      <div className="topbar-actions">
        {!compact && <ThemeButton />}
        <button className="icon-btn" title="About this tool" aria-label="About" onClick={onAbout}>
          <InfoIcon />
        </button>
      </div>
      <i className="topbar-progress" data-done={Boolean(engine)} style={{ width: `${progress * 100}%` }} />
    </header>
  );
}
