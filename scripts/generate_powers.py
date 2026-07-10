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
    from scripts.common import strip_rich_text

    return strip_rich_text(desc)


def resolve_placeholders(desc: str) -> str:
    """Resolve {placeholder} template expressions in a power description.

    Icon tokens ({singleStarIcon} etc.) and icon-producing calls like
    {Amount:energyIcons()} are preserved/normalized so rich_text_to_html can
    render them; unknown value placeholders degrade to "X" or are stripped.
    """
    from scripts.common import _ICON_IMAGES

    for _ in range(3):
        # Resolve innermost {} (empty braces used as value ref in plurals)
        new_desc = desc.replace("{}", "X")
        # Handle {Name:plural:singular|plural} — use the plural form
        new_desc = re.sub(
            r"\{(\w+):plural:([^|]*)\|([^}]*)\}",
            lambda m: m.group(3),
            new_desc,
        )
        # Icon-producing calls: normalize to plain icon tokens
        new_desc = re.sub(r"\{\w+:energyIcons\([^)]*\)\}", "{colorlessEnergyIcon}", new_desc)
        new_desc = re.sub(r"\{\w+:starIcons\([^)]*\)\}", "{singleStarIcon}", new_desc)
        # Then resolve {Amount} etc.
        new_desc = re.sub(r"\{Amount\}", "X", new_desc)
        new_desc = re.sub(r"\{Amount:[^}]*\}", "X", new_desc)
        # Strip any other remaining placeholders — except icon tokens, which
        # rich_text_to_html renders as <img> (stripping them garbles the text)
        new_desc = re.sub(
            r"\{([^}]*)\}",
            lambda m: m.group(0) if m.group(1) in _ICON_IMAGES else "",
            new_desc,
        )
        if new_desc == desc:
            break
        desc = new_desc
    return desc


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

    # Load per-entity JSON overrides
    per_entity_dir = os.path.join(data_dir, "powers")
    if os.path.isdir(per_entity_dir):
        powers_by_class = {p["class_name"]: p for p in powers}
        for fname in os.listdir(per_entity_dir):
            if fname.endswith(".json"):
                with open(os.path.join(per_entity_dir, fname)) as f:
                    entity_data = json.load(f)
                cname = entity_data.get("class_name", fname.removesuffix(".json"))
                if cname in powers_by_class:
                    powers_by_class[cname].update(entity_data)
                else:
                    powers_by_class[cname] = entity_data
        powers = list(powers_by_class.values())

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for power in powers:
        # Fix CamelCase titles that lack localization (a per-entity file may
        # have title: null — fall back to the class name)
        title = power.get("title") or power["class_name"].removesuffix("Power")
        if title == title.replace(" ", "") and any(c.isupper() for c in title[1:]):
            # CamelCase → "Camel Case"
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", title)
        power["title"] = title

        slug = slugify(power["title"])
        desc = power.get("description", "")
        smart_desc = power.get("smart_description", "")

        # Use smart_description as fallback when description is missing or placeholder
        if not desc or desc == "TODO":
            desc = smart_desc

        desc = resolve_placeholders(desc)

        # Keep smart_description as-is; rich_text_to_html handles icon placeholders
        smart_desc_processed = smart_desc

        lines = ["---"]
        lines.append(f"title: {escape_yaml(power['title'])}")
        lines.append(f"class_name: {escape_yaml(power['class_name'])}")
        # LLM writes `power_type`; regex extractor wrote `type`
        ptype = power.get("power_type", power.get("type", "None"))
        lines.append(f"power_type: {escape_yaml(ptype)}")
        lines.append(f"stack_type: {escape_yaml(power.get('stack_type', 'None'))}")
        lines.append(f"description_plain: {escape_yaml(strip_tags(desc))}")
        lines.append(f"description_html: {escape_yaml(render_description_html(desc))}")
        lines.append(f"smart_description: {escape_yaml(smart_desc_processed)}")
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
