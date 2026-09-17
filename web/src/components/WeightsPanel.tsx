"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { diffFromDefaults, modified, roundTo } from "@/lib/defaults";
import { km } from "@/lib/format";
import { sweep, type Param, type Sweep } from "@/lib/sensitivity";
import { useStore } from "@/lib/store";
import {
  CAT_LABELS,
  REGIONS,
  SINK_CATS,
  type CatWeights,
  type Econ,
  type Region,
  type Weights,
} from "@/lib/types";

const REGION_LABELS: Record<Region, string> = { nyc: "New York City", upstate: "Upstate" };

/** Marks over a slider's track where the selected site's rank would change.
 *  Accent when the move is up the ranking, ember when down. */
function SensMarks({ sweep: sw, min, max }: { sweep: Sweep; min: number; max: number }) {
  if (sw.breaks.length === 0) return null;
  return (
    <span className="sens" aria-hidden>
      {sw.breaks.map((b) => {
        const v = sw.values[b.at];
        const x = ((v - min) / (max - min)) * 100;
        return (
          <i
            key={b.at}
            data-dir={b.to < b.from ? "up" : "down"}
            style={{ left: `${x}%` }}
            title={`→ #${b.to} from about ${v.toPrecision(3)}`}
          />
        );
      })}
    </span>
  );
}

function Slider({
  label,
  value,
  defaultValue,
  min,
  max,
  step,
  format,
  sweep: sw,
  onChange,
}: {
  label: string;
  value: number;
  defaultValue: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  sweep?: Sweep | null;
  onChange: (v: number) => void;
}) {
  const decimals = Math.max(0, Math.ceil(-Math.log10(step)));
  const show = format ?? ((v: number) => v.toFixed(decimals));
  // The nearest rank change ahead of the current value, for the tooltip.
  const nextBreak = sw?.breaks.find((b) => sw.values[b.at] > value);
  const hint = nextBreak
    ? `→ #${nextBreak.to} at ${show(sw!.values[nextBreak.at])}`
    : sw
      ? `Stays #${sw.ranks[0]} across the range`
      : undefined;
  return (
    <label className="ctl" data-modified={modified(value, defaultValue, step)}>
      <span className="ctl-label" title={`Default ${show(defaultValue)}`}>{label}</span>
      <span className="ctl-track" title={hint}>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={roundTo(value, step)}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        {sw && <SensMarks sweep={sw} min={min} max={max} />}
      </span>
      <span className="ctl-value">{show(value)}</span>
    </label>
  );
}

