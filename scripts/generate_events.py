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


def load_generated_ref_map(content_dir: str) -> dict[str, dict[str, str]]:
    """Build a class_name -> {title, slug} map from already-generated content
    markdown files. The page slug is the filename stem, which already accounts
    for collision dedup (e.g. FakeAnchor -> "anchor-fakeanchor"). Used so that
    event card_refs / relic_refs link to the real page slugs rather than the
    guessed slugs produced by the LLM extractor."""
    ref_map: dict[str, dict[str, str]] = {}
    if not os.path.isdir(content_dir):
        return ref_map
    for fname in os.listdir(content_dir):
        if not fname.endswith(".md"):
            continue
        slug = fname.removesuffix(".md")
        class_name = ""
        title = ""
        with open(os.path.join(content_dir, fname)) as f:
            for line in f:
                if line.startswith("class_name:"):
                    class_name = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("---") and class_name:
                    break
        if class_name:
            ref_map[class_name] = {"title": title or class_name, "slug": slug}
    return ref_map


def resolve_refs(refs: list[dict], ref_map: dict[str, dict[str, str]]) -> list[dict]:
    """Rewrite each ref's title/slug to the canonical generated-page values,
    keyed by class_name. Refs whose class_name has no generated page are left
    unchanged."""
    resolved = []
    for ref in refs:
        cname = ref.get("class_name", "")
        if cname in ref_map:
            resolved.append({"class_name": cname, **ref_map[cname]})
        else:
            resolved.append(ref)
    return resolved


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
        "notes": (
            "The [red]8[/red] HP loss from [gold]Trudge On[/gold] is [red]unblockable[/red] "
            "and [red]unpowered[/red] — it cannot be blocked or reduced by any powers or relics. "
            "[gold]Gold[/gold] gained is random: [blue]61\u201399[/blue] [gold]Gold[/gold].\n\n"
            "Choosing [gold]Rest[/gold] heals you for the standard rest site amount "
            "(roughly [green]30%[/green] of max HP), then immediately forces combat "
            "against a [red]Dense Vegetation encounter[/red]. "
            "This combat provides [red]no rewards[/red], and the event ends after the fight."
        ),
    },
    "FieldOfManSizedHoles": {
        "option_overrides": {
            "Enter Your Hole": {
                "description": "[gold]Enchant[/gold] a card with [purple]Perfect Fit[/purple]."
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
            "You must accept exactly one trade."
        ),
        "options": [
            {
                "title": "Take the Top One",
                "description": (
                    "Trade [gold]one of your relics[/gold] "
                    "for [gold]a new relic from the pool[/gold]."
                ),
            },
            {
                "title": "Take the Middle One",
                "description": (
                    "Trade [gold]one of your relics[/gold] "
                    "for [gold]a new relic from the pool[/gold]."
                ),
            },
            {
                "title": "Take the Bottom One",
                "description": (
                    "Trade [gold]one of your relics[/gold] "
                    "for [gold]a new relic from the pool[/gold]."
                ),
            },
        ],
    },
    "SelfHelpBook": {
        "option_overrides": {
            "Read the Back": {
                "description": "Choose an Attack to [gold]Enchant[/gold] "
                "with [purple]Sharp[/purple] [blue]2[/blue]."
            },
            "Read a Random Passage": {
                "description": "Choose a Skill to [gold]Enchant[/gold] "
                "with [purple]Nimble[/purple] [blue]2[/blue]."
            },
            "Read the Entire Book": {
                "description": "Choose a Power to [gold]Enchant[/gold] "
                "with [purple]Swift[/purple] [blue]2[/blue]."
            },
        },
    },
    "SlipperyBridge": {
        "option_overrides": {
            "Overcome": {"description": "A random card is removed from your [gold]Deck[/gold]."},
            "Hold On": {
                "description": "Lose [red]3[/red] HP (increases by 1 each time you Hold On). "
                "Damage is [red]unblockable[/red]. "
                "The card in the Overcome option is re-randomized."
            },
        },
        "notes": (
            "The first card removed is random from your non-Basic removable cards. "
            "Subsequent removals pick from cards of a "
            "[gold]different type[/gold] than the previous one "
            "(falls back to any removable card if none qualify).\n\n"
            "Hold On HP cost escalates: [red]3[/red], [red]4[/red], [red]5[/red], [red]6[/red]... "
            "(increases by 1 each time). "
            "The damage is [red]unblockable[/red] and ignores powers.\n\n"
            "The event has 7 unique pages of escalating distress text. "
            "After 7 or more holds, the text loops indefinitely — "
            "the developer apologizes for running out of content."
        ),
    },
    "SpiralingWhirlpool": {
        "option_overrides": {
            "Drink": {"description": "Heal [green]33%[/green] of max HP."},
        },
        "notes": "Heal amount is exactly 33% of your Max HP (rounded).",
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
                "description": "[gold]Enchant[/gold] an Attack with [purple]Corrupted[/purple]."
            },
        },
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
    "SunkenStatue": {
        "option_overrides": {
            "Grab the Sword": {"description": "Obtain the [gold]Sword of Stone[/gold]."},
        },
        "notes": (
            "Gold is randomized: [blue]101–121[/blue] gold. "
            "The HP loss from Dive into the Water is [red]unblockable[/red] "
            "and unaffected by powers."
        ),
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
            "Caviar (+4 Max HP): weight 6\n"
            "Clam Roll (heal 10 HP): weight 6, only if not at full HP\n"
            "Spicy Snappy (random upgrade): weight 3\n"
            "Jelly Liver (transform a card): weight 3\n"
            "Fried Eel (random colorless card): weight 3\n"
            "Suspicious Condiment (random potion): weight 3, only if you have open potion slots\n"
            "Golden Fysh (free, +75 gold): weight 1, only after first grab\n\n"
            "The previous dish cannot repeat. Spicy Snappy and Observe the Chef both "
            "upgrade a random card from your deck (not player-chosen). "
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
            "then you pick 2.\n\n"
            "[gold]Search[/gold]: the [red]14[/red] HP loss is [red]unblockable[/red] "
            "and not affected by powers or relics."
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
        "notes": (
            "This is a multi-stage event. Choosing [gold]Reject[/gold] on the initial screen "
            "leads to a second page where the [gold]Grand Arbiter[/gold] threatens death for "
            "refusal. From there you can still [gold]Accept[/gold] (give in) or "
            "[red]Double Down[/red] \u2014 [red]Double Down[/red] deals [red]9999[/red] damage "
            "(instant death) and shows an abandon-run confirmation dialog.\n\n"
            "After [gold]Accepting[/gold] (from either screen), one of three trial scenarios "
            "is chosen at random ([blue]1 in 3[/blue] each):\n\n"
            "[gold]The Merchant[/gold] \u2014 accused of murder; evidence is thin. "
            "[red]Guilty[/red]: Add [red]Regret[/red] to deck, gain [blue]2[/blue] random relics. "
            "[green]Innocent[/green]: Add [red]Shame[/red] to deck, "
            "upgrade [blue]2[/blue] cards.\n\n"
            "[gold]The Noble[/gold] \u2014 charged with corruption; slips you a bribe note. "
            "[red]Guilty[/red]: Heal [green]10[/green] HP. "
            "[green]Innocent[/green]: Add [red]Regret[/red] to deck, "
            "gain [blue]300[/blue] gold.\n\n"
            "[gold]The Nondescript Woman[/gold] \u2014 charged with theft and con-artistry; "
            "both sides compelling. "
            "[red]Guilty[/red]: Add [red]Doubt[/red] to deck, gain [blue]2[/blue] card rewards. "
            "[green]Innocent[/green]: Add [red]Doubt[/red] to deck, "
            "transform [blue]2[/blue] cards.\n\n"
            "The entrant number in the flavor text is randomly chosen between [blue]101[/blue] and "
            "[blue]999[/blue] when the event is generated. "
            "The [blue]2[/blue] random relics from the Merchant Guilty outcome are drawn from "
            "the front of your character\u2019s relic pool."
        ),
    },
    "DollRoom": {
        "notes": (
            "There are [blue]3[/blue] possible Doll Relics: "
            "[gold]Daughter of the Wind[/gold], [gold]Mr. Struggles[/gold], "
            "and [gold]Bing Bong[/gold].\n\n"
            "[gold]Pick at Random[/gold]: get 1 of the 3 relics at random (free).\n"
            "[gold]Take Some Time[/gold]: see [blue]2[/blue] of the 3 to choose from "
            "(costs [red]5[/red] unblockable HP).\n"
            "[gold]Examine Each[/gold]: see all [blue]3[/blue] to choose from "
            "(costs [red]15[/red] unblockable HP)."
        ),
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
                "description": "Lose [red]6[/red] HP. Gain [blue]41–68[/blue] [gold]Gold[/gold]."
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
            "Wongo's Featured Item": {
                "description": "Pay [red]200[/red] [gold]Gold[/gold]. "
                "Obtain a random [gold]Rare Relic[/gold]."
            },
        },
        "notes": (
            "[gold]Bargain Bin[/gold]: pulls from the Common relic pool. "
            "Earns [blue]32[/blue] [gold]Wongo Points[/gold].\n"
            "[gold]Featured Item[/gold]: pulls from the Rare relic pool; "
            "the specific relic is shown in the option. "
            "Earns [blue]16[/blue] [gold]Wongo Points[/gold].\n"
            "[gold]Mystery Box[/gold]: gives the [gold]Wongo's Mystery Ticket[/gold] "
            "relic (delivers [blue]3[/blue] relics after [blue]5[/blue] combats). "
            "Earns [blue]8[/blue] [gold]Wongo Points[/gold].\n\n"
            "[gold]Wongo Points[/gold] persist across runs. "
            "Every [blue]2000[/blue] points earns a "
            "[gold]Wongo Customer Appreciation Badge[/gold]. "
            "After each purchase the clerk announces your running total "
            "and remaining points to the next badge.\n\n"
            "[red]Leave[/red]: only downgrades an [blue]upgraded[/blue] card "
            "chosen at random. If you have no upgraded cards, nothing happens."
        ),
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


