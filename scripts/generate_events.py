#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted event data."""

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


def render_description_html(desc: str) -> str:
    """Convert game rich text tags to HTML."""
    html = desc
    html = re.sub(r"\[gold\](.*?)\[/gold\]", r'<span class="desc-gold">\1</span>', html)
    html = re.sub(r"\[red\](.*?)\[/red\]", r'<span class="desc-red">\1</span>', html)
    html = re.sub(r"\[blue\](.*?)\[/blue\]", r'<span class="desc-blue">\1</span>', html)
    html = re.sub(r"\[green\](.*?)\[/green\]", r'<span class="desc-green">\1</span>', html)
    html = re.sub(r"\[/?(?:sine|wave|shake|b|i|jitter)\]", "", html)
    html = html.replace("\n", "<br>")
    return html


def strip_tags(desc: str) -> str:
    """Strip game rich text tags for plain text."""
    return re.sub(r"\[/?[^\]]*\]", "", desc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate event content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/events/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "events.json")) as f:
        events = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for event in events:
        slug = slugify(event.get("title", event["class_name"]))
        desc = event.get("description", "")
        conditions = event.get("conditions", [])
        conditions_str = "; ".join(conditions) if conditions else ""

        lines = ["---"]
        lines.append(f"title: {escape_yaml(event.get('title', event['class_name']))}")
        lines.append(f"class_name: {escape_yaml(event['class_name'])}")
        lines.append(f"description_plain: {escape_yaml(strip_tags(desc))}")
        lines.append(f"description_html: {escape_yaml(render_description_html(desc))}")
        lines.append(f"options: {json.dumps(event.get('options', []))}")
        lines.append(f"acts: {json.dumps(event.get('acts', []))}")
        lines.append(f"conditions: {escape_yaml(conditions_str)}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{event['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} event pages in {output_dir}")


if __name__ == "__main__":
    main()
