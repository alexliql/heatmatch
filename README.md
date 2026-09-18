# heatmatch

Ranks data centers by how well their waste heat could be reused by nearby heat
consumers — pools, hospitals, greenhouses, wastewater plants and so on.

Eight regions across five states: **New York City** and **Upstate New York**;
**Northern Virginia** (Loudoun, Prince William, Fairfax, Arlington, Alexandria,
Manassas and Manassas Park — the largest data center cluster in the world);
**Seattle**; **Portland**; and three California metros — **Silicon Valley**,
**Los Angeles** and **Sacramento**.

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

### Demand is delivered heat, and every sink has a counterfactual

Every sink's `demand_kwh` is the heat its heating system delivered into its
spaces and hot water over a year — not the fuel it bought to do so. That is the
quantity a heat network would replace, and it is what the engine prices:
`econ.rs` divides delivered heat by boiler efficiency (0.85) to recover the fuel
avoided. So a measured source that reports fuel *input* — LL84 does — is scaled
by 0.85 on the way in. Before this, LL84 sinks were both overstated by 1/0.85
and had their savings inflated by the same factor.

ComStock-modelled demand is built on the same basis, per sampled building:

```
delivered = (gas + oil + propane)[heating + hot water] × 0.85
          + district heat[heating + hot water]              (already heat)
          + electric heating  × (3.0 if a heat pump, else 1.0)
          + electric hot water × 1.0    (baseline stock has no heat-pump water heaters)
```

This matters far more than it sounds. On a fuel-only basis, a building heated
electrically reads as having almost no demand — and in Loudoun County, large
offices are **52% electric resistance and 24% district heat**. Fuel-only saw the
remaining quarter and put the large-office intensity at 10 kWh/m²; delivered
heat puts it at 35. Every derived intensity file records the basis it was
computed on under `"basis"`, and keeps `kwh_per_m2_fuel_only` beside the number
so the difference stays visible.

Each sink also carries a **`counterfactual`**: what it heats with today, and so
what a connection would displace. A gas boiler saves gas at boiler efficiency; a
resistance heater saves a full MWh of electricity per MWh of heat; an existing
heat pump saves only the third or so of a MWh it would have drawn. In a place
where electricity costs far more than gas, a resistance-heated building is the
best sink on the map — and without this field the model would call it worthless.

| `counterfactual` | avoided cost per delivered MWh | how it is assigned |
|---|---|---|
| `gas` | `gas_price / boiler_eff` | measured sinks whose thermal fuels dominate; every footprint or category estimate (an estimate of demand says nothing about equipment) |
| `electric_resistance` | `elec_price` | modelled sinks whose ComStock type is majority resistance-heated |
| `heat_pump` | `elec_price / 3.0` | modelled sinks whose ComStock type is majority heat-pump |

Gas versus heat pump is not a fixed ordering: at a 3.6:1 electricity-to-gas
price ratio a COP-3 pump costs slightly *more* per MWh of heat than a boiler,
at 2:1 slightly less. That is a finding about prices, which is why the field
exists.

One more rule. A measured building reporting almost no thermal fuel is usually
not a building without heating — it is one heated electrically, which the fuel
columns cannot see. Where a measurement is below 10 kWh/m² and ComStock says a
typical building of that type wants more than 30, the measurement is set aside
for the model and the sink carries `demand_note: "measured_fuel_near_zero"`. New
York City reads its ComStock table for this alone; its footprint and category
estimates are never replaced. In the current bundle it fired on no NYC building.

### Defaults

Every number below is a slider in the app; the defaults are starting points,
not findings. They live in one place per layer — `Weights::default_for` and
`Econ::default_for` in `core/heatmatch-core/src/weights.rs`, and `REGIONS` in
`ingest/src/ingest/config.py` — with the reasoning beside each value.

- **Supply**: `mw × 0.9 × 8760` hours a year.
- **Temperatures**: waste heat leaves at 35 °C (air), 42 (rear-door) or 55
  (liquid); sinks need 32 (pools) up to 75 (hospitals, universities, offices).
  Cooling type is unknown for nearly every site, so 35 °C is the usual case.
- **Heat pumps**: `COP = 0.5 × T_hot / lift`, `lift = required − supply + 5 K`.
  A pairing that needs a pump scores `COP / (COP + 1)`, the share of delivered
  energy that came from waste heat rather than the meter.
- **Category weights** follow temperature and steadiness: pools 1.0 down to
  offices 0.3. Demand enters as `log₁₀(1 + MWh)` so one enormous neighbour
  cannot swamp the other signals.
- **Reach**: 1 km in Manhattan (rotated-L1 at 29°, because pipes follow the
  street grid) to 4 km upstate; score decays linearly to zero at the radius.
  No single sink may take more than 25% of a site's supply.
- **Zone bonuses**: +0.5 when both ends are in the steam territory, +0.3 when
  either is in a thermal-network pilot.
- **Economics**: pipe $800–3,000/m by region; heat pumps $900k per MW thermal;
  gas $40–55/MWh against an 85% boiler; electricity $80–210/MWh; $8/MWh of
  avoided cooling.
- **Capacity estimates** from floor area (75 W/sq ft in New York, 100–150
  elsewhere) are capped per region; see "Known limitations".

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

Two things this gets wrong:

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

## Washington, Oregon, California: methods and limitations

