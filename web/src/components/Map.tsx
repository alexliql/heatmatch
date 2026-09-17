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

import { BUCKET_COLORS, mw, paybackBucket, score } from "@/lib/format";

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

function basemapUrl(): string {
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
  return dark ? BASEMAPS.dark : BASEMAPS.light;
}

const SINK_OPACITY = 0.75;
const SINK_RADIUS: ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"], 10, 2, 15, 5,
];
// Connected sinks grow slightly so they read as picked out, not just brighter.
const SINK_RADIUS_SELECTED: ExpressionSpecification = [
  "interpolate", ["linear"], ["zoom"], 10, 3.5, 15, 7,
];

const CENTERS: Record<string, [number, number]> = {
  nyc: [-73.98, 40.73],
  upstate: [-75.5, 42.9],
};

/// Written out rather than spread from a table: maplibre's `match` expression
/// is typed by arity, so a spread loses the shape it needs.
const SINK_COLOR: ExpressionSpecification = [
  "match",
  ["get", "cat"],
  "pool", "#00acc1",
  "wwtp", "#8d6e63",
  "greenhouse", "#43a047",
  "hospital", "#e53935",
  "hotel", "#8e24aa",
  "residential_multifamily", "#3949ab",
  "university", "#00897b",
  "brewery", "#fb8c00",
  "school", "#c0ca33",
  "office", "#757575",
  "#9e9e9e",
] as unknown as ExpressionSpecification;

export function Map() {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const engine = useStore((s) => s.engine);
  const region = useStore((s) => s.region);
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
      center: CENTERS[useStore.getState().region] ?? CENTERS.nyc,
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
          id: "zones-fill",
          type: "fill",
          source: "zones",
          paint: {
            "fill-color": ["match", ["get", "kind"], "steam", "#d98b4a", "#4ad9a0"],
            // Kept faint: these are approximations, and should read as context
            // rather than as surveyed boundaries.
            "fill-opacity": 0.18,
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

      m.addLayer({
        id: "sinks-circle",
        type: "circle",
        source: "sinks",
        paint: {
          "circle-radius": SINK_RADIUS,
          "circle-color": SINK_COLOR,
          "circle-opacity": SINK_OPACITY,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 0,
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
    if (!site || !weights) return void src.setData(EMPTY);

    const radiusKm = weights.radius_m / 1000;
    const detour =
      weights.distance.kind === "detour"
        ? weights.distance.k
        : weights.distance.kind === "rotated_l1"
          ? Math.SQRT2
          : 1;
    src.setData({
      type: "FeatureCollection",
      features: [
        circle(site.geometry.coordinates, radiusKm, { steps: 64 }),
        circle(site.geometry.coordinates, radiusKm / detour, { steps: 64 }),
      ],
    });
  }, [selectedDc, weights, engine, styleReady]);

  // Fade the sinks a selected site cannot reach, rather than hiding them.
  //
  // Filtering them out was the first attempt and it read badly: the
  // surroundings vanished, so there was no way to see what a site was passing
  // up. Keeping every sink on the map, with the unreachable ones dropped to a
  // low opacity, preserves that context while the relevant ones still stand
  // out. Colour stays the category colour — the fade does the work, so the
  // muted points remain identifiable rather than turning into grey dots.
  useEffect(() => {
    const m = map.current;
    if (!m || !styleReady || !m.getLayer("sinks-circle")) return;

    const active = selectedDc !== null && explain.length > 0;
    if (!active) {
      m.setPaintProperty("sinks-circle", "circle-opacity", SINK_OPACITY);
      m.setPaintProperty("sinks-circle", "circle-radius", SINK_RADIUS);
      m.setPaintProperty("sinks-circle", "circle-stroke-opacity", 0);
      return;
    }

    const inExplain: ExpressionSpecification = [
      "in",
      ["get", "id"],
      ["literal", explain.map((c) => c.sink)],
    ];
    m.setPaintProperty("sinks-circle", "circle-opacity", [
      "case", inExplain, 0.95, 0.28,
    ]);
    m.setPaintProperty("sinks-circle", "circle-radius", [
      "case", inExplain, SINK_RADIUS_SELECTED, SINK_RADIUS,
    ]);
    // A thin halo lifts the connected sinks off a busy basemap.
    m.setPaintProperty("sinks-circle", "circle-stroke-opacity", [
      "case", inExplain, 0.9, 0,
    ]);
  }, [selectedDc, explain, styleReady]);

  // Recentre when the region changes.
  useEffect(() => {
    map.current?.flyTo({ center: CENTERS[region] ?? CENTERS.nyc, zoom: region === "nyc" ? 11 : 7 });
  }, [region]);

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
