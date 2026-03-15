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
    """Extract MinInitialHp and MaxInitialHp."""
    min_hp = None
    max_hp = None

    for target, prop_name in [("min", "MinInitialHp"), ("max", "MaxInitialHp")]:
        # Pattern 1: => N;
        m = re.search(rf"{prop_name}\s*=>\s*(\d+)\s*;", content)
        if m:
            val = int(m.group(1))
        else:
            # Pattern 2: => AscensionHelper.GetValueIfAscension(level, ascVal, baseVal)
            m = re.search(
                rf"{prop_name}\s*=>\s*AscensionHelper\.GetValueIfAscension\([^,]+,\s*(\d+),\s*(\d+)\)",
                content,
            )
            if m:
                val = int(m.group(1))  # Use ascension value (higher)
            else:
                continue

        if target == "min":
            min_hp = val
        else:
            max_hp = val

    return min_hp, max_hp


def parse_intent(text: str) -> dict:
    """Parse a single intent constructor."""
    # SingleAttackIntent with numeric literal
    m = re.search(r"SingleAttackIntent\((\d+)\)", text)
    if m:
        return {"type": "attack", "damage": int(m.group(1))}

    # SingleAttackIntent with variable reference (e.g., DarkStrikeDamage)
    m = re.search(r"SingleAttackIntent\((\w+)\)", text)
    if m and not m.group(1)[0].isupper():
        return {"type": "attack"}
    if m:
        return {"type": "attack"}

    # MultiAttackIntent
    m = re.search(r"MultiAttackIntent\((\d+),\s*(\d+)\)", text)
    if m:
        return {"type": "multi_attack", "damage": int(m.group(1)), "hits": int(m.group(2))}
    m = re.search(r"MultiAttackIntent\((\w+),\s*(\d+)\)", text)
    if m:
        return {"type": "multi_attack", "hits": int(m.group(2))}
    if "MultiAttackIntent" in text:
        return {"type": "multi_attack"}

    if "BuffIntent" in text:
        return {"type": "buff"}
    if "DebuffIntent" in text:
        return {"type": "debuff"}

    m = re.search(r"BlockIntent\((\d+)\)", text)
    if m:
        return {"type": "block", "amount": int(m.group(1))}
    if "BlockIntent" in text:
        return {"type": "block"}

    if "StunIntent" in text:
        return {"type": "stun"}
    if "SleepIntent" in text:
        return {"type": "sleep"}
    if "SummonIntent" in text or "SpawnIntent" in text:
        return {"type": "summon"}
    if "HealIntent" in text:
        return {"type": "heal"}
    if "EscapeIntent" in text:
        return {"type": "escape"}
    if "DeathBlowIntent" in text:
        return {"type": "death_blow"}
    if "StatusIntent" in text:
        return {"type": "status"}

    m = re.search(r"(\w+Intent)", text)
    if m:
        return {"type": m.group(1)}

    return {"type": "unknown"}


def extract_method_body(content: str, method_name: str) -> str | None:
    """Extract the body of a method by name, handling brace nesting."""
    escaped = re.escape(method_name)
    modifiers = r"(?:private|public|protected|internal|override|virtual|static|async|\s)+"
    pattern = rf"{modifiers}\w[\w<>\[\],\s]*\s+{escaped}\s*\("
    m = re.search(pattern, content)
    if not m:
        return None

    brace_pos = content.find("{", m.start())
    if brace_pos == -1:
        return None

    depth = 0
    i = brace_pos
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return content[brace_pos + 1 : i]
        i += 1
    return None


