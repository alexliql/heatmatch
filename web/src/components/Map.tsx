"use client";

import type { ExpressionSpecification, LngLatBoundsLike, PaddingOptions } from "maplibre-gl";
import {
  AttributionControl,
  Map as MlMap,
  NavigationControl,
  Popup,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import circle from "@turf/circle";

import type { Engine } from "@/lib/engine";
import { isPlaceholderName } from "@/lib/features";
import {
  BUCKET_VARS,
  SINK_VARS,
  cssVar,
  km,
  mw,
  num,
  palette,
  paybackBucket,
  score,
  type Palette,
} from "@/lib/format";
import { SHEET_SNAPS, resolvedTheme, useStore } from "@/lib/store";
import { isCoarsePointer, layoutMode } from "@/lib/useMedia";
import { CAT_LABELS, type DcFeature, type RegionView, type SinkCat } from "@/lib/types";

import "maplibre-gl/dist/maplibre-gl.css";

const EMPTY = { type: "FeatureCollection", features: [] } as never;

// CARTO's minimal basemaps: coastlines, water, major roads and labels, and
// little else, so the data drawn on top has the page to itself.
const BASEMAPS = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
} as const;

const NONE_FILTER: ExpressionSpecification = ["==", ["get", "id"], "__none__"];

// icon-size is a multiplier on a 24 px source image. Connected sinks grow
// so they read as picked out, not merely brighter. A layout property may
// hold only one zoom curve, so the per-feature choice sits inside each stop
// rather than around the curve.
const SINK_STOPS: [number, number, number][] = [
  [7, 0.14, 0.28],
  [11, 0.26, 0.46],
  [15, 0.42, 0.7],
];
function sinkSize(picked?: ExpressionSpecification): ExpressionSpecification {
  return [
    "interpolate", ["linear"], ["zoom"],
    ...SINK_STOPS.flatMap(([z, base, big]) => [z, picked ? ["case", picked, big, base] : base]),
  ] as unknown as ExpressionSpecification;
}
const SINK_SIZE = sinkSize();
// Quiet at state zoom, where 872 squares would otherwise read as confetti;
// fully present once the streets are visible.
const SINK_OPACITY: ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"], 7, 0.35, 10, 0.6, 13, 0.9,
];
// Sinks a selected site cannot reach stay on the map as context, dimmed but
// still readable.
const SINK_OPACITY_FADED = 0.5;

// Scaled by capacity.
const DC_RADIUS: ExpressionSpecification = [
  "interpolate", ["linear"], ["get", "mw"], 0, 5, 5, 9, 20, 16,
];

const ICON_PX = 24;
const ICON_BORDER_PX = 3;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

// Icons are generated rather than loaded from a sprite: eleven flat squares
// are cheaper to draw here than to ship, and they stay in step with the
// theme's colours. Squares, so sinks never read as small data centers: shape
// carries the distinction between the two populations, colour is free to
// carry category.
function squareIcon(fill: string, border: string) {
  const [r, g, b] = hexToRgb(fill);
  const [br, bg, bb] = hexToRgb(border);
  const data = new Uint8Array(ICON_PX * ICON_PX * 4);
  for (let y = 0; y < ICON_PX; y++) {
    for (let x = 0; x < ICON_PX; x++) {
      const edge =
        x < ICON_BORDER_PX || y < ICON_BORDER_PX ||
        x >= ICON_PX - ICON_BORDER_PX || y >= ICON_PX - ICON_BORDER_PX;
      const i = (y * ICON_PX + x) * 4;
      data[i] = edge ? br : r;
      data[i + 1] = edge ? bg : g;
      data[i + 2] = edge ? bb : b;
      data[i + 3] = 255;
    }
  }
  return { width: ICON_PX, height: ICON_PX, data };
}

const iconId = (cat: string) => `sink-${cat}`;

const SINK_ICON = [
  "match",
  ["get", "cat"],
  ...Object.keys(SINK_VARS).flatMap((cat) => [cat, iconId(cat)]),
  iconId("office"),
] as unknown as ExpressionSpecification;

