#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted encounter data."""

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
    parser = argparse.ArgumentParser(description="Generate encounter content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/encounters/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "encounters.json")) as f:
        encounters = json.load(f)

    # Load monster data for cross-referencing
    monster_titles: dict[str, str] = {}
    monsters_path = os.path.join(data_dir, "monsters.json")
    if os.path.exists(monsters_path):
        with open(monsters_path) as f:
            monsters = json.load(f)
        for m in monsters:
            monster_titles[m["class_name"]] = m["title"]

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for enc in encounters:
        slug = slugify(enc.get("title", enc["class_name"]))

        # Enrich monster list
        monster_refs = []
        for m_class in enc.get("monsters", []):
            m_title = monster_titles.get(m_class, m_class)
            monster_refs.append(
                {
                    "class_name": m_class,
                    "title": m_title,
                    "slug": slugify(m_title),
                }
            )

        lines = ["---"]
        lines.append(f"title: {escape_yaml(enc.get('title', enc['class_name']))}")
        lines.append(f"class_name: {escape_yaml(enc['class_name'])}")
        lines.append(f"room_type: {escape_yaml(enc.get('room_type', 'Monster'))}")
        lines.append(f"is_weak: {str(enc.get('is_weak', False)).lower()}")
        lines.append(f"monsters: {json.dumps(monster_refs)}")
        lines.append(f"tags: {json.dumps(enc.get('tags', []))}")
        lines.append(f"acts: {json.dumps(enc.get('acts', []))}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{enc['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} encounter pages in {output_dir}")


if __name__ == "__main__":
    main()
