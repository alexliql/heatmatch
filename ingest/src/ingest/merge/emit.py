"""Canonical GeoJSON/manifest writing.

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


def _write(name: str, ext: str, payload: dict, count: int) -> dict:
    """Write data/<name>.<hash8>.<ext> and return its manifest entry. Any
    previous build of the same asset is removed, or stale hashed files would
    accumulate and the web app could not tell which is current."""
    body = canonical(payload)
    digest = hashlib.sha256(body.encode()).hexdigest()
    DATA.mkdir(parents=True, exist_ok=True)
    for old in DATA.glob(f"{name}.*.{ext}"):
        old.unlink()
    path = DATA / f"{name}.{digest[:8]}.{ext}"
    path.write_text(body)
    return {"file": path.name, "count": count, "hash": digest}


def write_collection(name: str, models: list[BaseModel]) -> dict:
    return write_features(name, [to_feature(m) for m in models])


def write_features(name: str, features: list[dict]) -> dict:
    """Water and zones arrive as polygon features rather than model instances."""
    return _write(
        name, "geojson", {"type": "FeatureCollection", "features": features}, len(features)
    )


def write_json(name: str, payload: dict) -> dict:
    """A non-GeoJSON asset such as the profile table; `count` is its top-level keys."""
    return _write(name, "json", payload, len(payload))


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
    """Number rows within their region by position then name, so ids do not
    depend on upstream row order and adding a region cannot renumber another."""
    rows.sort(key=lambda r: (r["region"], r["lat"], r["lon"], r["name"]))
    out: list[tuple[str, dict]] = []
    seen: dict[str, int] = {}
    for row in rows:
        region = row["region"]
        i = seen.get(region, 0)
        seen[region] = i + 1
        out.append((f"{prefix}_{region}_{i:0{width}d}", row))
    return out
