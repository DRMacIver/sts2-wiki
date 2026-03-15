#!/usr/bin/env python3
"""Extract monster data from STS2 decompiled C# source code + localization."""

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

# Companion monsters that fight on the player's side, not as enemies
COMPANION_CLASSES = {
    "Osty",
    "BattleFriendV1",
    "BattleFriendV2",
    "BattleFriendV3",
    "Byrdpip",
    "PaelsLegion",
}


def parse_hp(content: str) -> tuple[int | None, int | None]:
    """Extract MinInitialHp and MaxInitialHp from monster source.

    Handles several patterns:
      - `MinInitialHp => N;`
      - `MinInitialHp { get } = N;`
      - `AscensionHelper.GetValueIfAscension(..., base, ascension)` — uses base value
    """
    min_hp = None
    max_hp = None

    for prop_name, target in [("MinInitialHp", "min"), ("MaxInitialHp", "max")]:
        # Pattern 1: arrow property  `MinInitialHp => 51;`
        m = re.search(rf"{prop_name}\s*=>\s*(\d+)\s*;", content)
        if m:
            val = int(m.group(1))
        else:
            # Pattern 2: auto-property  `MinInitialHp { get } = 51;`
            m = re.search(rf"{prop_name}\s*\{{\s*get\s*\}}\s*=\s*(\d+)\s*;", content)
            if m:
                val = int(m.group(1))
            else:
                # Pattern 3: AscensionHelper — use first (base) value
                m = re.search(
                    rf"{prop_name}\s*=>"
                    r"\s*AscensionHelper\.GetValueIfAscension\([^,]+,\s*(\d+),\s*(\d+)\)",
                    content,
                )
                if m:
                    val = int(m.group(1))
                else:
                    # Pattern 4: AscensionHelper in auto-property form
                    m = re.search(
                        rf"{prop_name}\s*\{{\s*get\s*\}}\s*=\s*"
                        r"AscensionHelper\.GetValueIfAscension\([^,]+,\s*(\d+),\s*(\d+)\)",
                        content,
                    )
                    if m:
                        val = int(m.group(1))
                    else:
                        continue

        if target == "min":
            min_hp = val
        else:
            max_hp = val

    return min_hp, max_hp


def parse_intent(intent_text: str) -> dict:
    """Parse a single intent constructor into a structured dict.

    Examples:
        `new SingleAttackIntent(12)` -> {"type": "attack", "damage": 12}
        `new MultiAttackIntent(6, 3)` -> {"type": "multi_attack", "damage": 6, "hits": 3}
        `new BuffIntent()` -> {"type": "buff"}
        `new DebuffIntent()` -> {"type": "debuff"}
        `new BlockIntent(8)` -> {"type": "block", "amount": 8}
        `new StunIntent()` -> {"type": "stun"}
    """
    intent_text = intent_text.strip()

    m = re.search(r"new\s+SingleAttackIntent\((\d+)\)", intent_text)
    if m:
        return {"type": "attack", "damage": int(m.group(1))}

    m = re.search(r"new\s+MultiAttackIntent\((\d+),\s*(\d+)\)", intent_text)
    if m:
        return {"type": "multi_attack", "damage": int(m.group(1)), "hits": int(m.group(2))}

    if re.search(r"new\s+BuffIntent\s*\(", intent_text):
        return {"type": "buff"}

    if re.search(r"new\s+DebuffIntent\s*\(", intent_text):
        return {"type": "debuff"}

    m = re.search(r"new\s+BlockIntent\((\d+)\)", intent_text)
    if m:
        return {"type": "block", "amount": int(m.group(1))}

    if re.search(r"new\s+StunIntent\s*\(", intent_text):
        return {"type": "stun"}

    # Fallback: capture the intent class name
    m = re.search(r"new\s+(\w+Intent)\s*\(", intent_text)
    if m:
        return {"type": m.group(1)}

    return {"type": "unknown"}


def parse_intents_from_args(args_text: str) -> list[dict]:
    """Parse all intents from the arguments portion of a MoveState constructor.

    The intents appear after the method delegate as `new XIntent(...)` arguments.
    """
    intents = []
    for m in re.finditer(r"new\s+\w*Intent\s*\([^)]*\)", args_text):
        intent = parse_intent(m.group(0))
        intents.append(intent)
    return intents


