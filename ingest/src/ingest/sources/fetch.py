"""Cached HTTP fetching shared by the source modules.

Everything downloaded lands in ingest/raw/ (gitignored) and is reused on later
runs, so a rerun costs nothing and the test suite never needs the network.
"""

import hashlib
import time
from pathlib import Path

import requests

from ingest.config import USER_AGENT

RAW = Path(__file__).resolve().parents[3] / "raw"


def cached_get(url: str, name: str, *, refresh: bool = False) -> Path:
    """GET `url` into raw/`name`, returning the local path. Cached by default."""
    dest = RAW / name
    if dest.exists() and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
        tmp.replace(dest)
    return dest


def cached_post(
    url: str,
    data: dict[str, str],
    *,
    subdir: str,
    max_retries: int,
    refresh: bool = False,
) -> str:
    """POST with retry/backoff, caching the response body keyed by payload hash.

    Overpass is a shared free service: the cache is what keeps repeated runs
    from re-querying it, and the backoff is what keeps a rate-limit response
    from turning into a hammering loop.
    """
    key = hashlib.sha256(repr(sorted(data.items())).encode()).hexdigest()[:16]
    dest = RAW / subdir / f"{key}.json"
    if dest.exists() and not refresh:
        return dest.read_text()

    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, data=data, headers={"User-Agent": USER_AGENT}, timeout=300)
            # 429/504 are Overpass's "busy, come back later" signals.
            if r.status_code in (429, 504):
                raise requests.HTTPError(f"{r.status_code} rate limited")
            r.raise_for_status()
            dest.write_text(r.text)
            return r.text
        except (requests.RequestException, requests.HTTPError) as exc:
            last = exc
            if attempt < max_retries - 1:
                time.sleep(2**attempt * 5)
    raise RuntimeError(f"request failed after {max_retries} attempts: {last}")
