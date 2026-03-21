#!/usr/bin/env python3
"""Extract enchantment data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    find_loc_key,
    load_localization,
    read_cs_files,
    write_json,
)


def parse_enchantment_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled enchantment .cs file."""
    if "Deprecated" in class_name or "Mock" in class_name:
        return None
    # Must be a concrete class
    if f"abstract class {class_name}" in content:
        return None
    if f"class {class_name}" not in content:
        return None

    enchantment: dict = {"class_name": class_name}

    # Card type restrictions from CanEnchantCardType
    card_type_match = re.search(
        r"CanEnchantCardType\(CardType\s+\w+\)\s*=>\s*(.*?);",
        content,
        re.DOTALL,
    )
    if card_type_match:
        body = card_type_match.group(1)
        if "Attack" in body and "Skill" not in body:
            enchantment["card_type"] = "Attack"
        elif "Skill" in body and "Attack" not in body:
            enchantment["card_type"] = "Skill"
        elif "Attack" in body and "Skill" in body:
            enchantment["card_type"] = "Attack or Skill"
        else:
            enchantment["card_type"] = "Any"
    else:
        enchantment["card_type"] = "Any"

    # Additional restrictions from CanEnchant override
    can_enchant = re.search(
        r"override\s+bool\s+CanEnchant\(.*?\)\s*\{(.*?)\n\t\}",
        content,
        re.DOTALL,
    )
    if can_enchant:
        body = can_enchant.group(1)
        restrictions: list[str] = []
        if "CardTag.Defend" in body:
            restrictions.append("Defend-tagged cards only")
        if "CardTag.Strike" in body and "CardTag.Defend" in body:
            restrictions.append("Strike or Defend-tagged Basic cards only")
        elif "CardTag.Strike" in body:
            restrictions.append("Strike-tagged cards only")
        if "CardRarity.Basic" in body:
            if "Basic cards only" not in str(restrictions):
                restrictions.append("Basic rarity only")
        if "Exhaust" in body:
            restrictions.append("Cards with Exhaust only")
        if "CostsX" in body:
            restrictions.append("Excludes X-cost cards")
        if "Unplayable" in body:
            restrictions.append("Excludes Unplayable cards")
        if restrictions:
            enchantment["restrictions"] = restrictions

    # IsStackable
    if "IsStackable => true" in content:
        enchantment["stackable"] = True

    # ShowAmount
    if "ShowAmount => true" in content:
        enchantment["show_amount"] = True

    # HasExtraCardText
    if "HasExtraCardText => true" in content:
        enchantment["has_extra_card_text"] = True

    return enchantment


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 enchantment data")
    parser.add_argument(
        "decompiled_dir",
        help="Path to decompiled source directory",
    )
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "enchantments")

    enchantments_dir = os.path.join(
        decompiled_dir,
        "MegaCrit.Sts2.Core.Models.Enchantments",
    )
    enchantments: list[dict] = []

    for class_name, content in read_cs_files(enchantments_dir):
        ench = parse_enchantment_file(class_name, content)
        if not ench:
            continue

        # Localization
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            ench["title"] = loc_data.get(f"{loc_key}.title", class_name)
            ench["description"] = loc_data.get(f"{loc_key}.description", "")
            extra = loc_data.get(f"{loc_key}.extraCardText", "")
            if extra:
                ench["extra_card_text"] = extra
        else:
            # CamelCase split for display
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", class_name)
            ench["title"] = title
            ench["description"] = ""

        enchantments.append(ench)

    output_path = os.path.join(output_dir, "enchantments.json")
    write_json(output_path, enchantments)

    print(f"Extracted {len(enchantments)} enchantments to {output_path}")


if __name__ == "__main__":
    main()
