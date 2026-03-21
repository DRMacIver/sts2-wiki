#!/usr/bin/env python3
"""Check that all content items have corresponding images.

Usage:
    uv run python -m scripts.check_images data/v0.100.0 site/public/images
"""

import argparse
import json
import re
import sys
from pathlib import Path


def pascal_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case (matches JS regex in utils.ts)."""
    return re.sub(
        r"([A-Z])",
        lambda m: ("_" if m.start() > 0 else "") + m.group(1),
        name,
    ).lower()


# Must match MONSTER_IMAGE_ALIASES in site/src/utils.ts
MONSTER_IMAGE_ALIASES: dict[str, str] = {
    "TorchHeadAmalgam": "amalgam",
    "GlobeHead": "orb_head",
    "Flyconid": "flying_mushrooms",
    "DecimillipedeSegment": "decimillipede",
    "LivingFog": "living_smog",
    "SkulkingColony": "living_shield",
    "Crusher": "infested_guardian",
    "Ovicopter": "egg_layer",
    "BowlbugEgg": "bowlbug",
    "BowlbugNectar": "bowlbug",
    "BowlbugRock": "bowlbug",
    "BowlbugSilk": "bowlbug",
    "CalcifiedCultist": "cultists",
    "DampCultist": "cultists",
    "BattleFriendV1": "battleworn_dummy",
    "BattleFriendV2": "battleworn_dummy",
    "BattleFriendV3": "battleworn_dummy",
    "BigDummy": "battleworn_dummy",
}

# Monsters that are test/unused and should be skipped
SKIP_MONSTERS = {
    "BigDummy",
    "MultiAttackMoveMonster",
    "OneHpMonster",
    "SingleAttackMoveMonster",
    "TenHpMonster",
    "TestSubject",
    "TheAdversaryMkOne",
    "TheAdversaryMkTwo",
    "TheAdversaryMkThree",
}

# Monsters without rendered images.
# Some have Spine data but need manual rendering via tools/spine-renderer/.
# Others genuinely have no skeleton data in the game files.
KNOWN_MISSING_MONSTERS = {
    "Crusher",  # No spine skel
    "Doormaker",  # No spine skel
    "FakeMerchantMonster",  # Has spine skel (fake_merchant_top) but not rendered
    "Flyconid",  # No spine skel
    "Ovicopter",  # Has spine skel but not rendered
    "Rocket",  # No spine skel
}


def check_cards(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check card images exist."""
    missing = []
    with open(data_dir / "cards.json") as f:
        cards = json.load(f)
    for card in cards:
        char_dir = card["character"].lower()
        filename = pascal_to_snake(card["class_name"])
        primary = images_dir / "card_atlas" / char_dir / f"{filename}.png"
        beta = images_dir / "card_atlas" / char_dir / "beta" / f"{filename}.png"
        if not primary.exists() and not beta.exists():
            missing.append((card["class_name"], str(primary)))
    return missing


def check_relics(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check relic images exist."""
    missing = []
    with open(data_dir / "relics.json") as f:
        relics = json.load(f)
    for relic in relics:
        image = relic.get("image", "")
        if not image:
            continue
        path = images_dir / "relic_atlas" / f"{image}.png"
        if not path.exists():
            missing.append((relic["class_name"], str(path)))
    return missing


def check_potions(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check potion images exist."""
    missing = []
    with open(data_dir / "potions.json") as f:
        potions = json.load(f)
    for potion in potions:
        if "Deprecated" in potion["class_name"]:
            continue
        image = potion.get("image", "")
        if not image:
            continue
        path = images_dir / "potion_atlas" / f"{image}.png"
        if not path.exists():
            missing.append((potion["class_name"], str(path)))
    return missing


def check_monsters(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check monster images exist."""
    missing = []
    with open(data_dir / "monsters.json") as f:
        monsters = json.load(f)
    for monster in monsters:
        cn = monster["class_name"]
        if cn in SKIP_MONSTERS or cn in KNOWN_MISSING_MONSTERS:
            continue
        image_name = MONSTER_IMAGE_ALIASES.get(cn, pascal_to_snake(cn))
        path = images_dir / "monsters" / f"{image_name}.png"
        if not path.exists():
            missing.append((cn, str(path)))
    return missing


def check_powers(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check power images exist."""
    missing = []
    with open(data_dir / "powers.json") as f:
        powers = json.load(f)
    for power in powers:
        filename = pascal_to_snake(power["class_name"])
        path = images_dir / "power_atlas" / f"{filename}.png"
        if not path.exists():
            missing.append((power["class_name"], str(path)))
    return missing


def check_ancients(data_dir: Path, images_dir: Path) -> list[tuple[str, str]]:
    """Check ancient images exist."""
    missing = []
    with open(data_dir / "ancients.json") as f:
        ancients = json.load(f)
    for ancient in ancients:
        if ancient.get("_loc_missing"):
            continue
        # Slug is title lowercased
        slug = re.sub(r"[^a-z0-9]+", "-", ancient["title"].lower()).strip("-")
        path = images_dir / "ancients" / f"{slug}.png"
        if not path.exists():
            missing.append((ancient["class_name"], str(path)))
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that content items have images")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("images_dir", help="Path to images directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    images_dir = Path(args.images_dir)

    all_missing: dict[str, list[tuple[str, str]]] = {}

    checkers = [
        ("Cards", check_cards),
        ("Relics", check_relics),
        ("Potions", check_potions),
        ("Monsters", check_monsters),
        ("Powers", check_powers),
        ("Ancients", check_ancients),
    ]

    total_checked = 0
    total_missing = 0

    for label, checker in checkers:
        missing = checker(data_dir, images_dir)
        if missing:
            all_missing[label] = missing
            total_missing += len(missing)
        # Count items checked from data files
        with open(data_dir / f"{label.lower()}.json") as f:
            total_checked += len(json.load(f))

    print(f"Checked {total_checked} items across {len(checkers)} types")

    if all_missing:
        print(f"\n{total_missing} missing image(s):\n")
        for label, items in all_missing.items():
            print(f"  {label} ({len(items)} missing):")
            for class_name, path in items[:10]:
                print(f"    {class_name} -> {path}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")
        print()
        sys.exit(1)
    else:
        print("All images OK")


if __name__ == "__main__":
    main()