The West Coast regions reuse everything Virginia introduced — modelled demand,
graded capacity, region-prefixed ids — and add two things: **measured demand
from city and state benchmarking programmes**, and the **counterfactual** on
every sink, which is what makes an electrically heated building on the West
Coast readable as a sink at all.

### Where the demand comes from

| Region | Measured source | Coverage | Everything else |
|---|---|---|---|
| Seattle | City of Seattle Building Energy Benchmarking (`seattle_bench`) | Seattle city limits, ≥ 20,000 sq ft; ~half of Seattle's sinks | ComStock, WA counties |
| Portland | none — see below | — | ComStock, OR counties |
| Silicon Valley, Los Angeles, Sacramento | California AB 802 public disclosure (`ab802`) | Statewide, ≥ 50,000 sq ft | ComStock, per region's counties |

Two programmes were verified and deliberately not used; both decisions are in
`manifest.json` under `sources` with a `status`, so they are on the record next
to the sources that were:

- **Portland's Energy Performance Reporting** does break out natural gas, but
  publishes addresses and tax-lot ids with no coordinates, and covers Portland
  city limits only — the data centers are in Hillsboro. Portland's sinks are
  ComStock-modelled.
- **Los Angeles's EBEWE disclosure** carries site and source EUI only, with no
  fuel breakdown and no coordinates. AB 802 covers the same city's buildings of
  50,000 sq ft and up with separate fuel fields and geocodes, so it is used
  instead. Nothing was derived from an EUI.

### Where the data centers come from

The IM3 Atlas is OpenStreetMap-derived, and OpenStreetMap's coverage of data
centers is uneven: 79 buildings in Silicon Valley, 28 in Portland, 21 in
Seattle — and 10 in Los Angeles, 5 in Sacramento. Where it is thin, building a
county-parcel ingest to find the missing sites is a data-collection project
wearing an ingest module's clothes. The honest tool is a cited **seed list**
(`ingest/manual/<region>_dcs.csv`): each row a real facility whose operator
publishes its location and floor area, with the URL that says so, emitted as a
`footprint_estimate` like any other area-derived figure.

Seeds also fix a failure mode the Atlas has for downtown carrier hotels: it
maps the building's ground footprint, and a 30-storey tower's footprint is a
thirtieth of its floor space. The Westin Building Exchange is 13,117 sq ft in
the Atlas and 400,400 sq ft on its owner's page; One Wilshire is 43,850 against
664,000. A seed carrying the stated floor area, at a carrier-hotel density of
75 W/sq ft rather than the purpose-built 150, wins the merge.

**San Diego is not included.** Nor is the Inland Empire. Each is a one-entry
config change if it ever earns one.

### Seattle specifically

- **Enwave Seattle's steam territory is a hand-drawn approximation** —
  downtown from Denny Way through Pioneer Square, plus First Hill. Enwave
  publishes no service-area geodata.
- **Steam-heated buildings are kept as sinks in Seattle only.** Everywhere
  else a district-steam building already has its heat and is dropped. Enwave's
  customers are the natural offtakers of a network-level heat swap, which is a
  commercial question the model does not evaluate and should not pre-empt.
  They carry `steam_heated: true` and `in_steam: true`.
- **Water crossings are excluded outright** rather than penalised: Lake Union,
  the Ship Canal and Elliott Bay separate most of Seattle's sinks from its data
  centers, and a penalty would still let a pipe be drawn under Lake Washington.
- **The Westin ↔ Amazon precedent is visible, and its evidence is suppressed by
  itself.** The Westin Building Exchange ranks first in Seattle. All seven
  Amazon towers within reach are found, measured and connected — Doppler is
  96 m away and fully served — but they sit around thirtieth of ninety-three
  sinks, behind fifty-one downtown hotels, because `office` carries weight 0.3
  to `hotel`'s 0.7 (offices empty out in summer; hotels heat water all year).
  Doppler's measured gas use is also *low*, because the campus already runs on
  recovered Westin heat. The precedent is real, and it is why the building
  reports little demand.

### California specifically

- Climate zones 3B/3C have little space-heating demand and California
  electricity is the highest-priced on the map, so results are DHW- and
  pool-dominated with long paybacks. **That is the expected finding**, not a
  defect. Sacramento is the control: same measured source, inland winters,
  SMUD's municipal power at well under coastal prices.
- AB 802 covers buildings of 50,000 sq ft and up; smaller sinks are modelled.
- Apartment buildings are collected as sinks in Los Angeles (and New York
  City) only, where they are dense enough to matter.

### Portland specifically

- All Portland-region demand is modelled: the measured programme covers the
  city, and the data centers are in Hillsboro.
- Hillsboro capacity figures in `pdx_mw.csv` are *planned campus* totals from
  operator announcements, which exceed what is built. They are restricted to
  campuses whose buildings the Atlas already maps, so the split lands on real
  structures, and they are all `UNVERIFIED`.

### Everywhere on the West Coast

Cooling type is unknown for every site. Curated capacity reflects approved or
contracted figures and is `UNVERIFIED` until a person reads each source. Rural
Washington and Oregon hyperscale sites — Quincy, Prineville, The Dalles,
Umatilla and Boardman — are not included; screening them needs sink categories
(food processing, aquaculture) the model does not have. And in Southern
California the community question about data centers is evaporative cooling
water, not heat; a water-savings term is the obvious next extension and is
kept out of the heat score.

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
