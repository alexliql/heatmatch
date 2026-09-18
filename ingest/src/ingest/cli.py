"""`ingest run --region <name>|all`. The no-op callback keeps Typer from
collapsing the single command into the root."""

import json
from collections import Counter

import typer

from ingest.config import (
    ATLAS_SOURCE,
    COMSTOCK_REGIONS,
    LL84_SOURCE,
    NYS_BOUNDARY_SOURCE,
    OVERPASS_SOURCE,
    PLUTO_SOURCE,
    REGIONS,
    RegionName,
)
from ingest.merge import datacenters, emit, sinks
from ingest.sources import ab802, comstock, curated_mw, hydro, nys_parcels, seattle_bench, seed_dcs
from ingest.sources.zones import ZONE_FILES
from ingest.util import MANUAL

app = typer.Typer(help="Build heatmatch's static data assets.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Build heatmatch's static data assets."""


def _resolve(region: str) -> list[RegionName]:
    if region == "all":
        return list(REGIONS)  # type: ignore[arg-type]
    if region not in REGIONS:
        known = ", ".join(REGIONS)
        raise typer.BadParameter(f"unknown region {region!r}; expected one of {known}, or all")
    return [region]  # type: ignore[list-item]


def _check_writable(region: str, write: bool) -> None:
    """Refuse a partial run that would publish an incomplete bundle: the bundle
    is one flat set of files, so a one-region run silently drops the others.
    A named function so the message can be tested without Rich's wrapping."""
    if write and region != "all":
        raise typer.BadParameter(
            f"--region {region} would rewrite the whole bundle with only {region} in it, "
            "dropping every other region. Use --region all to publish, or add --no-write "
            "to build and summarise without touching data/."
        )


@app.command()
def run(
    region: str = typer.Option("all", help=f"{' | '.join(REGIONS)} | all"),
    refresh: bool = typer.Option(False, help="Re-download sources instead of using raw/ cache."),
    write: bool = typer.Option(
        True,
        help="Write data/. Refused for a partial region unless --no-write is what you meant.",
    ),
) -> None:
    """Rebuild data/*.geojson and data/manifest.json for the given region(s)."""
    regions = _resolve(region)
    _check_writable(region, write)
    typer.echo(f"regions: {', '.join(regions)}")

    dcs, curated = datacenters.build(regions, refresh=refresh)
    typer.echo(f"data centers: {len(dcs)}")
    if curated["rows"]:
        typer.echo(
            f"curated capacities: {curated['rows']} rows -> {curated['buildings']} buildings"
            + (f", {curated['unmatched']} matched nothing" if curated["unmatched"] else "")
        )

    sink_rows, stats = sinks.build(regions, dcs, refresh=refresh)
    typer.echo(f"sinks: {len(sink_rows)} kept of {stats['fetched']} fetched")

    water_features: list[dict] = []
    for r in regions:
        anchors = [(d.lat, d.lon) for d in dcs if d.region == r]
        cutoff = sinks.cutoff_m(r)
        water_features += hydro.to_features(hydro.polygons(r, anchors, cutoff, refresh=refresh))
    typer.echo(f"water polygons: {len(water_features)}")

    if not write:
        _summary(regions, dcs, sink_rows, stats)
        typer.echo("--no-write: data/ left untouched")
        return

    entries = {
        "datacenters": emit.write_collection("datacenters", dcs),
        "sinks": emit.write_collection("sinks", sink_rows),
        "water": emit.write_features("water", water_features),
        "zones": emit.write_features("zones", zones_features()),
    }
    # Only regions that model their own seasonality; the engine fills the rest.
    profiles = {
        r: comstock.profiles_for_region(comstock.build(r, refresh=refresh)["by_type"])
        for r in regions
        if r in COMSTOCK_REGIONS
    }
    profiles = {r: p for r, p in profiles.items() if p}
    if profiles:
        entries["profiles"] = emit.write_json("profiles", profiles)
    for path in comstock.write_derived(regions, refresh=refresh):
        typer.echo(f"  derived      {path.name}")
    path = emit.write_manifest(
        entries,
        [
            ATLAS_SOURCE,
            OVERPASS_SOURCE,
            NYS_BOUNDARY_SOURCE,
            PLUTO_SOURCE,
            LL84_SOURCE,
            nys_parcels.PARCELS_SOURCE,
            comstock.COMSTOCK_SOURCE,
            curated_mw.CURATED_MW_SOURCE,
            seed_dcs.SEED_DCS_SOURCE,
            seattle_bench.SEATTLE_BENCH_SOURCE,
            ab802.AB802_SOURCE,
            *NOT_USED,
        ],
    )

    _summary(regions, dcs, sink_rows, stats)
    for key, entry in entries.items():
        typer.echo(f"  {key:12s} {entry['file']}  ({entry['count']} features)")
    typer.echo(f"  manifest     {path.name}")


# Measured-demand sources checked and deliberately not used, recorded in the
# manifest next to the ones that were.
NOT_USED = [
    {
        "id": "pdx_bench",
        "url": "https://www.portland.gov/bps/climate-action/energy-reporting",
        "license": "public-domain",
        "status": "not_used",
        "note": (
            "City of Portland Energy Performance Reporting does break out natural gas, but "
            "publishes addresses and tax-lot ids with no coordinates, and covers Portland city "
            "limits only — the data centers are in Hillsboro. Portland sinks are ComStock-modelled."
        ),
    },
    {
        "id": "la_ebewe",
        "url": "https://data.lacity.org/d/9yda-i4ya",
        "license": "public-domain",
        "status": "not_used",
        "note": (
            "City of Los Angeles EBEWE disclosure carries site and source EUI only, with no fuel "
            "breakdown and no coordinates. AB 802 covers Los Angeles buildings of 50,000 sq ft "
            "and up with separate fuel fields and geocodes, and is used instead."
        ),
    },
    {
        "id": "wa_clean_buildings",
        "url": "https://www.commerce.wa.gov/growing-the-economy/energy/buildings/clean-buildings-standards/",
        "license": "unknown",
        "status": "not_used_unverified",
        "note": "Washington Clean Buildings Performance Standard; per-building public disclosure not verified.",
    },
    {
        "id": "or_bps",
        "url": "https://www.oregon.gov/energy/save-energy/Pages/BPS.aspx",
        "license": "unknown",
        "status": "not_used_unverified",
        "note": "Oregon Building Performance Standard; per-building public disclosure not verified.",
    },
]


def zones_features() -> list[dict]:
    """Steam and thermal-network polygons for the map: the same files `zones.tag`
    reads, so what is drawn and what scores cannot drift apart."""
    out: list[dict] = []
    for name, kind in ZONE_FILES:
        path = MANUAL / name
        if not path.exists():
            continue
        for f in json.loads(path.read_text()).get("features", []):
            f.setdefault("properties", {})["kind"] = kind
            out.append(f)
    return out


def _summary(regions, dcs, sink_rows, stats) -> None:
    typer.echo("")
    for r in regions:
        r_dcs = [d for d in dcs if d.region == r]
        r_sinks = [s for s in sink_rows if s.region == r]
        mw = sum(d.mw for d in r_dcs)
        gwh = sum(s.demand_kwh for s in r_sinks) / 1e6
        typer.echo(
            f"[{r}] {len(r_dcs)} data centers, {mw:.1f} MW | {len(r_sinks)} sinks, {gwh:.1f} GWh"
        )
        for cat, n in sorted(Counter(s.cat for s in r_sinks).items()):
            typer.echo(f"      {cat:24s} {n:5d}")
        by_src = Counter(s.demand_source for s in r_sinks)
        typer.echo(f"      demand sources: {dict(by_src)}")
        by_conf = Counter(d.mw_confidence for d in r_dcs)
        if r_dcs:
            graded = sum(d.mw for d in r_dcs if d.mw_confidence in ("reported", "filed"))
            share = 100 * graded / mw if mw else 0.0
            typer.echo(f"      capacity confidence: {dict(by_conf)} ({share:.0f}% of MW stated)")
    typer.echo(
        f"dropped: {stats['dropped_far']} too far, "
        f"{stats['dropped_steam_heated']} steam-heated | LL84 joined: {stats['ll84_joined']}"
        f" | benchmarking joined: {stats['bench_joined']}"
        f" | measurements overruled as near-zero: {stats['measured_fuel_near_zero']}"
    )
    typer.echo("")