def extract_method_body(content: str, method_name: str) -> str | None:
    """Extract the body of a method by name, handling brace nesting."""
    # Find the method signature
    escaped = re.escape(method_name)
    pattern = rf"(?:private|public|protected|internal|static|\s)*\w[\w<>\[\],\s]*\s+{escaped}\s*\("
    m = re.search(pattern, content)
    if not m:
        return None

    # Find the opening brace after the method signature
    start = m.start()
    brace_pos = content.find("{", start)
    if brace_pos == -1:
        return None

    # Walk through and match braces
    depth = 0
    i = brace_pos
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return content[brace_pos : i + 1]
        i += 1
    return None


def parse_moves(content: str) -> list[dict]:
    """Parse MoveState declarations from GenerateMoveStateMachine() method.

    Extracts move IDs, intents, and follow-up state links.
    """
    method_body = extract_method_body(content, "GenerateMoveStateMachine")
    if not method_body:
        return []

    moves: list[dict] = []
    # Map variable names to move dicts for follow-up resolution
    var_to_move: dict[str, dict] = {}

    # Pattern: `MoveState varName = new MoveState("MOVE_ID", MethodRef, ...intents...);`
    # The constructor can span multiple lines, so we use DOTALL-friendly matching.
    # We'll find each `new MoveState(` and manually extract the full constructor call.
    move_state_pattern = re.compile(r"MoveState\s+(\w+)\s*=\s*new\s+MoveState\s*\(", re.DOTALL)

    for m in move_state_pattern.finditer(method_body):
        var_name = m.group(1)
        # Find the matching closing paren for the constructor
        start = m.end()  # position right after the opening paren
        depth = 1
        i = start
        while i < len(method_body) and depth > 0:
            if method_body[i] == "(":
                depth += 1
            elif method_body[i] == ")":
                depth -= 1
            i += 1
        constructor_args = method_body[start : i - 1]

        # First arg is the string ID
        id_match = re.search(r'"([^"]+)"', constructor_args)
        if not id_match:
            continue
        move_id = id_match.group(1)

        # Parse intents from the rest of the constructor args
        intents = parse_intents_from_args(constructor_args)

        move: dict = {
            "id": move_id,
            "intents": intents,
        }
        moves.append(move)
        var_to_move[var_name] = move

    # Parse follow-up states: `varName.FollowUpState = otherVar;`
    followup_pattern = re.compile(r"(\w+)\.FollowUpState\s*=\s*(\w+)\s*;")
    for m in followup_pattern.finditer(method_body):
        src_var = m.group(1)
        dst_var = m.group(2)
        if src_var in var_to_move and dst_var in var_to_move:
            var_to_move[src_var]["follow_up"] = var_to_move[dst_var]["id"]

    return moves


def parse_move_effects(content: str, moves: list[dict]) -> None:
    """For each move, try to find the execution method and extract effects.

    Looks for PowerCmd.Apply<PowerName>, DamageCmd.Attack,
    CardPileCmd.AddToCombatAndPreview<CardName> in move handler methods.
    """
    for move in moves:
        move_id = move["id"]

        # The method name is usually derived from the move ID or referenced in
        # the MoveState constructor. We look for methods that contain the move ID
        # or a name that matches a common pattern.
        # Heuristic: search for methods whose name appears right after the move ID
        # in the MoveState constructor. Since we already parsed constructor args,
        # look for method references near the move declaration.

        # Alternative approach: scan all methods for PowerCmd.Apply and DamageCmd.Attack
        # and correlate based on what we find. For simplicity, we look at the whole file
        # and try to attribute effects to moves by method name matching.

        effects: list[str] = []

        # Try to find a method name that relates to the move ID.
        # Common pattern: move "DARK_STRIKE_MOVE" might use method "DarkStrike"
        # Strip _MOVE suffix, convert to PascalCase for method lookup
        base_name = move_id.removesuffix("_MOVE")
        # Convert UPPER_SNAKE to PascalCase
        pascal_name = "".join(part.capitalize() for part in base_name.split("_"))

        # Look for a method with this name
        method_body = extract_method_body(content, pascal_name)
        if not method_body:
            # Try alternative: the method might be named differently. Try with "Execute" suffix
            method_body = extract_method_body(content, pascal_name + "Execute")
        if not method_body:
            # Try lowercase first letter
            if pascal_name:
                alt = pascal_name[0].lower() + pascal_name[1:]
                method_body = extract_method_body(content, alt)

        if method_body:
            # Extract effects from the method body
            for pm in re.finditer(r"PowerCmd\.Apply<(\w+)>", method_body):
                effects.append(f"Apply {pm.group(1)}")

            if "DamageCmd.Attack" in method_body:
                effects.append("Attack")

            for cm in re.finditer(r"CardPileCmd\.AddToCombatAndPreview<(\w+)>", method_body):
                effects.append(f"Add {cm.group(1)}")

            for cm in re.finditer(r"CardPileCmd\.AddToDiscardPile<(\w+)>", method_body):
                effects.append(f"Add {cm.group(1)} to discard")

        if effects:
            move["effects"] = effects


