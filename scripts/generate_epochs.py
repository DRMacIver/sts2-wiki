#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted epoch data."""

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
    parser = argparse.ArgumentParser(description="Generate epoch content files")
    parser.add_argument("data_dir")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "epochs.json")) as f:
        epochs = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for epoch in epochs:
        slug = slugify(epoch.get("id", epoch["class_name"]))

        lines = ["---"]
        lines.append(f"title: {escape_yaml(epoch.get('title', epoch['class_name']))}")
        lines.append(f"class_name: {escape_yaml(epoch['class_name'])}")
        lines.append(f"epoch_id: {escape_yaml(epoch.get('id', ''))}")
        lines.append(f"era: {escape_yaml(epoch.get('era', ''))}")
        lines.append(f"era_position: {epoch.get('era_position', 0)}")
        lines.append(f"story: {escape_yaml(epoch.get('story', ''))}")
        from scripts.common import rich_text_to_html

        raw_desc = epoch.get("description", "")
        lines.append(f"description: {escape_yaml(raw_desc)}")
        lines.append(f"description_html: {escape_yaml(rich_text_to_html(raw_desc))}")
        # Image filename: class_name to snake_case
        image = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", epoch["class_name"])
        image = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", image).lower()
        lines.append(f"image: {escape_yaml(image)}")
        lines.append(f"unlocks_cards: {json.dumps(epoch.get('unlocks_cards', []))}")
        lines.append(f"unlocks_relics: {json.dumps(epoch.get('unlocks_relics', []))}")
        lines.append(f"unlocks_events: {json.dumps(epoch.get('unlocks_events', []))}")
        lines.append(f"unlocks_encounters: {json.dumps(epoch.get('unlocks_encounters', []))}")
        lines.append(f"unlocks_potions: {json.dumps(epoch.get('unlocks_potions', []))}")
        lines.append(f"unlocks_ancients: {json.dumps(epoch.get('unlocks_ancients', []))}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} epoch pages in {output_dir}")


if __name__ == "__main__":
    main()
