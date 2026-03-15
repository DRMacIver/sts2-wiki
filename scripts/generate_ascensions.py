#!/usr/bin/env python3
"""Generate Astro content collection markdown files from ascension data."""

import argparse
import json
import os
import re
from pathlib import Path

from scripts.common import load_localization, read_cs_files, strip_rich_text


def escape_yaml(value: str) -> str:
    if not value:
        return '""'
    if value.lower() in ("null", "true", "false", "yes", "no", "on", "off", "~"):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


# Detailed mechanics for each ascension level, derived from decompiled source
DETAILED_MECHANICS: dict[int, dict] = {
    0: {
        "detail": "The baseline difficulty with no modifiers applied.",
    },
    1: {
        "detail": (
            "The number of elite encounters on each act's map is multiplied by 1.6x "
            "(from 5 to 8 elites per act). This means more dangerous fights between "
            "you and the boss, but also more opportunities for elite rewards."
        ),
    },
    2: {
        "detail": (
            "When an Ancient heals you, the amount is reduced to 80% of what it "
            "would normally be. For example, if you're at 30/100 HP and would "
            "normally heal 70 HP, you instead heal 56 HP."
        ),
    },
    3: {
        "detail": (
            "All gold drops from enemy encounters and treasure chests are multiplied "
            "by 0.75, giving you 25% less gold. This affects combat rewards and "
            "treasure rooms but not event gold."
        ),
    },
    4: {
        "detail": (
            "You start each run with one fewer potion slot. This reduces your "
            "ability to stockpile potions for tough fights."
        ),
    },
    5: {
        "detail": (
            "The curse card Ascender's Bane is added to your deck at the start of "
            "each run. It is Unplayable and Ethereal (discarded at end of turn if "
            "in hand), and has the Eternal keyword, meaning it cannot be removed "
            "from your deck by normal means."
        ),
    },
    6: {
        "detail": (
            "Each act generates one fewer Rest Site on the map. Rest Sites are "
            "where you can heal or upgrade cards, so this reduces both recovery "
            "and power-up opportunities. The base number of rest sites varies "
            "by act (typically 6-7), so losing one is significant."
        ),
    },
    7: {
        "detail": (
            "Rare cards appear roughly half as often in rewards and shops. "
            "The chance of finding an upgraded card also scales at half the "
            "normal rate (12.5% per act instead of 25% per act). Specific "
            "odds changes:\n"
            "- Regular encounter rare chance: 3% \u2192 1.5%\n"
            "- Elite encounter rare chance: 10% \u2192 5%\n"
            "- Shop rare chance: 9% \u2192 4.5%\n"
            "- Rarity growth per roll: 1% \u2192 0.5%\n"
            "- Upgrade scaling per act: 25% \u2192 12.5%"
        ),
    },
    8: {
        "detail": (
            "Every enemy in the game gains additional HP. The increase varies "
            "per enemy \u2014 it's not a flat percentage but specific values "
            "tuned for each monster. Weaker enemies might gain 1-3 HP while "
            "bosses and elites can gain 10+ HP."
        ),
        "has_monster_changes": True,
    },
    9: {
        "detail": (
            "Every enemy's attacks deal more damage. Like Tough Enemies, "
            "the increase is tuned per-attack rather than a flat multiplier. "
            "Individual attacks might deal 1-5 more damage each."
        ),
        "has_monster_changes": True,
    },
    10: {
        "detail": (
            "At the end of the final act, you face two bosses instead of one. "
            "The primary boss is determined normally, and a second boss is "
            "randomly selected from the remaining boss pool. Both bosses "
            "appear in the same encounter."
        ),
    },
}


