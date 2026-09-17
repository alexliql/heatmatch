// A handful of 16px line icons. Inline so there is no icon font or sprite to
// load; stroke inherits `currentColor`.

const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const SunIcon = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
  </svg>
);

export const MoonIcon = () => (
  <svg {...base}>
    <path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7Z" />
  </svg>
);

export const MonitorIcon = () => (
  <svg {...base}>
    <rect x="1.5" y="2.5" width="13" height="9" rx="1.5" />
    <path d="M5.5 14h5M8 11.5V14" />
  </svg>
);

export const InfoIcon = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="6.5" />
    <path d="M8 7.2v4M8 5v.2" />
  </svg>
);

export const CloseIcon = () => (
  <svg {...base}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
);

/** Points where a click will take the panel: up to expand, down to fold. */
export const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg {...base} style={{ transform: open ? undefined : "rotate(180deg)", transition: "transform 160ms" }}>
    <path d="M4 6l4 4 4-4" />
  </svg>
);

export const BackIcon = () => (
  <svg {...base}>
    <path d="M10 3L5 8l5 5" />
  </svg>
);

export const SearchIcon = () => (
  <svg {...base}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5L14 14" />
  </svg>
);
