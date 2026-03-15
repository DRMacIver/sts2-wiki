#!/usr/bin/env python3
"""Extract all potion data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    class_name_to_loc_key,
    find_loc_key,
    load_localization,
    parse_canonical_vars,
    read_cs_files,
    strip_rich_text,
    write_json,
)

POOL_MAP: dict[str, str] = {
    "IroncladPotionPool": "Ironclad",
    "SilentPotionPool": "Silent",
    "DefectPotionPool": "Defect",
    "NecrobinderPotionPool": "Necrobinder",
    "RegentPotionPool": "Regent",
    "SharedPotionPool": "Shared",
}


def build_potion_pool_map(decompiled_dir: str) -> dict[str, str]:
    """Parse PotionPool files to build class_name -> pool mapping."""
    pools_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.PotionPools")
    potion_to_pool: dict[str, str] = {}

    if not os.path.exists(pools_dir):
        return potion_to_pool

    for pool_name, content in read_cs_files(pools_dir):
        pool_label = POOL_MAP.get(pool_name, pool_name)
        for m in re.finditer(r"ModelDb\.Potion<(\w+)>\(\)", content):
            potion_class = m.group(1)
            # Character-specific pools override shared
            if potion_class not in potion_to_pool or pool_label != "Shared":
                potion_to_pool[potion_class] = pool_label

    return potion_to_pool


def parse_potion_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled potion .cs file."""
    if ": PotionModel" not in content:
        return None

    potion: dict = {"class_name": class_name}

    # Rarity
    m = re.search(r"PotionRarity\.(\w+)", content)
    if m:
        potion["rarity"] = m.group(1)

    # Usage
    m = re.search(r"PotionUsage\.(\w+)", content)
    if m:
        potion["usage"] = m.group(1)

    # Target
    m = re.search(r"TargetType\.(\w+)", content)
    if m:
        potion["target"] = m.group(1)

    # Dynamic vars
    vars_found = parse_canonical_vars(content)
    if vars_found:
        potion["vars"] = vars_found

    # Image filename: PascalCase -> snake_case
    image_name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", class_name)
    image_name = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", image_name)
    potion["image"] = image_name.lower()

    return potion


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 potion data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "potions")
    pool_map = build_potion_pool_map(decompiled_dir)

    potions_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Potions")
    potions: list[dict] = []

    for class_name, content in read_cs_files(potions_dir):
        potion = parse_potion_file(class_name, content)
        if not potion:
            continue

        # Pool assignment
        potion["pool"] = pool_map.get(class_name, "Unknown")

        # Localization
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            potion["loc_key"] = loc_key
            potion["title"] = loc_data.get(f"{loc_key}.title", class_name)
            raw_desc = loc_data.get(f"{loc_key}.description", "")
            potion["description"] = strip_rich_text(raw_desc)
        else:
            potion["loc_key"] = class_name_to_loc_key(class_name)
            potion["title"] = class_name
            potion["description"] = ""

        potions.append(potion)

    output_path = os.path.join(output_dir, "potions.json")
    write_json(output_path, potions)

    print(f"Extracted {len(potions)} potions to {output_path}")
    by_rarity: dict[str, int] = {}
    for p in potions:
        rar = p.get("rarity", "Unknown")
        by_rarity[rar] = by_rarity.get(rar, 0) + 1
    for rar, count in sorted(by_rarity.items()):
        print(f"  {rar}: {count}")


if __name__ == "__main__":
    main()
