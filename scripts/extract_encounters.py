#!/usr/bin/env python3
"""Extract encounter and act data from STS2 decompiled code + localization."""

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

# The four acts in the game
ACT_NAMES = ["Overgrowth", "Underdocks", "Hive", "Glory"]


def parse_encounter_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled encounter .cs file.

    Extracts room type, weakness flag, monster composition, and tags.
    """
    # Must look like an encounter class
    if "RoomType" not in content:
        return None

    encounter: dict = {"class_name": class_name}

    # RoomType (Monster, Elite, or Boss)
    m = re.search(r"RoomType\.(\w+)", content)
    if m:
        encounter["room_type"] = m.group(1)

    # IsWeak flag
    encounter["is_weak"] = "IsWeak => true" in content

    # Monster composition from GenerateMonsters() method
    monsters: list[str] = []
    gen_section = re.search(r"GenerateMonsters\(\).*?\{(.*?)\n\t\}", content, re.DOTALL)
    if gen_section:
        body = gen_section.group(1)
        for mm in re.finditer(r"ModelDb\.Monster<(\w+)>\(\)", body):
            monsters.append(mm.group(1))
    if not monsters:
        # Fallback: search the whole file for monster references
        for mm in re.finditer(r"ModelDb\.Monster<(\w+)>\(\)", content):
            monsters.append(mm.group(1))
    encounter["monsters"] = monsters

    # Encounter tags
    tags: list[str] = []
    seen_tags: set[str] = set()
    for tm in re.finditer(r"EncounterTag\.(\w+)", content):
        tag = tm.group(1)
        if tag not in seen_tags:
            seen_tags.add(tag)
            tags.append(tag)
    encounter["tags"] = tags

    return encounter


def parse_act_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled act .cs file.

    Extracts all encounters, boss discovery order, and base room count.
    """
    act: dict = {"class_name": class_name}

    # All encounters from GenerateAllEncounters()
    encounters: list[str] = []
    gen_section = re.search(r"GenerateAllEncounters\(\).*?\{(.*?)\n\t\}", content, re.DOTALL)
    if gen_section:
        body = gen_section.group(1)
        for m in re.finditer(r"ModelDb\.Encounter<(\w+)>\(\)", body):
            encounters.append(m.group(1))
    if not encounters:
        # Fallback: search the whole file
        for m in re.finditer(r"ModelDb\.Encounter<(\w+)>\(\)", content):
            encounters.append(m.group(1))
    act["encounters"] = encounters

    # Boss encounters from BossDiscoveryOrder
    bosses: list[str] = []
    boss_section = re.search(r"BossDiscoveryOrder.*?\{(.*?)\}", content, re.DOTALL)
    if boss_section:
        body = boss_section.group(1)
        for m in re.finditer(r"ModelDb\.Encounter<(\w+)>\(\)", body):
            bosses.append(m.group(1))
    act["bosses"] = bosses

    # BaseNumberOfRooms
    rooms_m = re.search(r"BaseNumberOfRooms\s*(?:=>|=)\s*(\d+)", content)
    if rooms_m:
        act["base_number_of_rooms"] = int(rooms_m.group(1))

    return act


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 encounter and act data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory (eng/)")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # --- Extract encounters ---

    encounter_loc = load_localization(loc_dir, "encounters")

    encounters_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Encounters")
    encounters: list[dict] = []

    for class_name, content in read_cs_files(encounters_dir):
        encounter = parse_encounter_file(class_name, content)
        if not encounter:
            continue

        # Localization: key pattern ENCOUNTER_NAME.title and .loss
        loc_key = find_loc_key(class_name, encounter_loc)
        if loc_key:
            encounter["loc_key"] = loc_key
            encounter["title"] = encounter_loc.get(f"{loc_key}.title", class_name)
            loss_text = encounter_loc.get(f"{loc_key}.loss")
            if loss_text:
                encounter["loss"] = loss_text
        else:
            encounter["loc_key"] = class_name_to_loc_key(class_name)
            encounter["title"] = class_name
            encounter["_loc_missing"] = True

        encounters.append(encounter)

    # --- Extract acts ---

    act_loc = load_localization(loc_dir, "acts")

    acts_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Acts")
    acts: list[dict] = []

    # Build a set of encounter class names belonging to each act for cross-referencing
    act_encounter_map: dict[str, list[str]] = {}

    for class_name, content in read_cs_files(acts_dir):
        if class_name not in ACT_NAMES:
            continue

        act = parse_act_file(class_name, content)
        if not act:
            continue

        act_encounter_map[class_name] = act["encounters"]

        # Localization
        loc_key = find_loc_key(class_name, act_loc)
        if loc_key:
            act["loc_key"] = loc_key
            act["title"] = act_loc.get(f"{loc_key}.title", class_name)
        else:
            act["loc_key"] = class_name_to_loc_key(class_name)
            act["title"] = class_name
            act["_loc_missing"] = True

        acts.append(act)

    # Annotate encounters with their act assignments
    for encounter in encounters:
        assigned_acts: list[str] = []
        for act_name, enc_list in act_encounter_map.items():
            if encounter["class_name"] in enc_list:
                assigned_acts.append(act_name)
        encounter["acts"] = assigned_acts

    # --- Write output ---

    encounters_path = os.path.join(output_dir, "encounters.json")
    write_json(encounters_path, encounters)

    acts_path = os.path.join(output_dir, "acts.json")
    write_json(acts_path, acts)

    # Stats
    print(f"Extracted {len(encounters)} encounters to {encounters_path}")
    by_type: dict[str, int] = {}
    for e in encounters:
        rt = e.get("room_type", "Unknown")
        by_type[rt] = by_type.get(rt, 0) + 1
    for rt, count in sorted(by_type.items()):
        print(f"  {rt}: {count}")
    weak_count = sum(1 for e in encounters if e.get("is_weak"))
    print(f"  Weak encounters: {weak_count}")

    print(f"\nExtracted {len(acts)} acts to {acts_path}")
    for act in acts:
        enc_count = len(act.get("encounters", []))
        boss_count = len(act.get("bosses", []))
        rooms = act.get("base_number_of_rooms", "?")
        print(f"  {act['class_name']}: {enc_count} encounters, {boss_count} bosses, {rooms} rooms")

    unmatched_enc = [e for e in encounters if e.get("_loc_missing")]
    if unmatched_enc:
        print(f"\nWARNING: {len(unmatched_enc)} encounters without localization:")
        for e in unmatched_enc[:10]:
            print(f"  {e['class_name']}")

    unmatched_acts = [a for a in acts if a.get("_loc_missing")]
    if unmatched_acts:
        print(f"\nWARNING: {len(unmatched_acts)} acts without localization:")
        for a in unmatched_acts[:10]:
            print(f"  {a['class_name']}")


if __name__ == "__main__":
    main()
