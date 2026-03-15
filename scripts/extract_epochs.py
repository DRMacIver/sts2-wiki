#!/usr/bin/env python3
"""Extract epoch/unlock progression data from STS2 decompiled code."""

import argparse
import os
import re

from scripts.common import (
    load_localization,
    read_cs_files,
    write_json,
)


def parse_epoch_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled epoch .cs file."""
    if ": EpochModel" not in content:
        return None

    epoch: dict = {"class_name": class_name}

    # Id
    m = re.search(r'override string Id\s*=>\s*"([^"]+)"', content)
    if m:
        epoch["id"] = m.group(1)

    # Era
    m = re.search(r"EpochEra\.(\w+)", content)
    if m:
        epoch["era"] = m.group(1)

    # EraPosition
    m = re.search(r"EraPosition\s*=>\s*(\d+)", content)
    if m:
        epoch["era_position"] = int(m.group(1))

    # StoryId
    m = re.search(r'StoryId\s*=>\s*"([^"]+)"', content)
    if m:
        epoch["story"] = m.group(1)

    # Cards unlocked
    cards: list[str] = []
    for m in re.finditer(r"ModelDb\.Card<(\w+)>\(\)", content):
        if m.group(1) not in cards:
            cards.append(m.group(1))
    if cards:
        epoch["unlocks_cards"] = cards

    # Relics unlocked
    relics: list[str] = []
    for m in re.finditer(r"ModelDb\.Relic<(\w+)>\(\)", content):
        if m.group(1) not in relics:
            relics.append(m.group(1))
    if relics:
        epoch["unlocks_relics"] = relics

    # Events unlocked
    events: list[str] = []
    for m in re.finditer(r"ModelDb\.Event<(\w+)>\(\)", content):
        if m.group(1) not in events:
            events.append(m.group(1))
    if events:
        epoch["unlocks_events"] = events

    # Ancients unlocked
    ancients: list[str] = []
    for m in re.finditer(r"ModelDb\.AncientEvent<(\w+)>\(\)", content):
        if m.group(1) not in ancients:
            ancients.append(m.group(1))
    if ancients:
        epoch["unlocks_ancients"] = ancients

    # Encounters unlocked
    encounters: list[str] = []
    for m in re.finditer(r"ModelDb\.Encounter<(\w+)>\(\)", content):
        if m.group(1) not in encounters:
            encounters.append(m.group(1))
    if encounters:
        epoch["unlocks_encounters"] = encounters

    # Potions unlocked
    potions: list[str] = []
    for m in re.finditer(r"ModelDb\.Potion<(\w+)>\(\)", content):
        if m.group(1) not in potions:
            potions.append(m.group(1))
    if potions:
        epoch["unlocks_potions"] = potions

    return epoch


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 epoch data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "epochs")

    epochs_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Timeline.Epochs")
    epochs: list[dict] = []

    for class_name, content in read_cs_files(epochs_dir):
        epoch = parse_epoch_file(class_name, content)
        if not epoch:
            continue

        # Localization
        epoch_id = epoch.get("id", "")
        title_key = f"{epoch_id}.title"
        desc_key = f"{epoch_id}.description"
        epoch["title"] = loc_data.get(title_key, epoch.get("story", class_name))
        epoch["description"] = loc_data.get(desc_key, "")

        epochs.append(epoch)

    # Sort by era then position
    era_order = {
        "Discovery": 0,
        "Growth1": 1,
        "Growth2": 2,
        "Blight1": 3,
        "Blight2": 4,
        "Mastery": 5,
    }
    epochs.sort(key=lambda e: (era_order.get(e.get("era", ""), 99), e.get("era_position", 0)))

    output_path = os.path.join(output_dir, "epochs.json")
    write_json(output_path, epochs)

    total_cards = sum(len(e.get("unlocks_cards", [])) for e in epochs)
    total_relics = sum(len(e.get("unlocks_relics", [])) for e in epochs)
    print(f"Extracted {len(epochs)} epochs to {output_path}")
    print(f"  Unlocks: {total_cards} cards, {total_relics} relics")


if __name__ == "__main__":
    main()
