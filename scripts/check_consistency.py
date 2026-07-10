"""Consistency checks for a version's extracted data (aggregate + per-entity JSON).

Structural invariants are errors (exit 1); known data-quality limitations are
warnings. Run via `just check-consistency` (part of `just check`).

Checks:
- per-entity file name matches embedded class_name
- no duplicate class_names within an aggregate file
- event card_refs/relic_refs resolve to real cards/relics
- per-entity card referenced_powers resolve to real powers
- encounter monster lists resolve to real monsters (after alias resolution)
- balanced color/formatting tags in all description-like fields
- placeholder text that should never reach the wiki (warning)
- monster HP sanity (warning)
- aggregate vs per-entity coverage gaps (warning)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Aggregate kinds and whether a per-entity directory of the same name exists.
KINDS = [
    "cards",
    "monsters",
    "relics",
    "potions",
    "powers",
    "encounters",
    "enchantments",
    "events",  # per-entity only, no aggregate
]

# Variant monster classes that resolve to a base monster page.
# (Kept in sync with generate_encounters.py.)
MONSTER_CLASS_ALIASES: dict[str, str] = {
    "DecimillipedeSegmentFront": "DecimillipedeSegment",
    "DecimillipedeSegmentMiddle": "DecimillipedeSegment",
    "DecimillipedeSegmentBack": "DecimillipedeSegment",
}

TEST_MONSTER_CLASSES = {"BigDummy", "OneHpMonster", "TenHpMonster"}

# Tags that pair up as [tag]...[/tag]. rainbow/font_size carry attributes.
PAIRED_TAGS = [
    "gold",
    "blue",
    "red",
    "green",
    "purple",
    "orange",
    "aqua",
    "pink",
    "b",
    "sine",
    "wave",
    "shake",
    "jitter",
    "center",
    "rainbow",
    "font_size",
]

# Strings that indicate an entity never got real content.
PLACEHOLDER_PATTERNS = [
    "[LOCALIZATION PENDING]",
    "localization data not available",
]

TEXT_FIELDS = [
    "description",
    "upgraded_description",
    "notes",
    "flavor",
    "extra_card_text",
    "smart_description",
]


def load_json(path: Path) -> object:
    with open(path) as f:
        return json.load(f)


def iter_entity_files(version_dir: Path, kind: str, errors: list[str] | None = None):
    entity_dir = version_dir / kind
    if not entity_dir.is_dir():
        return
    for path in sorted(entity_dir.glob("*.json")):
        try:
            data = load_json(path)
        except json.JSONDecodeError as e:
            if errors is not None:
                errors.append(f"{kind}/{path.name}: invalid JSON ({e})")
            continue
        if isinstance(data, dict):
            yield path, data


def check_tag_balance(text: str) -> list[str]:
    """Return a list of unbalanced-tag descriptions for a text blob."""
    problems = []
    for tag in PAIRED_TAGS:
        opens = len(re.findall(rf"\[{tag}(?:[\s=][^\]]*)?\]", text))
        closes = len(re.findall(rf"\[/{tag}\]", text))
        if opens != closes:
            problems.append(f"[{tag}] opens={opens} closes={closes}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version_dir", help="e.g. data/v0.108.0")
    args = parser.parse_args()
    version_dir = Path(args.version_dir)
    if not version_dir.is_dir():
        raise SystemExit(f"No such directory: {version_dir}")

    errors: list[str] = []
    warnings: list[str] = []

    # Load aggregates
    aggregates: dict[str, list[dict]] = {}
    for kind in KINDS:
        agg_path = version_dir / f"{kind}.json"
        if agg_path.exists():
            data = load_json(agg_path)
            if isinstance(data, list):
                aggregates[kind] = data

    agg_class_names: dict[str, set[str]] = {}
    for kind, entries in aggregates.items():
        names: list[str] = [
            e["class_name"] for e in entries if isinstance(e.get("class_name"), str)
        ]
        agg_class_names[kind] = set(names)
        dupes = {n for n in names if names.count(n) > 1}
        for d in sorted(dupes):
            errors.append(f"{kind}.json: duplicate class_name {d}")

    # Per-entity checks
    entity_class_names: dict[str, set[str]] = {}
    for kind in KINDS:
        seen: set[str] = set()
        for path, entity in iter_entity_files(version_dir, kind, errors):
            cname = entity.get("class_name")
            if cname != path.stem:
                errors.append(f"{kind}/{path.name}: class_name {cname!r} != filename")
            if cname:
                seen.add(cname)

            # Tag balance + placeholders on text fields
            for field in TEXT_FIELDS:
                value = entity.get(field)
                if not isinstance(value, str):
                    continue
                for problem in check_tag_balance(value):
                    errors.append(f"{kind}/{path.name}: unbalanced {problem} in {field}")
                for pat in PLACEHOLDER_PATTERNS:
                    if pat in value:
                        warnings.append(f"{kind}/{path.name}: placeholder text in {field}")

            # Event/option-level tag balance
            for opt in entity.get("options", []) if kind == "events" else []:
                for field in ("title", "description", "requires"):
                    value = opt.get(field)
                    if isinstance(value, str):
                        for problem in check_tag_balance(value):
                            errors.append(
                                f"{kind}/{path.name}: unbalanced {problem} in option {field}"
                            )

        entity_class_names[kind] = seen

    # Cross-references
    cards = agg_class_names.get("cards", set())
    relics = agg_class_names.get("relics", set())
    powers = agg_class_names.get("powers", set())
    monsters = agg_class_names.get("monsters", set())

    for path, event in iter_entity_files(version_dir, "events"):
        for ref in event.get("card_refs", []):
            cname = ref.get("class_name")
            if cname and cname not in cards and cname not in entity_class_names.get("cards", ()):
                errors.append(f"events/{path.name}: card_ref {cname} does not exist")
        for ref in event.get("relic_refs", []):
            cname = ref.get("class_name")
            if cname and cname not in relics and cname not in entity_class_names.get("relics", ()):
                errors.append(f"events/{path.name}: relic_ref {cname} does not exist")

    for path, card in iter_entity_files(version_dir, "cards"):
        for ref in card.get("referenced_powers", []):
            cname = ref.get("class_name") if isinstance(ref, dict) else ref
            if not cname:
                continue
            if cname in powers or cname in entity_class_names.get("powers", ()):
                continue
            if cname.endswith("Power"):
                # Would be rendered as a (broken) power link by generate_cards
                errors.append(f"cards/{path.name}: referenced power {cname} does not exist")
            else:
                # Filtered out at generation time, but still wrong data
                warnings.append(
                    f"cards/{path.name}: referenced_powers entry {cname} is not a power"
                )

    for path, enc in iter_entity_files(version_dir, "encounters"):
        for mname in enc.get("monsters", []):
            resolved = MONSTER_CLASS_ALIASES.get(mname, mname)
            if resolved in TEST_MONSTER_CLASSES:
                continue
            if (
                resolved not in monsters
                and resolved not in entity_class_names.get("monsters", ())
                and mname not in entity_class_names.get("monsters", ())
            ):
                warnings.append(f"encounters/{path.name}: monster {mname} not in monsters data")

    # Monster HP sanity
    for m in aggregates.get("monsters", []):
        cname = m.get("class_name", "?")
        if "Deprecated" in cname:
            continue
        min_hp, max_hp = m.get("min_hp"), m.get("max_hp")
        if isinstance(min_hp, int) and isinstance(max_hp, int):
            if min_hp > max_hp:
                errors.append(f"monsters.json: {cname} min_hp {min_hp} > max_hp {max_hp}")
            elif max_hp == 0:
                warnings.append(f"monsters.json: {cname} has 0 HP")

    # Coverage: aggregate entries without per-entity files and vice versa
    for kind in KINDS:
        agg = agg_class_names.get(kind)
        per = entity_class_names.get(kind)
        if agg is None or not per:
            continue
        missing_files = sorted(agg - per)
        extra_files = sorted(per - agg)
        if missing_files:
            warnings.append(
                f"{kind}: {len(missing_files)} aggregate entries lack per-entity JSON: "
                + ", ".join(missing_files[:8])
                + ("…" if len(missing_files) > 8 else "")
            )
        if extra_files:
            warnings.append(
                f"{kind}: {len(extra_files)} per-entity files not in aggregate: "
                + ", ".join(extra_files[:8])
                + ("…" if len(extra_files) > 8 else "")
            )

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"\ncheck_consistency {version_dir}: {len(errors)} errors, {len(warnings)} warnings")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
