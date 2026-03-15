#!/usr/bin/env python3
"""Extract all card data from STS2 decompiled code + localization."""

import argparse
import re

from scripts.common import (
    class_name_to_loc_key,
    find_loc_key,
    load_localization,
    parse_canonical_vars,
    parse_keywords,
    parse_referenced_powers,
    read_cs_files,
    write_json,
)

# Map pool file class names to character/pool labels
POOL_MAP: dict[str, str] = {
    "IroncladCardPool": "Ironclad",
    "SilentCardPool": "Silent",
    "DefectCardPool": "Defect",
    "NecrobinderCardPool": "Necrobinder",
    "RegentCardPool": "Regent",
    "ColorlessCardPool": "Colorless",
    "CurseCardPool": "Curse",
    "StatusCardPool": "Status",
    "TokenCardPool": "Token",
    "EventCardPool": "Event",
    "QuestCardPool": "Quest",
    "DeprecatedCardPool": "Deprecated",
    "MockCardPool": "Mock",
}


def build_card_pool_map(decompiled_dir: str) -> dict[str, str]:
    """Parse CardPool files to build class_name -> character mapping."""
    import os

    pools_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.CardPools")
    card_to_char: dict[str, str] = {}

    for class_name, content in read_cs_files(pools_dir):
        character = POOL_MAP.get(class_name)
        if not character:
            continue

        # Extract all ModelDb.Card<ClassName>() references
        for m in re.finditer(r"ModelDb\.Card<(\w+)>\(\)", content):
            card_class = m.group(1)
            # Don't override character pools with token/status/etc.
            if card_class not in card_to_char or character in (
                "Ironclad",
                "Silent",
                "Defect",
                "Necrobinder",
                "Regent",
                "Colorless",
            ):
                card_to_char[card_class] = character

    return card_to_char


def parse_card_file(class_name: str, content: str) -> dict:
    """Parse a decompiled card .cs file to extract key properties."""
    card: dict = {"class_name": class_name}

    # Extract constructor: base(cost, CardType.X, CardRarity.Y, TargetType.Z)
    m = re.search(
        r":\s*base\((-?\d+),\s*CardType\.(\w+),\s*CardRarity\.(\w+),\s*TargetType\.(\w+)\)",
        content,
    )
    if m:
        card["energy_cost"] = int(m.group(1))
        card["type"] = m.group(2)
        card["rarity"] = m.group(3)
        card["target"] = m.group(4)

    # Check for X cost
    if "HasEnergyCostX => true" in content:
        card["x_cost"] = True

    # Extract keywords from CanonicalKeywords property
    keywords = parse_keywords(content)
    if keywords:
        card["keywords"] = keywords

    # Extract dynamic vars
    vars_found = parse_canonical_vars(content)
    if vars_found:
        card["vars"] = vars_found

    # Extract upgrade info
    upgrades: list[dict] = []
    upgrade_section = re.search(r"OnUpgrade\(\).*?\{(.*?)\n\t\}", content, re.DOTALL)
    if upgrade_section:
        body = upgrade_section.group(1)
        for um in re.finditer(r"(\w+)\.UpgradeValueBy\((-?\d+)m\)", body):
            upgrades.append({"var": um.group(1), "amount": int(um.group(2))})
        # Also match DynamicVars["Name"].UpgradeValueBy pattern
        for um in re.finditer(r'DynamicVars\["(\w+)"\]\.UpgradeValueBy\((-?\d+)m\)', body):
            upgrades.append({"var": um.group(1), "amount": int(um.group(2))})
        for um in re.finditer(r"UpgradeEnergyCostBy\((-?\d+)\)", body):
            upgrades.append({"var": "EnergyCost", "amount": int(um.group(1))})
        for km in re.finditer(r"RemoveKeyword\(CardKeyword\.(\w+)\)", body):
            upgrades.append({"action": "remove_keyword", "keyword": km.group(1)})
        for km in re.finditer(r"AddKeyword\(CardKeyword\.(\w+)\)", body):
            upgrades.append({"action": "add_keyword", "keyword": km.group(1)})
    if upgrades:
        card["upgrades"] = upgrades

    # Extract referenced powers
    powers = parse_referenced_powers(content)
    if powers:
        card["referenced_powers"] = powers

    return card


