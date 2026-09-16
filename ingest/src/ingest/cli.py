"""`ingest run --region nyc|upstate|all` — see HEATMATCH.md §3.4.

Source modules land in T2 (OSM + PNNL, nyc) and T8 (PLUTO, LL84, parcels,
water, zones); this is the entry point they will hang off.
"""

import typer

app = typer.Typer(help="Build heatmatch's static data assets.")


@app.command()
def run(region: str = typer.Option("all", help="nyc | upstate | all")) -> None:
    """Rebuild data/*.geojson and data/manifest.json for the given region(s)."""
    raise NotImplementedError("source pipeline lands in T2")
