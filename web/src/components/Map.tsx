"use client";

import type * as maplibregl from "maplibre-gl";
import {
  AttributionControl,
  Map as MlMap,
  NavigationControl,
  Popup,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { useStore } from "@/lib/store";
import { BUCKET_COLORS, mw, paybackBucket, score } from "@/lib/format";

import "maplibre-gl/dist/maplibre-gl.css";

const CENTERS: Record<string, [number, number]> = {
  nyc: [-73.98, 40.73],
  upstate: [-75.5, 42.9],
};

/// Written out rather than spread from a table: maplibre's `match` expression
/// is typed by arity, so a spread loses the shape it needs.
const SINK_COLOR = [
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
] as unknown as maplibregl.ExpressionSpecification;

export function Map() {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const engine = useStore((s) => s.engine);
  const region = useStore((s) => s.region);
  const results = useStore((s) => s.results);
  const explain = useStore((s) => s.explain);
  const selectedDc = useStore((s) => s.selectedDc);
  const select = useStore((s) => s.select);

  // Create the map once the data is in hand, so sources can be added with the
  // style rather than patched in afterwards.
  useEffect(() => {
    if (!ref.current || map.current || !engine) return;

    let m: MlMap;
    try {
      m = new MlMap({
      container: ref.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: CENTERS[region] ?? CENTERS.nyc,
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
          paint: { "fill-color": "#4a90d9", "fill-opacity": 0.25 },
        });
      }

      m.addLayer({
        id: "sinks-circle",
        type: "circle",
        source: "sinks",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 15, 5],
          "circle-color": SINK_COLOR,
          "circle-opacity": 0.75,
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
        const match = results.find((r) => r.dc === p.id);
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
        if (id) select(id === useStore.getState().selectedDc ? null : id);
      });

      map.current = m;
      // Trigger the first paint of scores now that layers exist.
      useStore.setState((s) => ({ ...s }));
    });

    return () => {
      m.remove();
      map.current = null;
    };
  }, [engine, region, results, select]);

  // Push scores into feature state rather than rebuilding the source: the
  // geometry never changes, only the colour.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.isStyleLoaded()) return;
    for (const r of results) {
      m.setFeatureState(
        { source: "dcs", id: r.dc },
        { bucket: paybackBucket(r.payback_yrs), selected: r.dc === selectedDc },
      );
    }
  }, [results, selectedDc]);

  // Dim sinks that are not part of the selected site's explanation.
  useEffect(() => {
    const m = map.current;
    if (!m || !m.getLayer("sinks-circle")) return;
    if (!selectedDc || explain.length === 0) {
      m.setFilter("sinks-circle", null);
      return;
    }
    m.setFilter("sinks-circle", [
      "in",
      ["get", "id"],
      ["literal", explain.map((c) => c.sink)],
    ]);
  }, [selectedDc, explain]);

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
