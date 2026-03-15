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

    # Check ModelDb for shared ancients (AllSharedAncients)
    model_db_path = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models", "ModelDb.cs")
    if os.path.exists(model_db_path):
        with open(model_db_path) as f:
            model_db = f.read()
        # Find "AllSharedAncients =>" property definition
        shared_match = re.search(r"AllSharedAncients\s*=>.*?;", model_db, re.DOTALL)
        if shared_match:
            shared_block = shared_match.group(0)
            for sm in re.finditer(r"AncientEvent<(\w+)>", shared_block):
                ancient_class = sm.group(1)
                ancient_to_acts[ancient_class] = ["All Acts"]

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
    relic_loc = load_localization(loc_dir, "relics")

    # Build relic lookup: class_name -> {title, description, slug}
    relic_lookup: dict[str, dict[str, str]] = {}
    for key in relic_loc:
        if key.endswith(".title"):
            base_key = key.removesuffix(".title")
            title = relic_loc[key]
            desc = relic_loc.get(f"{base_key}.description", "")
            # Strip rich text tags for plain description
            plain_desc = re.sub(r"\[/?[^\]]*\]", "", desc)
            plain_desc = re.sub(r"\{[^}]*\}", "?", plain_desc)
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            # Image filename uses the loc key (UPPER_SNAKE) lowered
            image = base_key.lower()
            info = {"title": title, "description": plain_desc, "slug": slug, "image": image}
            relic_lookup[base_key] = info
            # Also map PascalCase class name
            parts = base_key.split("_")
            camel = "".join(p.capitalize() for p in parts)
            relic_lookup[camel] = info

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

        # Enrich relic offerings with display names and descriptions
        all_relics = list(
            dict.fromkeys(ancient.get("relic_offerings", []) + ancient.get("relic_refs", []))
        )
        enriched_relics: list[dict[str, str]] = []
        for relic_class in all_relics:
            relic_info = relic_lookup.get(relic_class)
            if relic_info:
                enriched_relics.append(relic_info)
            else:
                slug = re.sub(r"[^a-z0-9]+", "-", relic_class.lower()).strip("-")
                enriched_relics.append({"title": relic_class, "description": "", "slug": slug})
        ancient["relic_offerings"] = enriched_relics

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
