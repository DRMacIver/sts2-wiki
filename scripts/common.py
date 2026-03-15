"""Shared utilities for STS2 data extraction scripts."""

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path


def class_name_to_loc_key(class_name: str) -> str:
    """Convert PascalCase class name to UPPER_SNAKE_CASE localization key.

    Examples:
        SwordBoomerang -> SWORD_BOOMERANG
        DemonForm -> DEMON_FORM
        IronWave -> IRON_WAVE
    """
    result = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", class_name)
    result = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", result)
    return result.upper()


def load_localization(loc_dir: str, table: str) -> dict[str, str]:
    """Load a localization JSON file.

    Args:
        loc_dir: Path to localization directory (e.g. .../localization/eng/)
        table: Name of the table (e.g. "cards", "relics") — without .json extension
    """
    path = os.path.join(loc_dir, f"{table}.json")
    with open(path) as f:
        result: dict[str, str] = json.load(f)
        return result


def parse_canonical_vars(cs_content: str) -> list[dict]:
    """Extract DynamicVar declarations from a C# file.

    Handles all known Var types from decompiled STS2 code.
    """
    vars_found: list[dict] = []

    # Simple numeric vars: new XxxVar(Nm) or new XxxVar(N)
    simple_vars = {
        "DamageVar": "Damage",
        "CalculatedDamageVar": "CalculatedDamage",
        "ExtraDamageVar": "ExtraDamage",
        "BlockVar": "Block",
        "CalculatedBlockVar": "CalculatedBlock",
        "HpLossVar": "HpLoss",
        "SummonVar": "Summon",
        "ForgeVar": "Forge",
        "GoldVar": "Gold",
        "HealVar": "Heal",
        "MaxHpVar": "MaxHp",
        "OstyDamageVar": "OstyDamage",
        "StarsVar": "Stars",
    }
    for var_class, var_type in simple_vars.items():
        for m in re.finditer(rf"new {var_class}\((-?\d+)m?(?:\b|[,)])", cs_content):
            vars_found.append({"type": var_type, "base_value": int(m.group(1))})

    # Vars without 'm' decimal suffix
    int_vars = {
        "EnergyVar": "Energy",
        "CardsVar": "Cards",
        "RepeatVar": "Repeat",
        "IntVar": "Int",
    }
    for var_class, var_type in int_vars.items():
        for m in re.finditer(rf"new {var_class}\((-?\d+)\)", cs_content):
            vars_found.append({"type": var_type, "base_value": int(m.group(1))})
    # CardsVar can also have 'm' suffix
    for m in re.finditer(r"new CardsVar\((-?\d+)m\)", cs_content):
        # Avoid double-counting if already found without 'm'
        val = int(m.group(1))
        if not any(v["type"] == "Cards" and v["base_value"] == val for v in vars_found):
            vars_found.append({"type": "Cards", "base_value": val})

    # PowerVar<T>(Nm)
    for m in re.finditer(r"new PowerVar<(\w+)>\((-?\d+)m", cs_content):
        vars_found.append({"type": m.group(1).replace("Power", ""), "base_value": int(m.group(2))})

    # Named BlockVar: new BlockVar("Name", Nm, ...)
    for m in re.finditer(r'new BlockVar\("(\w+)",\s*(-?\d+)m', cs_content):
        vars_found.append({"type": m.group(1), "base_value": int(m.group(2))})

    # DynamicVar("Name", Nm) — generic named vars
    for m in re.finditer(r'new DynamicVar\("(\w+)",\s*(-?\d+)m', cs_content):
        vars_found.append({"type": m.group(1), "base_value": int(m.group(2))})

    # GenericVar("Name", Nm) — legacy pattern
    for m in re.finditer(r'new GenericVar\("(\w+)",\s*(-?\d+)m', cs_content):
        vars_found.append({"type": m.group(1), "base_value": int(m.group(2))})

    return vars_found


def parse_referenced_powers(cs_content: str) -> list[str]:
    """Extract power types from Apply<X>, PowerVar<X>, FromPower<X> patterns."""
    powers: list[str] = []
    powers += re.findall(r"FromPower<(\w+)>", cs_content)
    powers += re.findall(r"Apply<(\w+)>", cs_content)
    powers += re.findall(r"PowerVar<(\w+)>", cs_content)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for p in powers:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def parse_keywords(cs_content: str) -> list[str]:
    """Extract CardKeyword enum values from C# source."""
    keywords = re.findall(r"CardKeyword\.(\w+)", cs_content)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result


def read_cs_files(directory: str) -> Iterator[tuple[str, str]]:
    """Yield (class_name, file_content) pairs from a directory of .cs files."""
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".cs"):
            continue
        filepath = os.path.join(directory, filename)
        with open(filepath) as f:
            content = f.read()
        class_name = filename.removesuffix(".cs")
        yield class_name, content


_COLOR_TAGS = {
    "gold": "desc-gold",
    "red": "desc-red",
    "blue": "desc-blue",
    "green": "desc-green",
    "orange": "desc-orange",
    "purple": "desc-purple",
    "aqua": "desc-aqua",
    "pink": "desc-pink",
}


def rich_text_to_html(text: str) -> str:
    """Convert game rich text tags to HTML spans."""
    html = text
    for tag, css_class in _COLOR_TAGS.items():
        html = re.sub(
            rf"\[{tag}\](.*?)\[/{tag}\]",
            rf'<span class="{css_class}">\1</span>',
            html,
        )
    html = re.sub(r"\[/?(?:sine|wave|shake|b|i|jitter|center|thinky_dots)\]", "", html)
    html = html.replace("\n", "<br>")
    return html


def strip_rich_text(text: str) -> str:
    """Strip all game rich text tags for plain text."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def decompiled_dir(base: str, namespace: str) -> str:
    """Get path to a decompiled namespace directory."""
    return os.path.join(base, namespace)


def data_dir(base: str, version: str) -> str:
    """Get path to a versioned data directory, creating it if needed."""
    path = os.path.join(base, version)
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: str, data: object) -> None:
    """Write JSON data to a file, creating parent directories as needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def find_loc_key(
    class_name: str,
    loc_data: dict[str, str],
    suffix: str = ".title",
) -> str | None:
    """Find a localization key for a class name, trying multiple strategies.

    Returns the base key (without suffix) or None if not found.
    """
    # Strategy 1: direct conversion
    key = class_name_to_loc_key(class_name)
    if f"{key}{suffix}" in loc_data:
        return key

    # Strategy 2: fuzzy match - normalize both sides
    norm_class = class_name.lower().replace("'", "").replace("!", "")
    for k in loc_data:
        if k.endswith(suffix):
            candidate = k.removesuffix(suffix)
            norm_cand = candidate.lower().replace("_", "").replace("'", "").replace("!", "")
            if norm_class == norm_cand:
                return candidate

    return None
