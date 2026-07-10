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


def generate_card_markdown(card: dict, power_titles: dict[str, str] | None = None) -> str:
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

    # Star cost (Regent cards)
    if "star_cost" in card and card["star_cost"] is not None:
        lines.append(f"star_cost: {card['star_cost']}")
    if card.get("x_star_cost"):
        lines.append("x_star_cost: true")

    # Keywords
    keywords = card.get("keywords", [])
    lines.append(f"keywords: {json.dumps(keywords)}")

    # Vars
    vars_list = card.get("vars", [])
    lines.append(f"vars: {json.dumps(vars_list)}")

    # Descriptions: LLM's `description` (if present) takes precedence over old
    # `description_plain`/`description_html` from regex extraction.
    from scripts.common import rich_text_to_html, strip_rich_text

    if card.get("description"):
        desc_plain = strip_rich_text(card["description"])
        desc_html = rich_text_to_html(card["description"])
    else:
        desc_plain = card.get("description_plain", "")
        desc_html = card.get("description_html", "")
    lines.append(f"description_plain: {escape_yaml(desc_plain)}")
    lines.append(f"description_html: {escape_yaml(desc_html)}")

    up_plain: str | None
    up_html: str | None
    if card.get("upgraded_description"):
        up_plain = strip_rich_text(card["upgraded_description"])
        up_html = rich_text_to_html(card["upgraded_description"])
    else:
        up_plain = card.get("upgraded_description_plain")
        up_html = card.get("upgraded_description_html")
    if up_plain:
        lines.append(f"upgraded_description_plain: {escape_yaml(up_plain)}")
    if up_html:
        lines.append(f"upgraded_description_html: {escape_yaml(up_html)}")
    if card.get("upgraded_cost") is not None:
        lines.append(f"upgraded_cost: {card['upgraded_cost']}")

    # Referenced powers: filter to real PowerModel entries, look up canonical
    # title/slug from power_titles map. Fall back to CamelCase-split of
    # class_name when title is missing or has no word breaks.
    powers = card.get("referenced_powers", [])
    filtered_powers = []
    for p in powers:
        cname = p.get("class_name", "")
        if not cname.endswith("Power"):
            continue
        title = None
        if power_titles and cname in power_titles:
            title = power_titles[cname]
        if not title:
            title = p.get("title")
        # If title still has no spaces, split the class_name on camelCase boundaries
        # (covers cases where the raw localization title is e.g. "DyingStar").
        if not title or " " not in title:
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", cname.removesuffix("Power"))
        filtered_powers.append({"class_name": cname, "title": title, "slug": slugify(title)})
    lines.append(f"referenced_powers: {json.dumps(filtered_powers)}")

    # Epoch unlock
    if card.get("unlocked_by"):
        lines.append(f"unlocked_by: {escape_yaml(card['unlocked_by'])}")

    # Mechanic notes from code analysis
    if card.get("notes"):
        lines.append(f"notes: {escape_yaml(card['notes'])}")

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

    # Fields the LLM extractor cannot reliably determine from a single card
    # source file — either because they depend on how other files reference this
    # card (e.g. which CardPool it belongs to) or because they come straight from
    # the base() constructor and the LLM uses a different, lossier vocabulary
    # (target "Single" vs "AnyEnemy"/"RandomEnemy", energy_cost -1 for X-cost).
    # For these, the aggregate value produced by extract_cards.py is
    # authoritative and must not be clobbered by per-entity data.
    _AGGREGATE_AUTHORITATIVE = {"character", "energy_cost", "type", "rarity", "target"}

    # Load per-entity JSON overrides
    per_entity_dir = os.path.join(data_dir, "cards")
    if os.path.isdir(per_entity_dir):
        cards_by_class = {c["class_name"]: c for c in cards}
        for fname in os.listdir(per_entity_dir):
            if fname.endswith(".json"):
                with open(os.path.join(per_entity_dir, fname)) as f:
                    entity_data = json.load(f)
                cname = entity_data.get("class_name", fname.removesuffix(".json"))
                if cname in cards_by_class:
                    for field in _AGGREGATE_AUTHORITATIVE:
                        entity_data.pop(field, None)
                    cards_by_class[cname].update(entity_data)
                else:
                    cards_by_class[cname] = entity_data
        cards = list(cards_by_class.values())

    # Build power class_name → title lookup (powers.json + per-entity overrides)
    power_titles: dict[str, str] = {}
    powers_path = os.path.join(data_dir, "powers.json")
    if os.path.exists(powers_path):
        with open(powers_path) as f:
            for p in json.load(f):
                if p.get("class_name") and p.get("title"):
                    power_titles[p["class_name"]] = p["title"]
    powers_entity_dir = os.path.join(data_dir, "powers")
    if os.path.isdir(powers_entity_dir):
        for fname in os.listdir(powers_entity_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(powers_entity_dir, fname)) as f:
                pd = json.load(f)
            if pd.get("class_name") and pd.get("title"):
                power_titles[pd["class_name"]] = pd["title"]

    # Clear output directory
    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    # Load mechanic notes
    from scripts.card_notes import CARD_NOTES

    # Generate markdown files
    count = 0
    for card in cards:
        # Skip deprecated and mock cards
        if card.get("deprecated") or card.get("mock"):
            continue

        # Inject notes from code analysis
        note = CARD_NOTES.get(card["class_name"])
        if note:
            card["notes"] = note

        slug = slugify(card["title"])

        # Merge curated override (frontmatter fields into the entity, body kept
        # as extra page content)
        from scripts.gen_common import load_override

        override = load_override(data_dir, "cards", slug)
        override_body = ""
        if override:
            fields, override_body = override
            card.update(fields)

        md = generate_card_markdown(card, power_titles=power_titles)
        if override_body:
            md += override_body + "\n"
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