def parse_powers_on_spawn(content: str) -> list[str]:
    """Look for PowerCmd.Apply in AfterAddedToRoom method for powers applied on spawn."""
    method_body = extract_method_body(content, "AfterAddedToRoom")
    if not method_body:
        return []

    powers = []
    for m in re.finditer(r"PowerCmd\.Apply<(\w+)>", method_body):
        powers.append(m.group(1))
    return powers


def parse_monster_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled monster .cs file into a structured dict."""
    # Must be a monster model (extends MonsterModel or a known base)
    if (
        ": MonsterModel" not in content
        and ": EliteModel" not in content
        and ": BossModel" not in content
    ):
        # Some monsters extend other base classes; look for GenerateMoveStateMachine as a signal
        if "GenerateMoveStateMachine" not in content:
            return None

    monster: dict = {"class_name": class_name}

    # HP
    min_hp, max_hp = parse_hp(content)
    if min_hp is not None:
        monster["min_hp"] = min_hp
    if max_hp is not None:
        monster["max_hp"] = max_hp

    # Moves
    moves = parse_moves(content)

    # Move effects
    parse_move_effects(content, moves)

    if moves:
        monster["moves"] = moves

    # Powers on spawn
    powers = parse_powers_on_spawn(content)
    if powers:
        monster["powers_on_spawn"] = powers

    return monster


def apply_localization(monster: dict, loc_data: dict[str, str]) -> None:
    """Apply localization data to a monster and its moves."""
    class_name = monster["class_name"]

    # Find the monster's localization key
    loc_key = find_loc_key(class_name, loc_data, suffix=".name")
    if not loc_key:
        # Try without common suffixes — some monster class names don't map cleanly
        loc_key = class_name_to_loc_key(class_name)

    monster["loc_key"] = loc_key

    # Monster display name
    name_key = f"{loc_key}.name"
    if name_key in loc_data:
        monster["title"] = loc_data[name_key]
    else:
        # Strip common suffixes for display
        monster["title"] = class_name

    # Move display names
    for move in monster.get("moves", []):
        move_id = move["id"]
        # Strip "_MOVE" suffix for loc key lookup
        move_loc_id = move_id.removesuffix("_MOVE")
        move_title_key = f"{loc_key}.moves.{move_loc_id}.title"
        if move_title_key in loc_data:
            move["title"] = loc_data[move_title_key]
        else:
            # Try with the full move ID as-is
            alt_key = f"{loc_key}.moves.{move_id}.title"
            if alt_key in loc_data:
                move["title"] = loc_data[alt_key]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 monster data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "monsters")

    monsters_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Monsters")
    monsters: list[dict] = []

    for class_name, content in read_cs_files(monsters_dir):
        monster = parse_monster_file(class_name, content)
        if not monster:
            continue

        # Flag companions (they fight on the player's side)
        if class_name in COMPANION_CLASSES:
            monster["is_companion"] = True

        apply_localization(monster, loc_data)
        monsters.append(monster)

    output_path = os.path.join(output_dir, "monsters.json")
    write_json(output_path, monsters)

    print(f"Extracted {len(monsters)} monsters to {output_path}")
    with_moves = sum(1 for m in monsters if m.get("moves"))
    with_hp = sum(1 for m in monsters if m.get("min_hp") is not None)
    print(f"  With HP data: {with_hp}, With moves: {with_moves}")

    unmatched = [m for m in monsters if m.get("title") == m.get("class_name")]
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} monsters without localization:")
        for m in unmatched[:10]:
            print(f"  {m['class_name']}")


if __name__ == "__main__":
    main()
