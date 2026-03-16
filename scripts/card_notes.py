"""Hand-written notes about non-obvious card mechanics.

These are derived from reading the decompiled source code and comparing
against the localized descriptions. They document behaviors that a player
might not expect from reading the card text alone.
"""

# Maps card class_name -> note string
CARD_NOTES: dict[str, str] = {
    # --- A ---
    "AdaptiveStrike": (
        "The copy's 0-cost is permanent for the rest of combat, not just this turn."
    ),
    "Afterimage": "Upgrade adds Innate.",
    "Aggression": "Upgrade adds Innate.",
    "AllForOne": (
        "Excludes X-cost cards and Status/Curse/Quest cards from retrieval even if they cost 0."
    ),
    "Anointed": "Upgrade adds Retain.",
    "Apparition": "Upgrade removes Ethereal.",
    "AshenStrike": (
        "Base damage is 6 (upgraded: 6). The formula is "
        "6 + 3 per card in Exhaust Pile (upgraded: 6 + 4 per card)."
    ),
    # --- B ---
    "BansheesCry": (
        "Cost reduction is cumulative across the entire combat, not per-turn. "
        "Starts at 6 energy. Each Ethereal card played this combat reduces cost by 1."
    ),
    "BeatDown": ("Attacks auto-played from discard target a random enemy."),
    "BigBang": "Upgrade adds Innate.",
    "BlightStrike": (
        "Doom applied equals actual damage dealt (after Block, Strength, Vulnerable), "
        "not the card's face damage."
    ),
    "Bolas": (
        "Returns to hand at start of next turn from any pile "
        "(draw, discard, or exhaust), not just discard."
    ),
    "Bombardment": (
        "Auto-plays from Exhaust Pile at start of each turn. Since it has Exhaust, "
        "it re-exhausts after each auto-play, creating an indefinite loop."
    ),
    "BulletTime": "Does NOT make X-cost cards free.",
    "Bully": (
        "Base damage is 4. Formula: 4 + 2 per Vulnerable stack on the enemy "
        "(upgraded: 4 + 3 per stack)."
    ),
    # --- C ---
    "CallOfTheVoid": "Upgrade adds Innate.",
    "Catastrophe": (
        "Prioritizes playing non-Unplayable cards from draw pile. "
        "Only plays Unplayable cards as a fallback."
    ),
    "Chill": "Upgrade removes Exhaust.",
    "Claw": (
        "Each play permanently buffs ALL Claw copies across all piles. "
        "Upgrade increases both base damage and the per-play buff amount."
    ),
    "Conflagration": (
        "Base damage is 8 (upgraded: 9). Formula: 8 + 2 per other Attack "
        "played this turn (upgraded: 9 + 3)."
    ),
    "CrashLanding": "Hand size is capped at 10 cards.",
    "CrescentSpear": (
        "Counts Star-cost cards across all piles in combat "
        "(hand, draw, discard, exhaust), not just hand."
    ),
    # --- D ---
    "DeathMarch": (
        "Only counts mid-turn draws from card effects. "
        "The normal start-of-turn hand draw does NOT count."
    ),
    "DeathsDoor": ("Block is tripled (1 base + 2 additional) only if YOU applied Doom this turn."),
    "Discovery": (
        "The 0-cost persists if you Retain the card (lasts until played, not just this turn). "
        "Upgrade removes Exhaust."
    ),
    "DodgeAndRoll": (
        "Next-turn block uses the actual block gained (including Dexterity), "
        "not the card's base value."
    ),
    "Dominate": (
        "Strength gained equals the enemy's Vulnerable stack count. Upgrade removes Exhaust."
    ),
    "Dualcast": (
        "Evokes the same rightmost orb twice. The first evoke does not remove it from the slot."
    ),
    # --- E ---
    "EchoForm": "Has Ethereal. Upgrade removes Ethereal.",
    "EchoingSlash": (
        "Kill-chaining: each enemy killed adds another volley to ALL enemies, which can cascade."
    ),
    "Enlightenment": ("Only reduces costs, never increases them. Cards costing 0 stay at 0."),
    "Enthralled": (
        "Despite being labeled Unplayable, it costs 2 energy and IS playable. "
        "While in hand, it blocks you from playing any other card until played."
    ),
    # --- F ---
    "Fisticuffs": ("Block gained includes overkill damage beyond the enemy's remaining HP."),
    "Flatten": (
        "Cost reduction to 0 resets each turn. "
        "Triggers on any Osty attack, not just from specific cards."
    ),
    "FlakCannon": ("Exhausts Status cards from ALL piles (draw, discard, hand), not just hand."),
    "Ftl": (
        "Threshold is fewer than 3 cards played this turn (upgraded: 4). "
        "Both threshold and damage increase on upgrade."
    ),
    # --- G ---
    "GeneticAlgorithm": (
        "Block starts at 1 and increases by 3 per play (upgraded: 4). "
        "The increase persists permanently across combats."
    ),
    "GoldAxe": (
        "Counts cards played across the entire combat, not just the current turn. "
        "Upgrade adds Retain."
    ),
    "Grapple": ("The damage-on-Block-gain effect is applied as a power on the enemy."),
    "Graveblast": "Upgrade removes Exhaust.",
    # --- H ---
    "Hang": (
        "Damage multiplier compounds exponentially on the same target. "
        "Each play doubles the multiplier (2x → 4x → 8x → 16x)."
    ),
    "HiddenGem": (
        "Replay amount is 2 (upgraded: 3). "
        "Prioritizes Attack/Skill/Power cards and excludes Unplayable cards."
    ),
    "Hologram": "Upgrade removes Exhaust, making it reusable.",
    "HowlFromBeyond": (
        "Auto-plays from the Exhaust Pile before your hand is drawn each turn. "
        "It unexhausts itself to play."
    ),
    # --- I ---
    "Ignition": "Upgrade removes Exhaust.",
    "Inferno": ("Self-damage starts at 1 HP/turn and increments by 1 each time Inferno is played."),
    # --- K ---
    "KinglyKick": ("Cost reduction from drawing is permanent for the combat, not per-turn."),
    "KinglyPunch": ("Damage increase from drawing is permanent for the combat."),
    "KnifeTrap": (
        "Replays Shivs from the Exhaust Pile as actual card plays. "
        "Upgraded version upgrades each Shiv before playing it."
    ),
    "Knockdown": (
        "Damage multiplier applies only to OTHER players' attacks, not the caster's. "
        "Temporary: removed at end of enemy turn."
    ),
    "KnowThyPlace": "Upgrade removes Exhaust.",
    # --- L ---
    "Lethality": (
        "50% bonus (upgraded: 75%) is a true multiplicative modifier (1.5x/1.75x). "
        "Only applies to the first Attack each turn."
    ),
    # --- M ---
    "MakeItSo": ("Returns to hand from any pile (draw, discard, exhaust) every 3 Skills played."),
    "Mangle": (
        "Strength loss is temporary. The enemy regains the lost Strength at end of their turn."
    ),
    "MementoMori": (
        "Base damage is 8 (upgraded: 10). "
        "Formula: 8 + 4 per card discarded this turn (upgraded: 10 + 5)."
    ),
    "Mimic": "Upgrade removes Exhaust.",
    "Misery": "Upgrade adds Retain.",
    "Modded": ("Cost increase is permanent per combat. Each play raises cost by 1 forever."),
    "MoltenFist": (
        "Doubles the enemy's existing Vulnerable stacks. Does nothing if enemy has 0 Vulnerable."
    ),
    "MomentumStrike": ("Cost reduction to 0 is permanent for the rest of combat."),
    "Monologue": "All Strength gained is temporary, removed at end of turn.",
    "Murder": (
        "Counts cards drawn across the ENTIRE combat, not per-turn. "
        "Scales massively in long fights."
    ),
    # --- N ---
    "Neurosurge": ("Self-Doom is applied every turn permanently. The power never expires."),
    "NoEscape": (
        "Formula: 10 base Doom + 5 additional per 10 existing Doom on the enemy "
        "(upgraded: 15 base + 5 per 10)."
    ),
    "Normality": (
        "While in hand, blocks ALL card plays by the same player "
        "once 3 cards have been played this turn."
    ),
    # --- O ---
    "Oblivion": (
        "Applies Doom after each card played this turn. Effect expires at end of your turn."
    ),
    "Omnislice": (
        "Splash damage includes overkill damage and is Unpowered "
        "(ignores Strength/Vulnerable on splash targets)."
    ),
    "OneTwoPunch": ("Each stack makes one Attack play twice. Upgraded gives 2 stacks."),
    "Orbit": (
        "Energy threshold is always 4 regardless of stacks. "
        "Stacking increases energy gained per trigger. Can trigger multiple times per turn."
    ),
    # --- P ---
    "ParticleWall": (
        "Returns to hand after being played instead of discarding. Infinitely replayable."
    ),
    "PerfectedStrike": ("Counts Strike-tagged cards in ALL piles (hand, draw, discard, exhaust)."),
    "PiercingWail": (
        "Strength loss is temporary. Enemies regain lost Strength at end of their turn."
    ),
    "Pillage": "Draw loop stops at 10 cards in hand.",
    "Pinpoint": "Cost reduction resets each turn.",
    "PreciseCut": (
        "Base damage is 13 (upgraded: 16). Loses 2 damage per other card in hand. "
        "Excludes itself from the count."
    ),
    "Production": "Upgrade removes Exhaust, making it a repeatable 0-cost +2 energy card.",
    "Prolong": "Upgrade removes Exhaust.",
    # --- Q ---
    "Quadcast": "Upgrade reduces energy cost from 1 to 0.",
    # --- R ---
    "Radiate": (
        "Hit count equals total Stars gained this turn (gaining 3 at once = 3 hits, not 1)."
    ),
    "Rend": ("Base damage is 15. Only counts permanent debuffs; temporary debuffs are excluded."),
    "Restlessness": (
        "Triggers when Restlessness is the ONLY card in your hand "
        "(it excludes itself from the empty-hand check)."
    ),
    "RocketPunch": (
        "Cost reduction to 0 persists across turns until played, "
        "not just this turn as the description implies."
    ),
    # --- S ---
    "Scrape": (
        "Discards drawn cards that have any cost (energy or Stars). "
        "Only keeps truly 0-cost cards with no Star cost."
    ),
    "Scrawl": "Hand size cap is 10 cards.",
    "Seance": "This is a permanent Transform, not a temporary combat effect.",
    "SecretTechnique": "Upgrade removes Exhaust.",
    "SecretWeapon": "Upgrade removes Exhaust.",
    "Severance": (
        "The three Souls go to specific piles: one to Draw Pile, one to Hand, one to Discard Pile."
    ),
    "Shiv": ("If Fan of Knives is active, Shivs hit ALL enemies instead of one."),
    "SoulStorm": ("Base damage is 9. Formula: 9 + 2 per Soul in Exhaust Pile."),
    "Spite": ("Only triggers on unblocked damage during the player's combat turn."),
    "Squeeze": ("Base damage is 25. Counts Osty Attack cards across all piles, not just in hand."),
    "Stack": "Upgrade adds 3 to the base block calculation.",
    "Stratagem": "Single-player only. Cannot be used in co-op.",
    "SummonForth": ("Retrieves ALL Sovereign Blade copies from any pile, not just one."),
    "Supermassive": "Base damage is 5 plus cards generated this combat.",
    # --- T ---
    "TheHunt": ("Fatal reward can be prevented by enemy death-prevention powers."),
    "TheScythe": (
        "Damage increase is permanent across combats (saved to deck). Base damage starts at 13."
    ),
    "Thrash": (
        "Reads the full modified damage from the exhausted Attack, "
        "including Strength and other modifiers."
    ),
    "ThrummingHatchet": ("Returns to hand from any pile at start of turn, not just discard."),
    "Tracking": (
        "First play gives 2x damage multiplier on Weak enemies. "
        "Subsequent plays only add 1 stack each."
    ),
    "Transfigure": (
        "Permanently adds Replay to the chosen card AND increases its cost by 1. "
        "Upgrade removes Exhaust, allowing multiple uses."
    ),
    # --- U ---
    "Undeath": "Creates a clone inheriting all modifications, not a fresh copy.",
    "Unleash": "Base damage is 6 plus Osty's current HP.",
    "UpMySleeve": ("Cost reduction is permanent per combat. Can eventually cost 0."),
    "Uproar": (
        "Despite being Unplayable, auto-play effects can trigger it. "
        "Prefers non-Unplayable Attacks from draw pile."
    ),
    # --- V ---
    "VoidForm": "Immediately ends your turn. Cannot be undone.",
    "Voltaic": (
        "Counts Lightning channeled across the entire combat, not just this turn. "
        "Upgrade removes Exhaust."
    ),
}
