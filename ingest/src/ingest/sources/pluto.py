"""NYC tax lots, for data center candidates and for the LL84 join.

Queries the PLUTO table through NYC Open Data's API rather than downloading
the MapPLUTO shapefile: it carries a lot centroid and the BBL already, so
the hundreds of megabytes of lot geometry in MapPLUTO would be downloaded and
then thrown away.
"""

import json
from collections.abc import Iterator, Sequence

from ingest.config import (
    CARRIER_HOTEL_ADDRESSES,
    DC_OPERATOR_NAMES,
    MAX_ESTIMATED_DC_MW,
    MW_PER_SQFT,
    PLUTO_BLDG_CLASS_PREFIXES,
    PLUTO_SOURCE,
    PLUTO_URL,
    RegionName,
    region_for,
)
from ingest.sources.boundary import in_region_boundary
from ingest.sources.fetch import cached_get

_FIELDS = "bbl,address,ownername,bldgclass,bldgarea,numfloors,latitude,longitude"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _candidate_where() -> str:
    """SoQL for lots that might be data centers.

    Either the building class says industrial/utility and the owner looks like
    an operator, or the address is a known carrier hotel — those sit in ordinary
    office classes and the class filter alone would miss them.
    """
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

    from urllib.parse import quote

    rows = _rows(
        {"$select": _FIELDS, "$where": quote(_candidate_where()), "$limit": "5000"},
        "pluto_datacenters.json",
        refresh=refresh,
    )

    # One address can span several tax lots, and a carrier hotel's other
    # tenants own some of them; keep only the largest lot per address so a
    # building is not counted once per occupant.
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
        if region_for(lat, lon) != "nyc" or not in_region_boundary(lat, lon, "nyc"):
            continue

        area = float(row.get("bldgarea") or 0)
        if area <= 0:
            continue
        # A tax lot's owner is often a holding company ("One City Block LLC"),
        # which names nothing a reader would recognise. The street address does,
        # so lead with it and add the operator only when it is a known brand.
        address = (row.get("address") or "").strip().title()
        owner = (row.get("ownername") or "").strip().upper()
        brand = next((b for b in DC_OPERATOR_NAMES if b in owner), None)
        name = f"{brand.title()} — {address}" if brand and address else (address or owner.title())

        yield {
            "name": name or "Unnamed data center",
            "region": "nyc",
            "lat": lat,
            "lon": lon,
            # NYC-only source, so the nyc ceiling is the right one.
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
    """Tax lots within roughly `radius_m` of any anchor, for the LL84 join.

    Filtered by a latitude/longitude box per anchor rather than a true radius:
    PLUTO exposes the centroid as two numeric columns, not a geo point.
    """
    if not anchors:
        return []
    from urllib.parse import quote

    deg_lat = radius_m / 111_320.0
    out: dict[str, dict] = {}

    for i, (lat, lon) in enumerate(anchors):
        deg_lon = deg_lat / max(0.1, abs(__import__("math").cos(__import__("math").radians(lat))))
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
