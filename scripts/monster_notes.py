"""Hand-written notes about non-obvious monster mechanics.

Derived from reading the decompiled source code. Documents behaviors
that aren't obvious from the move list alone (card stealing logic,
summoning conditions, phase triggers, scaling, etc.).
"""

# Maps monster class_name -> note string
MONSTER_NOTES: dict[str, str] = {
    "ThievingHopper": (
        "Steals cards using a priority system. It searches your Draw + Discard "
        "piles and picks from the highest-priority category that has eligible cards:\n"
        "1. Uncommon non-Imbued cards (highest priority)\n"
        "2. Common/Rare/Event non-Imbued cards\n"
        "3. Basic/Quest non-Imbued cards\n"
        "4. Ancient or Imbued cards (lowest priority)\n\n"
        "Within each category, the stolen card is chosen uniformly at random. "
        "The card is removed from combat entirely."
    ),
    "Fabricator": (
        "Spawns from two pools: Aggro (Zapbot, Stabbot) and Defense (Guardbot, Noisebot). "
        "Cannot repeat the same monster consecutively. Can only fabricate when fewer than "
        "4 allies are alive; otherwise falls back to Disintegrate.\n\n"
        "Move selection is 50/50 between Fabricate (1 defense + 1 aggro bot) "
        "and Fabricating Strike (damage + 1 aggro bot)."
    ),
    "Noisebot": (
        "Adds 2 Dazed every turn: 1 to your Discard pile, 1 to a random position in your Draw pile."
    ),
    "Chomper": "Screech adds 3 Dazed to your Discard pile.",
    "LivingFog": (
        "Bloat spawns Gas Bomb minions with escalating count: "
        "1 on first use, 2 on second, up to a maximum of 5 per Bloat."
    ),
    "Doormaker": (
        "Starts the fight with 999,999,999 HP and an infinite health bar display. "
        "On Dramatic Open, HP is set back to its real value, all existing powers "
        "are removed, and Hunger of the Void is applied to each player. "
        "Pulverize gains +2/3 Strength per use."
    ),
    "Queen": (
        "Two-phase fight based on whether Torch Head Amalgam is alive:\n\n"
        "Phase 1 (Amalgam alive): Puppet Strings → You're Mine "
        "(applies 99 Frail, Weak, and Vulnerable!) → loops Burn Bright For Me "
        "(+1 Strength to allies, +20 Block).\n\n"
        "Phase 2 (Amalgam dead): switches to Off With Your Head (5-hit multi-attack) → "
        "Execution → Enrage (+2 Strength) loop. If she's mid-move when the Amalgam dies, "
        "she immediately switches to Enrage."
    ),
    "LagavulinMatriarch": (
        "Starts asleep with 12 Plating. Wakes after 3 turns (Asleep 3 counter).\n\n"
        "Soul Siphon steals 2 Strength and 2 Dexterity from all players, "
        "and the Matriarch gains 2 Strength. Eye animation changes at 50% HP."
    ),
    "CeremonialBeast": (
        "Phase 1: Stamps to gain Plow (150/160 shield), then repeatedly attacks "
        "and gains +2 Strength per Plow attack.\n\n"
        "Phase 2 (after Plow breaks): stunned for 1 turn, then Beast Cry (Ringing debuff) → "
        "Stomp → Crush (+3/4 Strength) loop."
    ),
    "FrogKnight": (
        "When HP drops below 50%, uses Beetle Charge (35/40 damage) exactly once. "
        "This overrides the normal move cycle."
    ),
    "BygoneEffigy": (
        "Starts asleep with Slow power. On waking, gains +10 Strength, then "
        "infinitely loops Slash attacks."
    ),
    "KnowledgeDemon": (
        "Three rounds of Curse of Knowledge: each round the player chooses between "
        "Disintegration (6/7/8 escalating damage) or a different curse (Mind Rot, Sloth, "
        "Waste Away). The curses are player-chosen, not random.\n\n"
        "Ponder heals 30 × player count and gains +2/3 Strength."
    ),
    "MechaKnight": (
        "Flamethrower adds 4 Burn cards to each player's hand. Starts with 3 Artifact."
    ),
    "TheInsatiable": (
        "Liquify Ground adds 6 Frantic Escape status cards per player: "
        "3 to Draw pile (random positions) and 3 to Discard pile."
    ),
    "SoulFysh": (
        "Beckon adds Beckon cards to your deck (1 to Draw pile, 1 to Discard). "
        "Gaze adds 1 Beckon to Discard. Fade gives 2 turns of Intangible."
    ),
    "TheLost": (
        "Has Possess Strength power — steals player Strength. Debilitating Smog "
        "removes Strength from players and adds it to itself."
    ),
    "TheForgotten": (
        "Has Possess Speed power. Miasma steals Dexterity from players and converts "
        "it to Block + self-Dexterity. Dread's damage scales with the Forgotten's "
        "current Dexterity (unusual — Dexterity adds to attack damage)."
    ),
    "DecimillipedeSegment": (
        "Each segment starts with a different move (staggered by slot index). "
        "Has Reattach power (25 HP threshold) for revival — after death, re-emerges "
        "and cycles back into its attack pattern. Each segment's Max HP is adjusted "
        "to ensure no two segments share the same value."
    ),
    "PhantasmalGardener": (
        "Starting move depends on slot position (Flail, Bite, Lash, or Enlarge). "
        "Enlarge grants Strength and physically scales the monster's size using a "
        "logarithmic formula."
    ),
    "TwoTailedRat": (
        "Can summon another rat, but with restrictions: cannot summon for the first "
        "2 turns, max 3 total summons across all rats, and cannot summon if another "
        "rat is already planning to summon this turn. When eligible, summon has 75% "
        "weight vs other moves."
    ),
    "Vantom": ("Dismember adds 3 Wound to Discard pile. Starts with 9 stacks of Slippery."),
    "HauntedShip": (
        "Ramming Speed adds 2 Wound to Discard pile. Move selection alternates "
        "between attack rounds (odd turns) and Haunt rounds (even turns). "
        "Haunt can only be used once per combat."
    ),
    "GremlinMerc": (
        "Uses Thievery power (amount 20) — steals gold on every attack move. "
        "Hehe gains +2 Strength. Double Smash applies 2 Weak."
    ),
    "Ovicopter": (
        "Lays 3 Tough Egg minions when 3 or fewer allies are alive. "
        "If it can't lay eggs, uses Nutritional Paste (+3/4 Strength) instead."
    ),
    "ToughEgg": (
        "Has a Hatch countdown (1 or 2 turns). When hatched, scales HP to 19–23 "
        "range, removes all powers except Minion, and becomes a regular enemy."
    ),
}
