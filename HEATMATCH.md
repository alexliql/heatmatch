# heatmatch — Implementation Specification

Target: an AI coding agent working in a fresh repo. Read the whole document before writing code. Build in the phase order given; each phase has acceptance criteria that must pass before the next phase starts.

## 0. Product summary

A static web app that ranks New York State data centers by how well their waste heat could be reused by nearby heat consumers ("sinks"). All computation runs in the browser via a Rust core compiled to WebAssembly. Data is prepared once, offline, by Python scripts and committed as static assets. There is no server, database, auth, or API.

Non-goals (do not build): user accounts, backend API routes, persistent storage, full road-network routing, national coverage, precise financial modeling, any "contact us / request a study" flow.

## 1. Repository layout

```
heatmatch/
  README.md
  LICENSE                      # MIT for code; data attributions in data/ATTRIBUTION.md
  Makefile                     # top-level targets: ingest, core-test, wasm, web-dev, web-build, check
  .github/workflows/ci.yml
  ingest/                      # Python 3.11+, uv-managed
    pyproject.toml
    src/ingest/
      __init__.py
      config.py                # regions, bboxes, constants
      sources/
        pnnl.py                # national data center dataset
        pluto.py               # NYC MapPLUTO
        nys_parcels.py         # upstate parcels
        osm.py                 # Overpass sinks
        ll84.py                # NYC LL84 energy disclosure
        hydro.py               # water polygons
        zones.py               # steam / UTEN polygons (manual GeoJSON inputs)
      merge/
        datacenters.py
        sinks.py
        dedupe.py
      schema.py                # pydantic models = the contract with core
      cli.py                   # `ingest run --region nyc|upstate|all`
    tests/
    raw/                       # .gitignored downloaded sources
  data/                        # committed outputs
    ATTRIBUTION.md
    manifest.json
    datacenters.<hash>.geojson
    sinks.<hash>.geojson
    water.<hash>.geojson
    zones.<hash>.geojson
  core/                        # Rust workspace
    Cargo.toml                 # [workspace] members = ["heatmatch-core", "heatmatch-wasm"]
    heatmatch-core/
      Cargo.toml
      src/
        lib.rs
        types.rs
        frame.rs               # local equirectangular projection
        index.rs               # rstar wrapper
        distance.rs            # euclid / detour / rotated-L1, water crossing check
        thermo.rs              # supply/required temps, heat pump COP
        season.rs              # monthly demand profiles
        econ.rs                # capex / savings / payback
        scoring.rs             # Engine::rank / explain
        weights.rs             # Weights, Econ, defaults, validation
      tests/
        fixtures/              # small hand-built GeoJSON
        golden.rs
        properties.rs          # proptest
    heatmatch-wasm/
      Cargo.toml
      src/lib.rs
  web/                         # Next.js 15, TypeScript, App Router, static export
    package.json
    next.config.ts
    src/
      app/
        layout.tsx
        page.tsx
      lib/
        engine.ts              # wasm loader + typed wrapper
        store.ts               # zustand
        types.ts               # mirrors core types (generated, see §4.4)
        format.ts
      components/
        Map.tsx
        WeightsPanel.tsx
        ResultsTable.tsx
        DcDetail.tsx
        RegionToggle.tsx
      styles/
    public/
      data -> ../../data       # symlink or copy step in build
```

## 2. Toolchain

- Python 3.11+, `uv`. Deps: `geopandas>=1.0`, `shapely>=2`, `pandas`, `pyarrow`, `requests`, `pydantic>=2`, `rapidfuzz`, `typer`, `pyproj`.
- Rust stable ≥1.80. Crates: `geo`, `rstar`, `geojson`, `serde`, `serde_json`, `enum-map`, `smallvec`, `thiserror`; wasm: `wasm-bindgen`, `serde-wasm-bindgen`, `console_error_panic_hook`; dev: `proptest`, `approx`. Build with `wasm-pack build --target bundler`.
- Node 20+, pnpm. Next.js 15, React 19, TypeScript strict, `maplibre-gl`, `@turf/circle`, `zustand`, `@tanstack/react-table`.
- Vercel: static output. `next.config.ts` sets `output: 'export'` and `webpack.experiments.asyncWebAssembly = true`.

## 3. Phase 1 — Ingest

### 3.1 Regions

