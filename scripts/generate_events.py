#!/usr/bin/env python3
"""Generate Astro content collection markdown files from extracted event data."""

import argparse
import json
import os
import re
from pathlib import Path


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def escape_yaml(value: str) -> str:
    if not value:
        return '""'
    if value.lower() in ("null", "true", "false", "yes", "no", "on", "off", "~"):
        return json.dumps(value)
    if any(c in value for c in ":{}\n[]#&*!|>'\"%@`"):
        return json.dumps(value)
    return value


def render_description_html(desc: str) -> str:
    """Convert game rich text tags to HTML."""
    from scripts.common import rich_text_to_html

    return rich_text_to_html(desc)


def strip_tags(desc: str) -> str:
    """Strip game rich text tags for plain text."""
    from scripts.common import strip_rich_text

    return strip_rich_text(desc)


# Hand-written enrichments for events whose descriptions/options are
# defined in code rather than localization data, or whose localization
# contains unresolved template variables.
#
# "options" replaces the extracted options entirely.
# "option_overrides" patches specific options by title match.
_EVENT_ENRICHMENTS: dict[str, dict] = {
    "FakeMerchant": {
        "description": (
            "A suspicious merchant has laid out a rug covered in relics. "
            "They look familiar, but something is off about them...\n\n"
            "The merchant sells [gold]fake relics[/gold] — weaker versions "
            "of real relics — for [gold]50 gold[/gold] each. "
            "Up to 6 are available from a pool of 9.\n\n"
            "If you have a [purple]Foul Potion[/purple], you can throw it "
            "at the merchant to trigger a fight. Defeating The Merchant??? "
            "(175 HP) rewards [gold]300 gold[/gold], "
            "[gold]The Merchant's Rug[/gold] relic, and any unsold fake relics."
        ),
        "options": [
            {"title": "Browse Wares", "description": "View and buy fake relics for 50 gold each."},
            {
                "title": "Throw Foul Potion",
                "description": "Requires a Foul Potion. Fight The Merchant??? (175 HP). "
                "Rewards: 300 gold, The Merchant's Rug, and unsold fake relics.",
            },
            {"title": "Leave", "description": "Walk away."},
        ],
    },
    "BattlewornDummy": {
        "option_overrides": {
            "Setting 1": {
                "description": "Fight a [blue]75[/blue] HP dummy. Reward: a random potion."
            },
            "Setting 2": {
                "description": "Fight a [blue]150[/blue] HP dummy. Reward: upgrade 2 random cards."
            },
            "Setting 3": {
                "description": "Fight a [blue]300[/blue] HP dummy. Reward: obtain a relic."
            },
        },
    },
    "ColossalFlower": {
        "options": [
            {"title": "Extract Nectar", "description": "Gain [blue]35[/blue] [gold]Gold[/gold]."},
            {
                "title": "Reach Deeper",
                "description": "Take [red]5[/red] damage. Access higher tiers: "
                "[blue]75 gold[/blue] (6 damage) or [blue]135 gold[/blue] (7 damage). "
                "At the deepest level, you can take the [gold]Pollinous Core[/gold] relic instead.",
            },
        ],
    },
    "DenseVegetation": {
        "option_overrides": {
            "Rest": {"description": "Heal [green]30%[/green] of max HP. Then fight some enemies."},
        },
    },
    "DrowningBeacon": {
        "option_overrides": {
            "Bottle": {"description": "Procure a random [aqua]Potion[/aqua]."},
            "Climb": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
    },
    "FieldOfManSizedHoles": {
        "option_overrides": {
            "Enter Your Hole": {
                "description": "[gold]Enchant[/gold] a card with "
                "a random [purple]Enchantment[/purple]."
            },
        },
    },
    "GraveOfTheForgotten": {
        "option_overrides": {
            "Accept the {Relic}": {
                "title": "Accept the Relic",
                "description": "Obtain a random [gold]Relic[/gold].",
            },
            "Confront with Truth": {
                "description": "Add [red]Decay[/red] to your Deck. "
                "Enchant a card that Exhausts with a random [purple]Enchantment[/purple].",
            },
        },
    },
    "HungryForMushrooms": {
        "options": [
            {
                "title": "Big Mushroom",
                "description": "Obtain the [gold]Big Mushroom[/gold] relic.",
            },
            {
                "title": "Fragrant Mushroom",
                "description": "Take [red]15[/red] damage. "
                "Obtain the [gold]Fragrant Mushroom[/gold] relic.",
            },
        ],
    },
    "PotionCourier": {
        "option_overrides": {
            "Grab Potions": {"description": "Procure [blue]3[/blue] [gold]Foul Potions[/gold]."},
        },
    },
    "RelicTrader": {
        "description": (
            "A mysterious figure offers to trade your relics. "
            "Three of your relics are randomly selected, each paired "
            "with a new relic from the pool. You may trade one pair.\n\n"
            "Requires [gold]5+[/gold] tradable relics. Available in Act 2+."
        ),
        "options": [
            {
                "title": "Trade a Relic",
                "description": "Swap one of your relics for a new one from the pool. "
                "Three trade options are offered — the specific relics are randomly determined.",
            },
            {"title": "Leave", "description": "Walk away."},
        ],
    },
    "SapphireSeed": {
        "option_overrides": {
            "Plant and Nourish": {
                "description": "[gold]Enchant[/gold] a card with "
                "a random [purple]Enchantment[/purple]."
            },
        },
    },
    "SelfHelpBook": {
        "option_overrides": {
            "Read the Back": {
                "description": "Choose an Attack to [gold]Enchant[/gold] "
                "with a random [purple]Enchantment[/purple] at level [blue]2[/blue]."
            },
            "Read a Random Passage": {
                "description": "Choose a Skill to [gold]Enchant[/gold] "
                "with a random [purple]Enchantment[/purple] at level [blue]2[/blue]."
            },
            "Read the Entire Book": {
                "description": "Choose a Power to [gold]Enchant[/gold] "
                "with a random [purple]Enchantment[/purple] at level [blue]2[/blue]."
            },
        },
    },
    "SlipperyBridge": {
        "option_overrides": {
            "Overcome": {"description": "A random card is removed from your [gold]Deck[/gold]."},
            "Hold On": {
                "description": "Lose [red]3[/red] HP (increases by 1 each time you Hold On)."
            },
        },
    },
    "SpiralingWhirlpool": {
        "option_overrides": {
            "Drink": {"description": "Heal [green]33%[/green] of max HP."},
        },
    },
    "SpiritGrafter": {
        "option_overrides": {
            "Let It In": {"description": "Heal [green]25[/green] HP."},
            "Rejection": {"description": "Lose [red]9[/red] HP. Remove a card from your Deck."},
        },
    },
    "StoneOfAllTime": {
        "option_overrides": {
            "Drink and Lift": {
                "description": "Lose a random [gold]Potion[/gold]. Gain [green]10[/green] Max HP."
            },
        },
    },
    "Symbiote": {
        "option_overrides": {
            "Approach": {
                "description": "[gold]Enchant[/gold] an Attack "
                "with a random [purple]Enchantment[/purple]."
            },
        },
    },
    "TeaMaster": {
        "options": [
            {
                "title": "Bone Tea",
                "description": "Pay [red]50[/red] [gold]Gold[/gold]. "
                "Obtain the [gold]Bone Tea[/gold] relic.",
            },
            {
                "title": "Ember Tea",
                "description": "Pay [red]150[/red] [gold]Gold[/gold]. "
                "Obtain the [gold]Ember Tea[/gold] relic.",
            },
            {
                "title": "Tea of Discourtesy",
                "description": "Free. Obtain the [gold]Tea of Discourtesy[/gold] relic.",
            },
        ],
    },
    "TheFutureOfPotions": {
        "description": (
            "A strange device promises to transform your potions into something greater.\n\n"
            "Trade a potion for a card reward of 3 [gold]upgraded[/gold] cards. "
            "The card rarity matches the potion rarity "
            "(Rare potion = Rare cards, etc.), "
            "and the card type (Attack/Skill/Power) is randomly assigned."
        ),
        "options": [
            {
                "title": "Insert a Potion",
                "description": "Trade a potion for 3 [gold]upgraded[/gold] card choices "
                "matching the potion's rarity.",
            },
            {"title": "Leave", "description": "Walk away."},
        ],
    },
    "LostWisp": {
        "option_overrides": {
            "Capture the Wisp": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
    },
    "RoundTeaParty": {
        "option_overrides": {
            "Enjoy Your Tea": {"description": "Obtain a random [red]Relic[/red]."},
        },
    },
    "SunkenStatue": {
        "option_overrides": {
            "Grab the Sword": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
    },
    "ThisOrThat": {
        "option_overrides": {
            "This": {
                "description": "Lose [red]6[/red] HP. Gain [blue]41–69[/blue] [gold]Gold[/gold]."
            },
        },
    },
    "WaterloggedScriptorium": {
        "option_overrides": {
            "Prickly Sponge": {
                "description": "Pay [red]155[/red] [gold]Gold[/gold]. "
                "[gold]Enchant[/gold] [blue]2[/blue] cards with [purple]Steady[/purple]."
            },
            "Locked": {"description": "Requires [blue]155[/blue] [gold]Gold[/gold]."},
        },
    },
    "WelcomeToWongos": {
        "option_overrides": {
            "Wongo's Featured Item": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
    },
    "WoodCarvings": {
        "option_overrides": {
            "Snake": {"description": "[gold]Enchant[/gold] 1 card with [purple]Slither[/purple]."},
        },
    },
    "ColorfulPhilosophers": {
        "description": (
            "A group of colorful philosophers argue about which school of thought is best.\n\n"
            "Choose another character's card pool to receive 3 card rewards "
            "(one Common, one Uncommon, one Rare), each with 3 cards to pick from."
        ),
        "options": [
            {
                "title": "Choose a Philosophy",
                "description": "Pick another character's card pool. "
                "Receive 3 card reward screens (Common, Uncommon, Rare).",
            },
        ],
    },
    "Trial": {
        "option_overrides": {
            "Guilty": {
                "description": "Effects vary by trial type. "
                "May include: relics + a curse, healing, or gold."
            },
            "Innocent": {
                "description": "Effects vary by trial type. "
                "May include: card upgrades + a curse, gold + a curse, "
                "or card transforms + a curse."
            },
        },
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate event content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/events/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    with open(os.path.join(data_dir, "events.json")) as f:
        events = json.load(f)

    out = Path(output_dir)
    if out.exists():
        for p in out.glob("*.md"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for event in events:
        slug = slugify(event.get("title", event["class_name"]))
        desc = event.get("description", "")

        # Skip placeholder descriptions
        if desc.lower() in ("placeholder", "todo", "tbd"):
            desc = ""

        # Enrich events with code-defined descriptions and options
        enrichments = _EVENT_ENRICHMENTS.get(event["class_name"])
        if enrichments:
            if enrichments.get("description"):
                desc = enrichments["description"]
            if enrichments.get("options"):
                event["options"] = enrichments["options"]
            if enrichments.get("option_overrides"):
                for opt in event.get("options", []):
                    override = enrichments["option_overrides"].get(opt.get("title", ""))
                    if override:
                        if "title" in override:
                            opt["title"] = override["title"]
                        if "description" in override:
                            opt["description"] = override["description"]

        conditions = event.get("conditions", [])
        conditions_str = "; ".join(conditions) if conditions else ""

        lines = ["---"]
        lines.append(f"title: {escape_yaml(event.get('title', event['class_name']))}")
        lines.append(f"class_name: {escape_yaml(event['class_name'])}")
        lines.append(f"description_plain: {escape_yaml(strip_tags(desc))}")
        lines.append(f"description_html: {escape_yaml(render_description_html(desc))}")
        lines.append(f"options: {json.dumps(event.get('options', []))}")
        lines.append(f"acts: {json.dumps(event.get('acts', []))}")
        lines.append(f"conditions: {escape_yaml(conditions_str)}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{event['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} event pages in {output_dir}")


if __name__ == "__main__":
    main()