def compute_upgraded_vars(card: dict) -> list[dict]:
    """Compute upgraded values for each var based on upgrade info."""
    vars_list = card.get("vars", [])
    upgrades = card.get("upgrades", [])

    # Build a lookup of upgrade amounts by var name
    upgrade_amounts: dict[str, int] = {}
    for u in upgrades:
        if "var" in u:
            var_name = u["var"]
            # Map DynamicVars property names to var types
            # e.g., "Damage" -> "Damage", "Vulnerable" -> "Vulnerable"
            # The var name from UpgradeValueBy corresponds to the DynamicVars property
            upgrade_amounts[var_name] = u["amount"]

    result = []
    for v in vars_list:
        new_v = dict(v)
        vtype = v["type"]
        base = v["base_value"]

        # Try direct match first
        upgrade_amt = upgrade_amounts.get(vtype)
        # Try with "Power" suffix stripped (PowerVar<VulnerablePower> -> "Vulnerable" type,
        # but upgrade uses DynamicVars.Vulnerable)
        if upgrade_amt is None:
            upgrade_amt = upgrade_amounts.get(vtype + "Power")

        if upgrade_amt is not None:
            new_v["upgraded_value"] = base + upgrade_amt
        result.append(new_v)

    return result


# Map of var type names to the placeholder names used in localization templates
VAR_TYPE_TO_PLACEHOLDER: dict[str, str] = {
    "Damage": "Damage",
    "CalculatedDamage": "Damage",
    "Block": "Block",
    "CalculatedBlock": "Block",
    "Energy": "Energy",
    "Cards": "Cards",
    "HpLoss": "HpLoss",
    "Summon": "Summon",
    "Forge": "Forge",
    "Repeat": "Repeat",
}


