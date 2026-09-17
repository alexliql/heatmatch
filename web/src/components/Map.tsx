"use client";

import type { ExpressionSpecification } from "maplibre-gl";
import {
  AttributionControl,
  Map as MlMap,
  NavigationControl,
  Popup,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { useStore } from "@/lib/store";
import circle from "@turf/circle";

import { isPlaceholderName } from "@/lib/features";
import { BUCKET_COLORS, SINK_COLORS, mw, num, paybackBucket, score } from "@/lib/format";
import { CAT_LABELS } from "@/lib/types";

import "maplibre-gl/dist/maplibre-gl.css";

const EMPTY = { type: "FeatureCollection", features: [] } as never;

// CARTO's minimal basemaps. The previous style (OpenFreeMap Liberty) drew a
// full topographic map — landuse, buildings, every road class — which competed
// with the data drawn on top of it. These carry coastlines, water, major roads
// and labels, and little else.
//
// Chosen once, at construction, to match the page theme. Switching the OS
// theme mid-session leaves the map as it was: swapping styles would drop every
// source and layer added below and they would all have to be rebuilt.
const BASEMAPS = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
} as const;

function prefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
}

function basemapUrl(): string {
  return prefersDark() ? BASEMAPS.dark : BASEMAPS.light;
}

const SINK_OPACITY = 0.8;
// icon-size is a multiplier on a 24 px source image.
const SINK_SIZE: ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"], 8, 0.16, 11, 0.24, 15, 0.42,
];
// Connected sinks grow so they read as picked out, not merely brighter.
const SINK_SIZE_SELECTED: ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"], 8, 0.24, 11, 0.36, 15, 0.62,
];

const CENTERS: Record<string, [number, number]> = {
  nyc: [-73.98, 40.73],
  upstate: [-75.5, 42.9],
};

// Icons are generated rather than loaded from a sprite: ten flat squares are
// cheaper to draw here than to ship, and they stay in step with SINK_COLORS.
const ICON_PX = 24;
const ICON_BORDER_PX = 3;

function squareIcon(hex: string, border: [number, number, number]): {
  width: number;
  height: number;
  data: Uint8Array;
} {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const data = new Uint8Array(ICON_PX * ICON_PX * 4);

  for (let y = 0; y < ICON_PX; y++) {
    for (let x = 0; x < ICON_PX; x++) {
      const edge =
        x < ICON_BORDER_PX ||
        y < ICON_BORDER_PX ||
        x >= ICON_PX - ICON_BORDER_PX ||
        y >= ICON_PX - ICON_BORDER_PX;
      const i = (y * ICON_PX + x) * 4;
      data[i] = edge ? border[0] : r;
      data[i + 1] = edge ? border[1] : g;
      data[i + 2] = edge ? border[2] : b;
      data[i + 3] = 255;
    }
  }
  return { width: ICON_PX, height: ICON_PX, data };
}

const iconId = (cat: string) => `sink-${cat}`;

/// Built from SINK_COLORS rather than written out, but still cast: spreading a
/// table into a `match` loses the arity the expression type requires.
const SINK_ICON = [
  "match",
  ["get", "cat"],
  ...Object.keys(SINK_COLORS).flatMap((cat) => [cat, iconId(cat)]),
  iconId("office"),
] as unknown as ExpressionSpecification;