def _humanize_condition(cond: str) -> str:
    """Convert machine-readable conditions to human-friendly text."""
    import re as re_mod

    # "Gold >= 100" -> "At least 100 Gold"
    m = re_mod.match(r"Gold\s*>=\s*(\d+)", cond)
    if m:
        return f"At least {m.group(1)} Gold"
    # "HP >= 12" -> "At least 12 HP"
    m = re_mod.match(r"HP\s*>=\s*(\d+)", cond)
    if m:
        return f"At least {m.group(1)} HP"
    # "HP > 5" -> "More than 5 HP"
    m = re_mod.match(r"HP\s*>\s*(\d+)", cond)
    if m:
        return f"More than {m.group(1)} HP"
    # "Floor >= 6" -> "Floor 6 or later"
    m = re_mod.match(r"Floor\s*>=\s*(\d+)", cond)
    if m:
        return f"Floor {m.group(1)} or later"
    # "Floor > 6" -> "After floor 6"
    m = re_mod.match(r"Floor\s*>\s*(\d+)", cond)
    if m:
        return f"After floor {m.group(1)}"
    # "Max HP >= N" -> "At least N Max HP"
    m = re_mod.match(r"Max HP\s*>=\s*(\d+)", cond)
    if m:
        return f"At least {m.group(1)} Max HP"
    # "Deck size >= N" -> "At least N cards in deck"
    m = re_mod.match(r"Deck size\s*>=\s*(\d+)", cond)
    if m:
        return f"At least {m.group(1)} cards in deck"
    return cond


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate event content files")
    parser.add_argument("data_dir", help="Path to versioned data directory")
    parser.add_argument("output_dir", help="Path to content/events/ directory")
    args = parser.parse_args()

    data_dir = os.path.expanduser(args.data_dir)
    output_dir = os.path.expanduser(args.output_dir)

    # Load legacy aggregate events.json if present (produced by the old regex
    # extractor). Now that every version has per-entity JSONs from the LLM
    # extractor, this file is optional and used only as a fallback for fields
    # not yet in per-entity data.
    aggregate_path = os.path.join(data_dir, "events.json")
    events: list[dict] = []
    if os.path.exists(aggregate_path):
        with open(aggregate_path) as f:
            events = json.load(f)

    # Load per-entity JSON from data/{version}/events/*.json
    per_entity_dir = os.path.join(data_dir, "events")
    per_entity_data: dict[str, dict] = {}
    if os.path.isdir(per_entity_dir):
        for fname in os.listdir(per_entity_dir):
            if fname.endswith(".json"):
                with open(os.path.join(per_entity_dir, fname)) as f:
                    entity_data = json.load(f)
                cname = entity_data.get("class_name", fname.removesuffix(".json"))
                per_entity_data[cname] = entity_data

    # Merge per-entity data over aggregate data (per-entity takes precedence)
    events_by_class = {e["class_name"]: e for e in events}
    for cname, entity_data in per_entity_data.items():
        if cname in events_by_class:
            events_by_class[cname].update(entity_data)
        else:
            events_by_class[cname] = entity_data
    events = list(events_by_class.values())

    # Build canonical class_name -> {title, slug} maps from the already-generated
    # card and relic content (generate-cards / generate-relics run before this
    # step), so event card_refs / relic_refs link to the real page slugs.
    content_root = os.path.dirname(output_dir)
    card_ref_map = load_generated_ref_map(os.path.join(content_root, "cards"))
    relic_ref_map = load_generated_ref_map(os.path.join(content_root, "relics"))

    # Load override directory path
    overrides_dir = os.path.join(os.path.dirname(os.path.dirname(data_dir)), "overrides", "events")

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
        conditions = [_humanize_condition(c) for c in conditions]
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
        elif event.get("notes"):
            notes = event["notes"]
        if notes:
            lines.append(f"notes: {escape_yaml(render_description_html(notes))}")
        card_refs = resolve_refs(event.get("card_refs", []), card_ref_map)
        relic_refs = resolve_refs(event.get("relic_refs", []), relic_ref_map)
        lines.append(f"card_refs: {json.dumps(card_refs)}")
        lines.append(f"relic_refs: {json.dumps(relic_refs)}")
        lines.append("---")
        lines.append("")

        filepath = out / f"{slug}.md"
        if filepath.exists():
            slug = f"{slug}-{event['class_name'].lower()}"
            filepath = out / f"{slug}.md"

        # Merge per-page override if it exists
        override_path = os.path.join(overrides_dir, f"{slug}.md")
        if os.path.exists(override_path):
            with open(override_path) as f:
                override_content = f.read().strip()
            if override_content:
                # Parse override: if it has YAML frontmatter, merge fields
                if override_content.startswith("---"):
                    parts = override_content.split("---", 2)
                    if len(parts) >= 3:
                        # Override frontmatter fields into the lines
                        for line in parts[1].strip().split("\n"):
                            if ":" in line:
                                key = line.split(":")[0].strip()
                                # Replace matching line in generated output
                                for idx, gen_line in enumerate(lines):
                                    if gen_line.startswith(f"{key}:"):
                                        lines[idx] = line
                                        break
                        # Append body content
                        body = parts[2].strip()
                        if body:
                            lines.append(body)
                else:
                    # Plain markdown — append after frontmatter
                    lines.append(override_content)

        filepath.write_text("\n".join(lines))
        count += 1

    print(f"Generated {count} event pages in {output_dir}")


if __name__ == "__main__":
    main()
