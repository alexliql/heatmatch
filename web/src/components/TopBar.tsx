"use client";

import { useStore, type Theme } from "@/lib/store";

import { InfoIcon, MonitorIcon, MoonIcon, SunIcon } from "./icons";

const NEXT: Record<Theme, Theme> = { system: "dark", dark: "light", light: "system" };
const THEME_LABEL: Record<Theme, string> = {
  system: "Theme: follows your system",
  dark: "Theme: dark",
  light: "Theme: light",
};

export function TopBar({ onAbout }: { onAbout: () => void }) {
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);
  const engine = useStore((s) => s.engine);
  const stage = useStore((s) => s.progress?.stage);
  const progress = engine ? 1 : stage === "engine" ? 0.85 : stage === "data" ? 0.55 : stage === "manifest" ? 0.15 : 0.05;

  return (
    <header className="topbar float">
      <h1 className="wordmark">heatmatch</h1>
      <span className="tagline">Which New York data centers could usefully heat their neighbours?</span>
      <div className="topbar-actions">
        <button
          className="icon-btn"
          title={THEME_LABEL[theme]}
          aria-label={THEME_LABEL[theme]}
          onClick={() => setTheme(NEXT[theme])}
        >
          {theme === "dark" ? <MoonIcon /> : theme === "light" ? <SunIcon /> : <MonitorIcon />}
        </button>
        <button className="icon-btn" title="About this tool" aria-label="About" onClick={onAbout}>
          <InfoIcon />
        </button>
      </div>
      <i className="topbar-progress" data-done={Boolean(engine)} style={{ width: `${progress * 100}%` }} />
    </header>
  );
}