def collect_monster_changes(
    decompiled_dir: str, monster_titles: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Collect HP and damage changes from monster files."""
    monsters_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Monsters")
    if not os.path.exists(monsters_dir):
        return [], []

    # Skip test monsters
    skip = {"BigDummy", "OneHpMonster", "TenHpMonster"}

    hp_changes: list[dict] = []
    dmg_changes: list[dict] = []

    for class_name, content in read_cs_files(monsters_dir):
        if class_name in skip:
            continue
        title = monster_titles.get(class_name, class_name)

        # HP changes (ToughEnemies)
        for m in re.finditer(
            r"(Min|Max)InitialHp\s*=>\s*AscensionHelper\.GetValueIfAscension\("
            r"[^,]+,\s*(\d+),\s*(\d+)\)",
            content,
        ):
            asc_val = int(m.group(2))
            base_val = int(m.group(3))
            if asc_val != base_val:
                hp_changes.append(
                    {
                        "monster": title,
                        "class_name": class_name,
                        "base": base_val,
                        "ascension": asc_val,
                        "diff": asc_val - base_val,
                    }
                )

        # Damage changes (DeadlyEnemies)
        for m in re.finditer(
            r"(\w+)\s*=>\s*AscensionHelper\.GetValueIfAscension\("
            r"AscensionLevel\.DeadlyEnemies,\s*(\d+),\s*(\d+)\)",
            content,
        ):
            prop = m.group(1)
            asc_val = int(m.group(2))
            base_val = int(m.group(3))
            if asc_val != base_val and "Hp" not in prop:
                dmg_changes.append(
                    {
                        "monster": title,
                        "class_name": class_name,
                        "property": prop,
                        "base": base_val,
                        "ascension": asc_val,
                        "diff": asc_val - base_val,
                    }
                )

    # Deduplicate and sort by monster name
    hp_changes.sort(key=lambda x: x["monster"])
    dmg_changes.sort(key=lambda x: x["monster"])

    return hp_changes, dmg_changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ascension content files")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to content/ascensions/ directory")
    parser.add_argument(
        "--decompiled-dir", default="", help="Path to decompiled source for monster data"
    )
    parser.add_argument("--data-dir", default="", help="Path to data dir for monster titles")
    args = parser.parse_args()

    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "ascension")

    # Load monster titles for cross-referencing
    monster_titles: dict[str, str] = {}
    if args.data_dir:
        monsters_path = os.path.join(args.data_dir, "monsters.json")
        if os.path.exists(monsters_path):
            with open(monsters_path) as f:
                monsters = json.load(f)
            for m in monsters:
                # Clean up template artifacts in titles
                title = re.sub(r"#[A-Z]\{[^}]*\}", "", m["title"]).strip()
                monster_titles[m["class_name"]] = title

    # Collect monster changes if decompiled source available
    hp_changes: list[dict] = []
    dmg_changes: list[dict] = []
    if args.decompiled_dir:
        hp_changes, dmg_changes = collect_monster_changes(args.decompiled_dir, monster_titles)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for level in range(11):
        key = f"LEVEL_{level:02d}"
        title = loc_data.get(f"{key}.title", f"Ascension {level}")
        desc = strip_rich_text(loc_data.get(f"{key}.description", ""))
        mechanics = DETAILED_MECHANICS.get(level, {})
        detail = mechanics.get("detail", "")

        lines = ["---"]
        lines.append(f"title: {escape_yaml(title)}")
        lines.append(f"level: {level}")
        lines.append(f"description: {escape_yaml(desc)}")
        lines.append(f"detail: {escape_yaml(detail)}")

        # Include monster change data for levels 8 and 9
        if level == 8 and hp_changes:
            # Deduplicate by monster (take max diff)
            by_monster: dict[str, dict] = {}
            for c in hp_changes:
                key2 = c["class_name"]
                if key2 not in by_monster or c["diff"] > by_monster[key2]["diff"]:
                    by_monster[key2] = c
            deduped = sorted(by_monster.values(), key=lambda x: x["monster"])
            lines.append(f"monster_changes: {json.dumps(deduped)}")
        elif level == 9 and dmg_changes:
            lines.append(f"monster_changes: {json.dumps(dmg_changes)}")

        lines.append("---")
        lines.append("")

        filepath = out / f"level-{level:02d}.md"
        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} ascension levels in {output_dir}")


if __name__ == "__main__":
    main()
