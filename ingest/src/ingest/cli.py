"""`ingest run --region nyc|upstate|all` — see HEATMATCH.md §3.4.

The no-op callback is load-bearing: with a single registered command Typer
collapses the group and exposes its options at the root, which would make the
invocation `ingest --region` instead of the specified `ingest run --region`.
"""

from collections import Counter

import typer

from ingest.config import (
    ATLAS_SOURCE,
    NYS_BOUNDARY_SOURCE,
    OVERPASS_SOURCE,
    REGIONS,
    RegionName,
)
from ingest.merge import datacenters, emit, sinks

app = typer.Typer(help="Build heatmatch's static data assets.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Build heatmatch's static data assets."""


def _resolve(region: str) -> list[RegionName]:
    if region == "all":
        return list(REGIONS)  # type: ignore[arg-type]
    if region not in REGIONS:
        raise typer.BadParameter(f"unknown region {region!r}; expected nyc, upstate or all")
    return [region]  # type: ignore[list-item]


@app.command()
def run(
    region: str = typer.Option("all", help="nyc | upstate | all"),
    refresh: bool = typer.Option(False, help="Re-download sources instead of using raw/ cache."),
) -> None:
    """Rebuild data/*.geojson and data/manifest.json for the given region(s)."""
    regions = _resolve(region)
    typer.echo(f"regions: {', '.join(regions)}")

    dcs = datacenters.build(regions, refresh=refresh)
    typer.echo(f"data centers: {len(dcs)}")

    sink_rows, stats = sinks.build(regions, dcs, refresh=refresh)
    typer.echo(f"sinks: {len(sink_rows)} kept of {stats['fetched']} fetched")

    entries = {
        "datacenters": emit.write_collection("datacenters", dcs),
        "sinks": emit.write_collection("sinks", sink_rows),
    }
    # water and zones land in T8; the manifest simply omits them until then.
    path = emit.write_manifest(
        entries, [ATLAS_SOURCE, OVERPASS_SOURCE, NYS_BOUNDARY_SOURCE]
    )

    _summary(regions, dcs, sink_rows, stats)
    for key, entry in entries.items():
        typer.echo(f"  {key:12s} {entry['file']}  ({entry['count']} features)")
    typer.echo(f"  manifest     {path.name}")


def _summary(regions, dcs, sink_rows, stats) -> None:
    typer.echo("")
    for r in regions:
        r_dcs = [d for d in dcs if d.region == r]
        r_sinks = [s for s in sink_rows if s.region == r]
        mw = sum(d.mw for d in r_dcs)
        gwh = sum(s.demand_kwh for s in r_sinks) / 1e6
        typer.echo(f"[{r}] {len(r_dcs)} data centers, {mw:.1f} MW | {len(r_sinks)} sinks, {gwh:.1f} GWh")
        for cat, n in sorted(Counter(s.cat for s in r_sinks).items()):
            typer.echo(f"      {cat:24s} {n:5d}")
        # LL84 joins in T8; until then every sink demand is an estimate.
        by_src = Counter(s.demand_source for s in r_sinks)
        typer.echo(f"      demand sources: {dict(by_src)}")
    typer.echo(f"dropped: {stats['dropped_far']} too far, {stats['dropped_steam_heated']} steam-heated")
    typer.echo("")