function Select({
  label,
  value,
  isModified,
  onChange,
  children,
}: {
  label: string;
  value: string;
  isModified: boolean;
  onChange: (v: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="ctl" data-modified={isModified}>
      <span className="ctl-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  );
}

function Group({
  title,
  open,
  onReset,
  children,
}: {
  title: string;
  open?: boolean;
  onReset?: () => void;
  children: ReactNode;
}) {
  return (
    <details className="group" open={open}>
      <summary>
        <span className="label">{title}</span>
        {onReset && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={(e) => {
              e.preventDefault();
              onReset();
            }}
          >
            Reset
          </button>
        )}
      </summary>
      <div className="group-body">{children}</div>
    </details>
  );
}

const ECON_FIELDS: { key: keyof Econ; label: string; unit: string; step: number }[] = [
  { key: "pipe_cost_per_m", label: "Pipe", unit: "$/m", step: 10 },
  { key: "hp_capex_per_mw_th", label: "Heat pump", unit: "$/MW", step: 1000 },
  { key: "gas_price_per_mwh_th", label: "Gas", unit: "$/MWh", step: 1 },
  { key: "elec_price_per_mwh", label: "Electricity", unit: "$/MWh", step: 1 },
  { key: "boiler_eff", label: "Boiler efficiency", unit: "", step: 0.01 },
  { key: "dc_avoided_cooling_per_mwh", label: "Avoided cooling", unit: "$/MWh", step: 1 },
];

export function WeightsPanel() {
  const engine = useStore((s) => s.engine);
  const tuningRegion = useStore((s) => s.tuningRegion);
  const setTuningRegion = useStore((s) => s.setTuningRegion);
  const weights = useStore((s) => (s.weights ? s.weights[s.tuningRegion] : null));
  const econ = useStore((s) => (s.econ ? s.econ[s.tuningRegion] : null));
  const setWeights = useStore((s) => s.setWeights);
  const setEcon = useStore((s) => s.setEcon);
  const resetRegion = useStore((s) => s.resetRegion);
  const allWeights = useStore((s) => s.weights);
  const allEcon = useStore((s) => s.econ);
  const selectedDc = useStore((s) => s.selectedDc);
  const results = useStore((s) => s.results);
  const [paste, setPaste] = useState<string | null>(null);
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"link" | "json" | null>(null);

  // Sensitivity: only for a selected site in the region being tuned, and a
  // beat behind the sliders so a drag stays smooth.
  const selectedRegion = results.find((m) => m.dc === selectedDc)?.region;
  const sensFor = selectedDc && selectedRegion === tuningRegion ? selectedDc : null;
  const [sensInputs, setSensInputs] = useState<{ w: typeof allWeights; e: typeof allEcon } | null>(null);
  useEffect(() => {
    if (!sensFor) return void setSensInputs(null);
    const t = setTimeout(() => setSensInputs({ w: allWeights, e: allEcon }), 150);
    return () => clearTimeout(t);
  }, [sensFor, allWeights, allEcon]);
  const sens = useMemo(() => {
    if (!engine || !sensFor || !sensInputs?.w || !sensInputs.e) return null;
    const { w, e } = sensInputs;
    const run = (param: Param, min: number, max: number) =>
      sweep(engine, w, e, tuningRegion, sensFor, param, min, max);
    const out = new Map<Param, Sweep>();
    for (const cat of SINK_CATS) out.set(`cat.${cat}`, run(`cat.${cat}`, 0, 2));
    out.set("radius_m", run("radius_m", 200, 8000));
    out.set("per_sink_cap", run("per_sink_cap", 0.05, 1));
    out.set("steam_bonus", run("steam_bonus", 0, 2));
    out.set("uten_bonus", run("uten_bonus", 0, 2));
    out.set("distance.k", run("distance.k", 1, 2));
    out.set("distance.theta_deg", run("distance.theta_deg", 0, 90));
    return out;
  }, [engine, sensFor, sensInputs, tuningRegion]);
  const sw = (p: Param) => sens?.get(p) ?? null;

  const diff = engine && allWeights && allEcon ? diffFromDefaults(engine, allWeights, allEcon) : null;

  if (!engine || !weights || !econ) return null;

  const dw = engine.defaultWeights(tuningRegion);
  const de = engine.defaultEcon(tuningRegion);

  const setCat = (cat: keyof CatWeights, v: number) =>
    setWeights({ cat: { ...weights.cat, [cat]: v } });

  const copy = (what: "link" | "json") => {
    const text =
      what === "link" ? window.location.href : JSON.stringify({ weights, econ }, null, 2);
    void navigator.clipboard?.writeText(text);
    setCopied(what);
    setTimeout(() => setCopied(null), 1500);
  };

  const applyPaste = () => {
    try {
      const parsed = JSON.parse(paste ?? "");
      if (!parsed.weights || !parsed.econ) throw new Error("expected { weights, econ }");
      // Let the engine validate: it owns the rules, and a round-trip through
      // rank is the only honest check that the values are usable.
      setWeights(parsed.weights as Weights);
      setEcon(parsed.econ);
      setPaste(null);
      setPasteError(null);
    } catch (e) {
      setPasteError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <>
      <section className="section">
        <div className="seg seg-full" role="tablist" aria-label="Region to tune">
          {REGIONS.map((r) => (
            <button key={r} role="tab" data-active={tuningRegion === r} aria-selected={tuningRegion === r} onClick={() => setTuningRegion(r)}>
              {REGION_LABELS[r]}
              {diff && diff.byRegion[r] > 0 && (
                <span className="tab-badge" title={`${diff.byRegion[r]} changed from default`}>
                  {diff.byRegion[r]}
                </span>
              )}
            </button>
          ))}
        </div>
        <p className="group-note" style={{ marginTop: 10, marginBottom: 0 }}>
          Both regions are ranked together but tuned apart: a pipe costs far more in the city and the
          default reach differs fourfold. One set of numbers across both would make one of them
          meaningless.
        </p>
        <p className="group-note sens-note" style={{ marginBottom: 0 }}>
          {sensFor ? (
            <>
              <i className="sens-key" data-dir="up" /> <i className="sens-key" data-dir="down" /> marks
              on a slider show where the selected site would move up or down the ranking.
            </>
          ) : (
            <>Select a {REGION_LABELS[tuningRegion]} site to see how each slider would move it.</>
          )}
        </p>
      </section>

      <Group
        title="Sink priorities"
        open
        onReset={() => setWeights({ cat: dw.cat })}
      >
        {SINK_CATS.map((cat) => (
          <Slider
            key={cat}
            label={CAT_LABELS[cat]}
            value={weights.cat[cat]}
            defaultValue={dw.cat[cat]}
            min={0}
            max={2}
            step={0.1}
            sweep={sw(`cat.${cat}`)}
            onChange={(v) => setCat(cat, v)}
          />
        ))}
      </Group>

      <Group
        title="Reach"
        onReset={() =>
          setWeights({
            radius_m: dw.radius_m,
            distance: dw.distance,
            decay: dw.decay,
            water_crossing: dw.water_crossing,
          })
        }
      >
        <Slider
          label="Radius"
          value={weights.radius_m}
          defaultValue={dw.radius_m}
          min={200}
          max={8000}
          step={100}
          format={km}
          sweep={sw("radius_m")}
          onChange={(v) => setWeights({ radius_m: v })}
        />
        <Select
          label="Distance model"
          value={weights.distance.kind}
          isModified={weights.distance.kind !== dw.distance.kind}
          onChange={(kind) =>
            setWeights({
              distance:
                kind === "euclid"
                  ? { kind: "euclid" }
                  : kind === "detour"
                    ? { kind: "detour", k: 1.3 }
                    : { kind: "rotated_l1", theta_deg: 29 },
            })
          }
        >
          <option value="euclid">Straight line</option>
          <option value="detour">Detour factor</option>
          <option value="rotated_l1">Street grid</option>
        </Select>
        {weights.distance.kind === "detour" && (
          <Slider
            label="Detour ×"
            value={weights.distance.k}
            defaultValue={dw.distance.kind === "detour" ? dw.distance.k : 1.3}
            min={1}
            max={2}
            step={0.05}
            sweep={sw("distance.k")}
            onChange={(k) => setWeights({ distance: { kind: "detour", k } })}
          />
        )}
        {weights.distance.kind === "rotated_l1" && (
          <Slider
            label="Grid angle °"
            value={weights.distance.theta_deg}
            defaultValue={dw.distance.kind === "rotated_l1" ? dw.distance.theta_deg : 29}
            min={0}
            max={90}
            step={1}
            sweep={sw("distance.theta_deg")}
            onChange={(theta_deg) => setWeights({ distance: { kind: "rotated_l1", theta_deg } })}
          />
        )}
        <Select
          label="Decay"
          value={weights.decay.kind}
          isModified={weights.decay.kind !== dw.decay.kind}
          onChange={(v) => setWeights({ decay: v === "linear" ? { kind: "linear" } : { kind: "exp", k: 2 } })}
        >
          <option value="linear">Linear</option>
          <option value="exp">Exponential</option>
        </Select>
        <Select
          label="Across water"
          value={weights.water_crossing.kind}
          isModified={weights.water_crossing.kind !== dw.water_crossing.kind}
          onChange={(v) =>
            setWeights({
              water_crossing: v === "exclude" ? { kind: "exclude" } : { kind: "penalty", factor: 2 },
            })
          }
        >
          <option value="penalty">Penalise</option>
          <option value="exclude">Exclude</option>
        </Select>
      </Group>

      <Group
        title="Model"
        onReset={() =>
          setWeights({
            per_sink_cap: dw.per_sink_cap,
            steam_bonus: dw.steam_bonus,
            uten_bonus: dw.uten_bonus,
          })
        }
      >
        <Slider
          label="Max share per sink"
          value={weights.per_sink_cap}
          defaultValue={dw.per_sink_cap}
          min={0.05}
          max={1}
          step={0.05}
          sweep={sw("per_sink_cap")}
          onChange={(v) => setWeights({ per_sink_cap: v })}
        />
        <Slider
          label="Steam bonus"
          value={weights.steam_bonus}
          defaultValue={dw.steam_bonus}
          min={0}
          max={2}
          step={0.1}
          sweep={sw("steam_bonus")}
          onChange={(v) => setWeights({ steam_bonus: v })}
        />
        <Slider
          label="Network bonus"
          value={weights.uten_bonus}
          defaultValue={dw.uten_bonus}
          min={0}
          max={2}
          step={0.1}
          sweep={sw("uten_bonus")}
          onChange={(v) => setWeights({ uten_bonus: v })}
        />
      </Group>

      <Group title="Economics" onReset={() => setEcon(de)}>
        {ECON_FIELDS.map(({ key, label, unit, step }) => (
          <label className="ctl" key={key} data-modified={modified(econ[key], de[key], step)}>
            <span className="ctl-label" title={`Default ${de[key]}`}>{label}</span>
            <span className="input-unit" style={{ gridColumn: "2 / 4" }}>
              <input
                type="number"
                className="input"
                value={Number(econ[key].toPrecision(6))}
                step={step}
                onChange={(e) => setEcon({ [key]: Number(e.target.value) })}
              />
              {unit && <span>{unit}</span>}
            </span>
          </label>
        ))}
      </Group>

      <section className="section" style={{ borderTop: "1px solid var(--line)" }}>
        <div className="actions">
          <button className="btn" onClick={() => copy("link")} disabled={!diff || diff.count === 0}>
            {copied === "link" ? "Link copied" : "Copy link"}
          </button>
          <button className="btn btn-ghost" onClick={() => resetRegion(tuningRegion)}>
            Reset {REGION_LABELS[tuningRegion]}
          </button>
        </div>
        <p className="group-note" style={{ marginTop: 8, marginBottom: 0 }}>
          {diff && diff.count > 0
            ? "The link carries every assumption you have changed."
            : "Change an assumption and the link will carry it."}
        </p>
        <details className="advanced">
          <summary className="faint">Advanced</summary>
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => copy("json")}>
              {copied === "json" ? "Copied" : "Copy JSON"}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setPaste(paste === null ? "" : null)}>
              {paste === null ? "Paste JSON" : "Cancel"}
            </button>
          </div>
          {paste !== null && (
            <>
              <textarea
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
                placeholder='{ "weights": …, "econ": … }'
                rows={5}
              />
              <div className="actions" style={{ marginTop: 8 }}>
                <button className="btn btn-sm" onClick={applyPaste}>
                  Apply
                </button>
                {pasteError && <span className="muted mono">{pasteError}</span>}
              </div>
            </>
          )}
        </details>
      </section>
    </>
  );
}