```python
REGIONS = {
  "nyc":     {"bbox": (-74.30, 40.45, -73.65, 40.95), "origin": (40.7128, -74.0060),
              "radius_m": 1000, "detour": 1.30, "grid_rotation_deg": 29.0,
              "pipe_cost_per_m": 3000.0},
  "upstate": {"bbox": (-79.80, 40.45, -71.80, 45.05), "origin": (42.90, -75.50),
              "radius_m": 4000, "detour": 1.20, "grid_rotation_deg": None,
              "pipe_cost_per_m": 800.0},
}
```
NYC bbox includes Westchester/Nassau edges; upstate is the remainder of NYS. A feature belongs to `nyc` if inside the nyc bbox, else `upstate`. Exclude anything outside NYS (use the NYS boundary polygon from NYS GIS Clearinghouse; do not rely on bbox alone).

### 3.2 Output schema (contract; `ingest/src/ingest/schema.py`)

```python
class DataCenter(BaseModel):
    id: str            # "dc_" + zero-padded index, stable across runs via sort by (lat, lon, name)
    name: str
    region: Literal["nyc", "upstate"]
    lat: float; lon: float
    mw: float          # IT load estimate, >0
    mw_source: Literal["pnnl", "pluto_estimate", "parcel_estimate", "manual"]
    cooling: Literal["air", "rear_door", "liquid", "unknown"]
    in_steam: bool
    in_uten: bool
    sources: list[str] # provenance ids

class Sink(BaseModel):
    id: str            # "s_" + index
    name: str
    region: Literal["nyc", "upstate"]
    lat: float; lon: float
    cat: Literal["pool", "hospital", "university", "school", "greenhouse", "brewery",
                 "wwtp", "office", "residential_multifamily", "hotel"]
    demand_kwh: float  # annual THERMAL demand estimate (heating fuels only), >0
    demand_source: Literal["ll84_fuel", "footprint_estimate", "category_default"]
    steam_heated: bool # true if LL84 shows district steam as primary fuel → excluded from matching
    in_steam: bool
    in_uten: bool
    sources: list[str]
```

GeoJSON: `FeatureCollection` of `Point` features, `properties` = model dump, coordinates `[lon, lat]`, 6 decimals. Files named with the first 8 hex chars of sha256 over canonical JSON content. `manifest.json`:

```json
{ "built_at": "ISO8601", "datacenters": {"file": "...", "count": N, "hash": "..."},
  "sinks": {...}, "water": {...}, "zones": {...},
  "sources": [{"id": "pnnl_dc", "url": "...", "retrieved": "YYYY-MM-DD", "license": "..."}] }
```

### 3.3 Sources and rules

