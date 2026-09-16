"use client";

import { useState } from "react";

import { useStore } from "@/lib/store";
import { CAT_LABELS, SINK_CATS, type CatWeights, type Weights } from "@/lib/types";

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  // Values come back from the engine as f32 widened to f64, so a stored 0.9
  // reads as 0.8999999761581421. Round to the slider's own precision for
  // display; the underlying value is left alone.
  const decimals = Math.max(0, Math.ceil(-Math.log10(step)));
  return (
    <label className="slider">
      <span>{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="num">{value.toFixed(decimals)}</span>
    </label>
  );
}

export function WeightsPanel() {
  const weights = useStore((s) => s.weights);
  const econ = useStore((s) => s.econ);
  const setWeights = useStore((s) => s.setWeights);
  const setEcon = useStore((s) => s.setEcon);
  const resetDefaults = useStore((s) => s.resetDefaults);
  const [paste, setPaste] = useState<string | null>(null);
  const [pasteError, setPasteError] = useState<string | null>(null);

  if (!weights || !econ) return null;

  const setCat = (cat: keyof CatWeights, v: number) =>
    setWeights({ cat: { ...weights.cat, [cat]: v } });

  const copy = () =>
    void navigator.clipboard?.writeText(JSON.stringify({ weights, econ }, null, 2));

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
        <h2>Sink priorities</h2>
        {SINK_CATS.map((cat) => (
          <Slider
            key={cat}
            label={CAT_LABELS[cat]}
            value={weights.cat[cat]}
            min={0}
            max={2}
            step={0.1}
            onChange={(v) => setCat(cat, v)}
          />
        ))}
      </section>

      <section className="section">
        <h2>Reach</h2>
        <Slider
          label="Radius (m)"
          value={weights.radius_m}
          min={200}
          max={8000}
          step={100}
          onChange={(v) => setWeights({ radius_m: v })}
        />
        <label className="row">
          <span>Distance model</span>
          <select
            value={weights.distance.kind}
            onChange={(e) => {
              const kind = e.target.value;
              setWeights({
                distance:
                  kind === "euclid"
                    ? { kind: "euclid" }
                    : kind === "detour"
                      ? { kind: "detour", k: 1.3 }
                      : { kind: "rotated_l1", theta_deg: 29 },
              });
            }}
          >
            <option value="euclid">Straight line</option>
            <option value="detour">Detour factor</option>
            <option value="rotated_l1">Street grid</option>
          </select>
        </label>
        {weights.distance.kind === "detour" && (
          <Slider
            label="Detour ×"
            value={weights.distance.k}
            min={1}
            max={2}
            step={0.05}
            onChange={(k) => setWeights({ distance: { kind: "detour", k } })}
          />
        )}
        {weights.distance.kind === "rotated_l1" && (
          <Slider
            label="Grid angle °"
            value={weights.distance.theta_deg}
            min={0}
            max={90}
            step={1}
            onChange={(theta_deg) => setWeights({ distance: { kind: "rotated_l1", theta_deg } })}
          />
        )}
        <label className="row">
          <span>Decay</span>
          <select
            value={weights.decay.kind}
            onChange={(e) =>
              setWeights({
                decay: e.target.value === "linear" ? { kind: "linear" } : { kind: "exp", k: 2 },
              })
            }
          >
            <option value="linear">Linear</option>
            <option value="exp">Exponential</option>
          </select>
        </label>
        <label className="row">
          <span>Across water</span>
          <select
            value={weights.water_crossing.kind}
            onChange={(e) =>
              setWeights({
                water_crossing:
                  e.target.value === "exclude"
                    ? { kind: "exclude" }
                    : { kind: "penalty", factor: 2 },
              })
            }
          >
            <option value="penalty">Penalise</option>
            <option value="exclude">Exclude</option>
          </select>
        </label>
      </section>

      <section className="section">
        <h2>Model</h2>
        <Slider
          label="Max share per sink"
          value={weights.per_sink_cap}
          min={0.05}
          max={1}
          step={0.05}
          onChange={(v) => setWeights({ per_sink_cap: v })}
        />
        <Slider
          label="Steam bonus"
          value={weights.steam_bonus}
          min={0}
          max={2}
          step={0.1}
          onChange={(v) => setWeights({ steam_bonus: v })}
        />
        <Slider
          label="Network bonus"
          value={weights.uten_bonus}
          min={0}
          max={2}
          step={0.1}
          onChange={(v) => setWeights({ uten_bonus: v })}
        />
      </section>

      <section className="section">
        <h2>Economics</h2>
        {(
          [
            ["pipe_cost_per_m", "Pipe $/m"],
            ["hp_capex_per_mw_th", "Heat pump $/MW"],
            ["gas_price_per_mwh_th", "Gas $/MWh"],
            ["elec_price_per_mwh", "Electricity $/MWh"],
            ["boiler_eff", "Boiler efficiency"],
            ["dc_avoided_cooling_per_mwh", "Avoided cooling $/MWh"],
          ] as const
        ).map(([key, label]) => (
          <label className="row" key={key}>
            <span>{label}</span>
            <input
              type="number"
              className="num"
              value={Number(econ[key].toPrecision(6))}
              step={key === "boiler_eff" ? 0.01 : 1}
              onChange={(e) => setEcon({ [key]: Number(e.target.value) })}
            />
          </label>
        ))}
      </section>

      <section className="section">
        <div className="row">
          <button onClick={resetDefaults}>Reset</button>
          <button onClick={copy}>Copy JSON</button>
          <button onClick={() => setPaste(paste === null ? "" : null)}>
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
            <div className="row">
              <button onClick={applyPaste}>Apply</button>
              {pasteError && <span className="muted">{pasteError}</span>}
            </div>
          </>
        )}
      </section>
    </>
  );
}
