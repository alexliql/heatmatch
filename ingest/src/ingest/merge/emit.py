"""Canonical GeoJSON/manifest writing (HEATMATCH.md §3.2).

Output must be byte-identical across runs for the same input: the filename
embeds a content hash, and CI's data-freshness job compares the two.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[4] / "data"
COORD_DECIMALS = 6


def to_feature(model: BaseModel) -> dict:
    props = model.model_dump()
    lon = round(props.pop("lon"), COORD_DECIMALS)
    lat = round(props.pop("lat"), COORD_DECIMALS)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


def canonical(collection: dict) -> str:
    """Stable serialization: sorted keys, fixed separators, no trailing space."""
    return json.dumps(collection, sort_keys=True, separators=(",", ":")) + "\n"


def write_collection(name: str, models: list[BaseModel]) -> dict:
    """Write data/<name>.<hash8>.geojson; return its manifest entry.

    Any previous build of the same asset is removed, otherwise stale hashed
    files accumulate and the web app cannot tell which one is current.
    """
    body = canonical({"type": "FeatureCollection", "features": [to_feature(m) for m in models]})
    digest = hashlib.sha256(body.encode()).hexdigest()
    DATA.mkdir(parents=True, exist_ok=True)
    for old in DATA.glob(f"{name}.*.geojson"):
        old.unlink()
    path = DATA / f"{name}.{digest[:8]}.geojson"
    path.write_text(body)
    return {"file": path.name, "count": len(models), "hash": digest}


def write_manifest(entries: dict[str, dict], sources: list[dict]) -> Path:
    manifest = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **entries,
        "sources": sources,
    }
    path = DATA / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path
