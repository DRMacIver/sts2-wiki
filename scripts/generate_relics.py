#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted relic data."""

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
    parser = argparse.ArgumentParser(description="Generate relic content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/relics/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "relics.json")) as f:
        relics = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for relic in relics:
        slug = slugify(relic["title"])

        from scripts.common import rich_text_to_html, strip_rich_text

        raw_desc = relic.get("description", "")
        # Substitute vars into description
        for v in relic.get("vars", []):
            vtype = v["type"]
            val = v["base_value"]
            raw_desc = re.sub(rf"\{{{vtype}(?:Power)?(?::[^}}]*)?\}}", str(val), raw_desc)
        raw_desc = re.sub(r"\{[^}]*\}", "?", raw_desc)

        lines = ["---"]
        lines.append(f"title: {escape_yaml(relic['title'])}")
        lines.append(f"class_name: {escape_yaml(relic['class_name'])}")
        lines.append(f"rarity: {escape_yaml(relic.get('rarity', 'Unknown'))}")
        lines.append(f"pool: {escape_yaml(relic.get('pool', 'Unknown'))}")
        lines.append(f"image: {escape_yaml(relic.get('image', ''))}")
        lines.append(f"description_plain: {escape_yaml(strip_rich_text(raw_desc))}")
        lines.append(f"description_html: {escape_yaml(rich_text_to_html(raw_desc))}")
        lines.append(f"flavor: {escape_yaml(strip_rich_text(relic.get('flavor', '')))}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{relic['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} relic pages in {output_dir}")


if __name__ == "__main__":
    main()
