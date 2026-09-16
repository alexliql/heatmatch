"""Verify data/manifest.json matches the files it names (spec §7).

Each asset is recorded with a sha256 over its bytes; the filename embeds the
first 8 hex chars. Both must agree, or the committed data was hand-edited
without rerunning `make ingest`.
"""

import hashlib
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ASSETS = ("datacenters", "sinks", "water", "zones")


def main() -> int:
    manifest_path = DATA / "manifest.json"
    if not manifest_path.exists():
        print("manifest.json not present yet — data pipeline has not been run (T2/T8)")
        return 0

    manifest = json.loads(manifest_path.read_text())
    errors = []
    for key in ASSETS:
        entry = manifest.get(key)
        if entry is None:
            errors.append(f"{key}: missing from manifest")
            continue
        path = DATA / entry["file"]
        if not path.exists():
            errors.append(f"{key}: {entry['file']} named in manifest but not on disk")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["hash"]:
            errors.append(f"{key}: {entry['file']} hash {digest[:8]} != manifest {entry['hash'][:8]}")
        elif digest[:8] not in path.name:
            errors.append(f"{key}: filename {path.name} does not embed hash {digest[:8]}")

    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"manifest.json consistent across {len(ASSETS)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
