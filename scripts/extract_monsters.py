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


def _move_id_to_name(move_id: str) -> str:
    """Convert a move ID like FORBIDDEN_INCANTATION_MOVE to 'Forbidden Incantation'."""
    name = move_id.removesuffix("_MOVE")
    return name.replace("_", " ").title()


def _parse_move_pattern(method_body: str) -> dict:
    """Extract move pattern info: starting move, cycles, random branches."""
    pattern: dict = {}

    # Find starting move: MonsterMoveStateMachine(list, startingMoveVar)
    start_m = re.search(r"new\s+MonsterMoveStateMachine\s*\([^,]+,\s*(\w+)\)", method_body)
    if start_m:
        start_var = start_m.group(1)
        # Find what move ID this variable corresponds to
        var_m = re.search(rf'{start_var}\s*=\s*new\s+MoveState\s*\(\s*"([^"]+)"', method_body)
        if var_m:
            pattern["starts_with"] = var_m.group(1)

    # Build a map of variable name -> move ID
    var_to_id: dict[str, str] = {}
    for m in re.finditer(
        r'(?:MoveState\s+)?(\w+)\s*=\s*(?:\(MoveState\))?\s*(?:\()?new\s+MoveState\s*\(\s*"([^"]+)"',
        method_body,
    ):
        var_to_id[m.group(1)] = m.group(2)

    # Find FollowUpState chains
    follow_ups: list[tuple[str, str]] = []
    for m in re.finditer(
        r"(\w+)\.FollowUpState\s*=\s*"
        r'(?:new\s+MoveState\s*\(\s*"([^"]+)"'
        r"|new\s+(?:Random|Conditional)BranchState"
        r"|\(?(\w+)\)?)",
        method_body,
    ):
        src_var = m.group(1)
        src_id = var_to_id.get(src_var, src_var)
        if m.group(2):
            # Inline new MoveState
            dst_id = m.group(2)
            follow_ups.append((src_id, dst_id))
        elif m.group(3):
            # Variable reference (skip if it's a BranchState variable)
            dst_var = m.group(3)
            dst_id = var_to_id.get(dst_var, dst_var)
            # Only include if it resolved to a move ID (not a variable name)
            if dst_id != dst_var:
                follow_ups.append((src_id, dst_id))
        # else: RandomBranchState/ConditionalBranchState — skip

    if follow_ups:
        chains: list[str] = []
        for src_id, dst_id in follow_ups:
            chains.append(f"{src_id} -> {dst_id}")
        pattern["follow_ups"] = chains

    # Find RandomBranchState
    random_branches: list[dict] = []
    for m in re.finditer(
        r"AddBranch\s*\(\s*(\w+)(?:,\s*MoveRepeatType\.(\w+))?\s*(?:,\s*(\d+))?\s*\)",
        method_body,
    ):
        var_name = m.group(1)
        repeat_type = m.group(2)
        weight = m.group(3)

        # Resolve variable to move ID
        var_to_id_local: dict[str, str] = {}
        for vm in re.finditer(
            r'MoveState\s+(\w+)\s*=\s*new\s+MoveState\s*\(\s*"([^"]+)"',
            method_body,
        ):
            var_to_id_local[vm.group(1)] = vm.group(2)

        move_id = var_to_id_local.get(var_name, var_name)
        branch: dict = {"move": move_id}
        if repeat_type:
            branch["repeat"] = repeat_type
        if weight:
            branch["weight"] = int(weight)
        random_branches.append(branch)

    if random_branches:
        pattern["random_branches"] = random_branches

    # Self-loops (move follows up to itself)
    for m in re.finditer(r"(\w+)\.FollowUpState\s*=\s*\1\b", method_body):
        var_name = m.group(1)
        for vm in re.finditer(
            r'MoveState\s+(\w+)\s*=\s*new\s+MoveState\s*\(\s*"([^"]+)"',
            method_body,
        ):
            if vm.group(1) == var_name:
                pattern.setdefault("repeats", []).append(vm.group(2))

    return pattern


def _describe_pattern(pattern: dict, move_titles: dict[str, str]) -> str:
    """Generate a human-readable description of the move pattern."""
    parts: list[str] = []

    def name(move_id: str) -> str:
        return move_titles.get(move_id, _move_id_to_name(move_id))

    if "starts_with" in pattern:
        parts.append(f"Starts with {name(pattern['starts_with'])}.")

    if "follow_ups" in pattern:
        for chain in pattern["follow_ups"]:
            src, dst = chain.split(" -> ")
            if src == dst or dst in pattern.get("repeats", []):
                continue  # Skip self-loops, covered below
            parts.append(f"After {name(src)}, uses {name(dst)}.")

    if "repeats" in pattern:
        for move_id in pattern["repeats"]:
            parts.append(f"Repeats {name(move_id)}.")

    if "random_branches" in pattern:
        branch_parts = []
        total_weight = sum(b.get("weight", 1) for b in pattern["random_branches"])
        for b in pattern["random_branches"]:
            w = b.get("weight", 1)
            repeat = b.get("repeat", "")
            pct = round(100 * w / total_weight) if total_weight > 0 else 0
            desc = name(b["move"])
            if repeat == "CannotRepeat":
                desc += " (can't repeat)"
            branch_parts.append(f"{desc} ({pct}%)")
        parts.append("Then randomly: " + ", ".join(branch_parts) + ".")

    return " ".join(parts)


def parse_moves(content: str) -> tuple[list[dict], dict]:
    """Parse MoveState declarations from GenerateMoveStateMachine()."""
    method_body = extract_method_body(content, "GenerateMoveStateMachine")
    if not method_body:
        return [], {}

    moves: list[dict] = []
    seen_ids: set[str] = set()

    # Extract move pattern info
    move_pattern = _parse_move_pattern(method_body)

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

    return moves, move_pattern


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

    # Apply move titles (with fallback name generation)
    move_titles: dict[str, str] = {}
    for move in monster.get("moves", []):
        move_id = move["id"]
        move_loc_id = move_id.removesuffix("_MOVE")
        move_title_key = f"{loc_key}.moves.{move_loc_id}.title"
        title = loc_data.get(move_title_key, "")
        if not title:
            title = _move_id_to_name(move_id)
        move["title"] = title
        move_titles[move_id] = title

    # Generate move pattern description
    if monster.get("move_pattern"):
        monster["move_pattern_desc"] = _describe_pattern(monster["move_pattern"], move_titles)


def parse_monster_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled monster .cs file."""
    if ": MonsterModel" not in content:
        return None

    monster: dict = {"class_name": class_name}

    min_hp, max_hp = parse_hp(content)
    monster["min_hp"] = min_hp or 0
    monster["max_hp"] = max_hp or min_hp or 0

    moves, move_pattern = parse_moves(content)
    monster["moves"] = moves
    monster["move_pattern"] = move_pattern
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