export function Map() {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const engine = useStore((s) => s.engine);
  const results = useStore((s) => s.results);
  const explain = useStore((s) => s.explain);
  const selectedDc = useStore((s) => s.selectedDc);
  const [styleReady, setStyleReady] = useState(false);

  // Built exactly once per engine. Anything that changes as the user works —
  // results, selection — is read from the store inside the handlers rather
  // than closed over, because a dependency that changes on every recompute
  // would tear the map down and rebuild it mid-load, leaving a blank canvas.
  useEffect(() => {
    if (!ref.current || map.current || !engine) return;

    let m: MlMap;
    try {
      m = new MlMap({
      container: ref.current,
      style: basemapUrl(),
      center: CENTERS.nyc,
        zoom: 11,
        attributionControl: false,
      });
    } catch (e) {
      // maplibre needs WebGL2. Without it the map cannot render, but the
      // ranking is plain numbers and must survive: losing the whole page
      // because of the basemap would be a poor trade.
      setMapError(e instanceof Error ? e.message : String(e));
      return;
    }
    m.on("error", (e) => setMapError(e.error?.message ?? "map failed to load"));
    m.addControl(new AttributionControl({ compact: true }));
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");

    const dark = prefersDark();

    m.on("load", () => {
      m.addSource("sinks", { type: "geojson", data: engine.geo.sinks as never });
      m.addSource("dcs", { type: "geojson", data: engine.geo.datacenters as never, promoteId: "id" });
      if (engine.geo.water) {
        m.addSource("water", { type: "geojson", data: engine.geo.water as never });
        m.addLayer({
          id: "water-fill",
          type: "fill",
          source: "water",
          paint: { "fill-color": "#4a90d9", "fill-opacity": 0.35 },
        });
      }

      if (engine.geo.zones) {
        m.addSource("zones", { type: "geojson", data: engine.geo.zones as never });
        m.addLayer({
          id: "zones-line",
          type: "line",
          source: "zones",
          paint: {
            "line-color": ["match", ["get", "kind"], "steam", "#d98b4a", "#4ad9a0"],
            // An outline, not a fill. A tinted polygon over lower Manhattan
            // washed the whole area and read as a filter applied to the data,
            // which is exactly the wrong impression: the boundary is
            // hand-drawn and approximate, so it should mark an edge rather
            // than colour everything inside it.
            "line-width": 1,
            "line-opacity": 0.55,
            "line-dasharray": [3, 3],
          },
        });
      }

      // Reach rings for the selected site, populated on selection.
      m.addSource("rings", { type: "geojson", data: EMPTY });
      m.addLayer({
        id: "rings-line",
        type: "line",
        source: "rings",
        paint: {
          "line-color": "#666",
          "line-width": 1.2,
          "line-dasharray": [2, 2],
        },
      });

      // Squares, so sinks never read as small data centers. Shape carries the
      // distinction between the two populations; colour is free to carry
      // category instead.
      const border: [number, number, number] = dark ? [24, 26, 30] : [255, 255, 255];
      for (const [cat, hex] of Object.entries(SINK_COLORS)) {
        if (!m.hasImage(iconId(cat))) m.addImage(iconId(cat), squareIcon(hex, border));
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
      });

      // Names for the sinks a selected site could actually reach. Filtered to
      // nothing until a selection exists, so the map stays quiet by default.
      m.addLayer({
        id: "sinks-label",
        type: "symbol",
        source: "sinks",
        filter: ["==", ["get", "id"], "__none__"],
        layout: {
          "text-field": ["get", "name"],
          "text-size": 11,
          "text-offset": [0, 1.1],
          "text-anchor": "top",
          "text-max-width": 12,
          "text-optional": true,
        },
        paint: {
          "text-color": dark ? "#e8eaed" : "#1f2023",
          "text-halo-color": dark ? "#16181c" : "#ffffff",
          "text-halo-width": 1.4,
        },
      });

      m.addLayer({
        id: "dcs-circle",
        type: "circle",
        source: "dcs",
        paint: {
          // Scaled by capacity, coloured by how fast the scheme pays back.
          "circle-radius": [
            "interpolate", ["linear"], ["get", "mw"], 0, 5, 5, 10, 20, 18,
          ],
          "circle-color": [
            "match",
            ["feature-state", "bucket"],
            "fast", BUCKET_COLORS.fast,
            "medium", BUCKET_COLORS.medium,
            "slow", BUCKET_COLORS.slow,
            BUCKET_COLORS.none,
          ],
          "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 3, 1],
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.9,
        },
      });

      const popup = new Popup({ closeButton: false, closeOnClick: false });
      m.on("mouseenter", "dcs-circle", (e: MapLayerMouseEvent) => {
        m.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as { id: string; name: string; mw: number };
        const match = useStore.getState().results.find((r) => r.dc === p.id);
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${p.name}</strong><br/>${mw(Number(p.mw))}` +
              (match ? `<br/>score ${score(match.score)}` : ""),
          )
          .addTo(m);
      });
      m.on("mouseleave", "dcs-circle", () => {
        m.getCanvas().style.cursor = "";
        popup.remove();
      });
      m.on("mouseenter", "sinks-square", (e: MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as { name: string; cat: string; demand_kwh: number };
        const label = CAT_LABELS[p.cat as keyof typeof CAT_LABELS] ?? p.cat;
        // 30% of sinks have no name in OpenStreetMap; the category is the
        // honest fallback rather than an empty tooltip.
        const title = isPlaceholderName(p.name) ? label : p.name;
        const sub = isPlaceholderName(p.name) ? "" : `<br/><span>${label}</span>`;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${title}</strong>${sub}<br/>${num(Number(p.demand_kwh) / 1000)} MWh/yr`,
          )
          .addTo(m);
      });
      m.on("mouseleave", "sinks-square", () => popup.remove());

      m.on("click", "dcs-circle", (e: MapLayerMouseEvent) => {
        const id = (e.features?.[0]?.properties as { id?: string })?.id;
        if (!id) return;
        const store = useStore.getState();
        store.select(id === store.selectedDc ? null : id);
      });

      map.current = m;
      // Layers exist now, so the effects that paint scores and rings can run.
      setStyleReady(true);
    });

    return () => {
      m.remove();
      map.current = null;
    };
  }, [engine]);

  // Push scores into feature state rather than rebuilding the source: the
  // geometry never changes, only the colour.
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady) return;
    for (const r of results) {
      m.setFeatureState(
        { source: "dcs", id: r.dc },
        { bucket: paybackBucket(r.payback_yrs), selected: r.dc === selectedDc },
      );
    }
  }, [results, selectedDc, styleReady]);

  // Draw the reach rings for the selected site: the radius itself, and the
  // straight-line distance that radius corresponds to once the detour factor
  // is applied, which is what a reader's eye actually measures.
  const weights = useStore((s) => s.weights);
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady) return;
    const src = m.getSource("rings") as { setData?: (d: unknown) => void } | undefined;
    if (!src?.setData) return;

    const fc = engine?.geo.datacenters as
      | { features: { properties: { id: string }; geometry: { coordinates: [number, number] } }[] }
      | undefined;
    const site = fc?.features.find((f) => f.properties.id === selectedDc);
    const region = results.find((m) => m.dc === selectedDc)?.region;
    if (!site || !weights || !region) return void src.setData(EMPTY);

    // The site's own region's reach, not whichever region the panel is tuning.
    const w = weights[region];
    const radiusKm = w.radius_m / 1000;
    const detour =
      w.distance.kind === "detour"
        ? w.distance.k
        : w.distance.kind === "rotated_l1"
          ? Math.SQRT2
          : 1;
    src.setData({
      type: "FeatureCollection",
      features: [
        circle(site.geometry.coordinates, radiusKm, { steps: 64 }),
        circle(site.geometry.coordinates, radiusKm / detour, { steps: 64 }),
      ],
    });
  }, [selectedDc, weights, engine, styleReady, results]);

  // Fade the sinks a selected site cannot reach, rather than hiding them, and
  // name the ones it can.
  //
  // Filtering them out was the first attempt and it read badly: the
  // surroundings vanished, so there was no way to see what a site was passing
  // up. Keeping every sink on the map, with the unreachable ones dropped to a
  // low opacity, preserves that context while the relevant ones still stand
  // out. Colour stays the category colour — the fade does the work, so the
  // muted squares remain identifiable rather than turning into grey dots.
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady || !m.getLayer("sinks-square")) return;

    const active = selectedDc !== null && explain.length > 0;
    if (!active) {
      m.setPaintProperty("sinks-square", "icon-opacity", SINK_OPACITY);
      m.setLayoutProperty("sinks-square", "icon-size", SINK_SIZE);
      m.setFilter("sinks-label", ["==", ["get", "id"], "__none__"]);
      return;
    }

    const inExplain: ExpressionSpecification = [
      "in",
      ["get", "id"],
      ["literal", explain.map((c) => c.sink)],
    ];
    m.setPaintProperty("sinks-square", "icon-opacity", ["case", inExplain, 0.95, 0.28]);
    m.setLayoutProperty("sinks-square", "icon-size", [
      "case", inExplain, SINK_SIZE_SELECTED, SINK_SIZE,
    ]);

    // Label only the connected sinks, and only where OpenStreetMap actually
    // had a name — "Unnamed hotel" on the map is worse than no label.
    m.setFilter("sinks-label", [
      "all",
      inExplain,
      ["!", ["in", "Unnamed", ["get", "name"]]],
    ]);
  }, [selectedDc, explain, styleReady]);

  // Frame the selected site and everything it could reach.
  //
  // Without this the map stays at the statewide view where a single site is a
  // few pixels across, and the labels, rings and fade are all invisible —
  // selecting a site would change the panel and appear to do nothing to the
  // map.
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady || !selectedDc || !engine) return;

    const dcFc = engine.geo.datacenters as
      | { features: { properties: { id: string }; geometry: { coordinates: [number, number] } }[] }
      | undefined;
    const site = dcFc?.features.find((f) => f.properties.id === selectedDc);
    if (!site) return;

    const sinkFc = engine.geo.sinks as
      | { features: { properties: { id: string }; geometry: { coordinates: [number, number] } }[] }
      | undefined;
    const reachable = new Set(explain.map((c) => c.sink));
    const points = [
      site.geometry.coordinates,
      ...(sinkFc?.features ?? [])
        .filter((f) => reachable.has(f.properties.id))
        .map((f) => f.geometry.coordinates),
    ];

    const lons = points.map((c) => c[0]);
    const lats = points.map((c) => c[1]);
    m.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 80, maxZoom: 15, duration: 600 },
    );
  }, [selectedDc, explain, engine, styleReady]);

  // Frame every data center once, rather than centring on a region: the two
  // are shown together, and New York State does not fit in one sensible
  // default view.
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady || !engine) return;
    const fc = engine.geo.datacenters as
      | { features: { geometry: { coordinates: [number, number] } }[] }
      | undefined;
    const coords = fc?.features.map((f) => f.geometry.coordinates) ?? [];
    if (coords.length === 0) return;

    const lons = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    m.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 60, duration: 0, maxZoom: 11 },
    );
  }, [engine, styleReady]);

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
          <code>{mapError}</code>
        </div>
      </div>
    );
  }

  return <div className="map-wrap" ref={ref} />;
}
