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


def compute_total_monsters(enc: dict, test_monster_classes: set[str]) -> int:
    """Monster count for an encounter.

    A curated per-entity `total_monsters` (from LLM extraction, e.g. "2 Chompers"
    when the monster list only names Chomper once) is authoritative; otherwise
    count the non-test entries in the monster list.
    """
    curated = enc.get("total_monsters")
    if curated:
        return int(curated)
    return len([m for m in enc.get("monsters", []) if m not in test_monster_classes])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate encounter content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/encounters/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "encounters.json")) as f:
        encounters = json.load(f)

    # Load per-entity JSON overrides
    per_entity_dir = os.path.join(data_dir, "encounters")
    if os.path.isdir(per_entity_dir):
        enc_by_class = {e["class_name"]: e for e in encounters}
        for fname in os.listdir(per_entity_dir):
            if fname.endswith(".json"):
                with open(os.path.join(per_entity_dir, fname)) as f:
                    entity_data = json.load(f)
                cname = entity_data.get("class_name", fname.removesuffix(".json"))
                if cname in enc_by_class:
                    enc_by_class[cname].update(entity_data)
                else:
                    enc_by_class[cname] = entity_data
        encounters = list(enc_by_class.values())

    # Filter out test/debug encounters
    test_monster_classes = {"BigDummy", "OneHpMonster", "TenHpMonster"}

    # Map variant monster class names to their base class
    # (e.g., DecimillipedeSegmentFront -> DecimillipedeSegment)
    monster_class_aliases: dict[str, str] = {
        "DecimillipedeSegmentFront": "DecimillipedeSegment",
        "DecimillipedeSegmentMiddle": "DecimillipedeSegment",
        "DecimillipedeSegmentBack": "DecimillipedeSegment",
    }

    # Load monster data for cross-referencing
    monster_titles: dict[str, str] = {}
    monsters_path = os.path.join(data_dir, "monsters.json")
    if os.path.exists(monsters_path):
        with open(monsters_path) as f:
            monsters = json.load(f)
        for m in monsters:
            # Clean up template artifacts in titles
            title = re.sub(r"#[A-Z]\{[^}]*\}", "", m["title"]).strip()
            monster_titles[m["class_name"]] = title

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    from scripts.gen_common import load_override

    count = 0
    for enc in encounters:
        slug = slugify(enc.get("title", enc["class_name"]))

        # Merge curated override (frontmatter fields into the entity, body kept
        # as extra page content). An override "monsters" list of dicts is
        # already-resolved refs and replaces the computed monster_refs.
        override = load_override(data_dir, "encounters", slug)
        override_body = ""
        override_monster_refs: list[dict] | None = None
        if override:
            fields, override_body = override
            monsters_field = fields.get("monsters")
            if isinstance(monsters_field, list) and all(
                isinstance(m, dict) for m in monsters_field
            ):
                override_monster_refs = fields.pop("monsters")  # type: ignore[assignment]
            enc.update(fields)

        # Skip encounters that only contain test monsters
        enc_monsters = enc.get("monsters", [])
        if enc_monsters and all(m in test_monster_classes for m in enc_monsters):
            continue

        # Enrich monster list
        monster_refs = []
        seen_slugs: set[str] = set()
        for m_class in enc_monsters:
            if m_class in test_monster_classes:
                continue
            # Resolve aliases (e.g., segment variants)
            resolved_class = monster_class_aliases.get(m_class, m_class)
            m_title = monster_titles.get(resolved_class, monster_titles.get(m_class, m_class))
            m_slug = slugify(m_title)
            # Deduplicate (multiple segment variants map to same monster)
            if m_slug in seen_slugs:
                continue
            seen_slugs.add(m_slug)
            monster_refs.append(
                {
                    "class_name": resolved_class,
                    "title": m_title,
                    "slug": m_slug,
                }
            )

        if override_monster_refs is not None:
            monster_refs = override_monster_refs

        total_monsters = compute_total_monsters(enc, test_monster_classes)

        lines = ["---"]
        lines.append(f"title: {escape_yaml(enc.get('title', enc['class_name']))}")
        lines.append(f"class_name: {escape_yaml(enc['class_name'])}")
        lines.append(f"room_type: {escape_yaml(enc.get('room_type', 'Monster'))}")
        lines.append(f"is_weak: {str(enc.get('is_weak', False)).lower()}")
        lines.append(f"monsters: {json.dumps(monster_refs)}")
        lines.append(f"total_monsters: {total_monsters}")
        lines.append(f"tags: {json.dumps(enc.get('tags', []))}")
        lines.append(f"acts: {json.dumps(enc.get('acts', []))}")
        lines.append("---")
        lines.append("")

        # Add notes as content body if present
        if enc.get("notes"):
            lines.append(enc.get("notes"))
        if override_body:
            lines.append(override_body)

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{enc['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} encounter pages in {output_dir}")


if __name__ == "__main__":
    main()
