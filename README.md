# heatmatch

Ranks data centers by how well their waste heat could be reused by nearby heat
consumers — pools, hospitals, greenhouses, wastewater plants and so on.

Three regions: **New York City**, **Upstate New York**, and **Northern
Virginia** — Loudoun, Prince William, Fairfax, Arlington, Alexandria, Manassas
and Manassas Park, the largest data center cluster in the world.

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

The score answers one question: **if this data center's waste heat were
available, how much of it could usefully reach a neighbour, and how attractive
would that be?** It is a ranking signal, not a measurement.

### The pipeline

1. **Project.** Each region gets a local equirectangular frame so every
   distance is in plain metres. Distances here span kilometres, not continents,
   so a full map projection buys nothing.
2. **Find neighbours.** Sinks go in an R-tree per region. For a given data
   center, everything within the search radius is a candidate.
3. **Measure the pipe.** Straight-line distance becomes a pipe length under the
   chosen model — straight, a detour factor, or Manhattan distance on a rotated
   street grid. A pipe crossing open water is penalised or excluded.
4. **Judge each pairing.** Category weight × normalised demand × distance decay
   × heat-pump penalty × zone bonus.
5. **Share out the heat.** A facility's supply is finite, so sinks compete for
   it, best first. This is what stops the score from simply rewarding whoever
   has the most neighbours.
6. **Apply the seasons.** Flat supply is overlaid on monthly demand. Heat
   produced in a month nobody needs it is wasted; there is no storage.
7. **Cost it.** Pipe and heat-pump capital against displaced gas, heat-pump
   electricity and avoided cooling.

### Constants and why they are what they are

Everything below is tunable in the app. The defaults are starting points, not
findings.

**Supply.** `utilization_hours = 0.9 × 8760`. Data centers run continuously;
the 10% allows for downtime and load variation. `supply_mwh = mw × hours`.

**Temperatures** (°C). Waste heat leaves at the temperature its cooling system
implies — air 35, rear-door 42, liquid 55 — and must reach what the sink needs:
pools 32, wastewater 35, greenhouses 40, breweries 50, hotels and apartments
60, schools 70, hospitals, universities and offices 75. Cooling type is unknown
for nearly every real site, so almost everything defaults to the least
favourable case, 35 °C.

**Heat pumps.** Where the lift is positive, `COP = carnot_fraction × T_hot /
lift`, with `lift = required − supply + approach`, `approach = 5 K` and
`carnot_fraction = 0.5` for a real machine against the ideal. A pairing needing
a pump scores `COP / (COP + 1)` — the share of delivered energy that came from
the waste heat rather than from the electricity meter. Low-temperature sinks
therefore rank well: a pool needs almost no lift.

**Category weights.** Pools 1.0, wastewater and greenhouses 0.9, hospitals 0.8,
hotels 0.7, apartments 0.6, universities and breweries 0.5, schools and offices
0.3. These follow temperature and steadiness: a pool wants low-grade heat all
year, which is exactly what a data center has. An office wants high-grade heat
only in winter.

**Demand normalisation.** `log₁₀(1 + MWh)`, so a 1 GWh sink scores ~3 and a
10 GWh sink ~4. Compressing demand this way keeps one enormous neighbour from
swamping the category and distance signals.

**Distance.** Default radius 1 km in the city, 4 km upstate, reflecting what a
pipe trench can plausibly cost in each. Score decays linearly to zero at the
radius. NYC uses rotated-L1 at 29° because Manhattan's grid runs about that far
off true north and pipes follow streets; upstate uses a 1.2 detour factor.

**Allocation.** No single sink may take more than 25% of a facility's supply,
so one large neighbour cannot claim the whole site.

**Zone bonuses.** +0.5 where data center and sink are both in the steam
territory, +0.3 where either is in a thermal-network pilot: existing
distribution and an existing regulatory path both make a scheme likelier.

**Economics.** Pipe $3,000/m in the city and $800/m upstate; heat pumps
$900,000 per MW thermal; gas $45/MWh against a boiler at 85%; electricity
$150/MWh in the city, $90 upstate; $8/MWh of cooling the data center avoids.

**Capacity estimates.** Where no capacity is published, it is derived from
building floor area at 75 W/sq ft and **capped at 25 MW**. The cap exists
because the area method assumes a whole building is white space: 111 8th Avenue
came out at 162 MW, more than any facility in the state, purely as an artefact
of a large mixed-use tower. Estimated capacities are flagged in the data as
`mw_source`.

## Virginia: methods and limitations

Northern Virginia is the reason two things in this project exist that New York
did not need. Both are consequences of one fact: **Virginia has no building
energy benchmarking disclosure.** There is no Local Law 84 equivalent, so no
Virginia building in this dataset has a measured heating demand.

### All Virginia demand is modelled, not measured

