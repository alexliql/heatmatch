"""NYC tax lots via the PLUTO API, for data center candidates and the LL84
join. The table already carries a lot centroid and BBL, so the MapPLUTO
shapefile's geometry is not needed."""

import json
import math
from collections.abc import Iterator, Sequence
from urllib.parse import quote

from ingest.config import (
    CARRIER_HOTEL_ADDRESSES,
    DC_OPERATOR_NAMES,
    MAX_ESTIMATED_DC_MW,
    MW_PER_SQFT,
    PLUTO_BLDG_CLASS_PREFIXES,
    PLUTO_SOURCE,
    PLUTO_URL,
    RegionName,
)
from ingest.sources.boundary import in_region
from ingest.sources.fetch import cached_get

_FIELDS = "bbl,address,ownername,bldgclass,bldgarea,numfloors,latitude,longitude"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _candidate_where() -> str:
    """SoQL for lots that might be data centers: an industrial/utility class
    with an operator-like owner, or a known carrier-hotel address."""
    classes = " OR ".join(f"starts_with(bldgclass, {_quote(p)})" for p in PLUTO_BLDG_CLASS_PREFIXES)
    owners = " OR ".join(
        f"upper(ownername) like {_quote('%' + n + '%')}" for n in DC_OPERATOR_NAMES
    )
    addresses = " OR ".join(f"upper(address) = {_quote(a)}" for a in CARRIER_HOTEL_ADDRESSES)
    return f"(({classes}) AND ({owners})) OR ({addresses})"


def _rows(params: dict[str, str], name: str, *, refresh: bool) -> list[dict]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path = cached_get(f"{PLUTO_URL}?{query}", name, refresh=refresh)
    return json.loads(path.read_text())


def candidates(region: RegionName, *, refresh: bool = False) -> Iterator[dict]:
    """Yield data center candidates from PLUTO. NYC only; upstate uses parcels."""
    if region != "nyc":
        return

    rows = _rows(
        {"$select": _FIELDS, "$where": quote(_candidate_where()), "$limit": "5000"},
        "pluto_datacenters.json",
        refresh=refresh,
    )

    # Keep the largest lot per address, so a carrier hotel is not counted once
    # per tenant.
    largest: dict[str, dict] = {}
    for row in rows:
        key = (row.get("address") or row.get("bbl") or "").strip().upper()
        if not key:
            continue
        if float(row.get("bldgarea") or 0) > float(largest.get(key, {}).get("bldgarea") or 0):
            largest[key] = row

    for row in largest.values():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not in_region(lat, lon, "nyc"):
            continue

        area = float(row.get("bldgarea") or 0)
        if area <= 0:
            continue
        # Owners are often holding companies; lead with the address and add the
        # operator only when it is a known brand.
        address = (row.get("address") or "").strip().title()
        owner = (row.get("ownername") or "").strip().upper()
        brand = next((b for b in DC_OPERATOR_NAMES if b in owner), None)
        name = f"{brand.title()} — {address}" if brand and address else (address or owner.title())

        yield {
            "name": name or "Unnamed data center",
            "region": "nyc",
            "lat": lat,
            "lon": lon,
            "mw": min(area * MW_PER_SQFT, MAX_ESTIMATED_DC_MW["nyc"]),
            "mw_source": "pluto_estimate",
            "cooling": "unknown",
            "sources": [PLUTO_SOURCE["id"]],
            # Kept for dedupe against the Atlas, then dropped before the model.
            "_address": (row.get("address") or "").strip(),
        }


def lots_near(
    anchors: Sequence[tuple[float, float]], radius_m: float, *, refresh: bool = False
) -> list[dict]:
    """Tax lots within a lat/lon box of `radius_m` around any anchor, for the
    LL84 join. PLUTO exposes the centroid as two numeric columns, not a point."""
    if not anchors:
        return []

    deg_lat = radius_m / 111_320.0
    out: dict[str, dict] = {}

    for i, (lat, lon) in enumerate(anchors):
        deg_lon = deg_lat / max(0.1, abs(math.cos(math.radians(lat))))
        where = (
            f"latitude between {lat - deg_lat} and {lat + deg_lat} "
            f"and longitude between {lon - deg_lon} and {lon + deg_lon}"
        )
        rows = _rows(
            {"$select": _FIELDS, "$where": quote(where), "$limit": "50000"},
            f"pluto_lots_{i}_{lat:.4f}_{lon:.4f}.json",
            refresh=refresh,
        )
        for row in rows:
            if row.get("bbl") and row.get("latitude") and row.get("longitude"):
                out[str(row["bbl"])] = row
    return list(out.values())
