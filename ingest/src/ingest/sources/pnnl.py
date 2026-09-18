"""Data centers from the IM3 Open Source Data Center Atlas (PNNL, hence the
module name). It carries no capacity field, and its `sqft` is an
OpenStreetMap footprint, not floor area, so MW is estimated at the
per-region footprint density."""

import json
from collections.abc import Iterator

from ingest.config import (
    ATLAS_SOURCE,
    ATLAS_URL,
    DEFAULT_DC_MW,
    MAX_ESTIMATED_DC_MW,
    MW_PER_SQFT_BY_REGION,
    REGIONS,
    RegionName,
)
from ingest.sources.boundary import in_region
from ingest.sources.fetch import cached_get


def _name_of(props: dict) -> str:
    """Atlas rows may carry name, operator, both or neither."""
    for key in ("name", "operator"):
        value = props.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return "Unnamed data center"


def candidates(region: RegionName, *, refresh: bool = False) -> Iterator[dict]:
    """Raw candidates for `region`; ids are assigned later, once the full set
    can be sorted into a stable order."""
    path = cached_get(ATLAS_URL, "im3_datacenter_centroids.geojson", refresh=refresh)
    features = json.loads(path.read_text())["features"]

    state = REGIONS[region]["state_abb"]
    per_sqft = MW_PER_SQFT_BY_REGION[region]
    cap = MAX_ESTIMATED_DC_MW[region]

    for feat in features:
        props = feat.get("properties") or {}
        if str(props.get("state_abb", "")).upper() != state:
            continue
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = (float(c) for c in geom["coordinates"][:2])
        if not in_region(lat, lon, region):
            continue

        sqft = props.get("sqft")
        if sqft and float(sqft) > 0:
            mw = min(float(sqft) * per_sqft, cap)
            mw_source = "atlas_sqft"
        else:
            mw, mw_source = DEFAULT_DC_MW, "atlas_default"

        yield {
            "name": _name_of(props),
            "region": region,
            "lat": lat,
            "lon": lon,
            "mw": mw,
            "mw_source": mw_source,
            "cooling": "unknown",
            "sources": [ATLAS_SOURCE["id"]],
        }