Annual heating demand comes from [NREL
ComStock](https://registry.opendata.aws/nrel-pds-building-stock/), release
`2025/comstock_amy2018_release_3`, pinned in `config.py` so a re-run cannot
silently change every figure. For each ComStock building type, sampled across
the seven jurisdictions, the pipeline computes heating-fuel use per square
metre of floor area, then multiplies by each sink's footprint. Monthly shapes
come from the same release's state-level timeseries aggregates.

Sinks carry `demand_source: "comstock_modeled"` to say so. **A ComStock
intensity describes a typical building of its type in climate zone 4A — not the
specific building on the map.**

Three things this gets wrong, in decreasing order of how much they matter:

- **Electrically heated buildings read as having almost no demand.** The
  intensities count gas, oil and propane only, matching how New York's LL84
  figures are treated and how the economics price a displaced gas boiler. But
  Virginia's mild climate means much of the commercial stock runs heat pumps:
  only **36% of large offices burn any fuel at all**, which drags the
  fuel-only large-office intensity to 10 kWh/m² against 24 kWh/m² including
  electric heat. Those buildings still have thermal demand a heat network could
  serve. This model does not count it, so Virginia office demand is understated.
  Every intensity in `ingest/derived/va_intensity.json` carries a
  `fuel_heated_share` and a `kwh_per_m2_incl_electric` so the size of the gap is
  visible rather than buried here.
- **Hospitals get no ComStock intensity at all.** ComStock samples only six
  hospitals across the seven jurisdictions, below the 30-sample floor the
  pipeline requires before publishing a number. Virginia hospitals therefore
  fall back to the same category constant New York uses.
- **The weather is one particular year.** `amy2018` is an *actual*
  meteorological year, so the monthly shapes reflect 2018's weather rather than
  a typical year. February 2018 was mild in Virginia and March was cold, which
  is why the shapes show less February heating than March.

### Capacity is graded, not assumed

Virginia capacities range from figures an operator publishes to a guess from a
building's footprint, and the model should not treat those alike. Every data
center carries `mw_confidence`:

| Grade | Meaning | Ranking multiplier |
|---|---|---|
| `reported` | The operator states it | 1.0 |
| `filed` | A county approval or utility filing states it | 0.95 |
| `parcel_estimate` | Derived from assessed building area | 0.7 |
| `footprint_estimate` | Derived from a building footprint | 0.5 |

The multiplier applies **to the ranking score only**. `supply_mwh`,
`delivered_mwh`, `capex`, `annual_savings` and `payback_yrs` are always reported
undiscounted — a shaky capacity figure should make a site rank lower, not make
its pipes cheaper. New York's defaults are 1.0 across the board, because every
New York capacity is area-derived and grading guesses against guesses is noise.

On the map and in the ranking, a solid disc is a stated capacity and an outline
is one inferred from a building.

Curated figures live in `ingest/manual/nova_mw.csv`, one row per campus or
building, each with a source URL. Because operators publish campus totals
rather than per-building numbers, a campus row is split across its buildings
pro rata by footprint. **Rows whose note still begins `UNVERIFIED` were seeded
by an automated research pass: their value is used but their confidence is
not — they are emitted as `parcel_estimate` until a person reads the source and
removes the marker.** At present every seeded row is unverified, so the summary
correctly reports 0% of Virginia capacity as stated.

### Other Virginia-specific caveats

- **Cooling type is unknown for effectively every site**, and most Northern
  Virginia capacity is air-cooled, so institutional sinks need heat pumps. The
  model says so, via the COP column in the detail view.
- **Neighbouring data centers compete for the same sinks.** Each site's supply
  is allocated independently, so in Ashburn the same pool can be counted as
  served by several neighbours at once. The detail view flags sinks claimed by
  more than one top-20 site as "also claimed nearby"; nothing resolves the
  conflict.
- **Curated capacity is approved or planned capacity**, which can exceed what is
  installed and energised today.
- **The City of Fairfax is excluded.** It is an independent city, not one of the
  seven jurisdictions, so it appears as a hole inside Fairfax County.
- **Back-garden pools are filtered out of Virginia only.** OpenStreetMap
  coverage of suburban Virginia includes domestic pools: 544 of 588 matches were
  unnamed with a median area of 81 m², against ~330 m² for the smallest named
  community pool. Since `pool` carries the highest category weight, they would
  otherwise decide the ranking. Virginia gates pools at 250 m².
  **New York has the same problem and is deliberately left ungated** — 76% of
  NYC pool matches are under 250 m², median 21 m² — because fixing it would move
  already-published New York results. See the note in `config.py`.

## Known limitations

These are deliberate simplifications, not bugs:

- Pipe lengths are straight-line, detour-factored, or rotated-L1 — never routed
  on the real street network.
- Per-sink pipe cost sums each connection independently, over-counting shared
  trunk lines. Capex is therefore conservative (too high).
- MW capacity is estimated from building area for most sites.
- Cooling type — which sets the waste-heat supply temperature — is unknown for
  nearly all sites and defaults to air-cooled.
- LL84 energy disclosure covers only NYC buildings ≥ 25,000 sq ft. Virginia has
  no equivalent at all; see "Virginia: methods and limitations".
- OSM sink coverage is uneven, especially upstate.
- Steam-territory and thermal-network polygons are hand-drawn approximations.
- Temperatures come from a fixed per-category lookup; there is no real
  temperature or network hydraulics modeling.
- Nothing accounts for existing cooling contracts, easements, land access, or
  regulatory approval.
- **Allocation and seasonality are computed in that order**, so the per-sink
  deliveries that size the plant sum to slightly more than the seasonally
  adjusted energy the savings are based on. Equipment is sized from the former
  and revenue from the latter, which is conservative in both directions but not
  self-consistent.
- Heat-pump capacity is sized from average load, not winter peak, so it is
  undersized for the coldest months.
- Capacity estimates derived from floor area are capped per region — 25 MW in
  New York, 150 MW in Virginia. Without the New York cap a single mixed-use
  tower outranks every real facility in the state; a cap that low in Virginia
  would clip most of the Ashburn cluster to the same value and flatten the
  ranking it exists to produce.
- Feature ids carry their region (`dc_nova_0007`), so adding a region does not
  renumber the ones already published. Ids are otherwise assigned by position
  and are not stable across a change to the underlying source data.
- NYC data center coverage is **not exhaustive**. It combines an
  OpenStreetMap-derived atlas with a tax-lot filter, and both miss sites that
  are not tagged or not owned under a recognisable name.

## License

MIT for the code. Data carries its upstream licenses — see
[`data/ATTRIBUTION.md`](data/ATTRIBUTION.md).
