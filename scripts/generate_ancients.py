#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted ancient data."""

import argparse
import json
import os
import re
from pathlib import Path


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def escape_yaml(value: str) -> str:
    if not value:
        return '""'
    if value.lower() in ("null", "true", "false", "yes", "no", "on", "off", "~"):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ancient content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/ancients/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "ancients.json")) as f:
        ancients = json.load(f)

    # Load relic data for resolved descriptions
    relic_descs: dict[str, str] = {}
    relic_desc_by_slug: dict[str, str] = {}
    relics_path = os.path.join(data_dir, "relics.json")
    relics_data: list[dict] = []
    if os.path.exists(relics_path):
        with open(relics_path) as f:
            relics_data = json.load(f)
        from scripts.common import strip_rich_text
        from scripts.generate_relics import _resolve_var

        for relic in relics_data:
            raw_desc = relic.get("description", "")
            var_lookup: dict[str, int] = {}
            for v in relic.get("vars", []):
                var_lookup[v["type"]] = v["base_value"]
                if not v["type"].endswith("Power"):
                    var_lookup[v["type"] + "Power"] = v["base_value"]
            for _ in range(3):
                new_desc = re.sub(
                    r"\{([^{}]*)\}",
                    lambda m: _resolve_var(m.group(0), var_lookup),
                    raw_desc,
                )
                if new_desc == raw_desc:
                    break
                raw_desc = new_desc
            resolved = strip_rich_text(raw_desc)
            relic_descs[relic["class_name"]] = resolved
            relic_desc_by_slug[slugify(relic["class_name"])] = resolved
            relic_desc_by_slug[slugify(relic.get("title", relic["class_name"]))] = resolved

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for ancient in ancients:
        # Skip deprecated
        if "Deprecated" in ancient.get("class_name", ""):
            continue

        slug = slugify(ancient["title"])

        # Update relic offering descriptions with resolved versions
        offerings = ancient.get("relic_offerings", [])
        for offering in offerings:
            rslug = offering.get("slug", "")
            if rslug in relic_desc_by_slug:
                offering["description"] = relic_desc_by_slug[rslug]

        lines = ["---"]
        lines.append(f"title: {escape_yaml(ancient['title'])}")
        lines.append(f"class_name: {escape_yaml(ancient['class_name'])}")
        lines.append(f"epithet: {escape_yaml(ancient.get('epithet', ''))}")
        lines.append(f"relic_offerings: {json.dumps(offerings)}")
        lines.append(f"acts: {json.dumps(ancient.get('acts', []))}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} ancient pages in {output_dir}")


if __name__ == "__main__":
    main()
