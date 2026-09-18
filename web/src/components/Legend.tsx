"use client";

import { useEffect, useState } from "react";

import { useSelectedMatch, useStore } from "@/lib/store";
import { BUCKET_LABELS, SINK_VARS, cssVar, km } from "@/lib/format";
import { CAT_LABELS, SINK_CATS, ZONE_LABELS } from "@/lib/types";

import { ChevronIcon } from "./icons";

const KEY = "heatmatch:legend";

/** On the map, bottom-left. Reference material, so it can be folded away,
 *  and it only explains category colours and rings once a site is selected
 *  and they are actually on screen. */
export function Legend() {
  const [open, setOpen] = useState(true);
  const selectedDc = useStore((s) => s.selectedDc);
  const weights = useStore((s) => s.weights);
  const region = useSelectedMatch()?.region;
  const hasZones = useStore((s) => Boolean(s.engine?.geo.zones));
  const viewRegion = useStore((s) => s.viewRegion);
  // Which territory is on screen. In the "All" view every drawn zone is, so
  // the generic label is the honest one.
  const zoneLabel =
    viewRegion === "all" ? "District heating territory" : ZONE_LABELS[viewRegion];
  // True once any site carries a stated capacity, which is what makes the
  // solid-versus-outline distinction on the map mean anything.
  const hasEstimates = useStore(
    (s) => new Set(s.engine?.geo.datacenters.features.map((f) => f.properties.mw_confidence)).size > 1,
  );

  // Open by default where there is room; folded on a phone, where it would
  // cover most of the map above the sheet.
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(KEY);
    } catch {
      /* ignore */
    }
    if (stored === "closed") setOpen(false);
    else if (stored === null && window.matchMedia("(max-width: 900px)").matches) setOpen(false);
  }, []);

  const toggle = () => {
    setOpen((o) => {
      try {
        localStorage.setItem(KEY, o ? "closed" : "open");
      } catch {
        /* ignore */
      }
      return !o;
    });
  };

  const reach = region && weights ? weights[region].radius_m : null;

  return (
    <aside className="legend float" data-open={open}>
      <button onClick={toggle} aria-expanded={open}>
        <span className="label">Legend</span>
        <ChevronIcon open={open} />
      </button>
      {open && (
        <div className="legend-body">
          <div>
            <div className="legend-row" style={{ marginBottom: 6 }}>
              <i className="dot" style={{ background: "var(--heat-medium)" }} />
              <span>Data centers — sized by capacity, coloured by payback</span>
            </div>
            <div className="legend-ramp" />
            <div className="legend-ticks">
              <span>{BUCKET_LABELS.fast}</span>
              <span>{BUCKET_LABELS.medium}</span>
              <span>{BUCKET_LABELS.slow}</span>
            </div>
            <div className="legend-row" style={{ marginTop: 6 }}>
              <i className="dot" style={{ background: "var(--heat-none)" }} />
              <span>{BUCKET_LABELS.none}</span>
            </div>
          </div>

          {/* Only worth the space where capacities actually differ in how well
              they are known — in New York every figure is a footprint guess. */}
          {hasEstimates && (
            <div>
              <div className="legend-row">
                <i className="dot" style={{ background: "var(--heat-medium)" }} />
                <span>Capacity stated by the operator or a filing</span>
              </div>
              <div className="legend-row">
                <i
                  className="dot"
                  style={{
                    background: "transparent",
                    boxShadow: "inset 0 0 0 1.5px var(--heat-medium)",
                  }}
                />
                <span>Capacity estimated from the building</span>
              </div>
            </div>
          )}

          <div className="legend-row">
            <i className="sq" style={{ background: "var(--sink)" }} />
            <span>Heat sinks</span>
          </div>

          {hasZones && zoneLabel && (
            <div className="legend-row">
              <i className="zone" />
              <span>{zoneLabel}</span>
            </div>
          )}

          {selectedDc && (
            <>
              <div className="legend-sep" />
              <div className="legend-row">
                <i className="ring" />
                <span>{reach ? `${km(reach)} reach` : "Reach"} · inner ring is the straight-line equivalent</span>
              </div>
              <div className="legend-cats">
                {SINK_CATS.map((cat) => (
                  <div className="legend-row" key={cat}>
                    <i className="sq" style={{ background: cssVar(SINK_VARS[cat]) }} />
                    <span>{CAT_LABELS[cat]}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
