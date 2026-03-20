#!/usr/bin/env python3
"""Extract all power/status effect data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    find_loc_key,
    load_localization,
    read_cs_files,
    write_json,
)


def parse_power_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled power .cs file."""
    # Must be a concrete class in the Powers namespace
    if f"abstract class {class_name}" in content:
        return None
    if f"class {class_name}" not in content:
        return None

    power: dict = {"class_name": class_name}

    # PowerType
    m = re.search(r"PowerType\.(\w+)", content)
    if m:
        power["type"] = m.group(1)

    # PowerStackType
    m = re.search(r"PowerStackType\.(\w+)", content)
    if m:
        power["stack_type"] = m.group(1)

    # AllowNegative
    if "AllowNegative => true" in content:
        power["allow_negative"] = True

    return power


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 power data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "powers")

    powers_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Powers")
    powers: list[dict] = []

    for class_name, content in read_cs_files(powers_dir):
        power = parse_power_file(class_name, content)
        if not power:
            continue

        # Localization — power keys use _POWER suffix
        # e.g., VulnerablePower -> VULNERABLE_POWER
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            power["loc_key"] = loc_key
            power["title"] = loc_data.get(f"{loc_key}.title", class_name)
            power["description"] = loc_data.get(f"{loc_key}.description", "")
            power["smart_description"] = loc_data.get(f"{loc_key}.smartDescription", "")
        else:
            power["loc_key"] = class_name
            power["title"] = class_name.removesuffix("Power")
            power["description"] = ""
            power["smart_description"] = ""

        powers.append(power)

    output_path = os.path.join(output_dir, "powers.json")
    write_json(output_path, powers)

    print(f"Extracted {len(powers)} powers to {output_path}")
    buffs = sum(1 for p in powers if p.get("type") == "Buff")
    debuffs = sum(1 for p in powers if p.get("type") == "Debuff")
    print(f"  Buffs: {buffs}, Debuffs: {debuffs}")

    unmatched = [
        p for p in powers if p.get("title") == p.get("class_name", "").removesuffix("Power")
    ]
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} powers without localization:")
        for p in unmatched[:10]:
            print(f"  {p['class_name']}")


if __name__ == "__main__":
    main()
