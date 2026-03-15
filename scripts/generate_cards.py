#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted card data."""

import argparse
import json
import os
import re
from pathlib import Path


def slugify(name: str) -> str:
    """Convert a card title to a URL-safe slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def escape_yaml(value: str) -> str:
    """Escape a string for YAML frontmatter."""
    if not value:
        return '""'
    # YAML special values that need quoting
    if value.lower() in ("null", "true", "false", "yes", "no", "on", "off", "~"):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


def generate_card_markdown(card: dict) -> str:
    """Generate a markdown file with YAML frontmatter for a card."""
    lines = ["---"]

    lines.append(f"title: {escape_yaml(card['title'])}")
    lines.append(f"class_name: {escape_yaml(card['class_name'])}")
    lines.append(f"character: {escape_yaml(card.get('character', 'Unknown'))}")
    lines.append(f"energy_cost: {card.get('energy_cost', 0)}")
    lines.append(f"type: {escape_yaml(card.get('type', 'Unknown'))}")
    lines.append(f"rarity: {escape_yaml(card.get('rarity', 'Unknown'))}")
    lines.append(f"target: {escape_yaml(card.get('target', 'None'))}")
    lines.append(f"x_cost: {str(card.get('x_cost', False)).lower()}")
    lines.append(f"pool: {escape_yaml(card.get('character', ''))}")

    # Keywords
    keywords = card.get("keywords", [])
    lines.append(f"keywords: {json.dumps(keywords)}")

    # Vars
    vars_list = card.get("vars", [])
    lines.append(f"vars: {json.dumps(vars_list)}")

    # Descriptions
    lines.append(f"description_plain: {escape_yaml(card.get('description_plain', ''))}")
    lines.append(f"description_html: {escape_yaml(card.get('description_html', ''))}")

    if card.get("upgraded_description_plain"):
        lines.append(
            f"upgraded_description_plain: {escape_yaml(card['upgraded_description_plain'])}"
        )
    if card.get("upgraded_description_html"):
        lines.append(f"upgraded_description_html: {escape_yaml(card['upgraded_description_html'])}")
    if card.get("upgraded_cost") is not None:
        lines.append(f"upgraded_cost: {card['upgraded_cost']}")

    # Referenced powers
    powers = card.get("referenced_powers", [])
    lines.append(f"referenced_powers: {json.dumps(powers)}")

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate card content files")
    parser.add_argument("data_dir", help="Path to versioned data directory (e.g. data/v0.98.2)")
    parser.add_argument("output_dir", help="Path to content/cards/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load card data
    cards_path = os.path.join(data_dir, "cards.json")
    with open(cards_path) as f:
        cards = json.load(f)

    # Clear output directory
    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    # Generate markdown files
    count = 0
    for card in cards:
        # Skip deprecated and mock cards
        if card.get("deprecated") or card.get("mock"):
            continue

        slug = slugify(card["title"])
        md = generate_card_markdown(card)
        filepath = out / f"{slug}.md"

        # Handle duplicate slugs (e.g., Defend Ironclad vs Defend Silent)
        if filepath.exists():
            slug = f"{slug}-{card.get('character', 'unknown').lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text(md)
        count += 1

    print(f"Generated {count} card pages in {output_dir}")


if __name__ == "__main__":
    main()
