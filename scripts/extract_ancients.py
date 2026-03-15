#!/usr/bin/env python3
"""Extract Ancient event data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    class_name_to_loc_key,
    find_loc_key,
    load_localization,
    read_cs_files,
    write_json,
)


def parse_ancient_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled ancient event .cs file.

    Returns a dict with class_name, relic_offerings, and relic_refs,
    or None if the file is not an AncientEventModel subclass.
    """
    if ": AncientEventModel" not in content:
        return None

    ancient: dict = {"class_name": class_name}

    # Extract relic offerings from RelicOption<ClassName>() patterns
    relic_offerings: list[str] = []
    for m in re.finditer(r"RelicOption<(\w+)>\(\)", content):
        relic_class = m.group(1)
        if relic_class not in relic_offerings:
            relic_offerings.append(relic_class)
    ancient["relic_offerings"] = relic_offerings

    # Also extract ModelDb.Relic<ClassName>() references
    relic_refs: list[str] = []
    for m in re.finditer(r"ModelDb\.Relic<(\w+)>\(\)", content):
        relic_class = m.group(1)
        if relic_class not in relic_refs and relic_class not in relic_offerings:
            relic_refs.append(relic_class)
    if relic_refs:
        ancient["relic_refs"] = relic_refs

    return ancient


def build_act_ancient_map(decompiled_dir: str) -> dict[str, list[str]]:
    """Parse act model files to find which ancients appear in which acts.

    Returns a mapping of ancient class name -> list of act names.
    """
    acts_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Acts")
    ancient_to_acts: dict[str, list[str]] = {}

    for act_class_name, content in read_cs_files(acts_dir):
        # Look for ModelDb.AncientEvent<ClassName>() references
        for m in re.finditer(r"ModelDb\.AncientEvent<(\w+)>\(\)", content):
            ancient_class = m.group(1)
            if ancient_class not in ancient_to_acts:
                ancient_to_acts[ancient_class] = []
            if act_class_name not in ancient_to_acts[ancient_class]:
                ancient_to_acts[ancient_class].append(act_class_name)

        # Also check AllAncients property blocks for ancient references
        # These may list ancients as new ClassName() or similar patterns
        all_ancients_match = re.search(r"AllAncients.*?\{(.*?)\}", content, re.DOTALL)
        if all_ancients_match:
            block = all_ancients_match.group(1)
            for am in re.finditer(r"new (\w+)\(\)", block):
                ancient_class = am.group(1)
                if ancient_class not in ancient_to_acts:
                    ancient_to_acts[ancient_class] = []
                if act_class_name not in ancient_to_acts[ancient_class]:
                    ancient_to_acts[ancient_class].append(act_class_name)

    return ancient_to_acts


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 ancient event data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory (eng/)")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load localization
    loc_data = load_localization(loc_dir, "ancients")

    # Build act assignment map
    act_ancient_map = build_act_ancient_map(decompiled_dir)

    # Parse all ancient event files
    events_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Events")
    ancients: list[dict] = []

    for class_name, content in read_cs_files(events_dir):
        ancient = parse_ancient_file(class_name, content)
        if not ancient:
            continue

        # Localization — ancient keys are UPPER_SNAKE_CASE of class name
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            ancient["loc_key"] = loc_key
            ancient["title"] = loc_data.get(f"{loc_key}.title", class_name)
            ancient["epithet"] = loc_data.get(f"{loc_key}.epithet", "")
        else:
            ancient["loc_key"] = class_name_to_loc_key(class_name)
            ancient["title"] = class_name
            ancient["epithet"] = ""
            ancient["_loc_missing"] = True

        # Act assignments
        acts = act_ancient_map.get(class_name, [])
        ancient["acts"] = acts

        ancients.append(ancient)

    # Write output
    output_path = os.path.join(output_dir, "ancients.json")
    write_json(output_path, ancients)

    # Stats
    print(f"Extracted {len(ancients)} ancients to {output_path}")
    total_relics = sum(len(a.get("relic_offerings", [])) for a in ancients)
    print(f"  Total relic offerings: {total_relics}")

    with_acts = sum(1 for a in ancients if a.get("acts"))
    print(f"  With act assignments: {with_acts}/{len(ancients)}")

    unmatched = [a for a in ancients if a.get("_loc_missing")]
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} ancients without localization match:")
        for a in unmatched[:10]:
            print(f"  {a['class_name']} (tried key: {a['loc_key']})")


if __name__ == "__main__":
    main()