def parse_move_effects(content: str, move_id: str) -> list[str]:
    """Extract detailed effects from a move's execution method."""
    # Convert MOVE_ID to likely method name: DARK_STRIKE_MOVE -> DarkStrike, then DarkStrikeMove
    base = move_id.removesuffix("_MOVE")
    parts = base.split("_")
    method_name = "".join(p.capitalize() for p in parts)

    # Try MethodNameMove first, then MethodName
    body = extract_method_body(content, method_name + "Move")
    if not body:
        body = extract_method_body(content, method_name)
    if not body:
        return []

    effects: list[str] = []

    # DamageCmd.Attack(N)
    for m in re.finditer(r"DamageCmd\.Attack\((\d+)\)", body):
        effects.append(f"Deal {m.group(1)} damage")

    # DamageCmd.Attack(variable) — try to resolve from properties
    for m in re.finditer(r"DamageCmd\.Attack\((\w+)\)", body):
        name = m.group(1)
        if name.isdigit():
            continue
        # Try to find the property value in the class
        prop_m = re.search(rf"{name}\s*=>\s*(\d+)\s*;", content)
        if prop_m:
            effects.append(f"Deal {prop_m.group(1)} damage")
        else:
            prop_m = re.search(rf"{name}\s*=>\s*AscensionHelper[^;]*,\s*(\d+),\s*(\d+)\)", content)
            if prop_m:
                effects.append(f"Deal {prop_m.group(1)} damage")
            else:
                effects.append("Deal damage")

    # WithHitCount
    for m in re.finditer(r"WithHitCount\((\d+)\)", body):
        effects.append(f"{m.group(1)} hits")

    # PowerCmd.Apply<PowerName>(target, amount, ...)
    for m in re.finditer(r"PowerCmd\.Apply<(\w+)>\([^,]+,\s*(\d+)", body):
        power = m.group(1).removesuffix("Power")
        amount = m.group(2)
        effects.append(f"Apply {amount} {power}")

    # PowerCmd.Apply<PowerName>(target, variable, ...)
    for m in re.finditer(r"PowerCmd\.Apply<(\w+)>\([^,]+,\s*(\w+)", body):
        power = m.group(1).removesuffix("Power")
        var_name = m.group(2)
        if var_name.isdigit():
            continue
        # Already captured by numeric version above?
        if any(power in e for e in effects):
            continue
        # Try to resolve the variable
        prop_m = re.search(rf"{var_name}\s*=>\s*(\d+)", content)
        if prop_m:
            effects.append(f"Apply {prop_m.group(1)} {power}")
        else:
            prop_m = re.search(
                rf"{var_name}\s*=>\s*AscensionHelper[^;]*,\s*(\d+),\s*(\d+)\)", content
            )
            if prop_m:
                effects.append(f"Apply {prop_m.group(1)} {power}")
            else:
                effects.append(f"Apply {power}")

    # GainBlock
    for m in re.finditer(r"GainBlock\([^,]*,\s*(\d+)", body):
        effects.append(f"Gain {m.group(1)} Block")

    # CardPileCmd.AddToCombatAndPreview<CardName>
    for m in re.finditer(r"AddToCombatAndPreview<(\w+)>", body):
        effects.append(f"Add {m.group(1)} to discard")

    # CreatureCmd.Heal
    for m in re.finditer(r"CreatureCmd\.Heal\([^,]*,\s*(\d+)", body):
        effects.append(f"Heal {m.group(1)}")

    # CreatureCmd.Damage (self-damage / to player)
    for m in re.finditer(r"CreatureCmd\.Damage\([^,]*,\s*[^,]*,\s*(\d+)", body):
        effects.append(f"Deal {m.group(1)} damage (fixed)")

    return effects


