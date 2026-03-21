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

    # Extract star cost (Regent cards)
    star_match = re.search(r"CanonicalStarCost\s*=>\s*(\d+)", content)
    if star_match:
        card["star_cost"] = int(star_match.group(1))
    if "HasStarCostX => true" in content:
        card["x_star_cost"] = True

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


def _build_var_lookup(vars_list: list[dict], use_upgraded: bool) -> dict[str, int]:
    """Build a name->value lookup from vars list, handling multiple name forms."""
    lookup: dict[str, int] = {}
    for v in vars_list:
        vtype = v["type"]
        if use_upgraded and "upgraded_value" in v:
            raw_val = v.get("upgraded_value")
        else:
            raw_val = v["base_value"]
        val: int = int(raw_val) if raw_val is not None else 0
        lookup[vtype] = val
        # Power vars: "Vulnerable" -> also register "VulnerablePower"
        if not vtype.endswith("Power") and vtype not in VAR_TYPE_TO_PLACEHOLDER:
            lookup[vtype + "Power"] = val
        # Standard mapping: "CalculatedDamage" -> also "Damage"
        if vtype in VAR_TYPE_TO_PLACEHOLDER:
            lookup[VAR_TYPE_TO_PLACEHOLDER[vtype]] = val
    return lookup


def _resolve_placeholder(match_str: str, var_lookup: dict[str, int], upgraded: bool) -> str:
    """Resolve a single {placeholder} expression.

    Handles: diff(), plural, IfUpgraded:show, energyIcons, starIcons,
    inverseDiff, InCombat, cond.
    """
    inner = match_str[1:-1]  # strip { }

    # Handle {IfUpgraded:show:upgraded_text|base_text}
    m = re.match(r"IfUpgraded:show:(.*)", inner, re.DOTALL)
    if m:
        parts = m.group(1).split("|", 1)
        if upgraded:
            return parts[0]
        return parts[1] if len(parts) > 1 else ""

    # Handle {InCombat:\n(text)|} — strip the conditional, show the combat text
    m = re.match(r"InCombat:(.*)", inner, re.DOTALL)
    if m:
        parts = m.group(1).rsplit("|", 1)
        text = parts[0].strip()
        # Recursively resolve any nested placeholders
        return text

    # Handle {singleStarIcon} — literal icon references
    if inner == "singleStarIcon":
        return "[star]"

    # Split name:format
    parts = inner.split(":", 1)
    name = parts[0]
    fmt = parts[1] if len(parts) > 1 else ""

    val = var_lookup.get(name)

    # Handle {Name:energyIcons()} and {Name:energyIcons(N)}
    if "energyIcons" in fmt:
        if val is not None:
            return f"{val} Energy"
        # energyPrefix is a display-only var (the number is in surrounding text)
        if name == "energyPrefix":
            return " Energy"
        m2 = re.search(r"energyIcons\((\d+)\)", fmt)
        if m2:
            return f"{m2.group(1)} Energy"
        return "Energy"

    # Handle {Name:starIcons()}
    if "starIcons" in fmt:
        if val is not None:
            return f"{val} Stars"
        return "Stars"

    # Handle {Name:inverseDiff()}
    if "inverseDiff" in fmt:
        if val is not None:
            return str(val)
        return "?"

    # Handle {Name:cond:>N?true_text|false_text}
    m = re.match(r"cond:>(\d+)\?(.*)", fmt, re.DOTALL)
    if m:
        threshold = int(m.group(1))
        cond_parts = m.group(2).split("|", 1)
        if val is not None and val > threshold:
            # Recursively resolve nested {Name:diff()} in true branch
            result = cond_parts[0]
            result = result.replace(f"{{{name}:diff()}}", str(val))
            return result
        return cond_parts[1] if len(cond_parts) > 1 else ""

    # Handle {Name:plural:singular|plural}
    m = re.match(r"plural:(.*)", fmt, re.DOTALL)
    if m:
        plural_parts = m.group(1).split("|", 1)
        if val is not None:
            if val == 1:
                return plural_parts[0]
            return plural_parts[1] if len(plural_parts) > 1 else plural_parts[0]
        # No value — just use plural form
        return plural_parts[1] if len(plural_parts) > 1 else plural_parts[0]

    # Handle {Name:diff()} or just {Name}
    if val is not None:
        return str(val)

    # Unresolved
    return match_str


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

    var_lookup = _build_var_lookup(vars_list, use_upgraded)

    rendered = template

    # Pre-process: strip {InCombat:...|} blocks entirely (they show calculated
    # runtime values like "(Hits 3 times)" which we can't compute statically)
    rendered = re.sub(r"\{InCombat:[^}]*(?:\{[^}]*\}[^}]*)*\|\}", "", rendered)
    # Also handle simpler InCombat patterns
    rendered = re.sub(r"\{InCombat:.*?\|\}", "", rendered, flags=re.DOTALL)

    # Multi-pass resolution to handle nested placeholders
    for _ in range(3):
        # Match outermost { } that don't contain nested { }
        new_rendered = re.sub(
            r"\{([^{}]*)\}",
            lambda m: _resolve_placeholder(m.group(0), var_lookup, use_upgraded),
            rendered,
        )
        if new_rendered == rendered:
            break
        rendered = new_rendered

    # Convert rich text tags to HTML spans
    html = rendered
    from scripts.common import _COLOR_TAGS as color_tags

    for tag, css_class in color_tags.items():
        html = re.sub(
            rf"\[{tag}\](.*?)\[/{tag}\]",
            rf'<span class="{css_class}">\1</span>',
            html,
        )
    html = re.sub(r"\[/?(?:sine|wave|shake|b|i|jitter|center|thinky_dots)\]", "", html)
    # Convert newlines to <br>
    html = html.replace("\n", "<br>")

    # Plain text: convert icon tags to text, then strip remaining tags
    plain = rendered.replace("[star]", "\u2605")
    plain = plain.replace("[energy]", "Energy")
    plain = re.sub(r"\[/?[^\]]*\]", "", plain)

    # Clean up any remaining unsubstituted placeholders — use "X" for
    # values that are calculated at runtime rather than "?" which looks broken.
    # Multi-pass to handle nested braces.
    for text_ref in ("plain", "html"):
        t = plain if text_ref == "plain" else html
        for _ in range(3):
            t = re.sub(r"\{[^{}]*\}", "X", t)
        # Clean up residual template artifacts:
        # "X turns}" → "X turns", "X time|X times}" → "X times"
        t = re.sub(r"X\s+\w+\|X\s+(\w+)\}", r"X \1", t)  # plural: X time|X times}
        t = re.sub(r"X\s+(\w+)\)\|?\}", r"X \1", t)  # X damage)|} patterns
        t = re.sub(r"(\w)\}", r"\1", t)  # stray trailing }
        t = re.sub(r"\|}", "", t)  # stray |}
        if text_ref == "plain":
            plain = t
        else:
            html = t

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
    power_loc = load_localization(loc_dir, "powers")

    # Build power lookup: class_name -> {title, slug}
    power_lookup: dict[str, dict[str, str]] = {}
    for key in power_loc:
        if key.endswith(".title"):
            base_key = key.removesuffix(".title")
            title = power_loc[key]
            # Convert loc key like VULNERABLE_POWER to class name VulnerablePower
            # We store by multiple possible names for lookup
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            info = {"class_name": base_key, "title": title, "slug": slug}
            power_lookup[base_key] = info
            # Also store by common class name patterns
            # e.g., VULNERABLE_POWER -> VulnerablePower
            parts = base_key.split("_")
            camel = "".join(p.capitalize() for p in parts)
            power_lookup[camel] = info

    # Build epoch unlock map: card_class -> epoch info
    card_epoch_map: dict[str, str] = {}
    epochs_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Timeline.Epochs")
    if os.path.exists(epochs_dir):
        for epoch_name, epoch_content in read_cs_files(epochs_dir):
            story_m = re.search(r'StoryId\s*=>\s*"([^"]+)"', epoch_content)
            story = story_m.group(1) if story_m else epoch_name
            for cm in re.finditer(r"ModelDb\.Card<(\w+)>\(\)", epoch_content):
                card_epoch_map[cm.group(1)] = story

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

        # Enrich referenced_powers with display names and slugs
        if "referenced_powers" in card:
            enriched_powers: list[dict[str, str]] = []
            for power_class in card["referenced_powers"]:
                power_info = power_lookup.get(power_class)
                if power_info:
                    enriched_powers.append(power_info)
                else:
                    # Fallback: strip "Power" suffix and split CamelCase
                    display = power_class.removesuffix("Power")
                    display = re.sub(r"([a-z])([A-Z])", r"\1 \2", display)
                    slug = re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")
                    enriched_powers.append(
                        {"class_name": power_class, "title": display, "slug": slug}
                    )
            card["referenced_powers"] = enriched_powers

        # Epoch unlock info
        if class_name in card_epoch_map:
            card["unlocked_by"] = card_epoch_map[class_name]

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
