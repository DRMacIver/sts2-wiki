"""Single source of truth for wiki versions, derived from data/ directories.

Every place that needs version information (justfile default, build-all-versions,
site fallbacks in BaseLayout/index) derives it from the set of data/vX.Y.Z
directories via this module, so adding a new patch requires no manual version
edits.

Usage:
    uv run python -m scripts.versions --latest      # print latest version
    uv run python -m scripts.versions --all-desc    # comma list, newest first
    uv run python -m scripts.versions --list-asc    # space list, oldest first
    uv run python -m scripts.versions --write       # write site/src/versions.json
"""

import argparse
import re
from pathlib import Path

from scripts.common import write_json

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def version_key(version: str) -> tuple[int, int, int]:
    """Sort key for vX.Y.Z version strings."""
    m = VERSION_RE.match(version)
    if m is None:
        raise ValueError(f"Not a vX.Y.Z version string: {version!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def all_versions(data_dir: str = "data") -> list[str]:
    """All extracted versions, oldest first, from data/ subdirectories."""
    versions = [p.name for p in Path(data_dir).iterdir() if p.is_dir() and VERSION_RE.match(p.name)]
    if not versions:
        raise SystemExit(f"No vX.Y.Z directories found under {data_dir}/")
    return sorted(versions, key=version_key)


def latest_version(data_dir: str = "data") -> str:
    """The newest extracted version."""
    return all_versions(data_dir)[-1]


def write_versions_json(data_dir: str = "data", out_path: str = "site/src/versions.json") -> None:
    """Write the committed versions manifest used as the site's fallback."""
    versions = all_versions(data_dir)
    write_json(out_path, {"latest": versions[-1], "all": list(reversed(versions))})
    print(f"Wrote {out_path}: latest={versions[-1]}, {len(versions)} versions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--latest", action="store_true", help="print latest version")
    mode.add_argument("--previous", action="store_true", help="print second-latest version")
    mode.add_argument("--all-desc", action="store_true", help="print comma list, newest first")
    mode.add_argument("--list-asc", action="store_true", help="print space list, oldest first")
    mode.add_argument("--write", action="store_true", help="write site/src/versions.json")
    args = parser.parse_args()

    if args.latest:
        print(latest_version(args.data_dir))
    elif args.previous:
        versions = all_versions(args.data_dir)
        if len(versions) < 2:
            raise SystemExit("No previous version exists")
        print(versions[-2])
    elif args.all_desc:
        print(",".join(reversed(all_versions(args.data_dir))))
    elif args.list_asc:
        print(" ".join(all_versions(args.data_dir)))
    else:
        write_versions_json(args.data_dir)


if __name__ == "__main__":
    main()