**PNNL / NREL data center dataset** (`sources/pnnl.py`). Locate the public download from the PNNL "data center map" tool announced Jan 2026 (search pnnl.gov and the associated data portal; also check NREL's data center map). Download CSV/GeoJSON to `ingest/raw/`. Filter to NYS. Keep name, lat, lon, capacity MW if present, operator. Record the license in `manifest.json`. If capacity is missing set `mw_source` later via estimate.

**NYC MapPLUTO** (`sources/pluto.py`). Download the current MapPLUTO shapefile/GeoJSON from NYC Planning open data. Candidate data centers: `BldgClass` in telecom/utility/industrial classes (start with `E*`, `F*`, `I*`, `Y*`) AND (`OwnerName` matches a curated operator list: Equinix, Digital Realty, Telx, Telehouse, Sabey, CoreSite, DataBank, Cyxtera, Zayo, Verizon, AT&T, "Data Center", "Colo") OR address in a curated list of known carrier hotels (60 Hudson St, 111 8th Ave, 32 Ave of the Americas, 375 Pearl St, 325 Hudson St, 85 10th Ave, 165 Halsey is NJ — exclude). Curated lists live in `config.py`; leave TODOs where unsure. Estimate `mw = BldgArea_sqft * 0.000075` (75 W/sq ft, low colo density) with `mw_source="pluto_estimate"`.

**NYS parcels** (`sources/nys_parcels.py`). NYS GIS Clearinghouse statewide parcels. Filter property class 700-series (industrial) / 800-series (public services) with owner names matching the operator list plus upstate names (Yahoo/Verizon Lockport, Sabey, Bloom, etc. — curated, TODO). Estimate `mw = sqft * 0.00005` with `mw_source="parcel_estimate"`.

**Dedupe** (`merge/dedupe.py`). Union all candidates. Two candidates are the same facility if within 75 m AND (`rapidfuzz.fuzz.token_set_ratio(nameA, nameB) >= 70` OR either name empty). Prefer PNNL record for coordinates and MW; union `sources`. Cooling: `"unknown"` unless a manual override file `ingest/manual/cooling.csv` (id or name, cooling) says otherwise. Ship an empty override file with a header.

**OSM sinks** (`sources/osm.py`). Overpass API (`https://overpass-api.de/api/interpreter`), one query per category per region bbox, `[out:json][timeout:180]`, centroids for ways/relations, retry with backoff, cache raw responses on disk. Category mapping:

| cat | Overpass filter |
|---|---|
| pool | `leisure=swimming_pool` (exclude `access=private`), `leisure=sports_centre` + `sport=swimming` |
| hospital | `amenity=hospital` |
| university | `amenity=university`, `amenity=college` |
| school | `amenity=school` (only if way area ≥ 5000 m²) |
| greenhouse | `landuse=greenhouse_horticulture`, `building=greenhouse` |
| brewery | `craft=brewery`, `industrial=brewery`, `microbrewery=yes` |
| wwtp | `man_made=wastewater_plant` |
| office | `building=office` OR `office=*` with way area ≥ 3000 m² |
| residential_multifamily | `building=apartments` with way area ≥ 2000 m² (NYC only; upstate skip) |
| hotel | `tourism=hotel` |

Footprint estimate when no LL84 match: `demand_kwh = area_m2 * floors_guess * intensity_kwh_per_m2` with per-category intensity defaults in `config.py` (pool 400, hospital 250, university 150, school 120, greenhouse 350, brewery 200, wwtp 100, office 90, residential 110, hotel 180; `floors_guess` from `building:levels` else category default). If no area is known, use `demand_source="category_default"` with a per-category constant.

**LL84** (`sources/ll84.py`). NYC Open Data "Energy and Water Data Disclosure for Local Law 84" (latest calendar year available; search the portal, record dataset id). Join to OSM sinks by nearest BBL centroid within 40 m (compute BBL centroids from MapPLUTO). `demand_kwh = natural_gas_kbtu*0.293 + fuel_oil_kbtu*0.293` (all fuel-oil grades), ignoring electricity and district steam. `steam_heated = district_steam_kbtu > 0.5 * total_fuel_kbtu`. When joined, `demand_source="ll84_fuel"`.

**Water** (`sources/hydro.py`). NYC Open Data hydrography polygons for nyc; USGS NHD waterbody + area polygons clipped to NYS for upstate. Simplify to 20 m tolerance, drop polygons < 5000 m². Output `water.<hash>.geojson`.

**Zones** (`sources/zones.py`). Reads two hand-drawn GeoJSON polygon files from `ingest/manual/`: `steam_territory.geojson` (approximation of Con Edison Manhattan steam service area; ship a placeholder polygon covering Manhattan south of 96th St with a `"approximate": true` property and a TODO) and `uten_pilots.geojson` (empty FeatureCollection initially; TODO to add utility pilot footprints). Tag every DC and sink with `in_steam` / `in_uten` by point-in-polygon.

**Pre-filter.** Keep only sinks within `region.radius_m * region.detour * 1.1` of at least one data center in the same region. Drop sinks with `steam_heated=true` from the output entirely, but log the count.

### 3.4 CLI and acceptance

`uv run ingest run --region all` writes all four GeoJSON files and `manifest.json`, prints a summary table (per region: DC count, MW total, sinks by category, join rate to LL84).

Acceptance: pydantic validation passes on every feature; ≥ 20 data centers in nyc and ≥ 10 upstate; LL84 join rate ≥ 40% of NYC sinks in categories hospital/office/university; no duplicate ids; total sinks file < 8 MB uncompressed; `pytest` covers dedupe rules and LL84 fuel math with fixtures.

## 4. Phase 2 — Core crate (`heatmatch-core`)

Pure Rust, `#![forbid(unsafe_code)]`, no I/O except in tests. Public API is exactly what §4.6 lists.

### 4.1 Types (`types.rs`)

```rust
pub type Id = String;

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Serialize, Deserialize, Enum)]
pub enum SinkCat { Pool, Hospital, University, School, Greenhouse, Brewery, Wwtp, Office, ResidentialMultifamily, Hotel }

#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum Cooling { Air, RearDoor, Liquid, Unknown }

#[derive(Clone, Copy, PartialEq, Eq, Debug, Serialize, Deserialize)]
pub enum Region { Nyc, Upstate }

pub struct DataCenter { pub id: Id, pub name: String, pub region: Region, pub lat: f64, pub lon: f64,
                        pub mw: f32, pub cooling: Cooling, pub in_steam: bool, pub in_uten: bool }

pub struct Sink { pub id: Id, pub name: String, pub region: Region, pub lat: f64, pub lon: f64,
                  pub cat: SinkCat, pub demand_kwh: f32, pub in_steam: bool, pub in_uten: bool }

pub struct Contribution { pub sink: Id, pub cat: SinkCat, pub dist_m: f32, pub pipe_m: f32,
                          pub crosses_water: bool, pub hp_required: bool, pub cop: f32,
                          pub delivered_mwh: f32, pub score: f32 }

pub struct Match { pub dc: Id, pub region: Region, pub score: f32,
                   pub supply_mwh: f32, pub demand_mwh_in_radius: f32, pub utilization: f32,
                   pub delivered_mwh: f32, pub capex: f32, pub annual_savings: f32,
                   pub payback_yrs: Option<f32>, pub top: SmallVec<[Contribution; 5]> }
```

Serde: `rename_all = "snake_case"` on all enums and structs; JSON field names must equal the ingest schema.

### 4.2 Weights and economics (`weights.rs`)

```rust
pub struct Weights {
    pub cat: EnumMap<SinkCat, f32>,   // defaults: Pool 1.0, Wwtp 0.9, Greenhouse 0.9, Hospital 0.8,
                                      // Hotel 0.7, ResidentialMultifamily 0.6, University 0.5,
                                      // Brewery 0.5, School 0.3, Office 0.3
    pub radius_m: f32,                // default per region (1000 / 4000)
    pub distance: DistanceModel,      // Euclid | Detour { k } | RotatedL1 { theta_deg }
    pub decay: Decay,                 // Linear | Exp { k: f32 }  default Linear
    pub steam_bonus: f32,             // 0.5
    pub uten_bonus: f32,              // 0.3
    pub per_sink_cap: f32,            // 0.25 (fraction of dc supply a single sink may claim in score)
    pub log_base: f32,                // 10.0 — demand normalization
    pub water_crossing: WaterPolicy,  // Exclude | Penalty { factor } default Penalty{2.0} on pipe_m
    pub approach_c: f32,              // 5.0
    pub hp_carnot_fraction: f32,      // 0.5
    pub utilization_hours: f32,       // 0.9 * 8760 → supply_mwh = mw * this
}

pub struct Econ {
    pub pipe_cost_per_m: f32,         // region default
    pub hp_capex_per_mw_th: f32,      // 900_000.0
    pub gas_price_per_mwh_th: f32,    // 45.0
    pub boiler_eff: f32,              // 0.85
    pub elec_price_per_mwh: f32,      // 150.0 (NYC) / 90.0 (upstate)
    pub dc_avoided_cooling_per_mwh: f32, // 8.0
}
impl Weights { pub fn default_for(region: Region) -> Self; pub fn validate(&self) -> Result<(), WeightsError>; }
impl Econ    { pub fn default_for(region: Region) -> Self; }
```

`validate` rejects NaN, negative weights, radius ≤ 0, boiler_eff outside (0,1].

### 4.3 Geometry

`frame.rs`: `LocalFrame { lat0, lon0, cos_lat0 }` with `to_xy(lat, lon) -> [f32; 2]` in meters using R = 6_371_000. One frame per region, origin from `Region` constants matching §3.1.

`index.rs`: `SinkPt { xy: [f32; 2], idx: u32 }` implementing `rstar::RTreeObject` + `PointDistance`. Build one `RTree` per region. Query: `locate_within_distance(xy, r*r)` where `r = radius_m * max_detour_factor` (use 1.5 as the safe upper bound so RotatedL1 candidates are not missed).

`distance.rs`:
```rust
pub fn euclid(a, b) -> f32;
pub fn pipe_length(a, b, model: &DistanceModel) -> f32   // Euclid: d; Detour: d*k; RotatedL1: rotate both by -theta then |dx|+|dy|
pub fn crosses_water(a, b, water: &WaterIndex) -> bool    // segment–polygon intersection via rstar of polygon bboxes then geo::Intersects
```
A sink is "in radius" iff `pipe_length <= radius_m`.

### 4.4 Thermodynamics (`thermo.rs`)

```rust
pub fn supply_temp_c(c: Cooling) -> f32 { Air=>35., RearDoor=>42., Liquid=>55., Unknown=>35. }
pub fn required_temp_c(cat: SinkCat) -> f32 {
  Pool=>32., Wwtp=>35., Greenhouse=>40., Brewery=>50., Hotel=>60., ResidentialMultifamily=>60.,
  School=>70., Hospital=>75., University=>75., Office=>75. }
pub struct HeatPump { pub required: bool, pub cop: f32 }
pub fn heat_pump(cooling: Cooling, cat: SinkCat, approach_c: f32, carnot_fraction: f32) -> HeatPump
// lift = required - supply + approach; if lift <= 0 → {false, INF}
// else th = required+273.15, tc = supply+273.15, cop = carnot_fraction * th/(th-tc)
```
Electricity for heat pump per delivered MWh_th = `1/cop` MWh_e (heat pump delivers cop units heat per unit electricity; treat DC heat as free source).

### 4.5 Seasonality (`season.rs`)

`pub const PROFILE: EnumMap<SinkCat, [f32; 12]>`, each row sums to 1.0 (assert in a test). Defaults (Jan..Dec):
- Pool, Wwtp, Brewery, Hotel: flat `1/12`.
- Greenhouse: `[.14,.13,.11,.08,.05,.03,.02,.02,.04,.08,.13,.17]`
- Hospital, ResidentialMultifamily: `[.14,.13,.11,.08,.05,.04,.03,.03,.04,.08,.12,.15]`
- University, School, Office: `[.17,.15,.12,.07,.03,.01,.00,.00,.02,.08,.15,.20]`

```rust
pub fn utilization(supply_mwh: f32, demands: &[(SinkCat, f32 /*mwh*/)]) -> (f32 /*util*/, f32 /*delivered_mwh*/)
// monthly_demand[m] = Σ_s demand_s * PROFILE[cat_s][m]; monthly_supply = supply/12
// delivered = Σ_m min(monthly_demand[m], monthly_supply); util = delivered / supply
```

### 4.6 Scoring and economics (`scoring.rs`, `econ.rs`)

```rust
pub struct Engine { /* per-region: dcs, sinks, tree, frame, water */ }
impl Engine {
    pub fn new(dcs: Vec<DataCenter>, sinks: Vec<Sink>, water: Vec<geo::Polygon<f32>> /*already in frame xy per region*/) -> Result<Self, EngineError>;
    pub fn rank(&self, region: Region, w: &Weights, e: &Econ) -> Vec<Match>;           // sorted by score desc
    pub fn explain(&self, dc: &str, w: &Weights, e: &Econ) -> Result<Vec<Contribution>, EngineError>; // all in-radius sinks, sorted by score desc
    pub fn datacenter(&self, id: &str) -> Option<&DataCenter>;
}
```

Per data center:
1. `supply_mwh = mw * utilization_hours`.
2. Candidates from tree; compute `pipe_m`; drop if `pipe_m > radius_m`. Compute `crosses_water`; if policy Exclude, drop; if Penalty, `pipe_m *= factor`.
3. Per candidate: `decay = 1 - pipe_m/radius_m` (Linear) or `exp(-k*pipe_m/radius_m)`; `demand_norm = log(1 + demand_kwh/1000) / log_base`; `hp = heat_pump(...)`; `hp_factor = if hp.required { cop / (cop + 1.0) } else { 1.0 }` (soft penalty proportional to electricity share); `bonus = 1 + steam_bonus*[dc.in_steam && s.in_steam] + uten_bonus*[dc.in_uten || s.in_uten]`; `raw = w.cat[cat] * demand_norm * decay * hp_factor * bonus`; `score_s = min(raw, per_sink_cap * something)` — implement cap as: sort by raw desc, then greedily allocate `remaining_supply`, each sink's `delivered_mwh_s = min(demand_mwh_s, remaining, per_sink_cap*supply_mwh)`, `score_s = raw * (delivered_mwh_s / demand_mwh_s)`.
4. `demand_mwh_in_radius = Σ demand_mwh_s`; `(utilization, delivered_mwh) = season::utilization(supply_mwh, allocated)`.
5. Econ, over the allocated set: `pipe_capex = Σ pipe_m_s * pipe_cost_per_m` (sum over allocated sinks; note this over-counts shared trunks — document as conservative); `hp_capacity_mw_th = Σ over hp-required allocated sinks of (delivered_mwh_s / utilization_hours)`; `capex = pipe_capex + hp_capacity_mw_th * hp_capex_per_mw_th`; `hp_elec_mwh = Σ delivered_mwh_s / cop_s` for hp-required sinks; `annual_savings = delivered_mwh * gas_price/boiler_eff - hp_elec_mwh * elec_price + delivered_mwh * dc_avoided_cooling`; `payback_yrs = if annual_savings > 0 { Some(capex/annual_savings) } else { None }`.
6. `score = Σ score_s`. `top` = first 5 by score.

Determinism: ties broken by id ascending. All f32; no randomness.

### 4.7 Tests

- `tests/fixtures/mini_{dcs,sinks,water}.geojson`: 4 DCs, 30 sinks, 1 water polygon, hand-computed expected ranking in `golden.rs` (assert order and scores within 1e-4).
- `properties.rs` (proptest): (a) increasing `w.cat[c]` never decreases any Match score; (b) moving a sink farther never increases its Contribution score; (c) `utilization ∈ [0,1]`, `delivered_mwh ≤ supply_mwh`; (d) `rank` scores equal `Σ explain` scores per DC; (e) PROFILE rows sum to 1 ± 1e-6.
- Unit: `heat_pump` known values (Air→Pool: not required; Air→Hospital: required, cop ≈ 0.5*348.15/45 ≈ 3.87 at approach 5).

Acceptance: `cargo test --workspace` green; `cargo clippy -- -D warnings`; `cargo bench` optional; `rank` on the real NYC dataset < 50 ms in release native.

## 5. Phase 3 — WASM crate (`heatmatch-wasm`)

```rust
#[wasm_bindgen]
pub struct WasmEngine { inner: Engine }

#[wasm_bindgen]
impl WasmEngine {
    #[wasm_bindgen(constructor)]
    pub fn new(dcs_geojson: &str, sinks_geojson: &str, water_geojson: &str) -> Result<WasmEngine, JsError>;
    pub fn rank(&self, region: &str, weights: JsValue, econ: JsValue) -> Result<JsValue, JsError>;
    pub fn explain(&self, dc_id: &str, weights: JsValue, econ: JsValue) -> Result<JsValue, JsError>;
    pub fn default_weights(region: &str) -> JsValue;
    pub fn default_econ(region: &str) -> JsValue;
    pub fn version() -> String;
}
```
GeoJSON parsing happens once in the constructor (use the `geojson` crate, convert to core types, project water polygons into each region's frame). `serde_wasm_bindgen` for JsValue conversion with `serialize_maps_as_objects(true)`. Install `console_error_panic_hook` in `new`. Generate TS types: add `tsify` derive with `#[tsify(into_wasm_abi, from_wasm_abi)]` on `Weights`, `Econ`, `Match`, `Contribution`, or alternatively write `web/src/lib/types.ts` by hand and add a test that serializes defaults and compares keys to a checked-in JSON snapshot.

Build: `wasm-pack build core/heatmatch-wasm --target bundler --release --out-dir ../../web/src/wasm`. Commit nothing from `web/src/wasm`; CI builds it. Acceptance: package builds; a node smoke test loads the fixture and returns 4 ranked rows.

## 6. Phase 4 — Web (`web/`)

### 6.1 Config
- `next.config.ts`: `output: 'export'`, `images: { unoptimized: true }`, `webpack: (c) => { c.experiments = {...c.experiments, asyncWebAssembly: true, layers: true}; return c; }`.
- `package.json` scripts: `predev`/`prebuild` run `pnpm run wasm` (calls wasm-pack) and `pnpm run copy-data` (copies `../data/*` to `public/data/`).
- Basemap: Protomaps free tiles or `https://tiles.openfreemap.org/styles/liberty`. Attribution control on.

### 6.2 Engine loader (`lib/engine.ts`)
Dynamic import inside `useEffect`; never on the server. Fetch `manifest.json` first, then the four data files by hashed name; construct `WasmEngine`; expose `{ rank, explain, defaults }` typed wrappers. Show a loading state with byte counts.

### 6.3 Store (`lib/store.ts`, zustand)
```ts
type State = { region: 'nyc'|'upstate'; weights: Weights; econ: Econ; selectedDc: string|null;
               results: Match[]; explain: Contribution[]; ready: boolean }
```
Actions: `setRegion` (also resets weights/econ to region defaults), `setWeight(path, value)`, `setEcon(path, value)`, `select(dcId)`, `recompute()`. `recompute` runs `engine.rank` synchronously; if measured > 16 ms in the browser, move to a Web Worker (`engine.worker.ts`) with a request-id protocol — implement the worker only if the threshold is exceeded.

### 6.4 Components
- `Map.tsx` (maplibre-gl): sources `dcs`, `sinks`, `water`, `zones`, `rings`. Layers: `zones-fill` (steam/uten, low alpha), `water-fill`, `sinks-circle` (filtered by `["in", ["get","id"], ["literal", explainIds]]`, colored by cat), `rings-line` (turf.circle at radius_m and radius_m/detour for the selected DC), `dcs-circle` (radius 4–18 px by score rank, color by payback bucket: <5y, 5–10y, >10y, none). Score is pushed with `setFeatureState`. Click DC → `select`. Hover → tooltip name/mw/score.
- `WeightsPanel.tsx`: sliders for each `cat`, `radius_m`, decay, bonuses, `per_sink_cap`, distance model select, water policy select; econ inputs as number fields with units. Buttons: Reset, Copy JSON, Paste JSON (validate via `WasmEngine` round-trip; show error).
- `ResultsTable.tsx`: columns name, region, mw, score, utilization %, delivered MWh, capex ($), savings ($/yr), payback (yrs), top sink. Sortable, sticky header, row click selects.
- `DcDetail.tsx`: selected DC facts + `explain` table (sink, cat, pipe m, HP required/COP, delivered MWh, score) with a monthly supply-vs-demand bar strip (12 bars, computed client-side from PROFILE exported by wasm or duplicated in `types.ts` with a snapshot test).
- `RegionToggle.tsx`.
- Footer: data sources + attribution from `manifest.json`, "indicative, not a feasibility study" disclaimer, link to repo.

### 6.5 Acceptance
- `pnpm build` produces `out/` with no server functions; Lighthouse performance ≥ 80 on desktop.
- Changing any slider re-ranks in < 100 ms perceived; selected DC and explain stay in sync.
- Works with WASM disabled? No — show an explicit error message.
- Deployed to Vercel from `main`; preview deploys on PRs.

## 7. CI (`.github/workflows/ci.yml`)

Jobs: `ingest-test` (uv, pytest, does not hit network — sources are mocked), `core` (cargo fmt --check, clippy -D warnings, test), `wasm` (wasm-pack build, node smoke test), `web` (pnpm lint, typecheck, build). Cache cargo, uv, pnpm. A `data-freshness` job fails if `manifest.json` hash does not match the data files.

## 8. Build order and checkpoints

1. Repo skeleton, Makefile, CI stubs (green on empty).
2. Ingest: OSM + PNNL only, nyc only → `datacenters`/`sinks` files. Checkpoint: files validate, map them in a notebook, sanity-check 5 known sites by name.
3. Core: types, frame, index, distance (Euclid + Detour), scoring without thermo/season/econ. Golden test.
4. Core: thermo, season, econ, water crossing, RotatedL1. Extend golden + proptests.
5. WASM crate + node smoke test.
6. Web: loader, store, map with DC layer, table. Deploy.
7. Web: weights panel, explain, detail, rings, zones.
8. Ingest: PLUTO, LL84 join, parcels, water, zones; rerun; regenerate hashes; redeploy.
9. README with methodology, every default constant and its rationale, known limitations.

## 9. Known limitations to state in README (do not silently fix)

Straight-line/detour pipe lengths; per-sink pipe cost over-counts shared trunks; MW estimates for most sites; cooling type unknown for nearly all sites; LL84 covers only buildings ≥ 25k sq ft; OSM sink coverage is uneven upstate; steam territory and UTEN polygons are approximations; no temperature modeling beyond a fixed lookup; no consideration of existing heat pump/cooling contracts, easements, or regulatory approval.
