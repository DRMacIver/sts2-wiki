#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted power data."""

import argparse
import json
import os
import re
from pathlib import Path


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def escape_yaml(value: str) -> str:
    """Escape a string for YAML frontmatter."""
    if not value:
        return '""'
    if value.lower() in ("null", "true", "false", "yes", "no", "on", "off", "~"):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


def render_description_html(desc: str) -> str:
    """Convert game rich text tags to HTML."""
    from scripts.common import rich_text_to_html

    return rich_text_to_html(desc)


def strip_tags(desc: str) -> str:
    """Strip game rich text tags for plain text."""
    return re.sub(r"\[/?[^\]]*\]", "", desc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate power content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/powers/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    powers_path = os.path.join(data_dir, "powers.json")
    with open(powers_path) as f:
        powers = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for power in powers:
        slug = slugify(power["title"])
        desc = power.get("description", "")
        smart_desc = power.get("smart_description", "")

        lines = ["---"]
        lines.append(f"title: {escape_yaml(power['title'])}")
        lines.append(f"class_name: {escape_yaml(power['class_name'])}")
        lines.append(f"power_type: {escape_yaml(power.get('type', 'None'))}")
        lines.append(f"stack_type: {escape_yaml(power.get('stack_type', 'None'))}")
        lines.append(f"description_plain: {escape_yaml(strip_tags(desc))}")
        lines.append(f"description_html: {escape_yaml(render_description_html(desc))}")
        lines.append(f"smart_description: {escape_yaml(strip_tags(smart_desc))}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{power['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} power pages in {output_dir}")


if __name__ == "__main__":
    main()
