#!/usr/bin/env python3
"""Extract character data from STS2 decompiled C# source code + localization."""

import argparse
import os
import re

from scripts.common import (
    load_localization,
    read_cs_files,
    strip_rich_text,
    write_json,
)


def parse_character_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled character .cs file."""
    if ": CharacterModel" not in content:
        return None

    char: dict = {"class_name": class_name}

    # Starting HP
    m = re.search(r"StartingHp\s*=>\s*(\d+)", content)
    if m:
        char["starting_hp"] = int(m.group(1))

    # Starting Gold
    m = re.search(r"StartingGold\s*=>\s*(\d+)", content)
    if m:
        char["starting_gold"] = int(m.group(1))

    # Orb slots (Defect)
    m = re.search(r"BaseOrbSlotCount\s*=>\s*(\d+)", content)
    if m:
        char["orb_slots"] = int(m.group(1))

    # Starting relic
    m = re.search(r"StartingRelics.*?Relic<(\w+)>", content, re.DOTALL)
    if m:
        char["starting_relic"] = m.group(1)

    # Starting deck
    deck: list[str] = []
    for m in re.finditer(r"ModelDb\.Card<(\w+)>\(\)", content):
        deck.append(m.group(1))
    char["starting_deck"] = deck

    return char


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 character data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "characters")

    chars_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Characters")
    characters: list[dict] = []

    skip = {"RandomCharacter", "CharacterGender", "Deprived"}

    for class_name, content in read_cs_files(chars_dir):
        if class_name in skip:
            continue
        char = parse_character_file(class_name, content)
        if not char:
            continue

        # Localization
        loc_key = class_name.upper()
        char["loc_key"] = loc_key
        char["title"] = loc_data.get(f"{loc_key}.title", class_name)
        char["description"] = strip_rich_text(loc_data.get(f"{loc_key}.description", ""))
        char["aroma"] = strip_rich_text(loc_data.get(f"{loc_key}.aromaPrinciple", ""))

        characters.append(char)

    output_path = os.path.join(output_dir, "characters.json")
    write_json(output_path, characters)
    print(f"Extracted {len(characters)} characters to {output_path}")


if __name__ == "__main__":
    main()
