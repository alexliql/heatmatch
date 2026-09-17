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


def write_features(name: str, features: list[dict]) -> dict:
    """Write an already-built feature list (water and zones, which are polygons
    rather than model instances)."""
    body = canonical({"type": "FeatureCollection", "features": features})
    digest = hashlib.sha256(body.encode()).hexdigest()
    DATA.mkdir(parents=True, exist_ok=True)
    for old in DATA.glob(f"{name}.*.geojson"):
        old.unlink()
    path = DATA / f"{name}.{digest[:8]}.geojson"
    path.write_text(body)
    return {"file": path.name, "count": len(features), "hash": digest}


def write_json(name: str, payload: dict) -> dict:
    """Write data/<name>.<hash8>.json; return its manifest entry.

    For assets that are not feature collections — the seasonal profile table is
    the first. `count` is the number of top-level keys, which for profiles is
    the number of regions that model their own shapes.
    """
    body = canonical(payload)
    digest = hashlib.sha256(body.encode()).hexdigest()
    DATA.mkdir(parents=True, exist_ok=True)
    for old in DATA.glob(f"{name}.*.json"):
        old.unlink()
    path = DATA / f"{name}.{digest[:8]}.json"
    path.write_text(body)
    return {"file": path.name, "count": len(payload), "hash": digest}


def write_manifest(entries: dict[str, dict], sources: list[dict]) -> Path:
    manifest = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **entries,
        "sources": sources,
    }
    path = DATA / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def assign_ids(rows: list[dict], prefix: str, width: int) -> list[tuple[str, dict]]:
    """Number rows within their region, best-effort stable across releases.

    Sorting on position-then-name (§3.2) is what makes ids reproducible: the
    upstream file's row order is not guaranteed stable between releases. The
    region goes in the id rather than in a single global counter so that adding
    a region cannot renumber the ones already published — Virginia sorts south
    of every New York site, and a global counter would have shifted all of them.
    """
    rows.sort(key=lambda r: (r["region"], r["lat"], r["lon"], r["name"]))
    out: list[tuple[str, dict]] = []
    seen: dict[str, int] = {}
    for row in rows:
        region = row["region"]
        i = seen.get(region, 0)
        seen[region] = i + 1
        out.append((f"{prefix}_{region}_{i:0{width}d}", row))
    return out
