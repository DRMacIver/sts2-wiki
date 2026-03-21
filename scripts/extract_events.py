#!/usr/bin/env python3
"""Extract event data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    class_name_to_loc_key,
    find_loc_key,
    load_localization,
    parse_canonical_vars,
    read_cs_files,
    write_json,
)


def parse_event_options(content: str) -> list[str]:
    """Extract option localization keys from GenerateInitialOptions() method.

    Handles multiple patterns:
    - new EventOption(this, Method, "FULL.LOC.KEY", ...)
    - new EventOption(this, Method, InitialOptionKey("KEY"), ...)
    - RelicOption<T>(...) constructors
    """
    options: list[str] = []

    # Pattern 1: Full string loc key containing "options."
    for m in re.finditer(
        r'new\s+EventOption\s*\([^"]*"([^"]*options\.[^"]+)"',
        content,
    ):
        full_key = m.group(1)
        parts = full_key.split(".")
        opt_name = parts[-1] if parts else full_key
        if opt_name not in options:
            options.append(opt_name)

    # Pattern 2: InitialOptionKey("KEY") helper
    for m in re.finditer(
        r'InitialOptionKey\(\s*"([^"]+)"\s*\)',
        content,
    ):
        opt_name = m.group(1)
        if opt_name not in options:
            options.append(opt_name)

    # Pattern 3: RelicOption<ClassName>() — extract relic class name as option
    for m in re.finditer(
        r"RelicOption<(\w+)>\s*\(",
        content,
    ):
        opt_name = m.group(1)
        if opt_name not in options:
            options.append(opt_name)

    # Pattern 4: String concatenation with variable + ".options."
    # e.g., "EVENT_NAME.pages.INITIAL.options." + variableName
    for m in re.finditer(
        r'"[^"]*options\.\s*"\s*\+\s*(\w+)',
        content,
    ):
        # Can't resolve the variable, but mark that options exist
        # We'll use a placeholder
        opt_name = f"DYNAMIC_{m.group(1)}"
        if opt_name not in options:
            options.append(opt_name)

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

    # Act requirements: Act == N or ActNumber or CurrentActIndex
    for m in re.finditer(r"(?:Act|ActNumber)\s*(>=?|<=?|==)\s*(\d+)", body):
        conditions.append(f"Act {m.group(1)} {m.group(2)}")
    # CurrentActIndex checks — these appear in rejection clauses
    # (if condition: return false), so the meaning is inverted:
    # "if CurrentActIndex < 1: return false" means "requires Act 2+"
    for m in re.finditer(r"CurrentActIndex\s*(<|>|<=|>=)\s*(\d+)", body):
        op = m.group(1)
        idx = int(m.group(2))
        # In IsAllowed, these are rejection conditions, so invert:
        # "< 1 → reject" means "requires >= 1" = Act 2+
        # "> 0 → accept" (in direct return) means Act 2+
        if op == "<" and idx == 1:
            conditions.append("Act 2+")
        elif op == ">" and idx == 0:
            conditions.append("Act 2+")
        elif op == "<" and idx == 2:
            conditions.append("Act 3 excluded")
        else:
            conditions.append(f"Act index {op} {idx}")

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

    # CurrentActIndex == 0 with return false means Act 2+ (rejection of Act 1)
    if re.search(r"CurrentActIndex\s*==\s*0\)?\s*\{?\s*return\s+false", body, re.DOTALL):
        if "Act 2+" not in conditions:
            conditions.append("Act 2+")
    # CurrentActIndex == 0 in acceptance context means Act 1 only
    elif re.search(r"CurrentActIndex\s*==\s*0", body):
        conditions.append("Act 1 only")

    # Enchantment requirements (has enchantable cards)
    if re.search(r"CanEnchant", body):
        conditions.append("Has enchantable cards")

    # Strike/Defend count requirements
    sd_m = re.search(
        r"Count.*?CardTag\.Strike.*?>=?\s*(\d+).*?CardTag\.Defend.*?>=?\s*(\d+)",
        body,
        re.DOTALL,
    )
    if sd_m:
        conditions.append(f"Has {sd_m.group(1)}+ Strikes and {sd_m.group(2)}+ Defends")

    # Tradable relic requirements
    tr_m = re.search(
        r"(?:IsTradable|Tradable|GetValidRelics).*?Count.*?>=?\s*(\d+)",
        body,
        re.DOTALL,
    )
    if tr_m:
        conditions.append(f"Has {tr_m.group(1)}+ tradable relics")

    # Multiplayer restrictions
    if re.search(r"Players\.Count\s*>\s*1.*return\s+false", body, re.DOTALL):
        conditions.append("Single player only")

    # Potion requirements
    for m in re.finditer(r"Potions\.Any.*?(\w+Potion)", body):
        conditions.append(f"OR has {m.group(1)}")

    return conditions


def parse_event_vars(content: str, cards_loc: dict[str, str]) -> dict[str, str]:
    """Extract DynamicVar definitions from CanonicalVars.

    Resolves:
    - StringVar("Name", ModelDb.Card<Class>().Title) → card title
    - StringVar("Name", "literal") → literal
    - IntVar("Name", Nm) → N
    - DamageVar("Name", Nm, ...) → N

    Returns a mapping of var name -> resolved string value.
    """
    resolved: dict[str, str] = {}

    # StringVar with card title: new StringVar("VarName", ModelDb.Card<ClassName>().Title)
    for m in re.finditer(
        r'new\s+StringVar\s*\(\s*"(\w+)"\s*,\s*ModelDb\.Card<(\w+)>\(\)\.Title\s*\)',
        content,
    ):
        var_name = m.group(1)
        card_class = m.group(2)
        card_key = class_name_to_loc_key(card_class)
        card_title = cards_loc.get(f"{card_key}.title", card_class)
        resolved[var_name] = card_title

    # StringVar with literal: new StringVar("VarName", "literal")
    for m in re.finditer(
        r'new\s+StringVar\s*\(\s*"(\w+)"\s*,\s*"([^"]+)"\s*\)',
        content,
    ):
        resolved[m.group(1)] = m.group(2)

    # IntVar: new IntVar("VarName", Nm) where N is the integer value
    for m in re.finditer(
        r'new\s+IntVar\s*\(\s*"(\w+)"\s*,\s*(-?\d+)m',
        content,
    ):
        resolved[m.group(1)] = m.group(2)

    # DamageVar: new DamageVar("VarName", Nm, ...)
    for m in re.finditer(
        r'new\s+DamageVar\s*\(\s*"(\w+)"\s*,\s*(-?\d+)m',
        content,
    ):
        resolved[m.group(1)] = m.group(2)

    # Also pick up canonical vars (MaxHpVar, GoldVar, HealVar, etc.)
    # Skip vars with base_value 0 — these are placeholders for runtime computation
    for v in parse_canonical_vars(content):
        if v["base_value"] == 0:
            continue
        vtype = v["type"]
        resolved[vtype] = str(v["base_value"])
        # Also register with "Power" suffix stripped
        if vtype.endswith("Power"):
            resolved[vtype.removesuffix("Power")] = str(v["base_value"])

    return resolved


def resolve_vars_in_text(text: str, vars_map: dict[str, str]) -> str:
    """Replace {VarName} placeholders with resolved values."""
    for name, value in vars_map.items():
        text = text.replace(f"{{{name}}}", value)
    return text


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

    # Extract referenced cards (ModelDb.Card<X>())
    card_refs: list[str] = []
    for m in re.finditer(r"ModelDb\.Card<(\w+)>\(\)", content):
        if m.group(1) not in card_refs:
            card_refs.append(m.group(1))
    if card_refs:
        event["card_refs"] = card_refs

    # Extract referenced relics (ModelDb.Relic<X>())
    relic_refs: list[str] = []
    for m in re.finditer(r"ModelDb\.Relic<(\w+)>\(\)", content):
        if m.group(1) not in relic_refs:
            relic_refs.append(m.group(1))
    if relic_refs:
        event["relic_refs"] = relic_refs

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
    cards_loc = load_localization(loc_dir, "cards")
    # Build title lookups from existing data files
    import json as json_mod

    card_titles: dict[str, str] = {}
    cards_path = os.path.join(output_dir, "cards.json")
    if os.path.exists(cards_path):
        with open(cards_path) as f:
            for c in json_mod.load(f):
                card_titles[c["class_name"]] = c["title"]

    relic_titles: dict[str, str] = {}
    relics_path = os.path.join(output_dir, "relics.json")
    if os.path.exists(relics_path):
        with open(relics_path) as f:
            for r in json_mod.load(f):
                relic_titles[r["class_name"]] = r["title"]

    def slugify(name: str) -> str:
        s = name.lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    # Build act assignment map
    act_event_map = build_act_event_map(decompiled_dir)

    # Parse all event files
    events_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Events")
    events: list[dict] = []

    for class_name, content in read_cs_files(events_dir):
        event = parse_event_file(class_name, content)
        if not event:
            continue

        # Resolve StringVar definitions (e.g. Card1 = UltimateStrike title)
        string_vars = parse_event_vars(content, cards_loc)

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
        desc = loc_data.get(desc_key, "")
        event["description"] = resolve_vars_in_text(desc, string_vars)

        # Option titles and descriptions from localization
        # Search INITIAL page first, then try all other pages for the key
        options: list[dict[str, str]] = []
        for opt_key in event.get("option_keys", []):
            # Skip DYNAMIC_ placeholders
            if opt_key.startswith("DYNAMIC_"):
                continue

            opt_title = opt_key
            opt_desc = ""

            # Try INITIAL page first
            initial_title_key = f"{loc_key}.pages.INITIAL.options.{opt_key}.title"
            if initial_title_key in loc_data:
                opt_title = loc_data[initial_title_key]
                opt_desc = loc_data.get(
                    f"{loc_key}.pages.INITIAL.options.{opt_key}.description", ""
                )
            else:
                # Search all pages for this option key
                suffix = f".options.{opt_key}.title"
                for lk, lv in loc_data.items():
                    if lk.startswith(f"{loc_key}.pages.") and lk.endswith(suffix):
                        opt_title = lv
                        desc_key = lk.replace(".title", ".description")
                        opt_desc = loc_data.get(desc_key, "")
                        break

            options.append(
                {
                    "title": resolve_vars_in_text(opt_title, string_vars),
                    "description": resolve_vars_in_text(opt_desc, string_vars),
                }
            )
        event["options"] = options

        # Remove the intermediate option_keys from output
        del event["option_keys"]

        # Act assignments
        event["acts"] = act_event_map.get(class_name, [])

        # Enrich card refs with titles and slugs
        if "card_refs" in event:
            event["card_refs"] = [
                {
                    "class_name": c,
                    "title": card_titles.get(c, c),
                    "slug": slugify(card_titles.get(c, c)),
                }
                for c in event["card_refs"]
            ]

        # Enrich relic refs with titles and slugs
        if "relic_refs" in event:
            event["relic_refs"] = [
                {
                    "class_name": r,
                    "title": relic_titles.get(r, r),
                    "slug": slugify(relic_titles.get(r, r)),
                }
                for r in event["relic_refs"]
            ]

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
