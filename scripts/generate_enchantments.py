#!/usr/bin/env python3
"""Generate Astro content collection markdown files for enchantments."""

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
    if value.lower() in (
        "null",
        "true",
        "false",
        "yes",
        "no",
        "on",
        "off",
        "~",
    ):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate enchantment content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument(
        "output_dir",
        help="Path to content/enchantments/ directory",
    )
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "enchantments.json")) as f:
        enchantments = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    from scripts.common import rich_text_to_html, strip_rich_text

    count = 0
    for ench in enchantments:
        slug = slugify(ench["title"])
        desc = ench.get("description", "")

        lines = ["---"]
        lines.append(f"title: {escape_yaml(ench['title'])}")
        lines.append(f"class_name: {escape_yaml(ench['class_name'])}")
        lines.append(f"card_type: {escape_yaml(ench.get('card_type', 'Any'))}")
        lines.append(f"description_plain: {escape_yaml(strip_rich_text(desc))}")
        lines.append(f"description_html: {escape_yaml(rich_text_to_html(desc))}")
        extra = ench.get("extra_card_text", "")
        if extra:
            lines.append(f"extra_card_text: {escape_yaml(strip_rich_text(extra))}")
        restrictions = ench.get("restrictions", [])
        lines.append(f"restrictions: {json.dumps(restrictions)}")
        lines.append(f"stackable: {str(ench.get('stackable', False)).lower()}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} enchantment pages in {output_dir}")


if __name__ == "__main__":
    main()
