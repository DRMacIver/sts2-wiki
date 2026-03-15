#!/usr/bin/env python3
"""Extract event data from STS2 decompiled code + localization."""

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


def parse_event_options(content: str) -> list[str]:
    """Extract option localization keys from GenerateInitialOptions() method.

    Looks for EventOption constructor patterns and extracts the option key
    (first string argument), which is the localization key for that option.
    """
    options: list[str] = []

    # Find GenerateInitialOptions method body
    gen_section = re.search(r"GenerateInitialOptions\(\).*?\{(.*?)\n\t\}", content, re.DOTALL)
    if gen_section:
        body = gen_section.group(1)
    else:
        # Fallback: search entire file
        body = content

    # Match EventOption("OPTION_KEY", ...) or new EventOption("OPTION_KEY" ...)
    for m in re.finditer(r'(?:new\s+)?EventOption\(\s*"([^"]+)"', body):
        key = m.group(1)
        if key not in options:
            options.append(key)

    return options


def parse_is_allowed(content: str) -> list[str]:
    """Parse the IsAllowed method body for readable conditions.

    Returns a list of human-readable condition strings.
    """
    conditions: list[str] = []

    # Find IsAllowed method body
    allowed_section = re.search(r"IsAllowed.*?\{(.*?)\n\t\}", content, re.DOTALL)
    if not allowed_section:
        # Try property-style: IsAllowed =>
        allowed_section = re.search(r"IsAllowed\s*=>(.*?);", content, re.DOTALL)
    if not allowed_section:
        return conditions

    body = allowed_section.group(1)

    # Gold requirements: Gold >= N or Gold > N
    for m in re.finditer(r"Gold\s*(>=?)\s*(\d+)", body):
        op = m.group(1)
        amount = m.group(2)
        conditions.append(f"Gold {op} {amount}")

    # Max HP requirements
    for m in re.finditer(r"MaxHp\s*(>=?|<=?)\s*(\d+)", body):
        conditions.append(f"Max HP {m.group(1)} {m.group(2)}")

    # Current HP requirements
    for m in re.finditer(r"(?:CurrentHp|Hp)\s*(>=?|<=?|==)\s*(\d+)", body):
        conditions.append(f"HP {m.group(1)} {m.group(2)}")

    # HP percentage checks
    for m in re.finditer(r"HpPercent\s*(>=?|<=?)\s*([\d.]+)", body):
        pct = float(m.group(2))
        if pct <= 1.0:
            pct = int(pct * 100)
        conditions.append(f"HP% {m.group(1)} {pct}%")

    # Act requirements: Act == N or ActNumber
    for m in re.finditer(r"(?:Act|ActNumber)\s*(>=?|<=?|==)\s*(\d+)", body):
        conditions.append(f"Act {m.group(1)} {m.group(2)}")

    # HasRelic checks
    for m in re.finditer(r"HasRelic<(\w+)>", body):
        conditions.append(f"Has relic: {m.group(1)}")

    # HasPower checks
    for m in re.finditer(r"HasPower<(\w+)>", body):
        conditions.append(f"Has power: {m.group(1)}")

    # Floor/room requirements
    for m in re.finditer(r"(?:Floor|RoomNumber)\s*(>=?|<=?)\s*(\d+)", body):
        conditions.append(f"Floor {m.group(1)} {m.group(2)}")

    # Deck size checks
    for m in re.finditer(r"(?:DeckSize|Deck\.Count)\s*(>=?|<=?)\s*(\d+)", body):
        conditions.append(f"Deck size {m.group(1)} {m.group(2)}")

    return conditions


def parse_event_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled event .cs file.

    Returns a dict with event data, or None if the file is not an EventModel
    subclass (excluding AncientEventModel).
    """
    # Must extend EventModel but NOT AncientEventModel
    if ": EventModel" not in content:
        return None
    if ": AncientEventModel" in content:
        return None

    event: dict = {"class_name": class_name}

    # Extract option keys
    event["option_keys"] = parse_event_options(content)

    # Extract conditions
    event["conditions"] = parse_is_allowed(content)

    return event


def build_act_event_map(decompiled_dir: str) -> dict[str, list[str]]:
    """Parse act model files to find which events appear in which acts.

    Returns a mapping of event class name -> list of act names.
    """
    acts_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Acts")
    event_to_acts: dict[str, list[str]] = {}

    for act_class_name, content in read_cs_files(acts_dir):
        # Look for ModelDb.Event<ClassName>() references
        for m in re.finditer(r"ModelDb\.Event<(\w+)>\(\)", content):
            event_class = m.group(1)
            if event_class not in event_to_acts:
                event_to_acts[event_class] = []
            if act_class_name not in event_to_acts[event_class]:
                event_to_acts[event_class].append(act_class_name)

    return event_to_acts


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 event data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory (eng/)")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load localization
    loc_data = load_localization(loc_dir, "events")

    # Build act assignment map
    act_event_map = build_act_event_map(decompiled_dir)

    # Parse all event files
    events_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Events")
    events: list[dict] = []

    for class_name, content in read_cs_files(events_dir):
        event = parse_event_file(class_name, content)
        if not event:
            continue

        # Localization — event title is at EVENT_NAME.title
        # Description and options at EVENT_NAME.pages.INITIAL.*
        loc_key = class_name_to_loc_key(class_name)

        # Try direct title key first
        title_key = f"{loc_key}.title"
        if title_key in loc_data:
            event["loc_key"] = loc_key
            event["title"] = loc_data[title_key]
        else:
            # Fallback: try fuzzy match
            found_key = find_loc_key(class_name, loc_data, suffix=".title")
            if found_key:
                event["loc_key"] = found_key
                event["title"] = loc_data.get(f"{found_key}.title", class_name)
                loc_key = found_key
            else:
                event["loc_key"] = loc_key
                event["title"] = class_name
                event["_loc_missing"] = True

        # Description from initial page
        desc_key = f"{loc_key}.pages.INITIAL.description"
        event["description"] = loc_data.get(desc_key, "")

        # Option titles from localization
        option_titles: list[str] = []
        for opt_key in event.get("option_keys", []):
            opt_title_key = f"{loc_key}.pages.INITIAL.options.{opt_key}.title"
            opt_title = loc_data.get(opt_title_key, "")
            if opt_title:
                option_titles.append(opt_title)
            else:
                # Use the raw key as fallback
                option_titles.append(opt_key)
        event["options"] = option_titles

        # Remove the intermediate option_keys from output
        del event["option_keys"]

        # Act assignments
        event["acts"] = act_event_map.get(class_name, [])

        events.append(event)

    # Write output
    output_path = os.path.join(output_dir, "events.json")
    write_json(output_path, events)

    # Stats
    print(f"Extracted {len(events)} events to {output_path}")

    with_acts = sum(1 for e in events if e.get("acts"))
    print(f"  With act assignments: {with_acts}/{len(events)}")

    total_options = sum(len(e.get("options", [])) for e in events)
    print(f"  Total options: {total_options}")

    with_conditions = sum(1 for e in events if e.get("conditions"))
    print(f"  With conditions: {with_conditions}/{len(events)}")

    unmatched = [e for e in events if e.get("_loc_missing")]
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} events without localization match:")
        for e in unmatched[:10]:
            print(f"  {e['class_name']} (tried key: {e['loc_key']})")


if __name__ == "__main__":
    main()
