#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted monster data."""

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
    parser = argparse.ArgumentParser(description="Generate monster content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/monsters/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load monster data
    with open(os.path.join(data_dir, "monsters.json")) as f:
        monsters = json.load(f)

    # Load encounter data for cross-referencing
    encounter_lookup: dict[str, list[dict]] = {}
    encounters_path = os.path.join(data_dir, "encounters.json")
    if os.path.exists(encounters_path):
        with open(encounters_path) as f:
            encounters = json.load(f)
        for enc in encounters:
            for m_class in enc.get("monsters", []):
                if m_class not in encounter_lookup:
                    encounter_lookup[m_class] = []
                # Deduplicate by encounter class_name
                enc_ref = {
                    "class_name": enc["class_name"],
                    "title": enc.get("title", enc["class_name"]),
                    "slug": slugify(enc.get("title", enc["class_name"])),
                }
                if not any(
                    e["class_name"] == enc_ref["class_name"] for e in encounter_lookup[m_class]
                ):
                    encounter_lookup[m_class].append(enc_ref)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for monster in monsters:
        slug = slugify(monster["title"])

        # Build encounter cross-refs
        enc_refs = encounter_lookup.get(monster["class_name"], [])

        is_companion = monster.get("is_companion", False)

        lines = ["---"]
        lines.append(f"title: {escape_yaml(monster['title'])}")
        lines.append(f"class_name: {escape_yaml(monster['class_name'])}")
        lines.append(f"min_hp: {monster.get('min_hp', 0)}")
        lines.append(f"max_hp: {monster.get('max_hp', 0)}")
        lines.append(f"is_companion: {str(is_companion).lower()}")
        lines.append(f"moves: {json.dumps(monster.get('moves', []))}")
        lines.append(f"powers_on_spawn: {json.dumps(monster.get('powers_on_spawn', []))}")
        lines.append(f"encounters: {json.dumps(enc_refs)}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{monster['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} monster pages in {output_dir}")


if __name__ == "__main__":
    main()