def parse_moves(content: str) -> list[dict]:
    """Parse MoveState declarations from GenerateMoveStateMachine()."""
    method_body = extract_method_body(content, "GenerateMoveStateMachine")
    if not method_body:
        return []

    moves: list[dict] = []
    seen_ids: set[str] = set()

    # Find ALL MoveState constructors, whether assigned to variables or inline
    for m in re.finditer(r'new\s+MoveState\s*\(\s*"([^"]+)"', method_body):
        move_id = m.group(1)
        if move_id in seen_ids:
            continue
        seen_ids.add(move_id)

        # Get the full constructor args (find matching paren)
        start = m.start()
        paren_start = method_body.find("(", start)
        depth = 0
        end = paren_start
        while end < len(method_body):
            if method_body[end] == "(":
                depth += 1
            elif method_body[end] == ")":
                depth -= 1
                if depth == 0:
                    break
            end += 1

        constructor_args = method_body[paren_start + 1 : end]

        # Parse intents from constructor args
        intents: list[dict] = []
        for intent_m in re.finditer(r"new\s+\w*Intent\s*\([^)]*\)", constructor_args):
            intents.append(parse_intent(intent_m.group(0)))

        # Also check for intent variables passed by name
        if not intents:
            # Sometimes intents are variables defined elsewhere
            if "SingleAttackIntent" in constructor_args:
                intents.append({"type": "attack"})
            elif "BuffIntent" in constructor_args:
                intents.append({"type": "buff"})

        # Parse effects from the move's execution method
        effects = parse_move_effects(content, move_id)

        # Try to resolve damage from intents that reference properties
        for intent in intents:
            if intent["type"] in ("attack", "multi_attack") and "damage" not in intent:
                # Look for the damage property referenced in the intent
                # Find the intent text to get the variable name
                intent_text = re.search(
                    rf'"{move_id}".*?(\w+AttackIntent)\s*\((\w+)',
                    method_body,
                    re.DOTALL,
                )
                if intent_text:
                    var_name = intent_text.group(2)
                    prop_m = re.search(rf"{var_name}\s*=>\s*(\d+)", content)
                    if prop_m:
                        intent["damage"] = int(prop_m.group(1))
                    else:
                        prop_m = re.search(
                            rf"{var_name}\s*=>\s*AscensionHelper[^;]*,\s*(\d+)",
                            content,
                        )
                        if prop_m:
                            intent["damage"] = int(prop_m.group(1))

        moves.append(
            {
                "id": move_id,
                "intents": intents,
                "effects": effects,
            }
        )

    return moves


def parse_powers_on_spawn(content: str) -> list[str]:
    """Extract powers applied when monster is added to room."""
    body = extract_method_body(content, "AfterAddedToRoom")
    if not body:
        return []

    powers = []
    for m in re.finditer(r"PowerCmd\.Apply<(\w+)>", body):
        power = m.group(1).removesuffix("Power")
        if power not in powers:
            powers.append(power)
    return powers


def apply_localization(monster: dict, loc_data: dict[str, str]) -> None:
    """Apply localization data to a monster dict."""
    class_name = monster["class_name"]
    loc_key = find_loc_key(class_name, loc_data, suffix=".name")
    if not loc_key:
        loc_key = class_name_to_loc_key(class_name)

    monster["loc_key"] = loc_key
    name_key = f"{loc_key}.name"
    monster["title"] = loc_data.get(name_key, class_name)

    # Apply move titles
    for move in monster.get("moves", []):
        move_id = move["id"]
        # Move loc key: strip _MOVE suffix
        move_loc_id = move_id.removesuffix("_MOVE")
        move_title_key = f"{loc_key}.moves.{move_loc_id}.title"
        move["title"] = loc_data.get(move_title_key, "")


def parse_monster_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled monster .cs file."""
    if ": MonsterModel" not in content:
        return None

    monster: dict = {"class_name": class_name}

    min_hp, max_hp = parse_hp(content)
    monster["min_hp"] = min_hp or 0
    monster["max_hp"] = max_hp or min_hp or 0

    monster["moves"] = parse_moves(content)
    monster["powers_on_spawn"] = parse_powers_on_spawn(content)

    return monster


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

        if class_name in COMPANION_CLASSES:
            monster["is_companion"] = True

        apply_localization(monster, loc_data)
        monsters.append(monster)

    output_path = os.path.join(output_dir, "monsters.json")
    write_json(output_path, monsters)

    print(f"Extracted {len(monsters)} monsters to {output_path}")
    with_moves = sum(1 for m in monsters if m.get("moves"))
    with_effects = sum(1 for m in monsters if any(mv.get("effects") for mv in m.get("moves", [])))
    print(f"  With moves: {with_moves}, With detailed effects: {with_effects}")


if __name__ == "__main__":
    main()
