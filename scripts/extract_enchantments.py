#!/usr/bin/env python3
"""Extract enchantment data from STS2 decompiled code + localization."""

import argparse
import os
import re

from scripts.common import (
    find_loc_key,
    load_localization,
    read_cs_files,
    write_json,
)


def parse_enchantment_file(class_name: str, content: str) -> dict | None:
    """Parse a decompiled enchantment .cs file."""
    if "Deprecated" in class_name or "Mock" in class_name:
        return None
    # Must be a concrete class
    if f"abstract class {class_name}" in content:
        return None
    if f"class {class_name}" not in content:
        return None

    enchantment: dict = {"class_name": class_name}

    # Card type restrictions from CanEnchantCardType
    card_type_match = re.search(
        r"CanEnchantCardType\(CardType\s+\w+\)\s*=>\s*(.*?);",
        content,
        re.DOTALL,
    )
    if card_type_match:
        body = card_type_match.group(1)
        if "Attack" in body and "Skill" not in body:
            enchantment["card_type"] = "Attack"
        elif "Skill" in body and "Attack" not in body:
            enchantment["card_type"] = "Skill"
        elif "Attack" in body and "Skill" in body:
            enchantment["card_type"] = "Attack or Skill"
        else:
            enchantment["card_type"] = "Any"
    else:
        enchantment["card_type"] = "Any"

    # Additional restrictions from CanEnchant override
    can_enchant = re.search(
        r"override\s+bool\s+CanEnchant\(.*?\)\s*\{(.*?)\n\t\}",
        content,
        re.DOTALL,
    )
    if can_enchant:
        body = can_enchant.group(1)
        restrictions: list[str] = []
        if "CardTag.Strike" in body and "CardTag.Defend" in body:
            restrictions.append("Strike or Defend-tagged Basic cards only")
        elif "CardTag.Defend" in body:
            restrictions.append("Defend-tagged cards only")
        elif "CardTag.Strike" in body:
            restrictions.append("Strike-tagged cards only")
        if "CardRarity.Basic" in body:
            if "Basic cards only" not in str(restrictions):
                restrictions.append("Basic rarity only")
        if "Exhaust" in body:
            restrictions.append("Cards with Exhaust only")
        if "CostsX" in body:
            restrictions.append("Excludes X-cost cards")
        if "Unplayable" in body:
            restrictions.append("Excludes Unplayable cards")
        if restrictions:
            enchantment["restrictions"] = restrictions

    # IsStackable
    if "IsStackable => true" in content:
        enchantment["stackable"] = True

    # ShowAmount
    if "ShowAmount => true" in content:
        enchantment["show_amount"] = True

    # HasExtraCardText
    if "HasExtraCardText => true" in content:
        enchantment["has_extra_card_text"] = True

    return enchantment


def _strip_cs_suffix(name: str) -> str:
    """Strip C# numeric literal suffixes (e.g. ``10m`` -> ``10``)."""
    if name.endswith(("m", "f", "d")) and name[:-1].isdigit():
        return name[:-1]
    return name


def find_enchantment_sources(
    decompiled_dir: str,
    loc_data_events: dict[str, str],
    loc_data_relics: dict[str, str],
) -> dict[str, list[dict]]:
    """Scan events and relics for enchantment application calls.

    Returns a dict mapping enchantment class name -> list of sources.
    Each source has: type ("event"|"relic"), class_name, title, amount.
    """
    sources: dict[str, list[dict]] = {}

    for source_type, subdir, loc_data in [
        ("event", "MegaCrit.Sts2.Core.Models.Events", loc_data_events),
        ("relic", "MegaCrit.Sts2.Core.Models.Relics", loc_data_relics),
    ]:
        source_dir = os.path.join(decompiled_dir, subdir)
        if not os.path.isdir(source_dir):
            continue
        for class_name, content in read_cs_files(source_dir):
            file_sources = find_enchantment_sources_in_content(
                content, source_type, class_name, loc_data
            )
            for ench_name, entries in file_sources.items():
                for entry in entries:
                    _add_source(
                        sources, ench_name, source_type, class_name, loc_data, entry.get("amount")
                    )

    return sources