/** How much of the viewport the floating chrome covers, so fits and flights
 *  centre on the visible map rather than the whole canvas. Measured from
 *  the panel itself rather than the CSS variables, which are in dvh. */
function chromePadding(): PaddingOptions {
  const panel = document.querySelector<HTMLElement>(".panel")?.getBoundingClientRect();
  const mode = layoutMode();
  if (mode === "sheet") {
    // The sheet may still be animating to its new snap; use the target.
    const sheet = SHEET_SNAPS[useStore.getState().sheetSnap] * window.innerHeight;
    return { top: 72, left: 24, right: 24, bottom: sheet + 24 };
  }
  const w = panel?.width ?? 400;
  return mode === "landscape"
    ? { top: 64, left: 24, right: w + 24, bottom: 24 }
    : { top: 72, left: 40, right: w + 48, bottom: 48 };
}

function dcBounds(engine: Engine, region: RegionView = "all"): LngLatBoundsLike | null {
  const coords = engine.geo.datacenters.features
    .filter((f) => region === "all" || f.properties.region === region)
    .map((f) => f.geometry.coordinates);
  if (coords.length === 0) return null;
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

function dcPosition(engine: Engine, id: string | null): [number, number] | undefined {
  return engine.geo.datacenters.features.find((f) => f.properties.id === id)?.geometry.coordinates;
}

const HOVERED: ExpressionSpecification = ["boolean", ["feature-state", "hover"], false];
const SELECTED: ExpressionSpecification = ["boolean", ["feature-state", "selected"], false];

/** Everything that depends on the style: sources, images, layers. Runs on
 *  first load and again after a theme swap, which drops all of it. */
function buildLayers(m: MlMap, engine: Engine, pal: Palette) {
  // Marks go under the basemap's place names, as on any editorial map; our
  // own labels go on top so they win collisions against them. The anchor is
  // the start of the label block, the first symbol layer with nothing but
  // symbols above it, not the first symbol layer in the style: Positron
  // puts `waterway_label` below every road and building, and anchoring
  // there buried the marks in light mode.
  const layers = m.getStyle().layers;
  let firstLabel = layers.length;
  for (let i = layers.length - 1; i >= 0 && layers[i].type === "symbol"; i--) firstLabel = i;
  const under = layers[firstLabel]?.id;

  m.addSource("sinks", { type: "geojson", data: engine.geo.sinks as never, promoteId: "id" });
  m.addSource("dcs", { type: "geojson", data: engine.geo.datacenters as never, promoteId: "id" });
  m.addSource("rings", { type: "geojson", data: EMPTY });
  m.addSource("ring-label", { type: "geojson", data: EMPTY });

  if (engine.geo.zones) {
    m.addSource("zones", { type: "geojson", data: engine.geo.zones as never });
    // An outline, not a fill: the boundary is hand-drawn and approximate, so
    // it should mark an edge rather than colour everything inside it.
    m.addLayer({
      id: "zones-line",
      type: "line",
      source: "zones",
      paint: {
        "line-color": pal.zone,
        "line-width": 1,
        "line-opacity": 0.7,
        "line-dasharray": [3, 3],
      },
    });
  }

  // Reach rings for the selected site: a faint wash and a hairline, in the
  // accent so they read as part of the selection.
  m.addLayer({
    id: "rings-fill",
    type: "fill",
    source: "rings",
    filter: ["==", ["get", "ring"], "outer"],
    paint: { "fill-color": pal.accent, "fill-opacity": 0.05 },
  }, under);
  m.addLayer({
    id: "rings-line",
    type: "line",
    source: "rings",
    paint: {
      "line-color": pal.accent,
      "line-width": ["case", ["==", ["get", "ring"], "outer"], 1.2, 0.8],
      "line-opacity": ["case", ["==", ["get", "ring"], "outer"], 0.8, 0.5],
      "line-dasharray": [3, 3],
    },
  }, under);
  m.addLayer({
    id: "rings-label",
    type: "symbol",
    source: "ring-label",
    layout: {
      "text-field": ["get", "label"],
      "text-size": 10.5,
      "text-anchor": "bottom",
      "text-offset": [0, -0.4],
      "text-letter-spacing": 0.04,
      "text-optional": true,
    },
    paint: {
      "text-color": pal.accent,
      "text-halo-color": pal.bg,
      "text-halo-width": 1.4,
    },
  }, under);

  for (const cat of Object.keys(SINK_VARS) as SinkCat[]) {
    if (!m.hasImage(iconId(cat))) m.addImage(iconId(cat), squareIcon(pal.sink[cat], pal.line));
  }

  m.addLayer({
    id: "sinks-square",
    type: "symbol",
    source: "sinks",
    layout: {
      "icon-image": SINK_ICON,
      "icon-size": SINK_SIZE,
      // These are data, not labels: never drop one to resolve a collision.
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    },
    paint: { "icon-opacity": SINK_OPACITY },
  }, under);

  // A sink pointed at from the detail table.
  m.addLayer({
    id: "sinks-hover",
    type: "circle",
    source: "sinks",
    filter: NONE_FILTER,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 7, 15, 12],
      "circle-color": "transparent",
      "circle-stroke-color": pal.accent,
      "circle-stroke-width": 1.5,
    },
  });

  // Names for the sinks a selected site could actually reach. Filtered to
  // nothing until a selection exists, so the map stays quiet by default.
  m.addLayer({
    id: "sinks-label",
    type: "symbol",
    source: "sinks",
    filter: NONE_FILTER,
    minzoom: 12,
    layout: {
      "text-field": ["get", "name"],
      "text-size": 10.5,
      "text-offset": [0, 0.9],
      "text-anchor": "top",
      "text-max-width": 10,
      "text-optional": true,
    },
    paint: {
      "text-color": pal.fg,
      "text-halo-color": pal.bg,
      "text-halo-width": 1.2,
      "text-opacity": 0.85,
    },
  });

  const radius: ExpressionSpecification = ["*", DC_RADIUS, ["case", HOVERED, 1.2, 1]];

  // A soft halo in the ground colour separates the mark from the basemap
  // without the hard white edge a stroke would give.
  m.addLayer({
    id: "dcs-halo",
    type: "circle",
    source: "dcs",
    paint: {
      "circle-radius": ["+", radius, 3],
      "circle-color": pal.line,
      "circle-opacity": 0.85,
    },
  }, under);

  // Selection pulse, driven by requestAnimationFrame on select.
  m.addLayer({
    id: "dcs-pulse",
    type: "circle",
    source: "dcs",
    filter: NONE_FILTER,
    paint: {
      "circle-radius": DC_RADIUS,
      "circle-color": "transparent",
      "circle-stroke-color": pal.accent,
      "circle-stroke-width": 2,
      "circle-stroke-opacity": 0,
    },
  });

  // Payback bucket gives the colour; how well established the site's capacity
  // is gives the fill. A stated capacity reads as a solid disc, a parcel
  // estimate as a part-filled one, a footprint guess as an outline — so a
  // glance at the map distinguishes "this site is 90 MW" from "this building
  // is about the right size to be 90 MW".
  //
  // Encoded as fill rather than as a dashed outline because MapLibre circle
  // layers have no dashed stroke: `circle-stroke-*` is solid only, and dashes
  // exist on line layers alone.
  const bucketColor: ExpressionSpecification = [
    "match",
    ["feature-state", "bucket"],
    "fast", pal.bucket.fast,
    "medium", pal.bucket.medium,
    "slow", pal.bucket.slow,
    pal.bucket.none,
  ];
  const stated: ExpressionSpecification = [
    "match", ["get", "mw_confidence"], ["reported", "filed"], true, false,
  ];
  const weakest: ExpressionSpecification = [
    "==", ["get", "mw_confidence"], "footprint_estimate",
  ];
  // Two opacity ramps rather than a multiplier: expressions cannot clamp, and
  // an outline still has to lift on hover without becoming a solid disc.
  const fill = (base: number, mid: number, weak: number): ExpressionSpecification => [
    "case", stated, base, weakest, weak, mid,
  ];

  m.addLayer({
    id: "dcs-circle",
    type: "circle",
    source: "dcs",
    paint: {
      "circle-radius": radius,
      "circle-color": bucketColor,
      // The ring carries the colour when the fill is too faint to.
      "circle-stroke-width": ["case", SELECTED, 2, stated, 0, 1.5],
      "circle-stroke-color": ["case", SELECTED, pal.accent, bucketColor],
      "circle-opacity": [
        "case",
        ["any", SELECTED, HOVERED], fill(1, 0.7, 0.35),
        fill(0.9, 0.45, 0.15),
      ],
    },
  }, under);

  m.addLayer({
    id: "dcs-label",
    type: "symbol",
    source: "dcs",
    filter: NONE_FILTER,
    layout: {
      "text-field": ["get", "name"],
      "text-size": 12,
      "text-anchor": "left",
      "text-offset": [1.4, 0],
      "text-max-width": 12,
      "text-optional": true,
    },
    paint: {
      "text-color": pal.fg,
      "text-halo-color": pal.bg,
      "text-halo-width": 1.6,
    },
  });
}