def render_description(
    template: str,
    vars_list: list[dict],
    use_upgraded: bool = False,
) -> tuple[str, str]:
    """Render a card description template with variable substitution.

    Returns (plain_text, html) tuple.
    """
    if not template:
        return ("", "")

    rendered = template

    # Substitute variables
    for v in vars_list:
        vtype = v["type"]
        val = v.get("upgraded_value") if use_upgraded and "upgraded_value" in v else v["base_value"]

        # The template uses patterns like {Damage:diff()}, {Block:diff()}, {VulnerablePower:diff()}
        # The var type from PowerVar<VulnerablePower> becomes "Vulnerable" in our data,
        # but the loc template uses "VulnerablePower"
        # Try both forms
        placeholder_names = [vtype]
        # For power vars, the loc template often uses the full power name (e.g., "VulnerablePower")
        if not vtype.endswith("Power") and vtype not in VAR_TYPE_TO_PLACEHOLDER:
            placeholder_names.append(vtype + "Power")
        # Standard mapping
        if vtype in VAR_TYPE_TO_PLACEHOLDER:
            mapped = VAR_TYPE_TO_PLACEHOLDER[vtype]
            if mapped != vtype:
                placeholder_names.append(mapped)

        for name in placeholder_names:
            # Match {Name:diff()}, {Name}, {Name:plural:xxx|yyy}, etc.
            rendered = re.sub(rf"\{{{name}(?::[^}}]*)?\}}", str(val), rendered)

    # Convert rich text tags to HTML spans
    html = rendered
    html = re.sub(r"\[gold\](.*?)\[/gold\]", r'<span class="desc-gold">\1</span>', html)
    html = re.sub(r"\[red\](.*?)\[/red\]", r'<span class="desc-red">\1</span>', html)
    html = re.sub(r"\[blue\](.*?)\[/blue\]", r'<span class="desc-blue">\1</span>', html)
    html = re.sub(r"\[green\](.*?)\[/green\]", r'<span class="desc-green">\1</span>', html)
    # Strip other formatting tags
    html = re.sub(r"\[/?(?:sine|wave|shake|b|i)\]", "", html)
    # Convert newlines to <br>
    html = html.replace("\n", "<br>")

    # Plain text: strip all tags
    plain = re.sub(r"\[/?[^\]]*\]", "", rendered)
    # Clean up any remaining unsubstituted placeholders
    plain = re.sub(r"\{[^}]*\}", "[?]", plain)
    html = re.sub(r"\{[^}]*\}", "[?]", html)

    return (plain, html)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract STS2 card data")
    parser.add_argument("decompiled_dir", help="Path to decompiled source directory")
    parser.add_argument("loc_dir", help="Path to localization directory (eng/)")
    parser.add_argument("output_dir", help="Path to output data directory")
    args = parser.parse_args()

    import os

    decompiled_dir = os.path.expanduser(args.decompiled_dir)
    loc_dir = os.path.expanduser(args.loc_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load localization
    loc_data = load_localization(loc_dir, "cards")

    # Build card pool mapping
    card_pool_map = build_card_pool_map(decompiled_dir)

    # Parse all card files
    cards_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Cards")
    cards: list[dict] = []

    for class_name, content in read_cs_files(cards_dir):
        card = parse_card_file(class_name, content)

        # Skip if we couldn't parse the constructor (not a real card)
        if "energy_cost" not in card:
            continue

        # Character assignment
        card["character"] = card_pool_map.get(class_name, "Unknown")

        # Localization
        loc_key = find_loc_key(class_name, loc_data)
        if loc_key:
            card["loc_key"] = loc_key
            card["title"] = loc_data.get(f"{loc_key}.title", class_name)
            card["description_template"] = loc_data.get(f"{loc_key}.description", "")
        else:
            card["loc_key"] = class_name_to_loc_key(class_name)
            card["title"] = class_name
            card["description_template"] = ""
            card["_loc_missing"] = True

        # Compute upgraded vars
        card["vars"] = compute_upgraded_vars(card)

        # Compute upgraded cost
        if "upgrades" in card:
            for u in card["upgrades"]:
                if u.get("var") == "EnergyCost":
                    card["upgraded_cost"] = card["energy_cost"] + u["amount"]
                    break

        # Render descriptions
        plain, html = render_description(
            card.get("description_template", ""),
            card.get("vars", []),
            use_upgraded=False,
        )
        card["description_plain"] = plain
        card["description_html"] = html

        # Render upgraded description
        upgraded_plain, upgraded_html = render_description(
            card.get("description_template", ""),
            card.get("vars", []),
            use_upgraded=True,
        )
        if upgraded_plain != plain or card.get("upgraded_cost") is not None:
            card["upgraded_description_plain"] = upgraded_plain
            card["upgraded_description_html"] = upgraded_html

        # Flag deprecated/mock cards
        if card["character"] == "Deprecated":
            card["deprecated"] = True
        if card["character"] == "Mock":
            card["mock"] = True

        cards.append(card)

    # Write output
    output_path = os.path.join(output_dir, "cards.json")
    write_json(output_path, cards)

    # Stats
    print(f"Extracted {len(cards)} cards to {output_path}")
    by_char: dict[str, int] = {}
    for c in cards:
        ch = c.get("character", "Unknown")
        by_char[ch] = by_char.get(ch, 0) + 1
    for ch, count in sorted(by_char.items()):
        print(f"  {ch}: {count}")

    unmatched = [c for c in cards if c.get("_loc_missing")]
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} cards without localization match:")
        for c in unmatched[:10]:
            print(f"  {c['class_name']} (tried key: {c['loc_key']})")


if __name__ == "__main__":
    main()
