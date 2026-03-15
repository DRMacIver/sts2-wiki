#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted character data."""

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
    parser = argparse.ArgumentParser(description="Generate character content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/characters/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "characters.json")) as f:
        characters = json.load(f)

    # Load card and relic data for cross-referencing
    card_titles: dict[str, str] = {}
    cards_path = os.path.join(data_dir, "cards.json")
    if os.path.exists(cards_path):
        with open(cards_path) as f:
            cards = json.load(f)
        for c in cards:
            card_titles[c["class_name"]] = c.get("title", c["class_name"])

    relic_titles: dict[str, str] = {}
    relics_path = os.path.join(data_dir, "relics.json")
    if os.path.exists(relics_path):
        with open(relics_path) as f:
            relics = json.load(f)
        for r in relics:
            relic_titles[r["class_name"]] = r.get("title", r["class_name"])

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for char in characters:
        slug = slugify(char["class_name"])

        # Resolve starting deck titles
        deck_refs = []
        for card_class in char.get("starting_deck", []):
            title = card_titles.get(card_class, card_class)
            deck_refs.append({"class_name": card_class, "title": title, "slug": slugify(title)})

        # Resolve starting relic
        relic_class = char.get("starting_relic", "")
        relic_title = relic_titles.get(relic_class, relic_class)
        relic_ref = {
            "class_name": relic_class,
            "title": relic_title,
            "slug": slugify(relic_title),
        }

        lines = ["---"]
        lines.append(f"title: {escape_yaml(char['title'])}")
        lines.append(f"class_name: {escape_yaml(char['class_name'])}")
        lines.append(f"description: {escape_yaml(char.get('description', ''))}")
        lines.append(f"aroma: {escape_yaml(char.get('aroma', ''))}")
        lines.append(f"starting_hp: {char.get('starting_hp', 0)}")
        lines.append(f"starting_gold: {char.get('starting_gold', 0)}")
        if "orb_slots" in char:
            lines.append(f"orb_slots: {char['orb_slots']}")
        lines.append(f"starting_relic: {json.dumps(relic_ref)}")
        lines.append(f"starting_deck: {json.dumps(deck_refs)}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} character pages in {output_dir}")


if __name__ == "__main__":
    main()