export function Map() {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const engineRef = useRef<Engine | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const engine = useStore((s) => s.engine);
  const results = useStore((s) => s.results);
  const explain = useStore((s) => s.explain);
  const selectedDc = useStore((s) => s.selectedDc);
  const hoveredDc = useStore((s) => s.hoveredDc);
  const hoveredSink = useStore((s) => s.hoveredSink);
  const theme = useStore((s) => s.theme);
  const viewRegion = useStore((s) => s.viewRegion);
  const weights = useStore((s) => s.weights);

  // Bumped every time the layers are (re)built; effects that paint state
  // key on it so they re-run after a theme swap drops the style.
  const [gen, setGen] = useState(0);
  const genRef = useRef(0);
  const currentScheme = useRef<"light" | "dark" | null>(null);

  engineRef.current = engine;

  // Built once, on mount, so the basemap is on screen while the engine
  // loads. Anything that changes as the user works is read from the store
  // inside the handlers rather than closed over.
  useEffect(() => {
    if (!ref.current || map.current) return;

    const scheme = resolvedTheme(useStore.getState().theme);
    currentScheme.current = scheme;

    let m: MlMap;
    try {
      m = new MlMap({
        container: ref.current,
        style: BASEMAPS[scheme],
        center: [-74.5, 42],
        zoom: 6,
        attributionControl: false,
        fadeDuration: 150,
      });
    } catch (e) {
      // maplibre needs WebGL2. Without it the map cannot render, but the
      // ranking is plain numbers and must survive.
      setMapError(e instanceof Error ? e.message : String(e));
      return;
    }
    m.on("error", (e) => {
      // Tile errors are transient; only a style failure is worth surfacing.
      // Everything else still goes to the console so a bad expression is
      // not silent.
      if (process.env.NODE_ENV !== "production") console.warn("[map]", e.error?.message ?? e);
      if (!m.isStyleLoaded()) setMapError(e.error?.message ?? "map failed to load");
    });
    m.addControl(new AttributionControl({ compact: true }), "bottom-left");
    // Pinch zooms on touch; the buttons would only cover the map.
    if (!isCoarsePointer()) m.addControl(new NavigationControl({ showCompass: false }), "bottom-right");

    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "260px" });

    m.on("mouseenter", "dcs-circle", (e: MapLayerMouseEvent) => {
      m.getCanvas().style.cursor = "pointer";
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties as DcFeature;
      const match = useStore.getState().results.find((r) => r.dc === p.id);
      useStore.getState().hoverDc(p.id);
      const bucket = paybackBucket(match?.payback_yrs);
      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<b><i class="popup-heat" style="background:${cssVar(BUCKET_VARS[bucket])}"></i>${p.name}</b>` +
            `<div class="muted num">${mw(Number(p.mw))}${match ? ` · score ${score(match.score)}` : ""}</div>`,
        )
        .addTo(m);
    });
    m.on("mouseleave", "dcs-circle", () => {
      m.getCanvas().style.cursor = "";
      useStore.getState().hoverDc(null);
      popup.remove();
    });
    const showSink = (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties as { name: string; cat: SinkCat; demand_kwh: number };
      const label = CAT_LABELS[p.cat] ?? p.cat;
      // 30% of sinks have no name in OpenStreetMap; the category is the
      // honest fallback rather than an empty tooltip.
      const title = isPlaceholderName(p.name) ? label : p.name;
      const sub = isPlaceholderName(p.name) ? "" : `${label} · `;
      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<b><i class="popup-cat" style="background:${cssVar(SINK_VARS[p.cat])}"></i>${title}</b>` +
            `<div class="muted num">${sub}${num(Number(p.demand_kwh) / 1000)} MWh/yr</div>`,
        )
        .addTo(m);
    };
    m.on("mouseenter", "sinks-square", showSink);
    m.on("mouseleave", "sinks-square", () => popup.remove());
    // Touch has no hover: a tap on a sink shows the card, a tap anywhere
    // else clears it.
    if (isCoarsePointer()) {
      m.on("click", "sinks-square", (e) => {
        showSink(e);
        e.originalEvent.stopPropagation();
      });
      m.on("click", () => popup.remove());
    }

    m.on("dragstart", () => useStore.getState().markInteracted());

    m.on("click", "dcs-circle", (e: MapLayerMouseEvent) => {
      const id = (e.features?.[0]?.properties as { id?: string })?.id;
      if (!id) return;
      const store = useStore.getState();
      store.select(id === store.selectedDc ? null : id, "map");
    });

    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  // Layers need both the style and the engine. Build when the second of the
  // two arrives, and again whenever the style is replaced. `isStyleLoaded`
  // is not the signal: it also waits for tiles, so it can read false long
  // after `style.load` has fired.
  const styleLoaded = useRef(false);
  const tryBuild = useRef(() => {});
  tryBuild.current = () => {
    const m = map.current;
    const eng = engineRef.current;
    if (!m || !eng || !styleLoaded.current || m.getSource("dcs")) return;
    buildLayers(m, eng, palette());
    genRef.current += 1;
    setGen(genRef.current);
  };

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const onStyle = () => {
      styleLoaded.current = true;
      tryBuild.current();
    };
    m.on("style.load", onStyle);
    return () => {
      m.off("style.load", onStyle);
    };
  }, []);

  useEffect(() => {
    tryBuild.current();
  }, [engine]);

  // Theme swap. setStyle drops every source and layer; the effect above
  // rebuilds them on style.load.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const scheme = resolvedTheme(useStore.getState().theme);
      if (scheme === currentScheme.current) return;
      currentScheme.current = scheme;
      styleLoaded.current = false;
      // No diffing: a diffed swap patches the style in place and never
      // fires style.load, so nothing would rebuild the data layers.
      m.setStyle(BASEMAPS[scheme], { diff: false });
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  // Frame the data centers in view once the layers exist. Neither New York
  // State nor the two states together fit in one sensible default view, so
  // this is a fit, not a centre — and it re-fits when the region changes,
  // because "All" spans from Buffalo to Manassas and nothing is legible at
  // that zoom.
  const framed = useRef<RegionView | null>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !engine || framed.current === viewRegion) return;
    const b = dcBounds(engine, viewRegion);
    if (!b) return;
    const first = framed.current === null;
    framed.current = viewRegion;
    m.fitBounds(b, {
      padding: chromePadding(),
      duration: first ? 0 : 700,
      maxZoom: 11,
    });
  }, [engine, gen, viewRegion]);

  // Push scores into feature state rather than rebuilding the source: the
  // geometry never changes, only the colour.
  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !m.getSource("dcs")) return;
    for (const r of results) {
      m.setFeatureState(
        { source: "dcs", id: r.dc },
        { bucket: paybackBucket(r.payback_yrs), selected: r.dc === selectedDc },
      );
    }
    m.setFilter("dcs-label", selectedDc ? ["==", ["get", "id"], selectedDc] : NONE_FILTER);
  }, [results, selectedDc, gen]);

  // Hover, from either direction. While a site is hovered the others recede,
  // so the row↔marker link is unmistakable even at state zoom; maplibre's
  // default paint transition eases the change.
  const prevHover = useRef<string | null>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !m.getSource("dcs")) return;
    if (prevHover.current) m.setFeatureState({ source: "dcs", id: prevHover.current }, { hover: false });
    if (hoveredDc) m.setFeatureState({ source: "dcs", id: hoveredDc }, { hover: true });
    prevHover.current = hoveredDc;

    const keep: ExpressionSpecification = ["any", HOVERED, SELECTED];
    m.setPaintProperty("dcs-circle", "circle-opacity", ["case", keep, 1, hoveredDc ? 0.35 : 0.9]);
    m.setPaintProperty("dcs-halo", "circle-opacity", ["case", keep, 0.85, hoveredDc ? 0.3 : 0.85]);
    // The selection's rings follow the same rule when the cursor is on a
    // different site.
    const away = hoveredDc !== null && hoveredDc !== selectedDc;
    m.setPaintProperty("rings-line", "line-opacity", [
      "case", ["==", ["get", "ring"], "outer"], away ? 0.35 : 0.8, away ? 0.2 : 0.5,
    ]);
    m.setPaintProperty("rings-fill", "fill-opacity", away ? 0.02 : 0.05);
  }, [hoveredDc, selectedDc, gen]);

  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !m.getLayer("sinks-hover")) return;
    m.setFilter("sinks-hover", hoveredSink ? ["==", ["get", "id"], hoveredSink] : NONE_FILTER);
  }, [hoveredSink, gen]);

  // Fly to a site picked from the list; centre on one clicked on the map,
  // zooming in only if the view is still at state level. Clearing the
  // selection returns to the full frame.
  const prevSelected = useRef<string | null>(null);
  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !engine) return;
    const was = prevSelected.current;
    prevSelected.current = selectedDc;

    if (!selectedDc) {
      if (was) {
        const b = dcBounds(engine, useStore.getState().viewRegion);
        if (b) m.fitBounds(b, { padding: chromePadding(), duration: 900, maxZoom: 11 });
      }
      return;
    }

    const { selectionSource, results: rs } = useStore.getState();
    const center = dcPosition(engine, selectedDc);
    if (!center) return;
    const region = rs.find((r) => r.dc === selectedDc)?.region;

    // A tick later, so the panel's own reaction to the selection (the
    // sheet moving to its new snap) is known when the padding is measured.
    const siteZoom = region === "nyc" ? 13.4 : 12.2;
    const fly = setTimeout(() => {
      if (selectionSource === "list") {
        m.flyTo({
          center,
          zoom: siteZoom,
          padding: chromePadding(),
          duration: 1100,
          essential: true,
        });
      } else {
        m.easeTo({
          center,
          zoom: Math.max(m.getZoom(), Math.min(siteZoom, 12)),
          padding: chromePadding(),
          duration: 600,
          essential: true,
        });
      }
    }, 0);

    // A single soft pulse so the eye lands on the mark.
    m.setFilter("dcs-pulse", ["==", ["get", "id"], selectedDc]);
    const t0 = performance.now();
    const D = 700;
    let raf = 0;
    const tick = () => {
      if (!map.current || !map.current.getLayer("dcs-pulse")) return;
      const t = Math.min(1, (performance.now() - t0) / D);
      const ease = 1 - Math.pow(1 - t, 3);
      map.current.setPaintProperty("dcs-pulse", "circle-radius", ["+", DC_RADIUS, 4 + ease * 22]);
      map.current.setPaintProperty("dcs-pulse", "circle-stroke-opacity", (1 - ease) * 0.7);
      if (t < 1) raf = requestAnimationFrame(tick);
      else map.current.setFilter("dcs-pulse", NONE_FILTER);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      clearTimeout(fly);
      cancelAnimationFrame(raf);
    };
  }, [selectedDc, gen, engine]);

  // Draw the reach rings for the selected site: the radius itself, and the
  // straight-line distance that radius corresponds to once the detour factor
  // is applied, which is what a reader's eye actually measures.
  useEffect(() => {
    const m = map.current;
    if (!m || !gen) return;
    const src = m.getSource("rings") as { setData?: (d: unknown) => void } | undefined;
    const lbl = m.getSource("ring-label") as { setData?: (d: unknown) => void } | undefined;
    if (!src?.setData || !lbl?.setData) return;

    const site = engine && dcPosition(engine, selectedDc);
    const region = results.find((r) => r.dc === selectedDc)?.region;
    if (!site || !weights || !region) {
      src.setData(EMPTY);
      lbl.setData(EMPTY);
      return;
    }

    // The site's own region's reach, not whichever region the panel is tuning.
    const w = weights[region];
    const radiusKm = w.radius_m / 1000;
    const detour =
      w.distance.kind === "detour" ? w.distance.k : w.distance.kind === "rotated_l1" ? Math.SQRT2 : 1;
    const [lng, lat] = site;
    src.setData({
      type: "FeatureCollection",
      features: [
        circle([lng, lat], radiusKm, { steps: 96, properties: { ring: "outer" } }),
        ...(detour > 1
          ? [circle([lng, lat], radiusKm / detour, { steps: 96, properties: { ring: "inner" } })]
          : []),
      ],
    });
    // Label at the ring's north point; one degree of latitude is ~111 km.
    lbl.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { label: `${km(w.radius_m)} reach` },
          geometry: { type: "Point", coordinates: [lng, lat + radiusKm / 111] },
        },
      ],
    });
  }, [selectedDc, weights, engine, gen, results]);

  // Fade the sinks a selected site cannot reach, rather than hiding them, and
  // grow and name the ones it can. Keeping every sink on the map preserves
  // the context of what a site is passing up.
  useEffect(() => {
    const m = map.current;
    if (!m || !gen || !m.getLayer("sinks-square")) return;

    const active = selectedDc !== null && explain.length > 0;
    if (!active) {
      m.setPaintProperty("sinks-square", "icon-opacity", SINK_OPACITY);
      m.setLayoutProperty("sinks-square", "icon-size", SINK_SIZE);
      m.setFilter("sinks-label", NONE_FILTER);
      return;
    }

    const inExplain: ExpressionSpecification = [
      "in",
      ["get", "id"],
      ["literal", explain.map((c) => c.sink)],
    ];
    m.setPaintProperty("sinks-square", "icon-opacity", ["case", inExplain, 1, SINK_OPACITY_FADED]);
    m.setLayoutProperty("sinks-square", "icon-size", sinkSize(inExplain));

    // Label only the connected sinks, and only where OpenStreetMap actually
    // had a name — "Unnamed hotel" on the map is worse than no label.
    m.setFilter("sinks-label", ["all", inExplain, ["!", ["in", "Unnamed", ["get", "name"]]]]);
  }, [selectedDc, explain, gen]);

  if (mapError) {
    return (
      <div className="map-wrap map-fallback">
        <div>
          <p>
            <strong>The map could not start.</strong>
          </p>
          <p className="muted">
            It needs WebGL2, which this browser did not provide. The ranking beside this panel is
            unaffected.
          </p>
          <code className="mono">{mapError}</code>
        </div>
      </div>
    );
  }

  return <div className="map-wrap" ref={ref} />;
}