def find_enchantment_sources_in_content(
    content: str,
    source_type: str,
    class_name: str,
    loc_data: dict[str, str],
) -> dict[str, list[dict]]:
    """Find enchantment applications in a single decompiled source file."""
    sources: dict[str, list[dict]] = {}

    # Pattern 1: CardCmd.Enchant<EnchName>(card, Nm)
    for m in re.finditer(r"CardCmd\.Enchant<(\w+)>\(\w+,\s*(\w+)\)", content):
        ench_name = m.group(1)
        amount_str = _strip_cs_suffix(m.group(2))
        amount = int(amount_str) if amount_str.isdigit() else None
        _add_source(sources, ench_name, source_type, class_name, loc_data, amount)

    # Pattern 2: CardCmd.Enchant(enchObj, card, Nm) or with DynamicVars.
    # The enchantment type is resolved from the nearest ModelDb.Enchantment<T>
    # *before* the call (falling back to just after), so a file referencing two
    # enchantment types attributes each amount to the right one.
    for m in re.finditer(r"CardCmd\.Enchant\([^,]+,\s*\w+,\s*(\w+)\)", content):
        amount_str = _strip_cs_suffix(m.group(1))
        amount = int(amount_str) if amount_str.isdigit() else None
        preceding = list(re.finditer(r"ModelDb\.Enchantment<(\w+)>", content[: m.start()]))
        if preceding:
            ench_name = preceding[-1].group(1)
        else:
            following = re.search(r"ModelDb\.Enchantment<(\w+)>", content[m.end() :])
            if not following:
                continue
            ench_name = following.group(1)
        _add_source(sources, ench_name, source_type, class_name, loc_data, amount)

    # Pattern 3: DynamicVar amounts used in Enchant calls
    # Find lines like: CardCmd.Enchant(..., base.DynamicVars["VarName"].BaseValue)
    for m in re.finditer(r'Enchant.*?DynamicVars\["(\w+)"\]', content):
        var_name = m.group(1)
        # Resolve the DynamicVar's default value
        var_m = re.search(rf'DynamicVar\("{var_name}",\s*(\d+)m?\)', content)
        if not var_m:
            continue
        var_val = int(var_m.group(1))
        # Find which enchantment is nearby
        # Look for Enchantment<Type> near this Enchant call
        context = content[max(0, m.start() - 500) : m.end() + 200]
        ench_m = re.search(r"Enchantment<(\w+)>", context)
        if ench_m:
            _add_source(sources, ench_m.group(1), source_type, class_name, loc_data, var_val)

    # Pattern 4: SelectAndEnchant<EnchName>(amount, ...)
    for m in re.finditer(r"SelectAndEnchant<(\w+)>\((\d+)", content):
        ench_name = m.group(1)
        amount = int(m.group(2))
        _add_source(sources, ench_name, source_type, class_name, loc_data, amount)

    return sources


def _add_source(
    sources: dict[str, list[dict]],
    ench_name: str,
    source_type: str,
    class_name: str,
    loc_data: dict[str, str],
    amount: int | None,
) -> None:
    """Add a source entry, deduplicating by class_name."""
    loc_key = find_loc_key(class_name, loc_data)
    title = loc_data.get(f"{loc_key}.title", class_name) if loc_key else class_name
    entry: dict[str, str | int] = {"type": source_type, "class_name": class_name, "title": title}
    if amount is not None:
        entry["amount"] = amount
    if ench_name not in sources:
        sources[ench_name] = []
    # Deduplicate
    if not any(s["class_name"] == class_name for s in sources[ench_name]):
        sources[ench_name].append(entry)


def resolve_description(desc: str, amounts: list[int]) -> str:
    """Resolve template variables in enchantment descriptions.

    Replaces {Amount}, {Amount:energyIcons()}, {Amount:plural:...},
    {Block:diff()} with concrete values.
    """
    if not amounts:
        return desc

    if len(set(amounts)) == 1:
        val = amounts[0]
    else:
        # Multiple different amounts — show range
        val_min, val_max = min(amounts), max(amounts)
        val_range = f"{val_min}-{val_max}"
        desc = re.sub(r"\{Amount:energyIcons\(\)\}", f"{val_range} Energy", desc)
        desc = re.sub(r"\{Amount:plural:(\w+)\|(\w+)\}", r"\2", desc)
        desc = re.sub(r"\{Amount\}", val_range, desc)
        desc = re.sub(r"\{Block:diff\(\)\}", val_range, desc)
        return desc

    desc = re.sub(r"\{Amount:energyIcons\(\)\}", f"{val} Energy", desc)
    desc = re.sub(
        r"\{Amount:plural:(\w+)\|(\w+)\}",
        lambda m: m.group(1) if val == 1 else m.group(2),
        desc,
    )
    desc = re.sub(r"\{Amount\}", str(val), desc)
    desc = re.sub(r"\{Block:diff\(\)\}", str(val), desc)
    return desc


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 enchantment data")
    parser.add_argument(
        "decompiled_dir",
        help="Path to decompiled source directory",
    )
    parser.add_argument("loc_dir", help="Path to localization directory")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    loc_data = load_localization(loc_dir, "enchantments")
    loc_data_events = load_localization(loc_dir, "events")
    loc_data_relics = load_localization(loc_dir, "relics")

    # Find sources (events/relics that grant each enchantment)
    ench_sources = find_enchantment_sources(decompiled_dir, loc_data_events, loc_data_relics)

    enchantments_dir = os.path.join(
        decompiled_dir,
        "MegaCrit.Sts2.Core.Models.Enchantments",
    )
    enchantments: list[dict] = []

    for class_name, content in read_cs_files(enchantments_dir):
        ench = parse_enchantment_file(class_name, content)
        if not ench:
            continue

        # Localization
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            ench["title"] = loc_data.get(f"{loc_key}.title", class_name)
            ench["description"] = loc_data.get(f"{loc_key}.description", "")
            extra = loc_data.get(f"{loc_key}.extraCardText", "")
            if extra:
                ench["extra_card_text"] = extra
        else:
            # CamelCase split for display
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", class_name)
            ench["title"] = title
            ench["description"] = ""

        # Attach sources and resolve description templates
        sources = ench_sources.get(class_name, [])
        ench["sources"] = sources
        amounts = [s["amount"] for s in sources if "amount" in s]
        if amounts:
            for field in ("description", "extra_card_text"):
                if "{" in ench.get(field, ""):
                    ench[field] = resolve_description(ench[field], amounts)

        enchantments.append(ench)

    output_path = os.path.join(output_dir, "enchantments.json")
    write_json(output_path, enchantments)

    print(f"Extracted {len(enchantments)} enchantments to {output_path}")


if __name__ == "__main__":
    main()
