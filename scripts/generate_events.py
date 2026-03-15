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
    from scripts.common import rich_text_to_html

    return rich_text_to_html(desc)


def strip_tags(desc: str) -> str:
    """Strip game rich text tags for plain text."""
    from scripts.common import strip_rich_text

    return strip_rich_text(desc)


# Hand-written enrichments for events whose descriptions/options are
# defined in code rather than localization data.
_EVENT_ENRICHMENTS: dict[str, dict] = {
    "FakeMerchant": {
        "description": (
            "A suspicious merchant has laid out a rug covered in relics. "
            "They look familiar, but something is off about them...\n\n"
            "The merchant sells [gold]fake relics[/gold] — weaker versions "
            "of real relics — for [gold]50 gold[/gold] each. "
            "Up to 6 are available from a pool of 9.\n\n"
            "If you have a [purple]Foul Potion[/purple], you can throw it "
            "at the merchant to trigger a fight. Defeating The Merchant??? "
            "(175 HP) rewards [gold]300 gold[/gold], "
            "[gold]The Merchant's Rug[/gold] relic, and any unsold fake relics."
        ),
        "options": [
            {
                "title": "Browse Wares",
                "description": (
                    "View and buy [gold]fake relics[/gold] for "
                    "[gold]50 gold[/gold] each. These are weaker versions "
                    "of existing relics (e.g. Strike Dummy??? deals 1 extra "
                    "damage instead of 3)."
                ),
            },
            {
                "title": "Throw [purple]Foul Potion[/purple]",
                "description": (
                    "Requires a Foul Potion. Initiates combat with "
                    "The Merchant??? (175 HP). Rewards: "
                    "[gold]300 gold[/gold], [gold]The Merchant's Rug???[/gold], "
                    "and all remaining unsold fake relics."
                ),
            },
            {
                "title": "Leave",
                "description": "Walk away.",
            },
        ],
    },
}


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

        # Skip placeholder descriptions
        if desc.lower() in ("placeholder", "todo", "tbd"):
            desc = ""

        # Enrich events with code-defined descriptions and options
        enrichments = _EVENT_ENRICHMENTS.get(event["class_name"])
        if enrichments:
            if not desc and enrichments.get("description"):
                desc = enrichments["description"]
            if not event.get("options") and enrichments.get("options"):
                event["options"] = enrichments["options"]

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
