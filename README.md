# heatmatch

Ranks New York State data centers by how well their waste heat could be reused
by nearby heat consumers — pools, hospitals, greenhouses, wastewater plants and
so on.

The whole thing is a static site. Data is prepared offline by a Python pipeline
and committed as GeoJSON; the scoring engine is Rust compiled to WebAssembly and
runs entirely in the browser. There is no server, database, or API.

> **Indicative, not a feasibility study.** Pipe routes are straight-line
> approximations, most capacity figures are estimates, and cooling type is
> unknown for nearly every site. See "Known limitations" below.

## Layout

| Path | What it is |
|---|---|
| `ingest/` | Python pipeline that builds `data/` from upstream sources |
| `data/` | Committed GeoJSON assets + `manifest.json` (hashes, provenance) |
| `core/heatmatch-core/` | Scoring engine: geometry, thermodynamics, economics |
| `core/heatmatch-wasm/` | wasm-bindgen wrapper around the engine |
| `web/` | Next.js static export — map, weights panel, results |

## Getting started

Requires Rust ≥1.80 with the `wasm32-unknown-unknown` target, `wasm-pack`,
Node 20+ with `pnpm`, and `uv`.

```sh
make check      # everything CI runs: fmt, clippy, cargo test, pytest, lint, typecheck
make web-dev    # build wasm, copy data, start the dev server
make ingest     # rebuild data/ from upstream sources (hits the network)
```

`make help` lists the rest.

## Methodology

_Populated in T9: every default constant and the reasoning behind it._

## Known limitations

These are deliberate simplifications, not bugs:

- Pipe lengths are straight-line, detour-factored, or rotated-L1 — never routed
  on the real street network.
- Per-sink pipe cost sums each connection independently, over-counting shared
  trunk lines. Capex is therefore conservative (too high).
- MW capacity is estimated from building area for most sites.
- Cooling type — which sets the waste-heat supply temperature — is unknown for
  nearly all sites and defaults to air-cooled.
- LL84 energy disclosure covers only NYC buildings ≥ 25,000 sq ft.
- OSM sink coverage is uneven, especially upstate.
- Steam-territory and thermal-network polygons are hand-drawn approximations.
- Temperatures come from a fixed per-category lookup; there is no real
  temperature or network hydraulics modeling.
- Nothing accounts for existing cooling contracts, easements, land access, or
  regulatory approval.

## License

MIT for the code. Data carries its upstream licenses — see
[`data/ATTRIBUTION.md`](data/ATTRIBUTION.md).
