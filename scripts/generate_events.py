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
        "notes": (
            "Setting 1 potion: drawn from your character's potion pool + shared pool, "
            "weighted by rarity (65% Common, 25% Uncommon, 10% Rare).\n\n"
            "Setting 2 upgrades: 2 random upgradable cards from your deck (not player-chosen).\n\n"
            "Setting 3 relic: pulled from the standard relic pool "
            "(the next relic you'd get from an elite)."
        ),
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
        "notes": "Gold from option 1 is randomized: [blue]61–100[/blue] gold.",
    },
    "DrowningBeacon": {
        "option_overrides": {
            "Bottle": {"description": "Procure a random [aqua]Potion[/aqua]."},
            "Climb": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
        "notes": (
            "The potion is drawn from your character's pool + shared pool "
            "(65% Common, 25% Uncommon, 10% Rare).\n\n"
            "The relic is the next from the standard relic pool."
        ),
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
            "Three of your relics are randomly shuffled and each paired "
            "with the next relic you would have found from the relic pool. "
            "You may accept one trade.\n\n"
            "Requires [gold]5+[/gold] tradable relics (non-Starter, non-Event, "
            "not used up, no on-pickup effects, not melted, "
            "doesn't spawn pets). Available in Act 2+."
        ),
        "options": [
            {
                "title": "Trade a Relic",
                "description": "Swap one of your relics for the paired one. "
                "The offered relics are the next 3 from the normal relic pool "
                "(the same relics you'd get from future elites).",
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
        "notes": (
            "The first card removed is random from your non-Basic removable cards. "
            "Subsequent removals pick from cards of a "
            "[gold]different type[/gold] than the previous one "
            "(falls back to any removable card if none qualify).\n\n"
            "Hold On HP cost escalates: 3, 4, 5, 6... (increases by 1 each time)."
        ),
    },
    "SpiralingWhirlpool": {
        "option_overrides": {
            "Drink": {"description": "Heal [green]33%[/green] of max HP."},
        },
        "notes": "Heal amount is exactly 33% of your Max HP (rounded).",
    },
    "SpiritGrafter": {
        "option_overrides": {
            "Let It In": {"description": "Heal [green]25[/green] HP."},
            "Rejection": {"description": "Lose [red]9[/red] HP. Upgrade a card."},
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
                "requires": "Requires [blue]50[/blue] [gold]Gold[/gold].",
            },
            {
                "title": "Ember Tea",
                "description": "Pay [red]150[/red] [gold]Gold[/gold]. "
                "Obtain the [gold]Ember Tea[/gold] relic.",
                "requires": "Requires [blue]150[/blue] [gold]Gold[/gold].",
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
        "notes": (
            "The card rarity exactly matches the potion rarity: Rare/Event potion → Rare cards, "
            "Uncommon → Uncommon, Common/Token → Common.\n\n"
            "The card type (Attack/Skill/Power) is chosen randomly for each potion "
            "(Common/Token potions exclude Power type). "
            "All 3 offered cards share the same type and rarity, drawn from your character's pool. "
            "All generated cards are pre-upgraded."
        ),
    },
    "LostWisp": {
        "option_overrides": {
            "Capture the Wisp": {"description": "Obtain a random [gold]Relic[/gold]."},
        },
        "notes": (
            "Gold from Search is randomized: [blue]45–75[/blue] gold.\n\n"
            "The relic from Capture is pulled from the standard relic pool."
        ),
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
        "notes": "Gold is randomized: [blue]101–121[/blue] gold.",
    },
    "TrashHeap": {
        "option_overrides": {
            "Dive In": {
                "description": "Lose [red]8[/red] HP. Obtain a random relic from the pool below. "
                "These are [gold]STS1 relics[/gold] exclusive to this event — "
                "one is chosen at random regardless of your character.",
            },
            "Grab Random Junk": {
                "description": "Gain [blue]100[/blue] [gold]Gold[/gold]. "
                "Add a random card from the pool below to your deck. "
                "These are [gold]STS1 cards[/gold] exclusive to this event — "
                "one is chosen at random regardless of your character.",
            },
        },
        "notes": (
            "Both pools are fixed — every card and relic has equal chance. "
            "The card is added directly to your deck (no choice screen). "
            "The HP loss from Dive In is unblockable and ignores powers."
        ),
    },
    "EndlessConveyor": {
        "notes": (
            "[gold]Dish selection[/gold] uses weighted randomization. "
            "Every 5th grab is always Seapunk Salad (adds Feeding Frenzy card). "
            "Otherwise, dishes are drawn by weight from those currently available:\n\n"
            "Caviar (upgrade a card): weight 6\n"
            "Clam Roll (heal): weight 6, only if not at full HP\n"
            "Spicy Snappy (random upgrade): weight 3\n"
            "Jelly Liver (+5 Max HP): weight 3\n"
            "Fried Eel (random colorless card): weight 3\n"
            "Suspicious Condiment (random potion): weight 3, only if you have open potion slots\n"
            "Golden Fysh (free, +75 gold): weight 1, only after first grab\n\n"
            "The previous dish cannot repeat. Spicy Snappy and Observe the Chef both "
            "upgrade a random card from your deck (not player-chosen). "
            "Suspicious Condiment draws from character + shared potion pool "
            "(65% Common, 25% Uncommon, 10% Rare). "
            "Fried Eel adds a random colorless card directly to your deck (no choice)."
        ),
    },
    "CrystalSphere": {
        "notes": (
            "The gold cost is randomized: [blue]51–99[/blue] gold. "
            "This is determined when the event spawns and varies between runs."
        ),
    },
    "BrainLeech": {
        "notes": (
            "[gold]Rip[/gold]: standard 3-card reward screen from the Colorless card pool.\n\n"
            "[gold]Share Knowledge[/gold]: generates 5 cards from your character's pool, "
            "then you pick 1 (you must choose one — cannot cancel)."
        ),
    },
    "InfestedAutomaton": {
        "notes": (
            "[gold]Study[/gold]: adds a random Power card from your "
            "character's pool directly to your deck (no choice).\n\n"
            "[gold]Touch Core[/gold]: adds a random 0-cost card from "
            "your character's pool directly to your deck (no choice)."
        ),
    },
    "RoomFullOfCheese": {
        "notes": (
            "[gold]Gorge[/gold]: generates 8 Common-rarity cards from your character's pool, "
            "then you pick 2."
        ),
    },
    "Reflections": {
        "notes": (
            "[gold]Touch a Mirror[/gold]: randomly downgrades up to 2 upgraded cards, "
            "then randomly upgrades up to 4 upgradable cards. Both selections are random, "
            "not player-chosen.\n\n"
            "[gold]Shatter[/gold]: duplicates your entire deck "
            "(doubles every card), then adds a Curse."
        ),
    },
    "TabletOfTruth": {
        "notes": (
            "Each Decipher costs increasing Max HP: [red]3[/red], [red]6[/red], "
            "[red]12[/red], [red]24[/red], then [red]all but 1[/red] Max HP.\n\n"
            "Deciphers 1–4 each upgrade a random card from your deck. "
            "The 5th and final decipher upgrades [gold]ALL[/gold] upgradable cards in your deck."
        ),
    },
    "TinkerTime": {
        "notes": (
            "You build a custom Mad Science card in two steps:\n\n"
            "Step 1: Choose a card type — shown 2 of 3 (Attack/Skill/Power) at random.\n\n"
            "Step 2: Choose a rider effect — each type has 3 possible riders "
            "(e.g. Attack: Sapping/Violence/Choking), shown 2 of 3 at random.\n\n"
            "The resulting card combines the chosen type and rider effect."
        ),
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
        "notes": (
            "The trial scenario (Merchant/Noble/Nondescript) is chosen "
            "randomly. Each scenario has different outcomes:\n\n"
            "Merchant: Guilty gives 2 relics + Clumsy curse. "
            "Innocent gives gold + Normality curse.\n\n"
            "Noble: Guilty gives healing. "
            "Innocent gives card transforms + Clumsy curse.\n\n"
            "Nondescript: Guilty gives 2 card rewards from your pool. "
            "Innocent gives card upgrades + Normality curse."
        ),
    },
    "DollRoom": {
        "notes": (
            "3 dolls are available, each containing a different relic "
            "(Daughter of the Wind, Mr. Struggles, and either Bing Bong or Fable).\n\n"
            "[gold]Random[/gold] (free): get 1 random doll.\n"
            "[gold]Take Some Time[/gold] (5 HP): see 2 of 3, choose 1.\n"
            "[gold]Examine[/gold] (15 HP): see all 3, choose 1."
        ),
    },
    "PunchOff": {
        "notes": "Gold from Nab is randomized: [blue]91–98[/blue] gold.",
    },
    "SunkenTreasury": {
        "notes": (
            "Small chest gold: [blue]52–67[/blue]. "
            "Large chest gold: [blue]303–363[/blue] (adds Greed curse)."
        ),
    },
    "ThisOrThat": {
        "option_overrides": {
            "This": {
                "description": "Lose [red]6[/red] HP. Gain [blue]41–69[/blue] [gold]Gold[/gold]."
            },
        },
        "notes": (
            "Gold from 'This' is randomized: [blue]41–68[/blue] gold.\n\n"
            "'That' gives a relic from the standard relic pool + Clumsy curse."
        ),
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
        "notes": (
            "[gold]Bargain Bin[/gold]: pulls from the Common relic pool specifically.\n"
            "[gold]Featured Item[/gold]: pulls from the Rare relic pool specifically.\n"
            "[gold]Mystery Box[/gold]: gives the Wongo's Mystery Ticket "
            "relic (deferred rewards over 5 combats).\n\n"
            "[gold]Leave[/gold] randomly downgrades 1 upgraded card from your deck.\n\n"
            "Wongo Points accumulate across runs — every 2000 points earns a "
            "Wongo Customer Appreciation Badge."
        ),
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
        "notes": (
            "Only shows unlocked characters other than your own. "
            "Up to 3 are offered from the fixed order: "
            "Necrobinder, Ironclad, Regent, Silent, Defect "
            "(if more than 3 qualify, extras are randomly removed).\n\n"
            "Each chosen pool gives 3 separate reward screens with guaranteed rarities "
            "(one Common, one Uncommon, one Rare) — you pick 1 card from each."
        ),
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

        # Merge "Locked"/"Broke" options into their corresponding unlocked options
        raw_options = event.get("options", [])
        merged_options: list[dict[str, str]] = []
        i = 0
        while i < len(raw_options):
            opt = raw_options[i]
            title = opt.get("title", "")
            if title in ("Locked", "Broke"):
                lock_desc = opt.get("description", "")
                # Locked before its unlocked counterpart: attach to next option
                if i + 1 < len(raw_options) and raw_options[i + 1].get("title", "") not in (
                    "Locked",
                    "Broke",
                ):
                    next_opt = dict(raw_options[i + 1])
                    next_opt["requires"] = lock_desc
                    merged_options.append(next_opt)
                    i += 2
                    continue
                # Orphaned locked option (e.g. ZenWeaver shared lock, EndlessConveyor "Broke")
                # Skip it — the requirement info is already in the option descriptions
                i += 1
                continue
            # Check if the next option is a Locked variant of this one
            if i + 1 < len(raw_options) and raw_options[i + 1].get("title", "") in (
                "Locked",
                "Broke",
            ):
                opt = dict(opt)
                opt["requires"] = raw_options[i + 1].get("description", "")
                merged_options.append(opt)
                i += 2
                continue
            merged_options.append(opt)
            i += 1
        event["options"] = merged_options

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
        notes = ""
        if enrichments and enrichments.get("notes"):
            notes = enrichments["notes"]
        if notes:
            lines.append(f"notes: {escape_yaml(render_description_html(notes))}")
        lines.append(f"card_refs: {json.dumps(event.get('card_refs', []))}")
        lines.append(f"relic_refs: {json.dumps(event.get('relic_refs', []))}")
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
