# Slay the Spire 2 Wiki — Build Plan

## Game Overview

Slay the Spire 2 is built with Godot 4.5.1 and C#/.NET 9.0.7. Game logic lives in a single `sts2.dll` (8.5MB), and all assets/localization are packed in a 1.5GB Godot `.pck` file. The game is currently in early access (v0.98.2 as of 2026-03-06).

## File Locations

### Game installation
```
~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/
  Contents/
    Resources/
      Slay the Spire 2.pck           # 1.5GB Godot pack file (assets, localization, scenes)
      release_info.json               # {"commit": "...", "version": "v0.98.2", "date": "...", "branch": "..."}
      data_sts2_macos_arm64/
        sts2.dll                      # 8.5MB — ALL game logic (C#/.NET)
        sts2.deps.json
        sts2.runtimeconfig.json       # Confirms .NET 9.0.7
        GodotSharp.dll                # Godot C# bindings
        0Harmony.dll                  # Harmony patching library
        Steamworks.NET.dll
        ... (200+ framework DLLs)
```

### Save data
```
~/Library/Application Support/SlayTheSpire2/steam/<steam-id>/
  profile1/
    saves/
      progress.save                   # JSON — unlocks, epoch states, encounter stats, character stats
      prefs.save                      # JSON — preferences
      current_run.save.backup         # JSON — full run state including RNG counters, room assignments
      history/
        <timestamp>.run               # JSON — completed run data (per run)
    replays/
      latest.mcr                      # Replay file
```

### Working directory (this project)
```
~/sts-scratch/
  sts2-decompiled/                    # Full ILSpy decompilation of sts2.dll (3,298 C# files)
  pck-extracted/                      # Extracted localization/data from PCK
    localization/eng/                 # 45 JSON files + patch_notes directory
  sts2_cards.json                     # Extracted card database (577 cards)
  sts2_cards_summary.txt              # Human-readable card summary
  extract_pck.py                      # PCK extraction tool
  extract_cards.py                    # Card data extraction script
```

## Game Content Inventory

| Category | Count | Decompiled location | Localization file |
|---|---|---|---|
| Cards | 577 | `MegaCrit.Sts2.Core.Models.Cards/` | `cards.json` (96KB) |
| Relics | 290 | `MegaCrit.Sts2.Core.Models.Relics/` | `relics.json` (87KB) |
| Powers (status effects) | 260 | `MegaCrit.Sts2.Core.Models.Powers/` | `powers.json` (80KB) |
| Monsters | 121 | `MegaCrit.Sts2.Core.Models.Monsters/` | `monsters.json` (24KB) |
| Encounters | 88 | `MegaCrit.Sts2.Core.Models.Encounters/` | `encounters.json` (13KB) |
| Events | 68 | `MegaCrit.Sts2.Core.Models.Events/` | `events.json` (113KB) |
| Potions | 64 | `MegaCrit.Sts2.Core.Models.Potions/` | `potions.json` (10KB) |
| Enchantments | 23 | `MegaCrit.Sts2.Core.Models.Enchantments/` | `enchantments.json` (4KB) |
| Characters | 5+1 | `MegaCrit.Sts2.Core.Models.Characters/` | `characters.json` (5KB) |
| Acts | 4 | `MegaCrit.Sts2.Core.Models.Acts/` | `acts.json` |
| Ancients | 9 | `MegaCrit.Sts2.Core.Models.Events/` | `ancients.json` (34KB) |

### Characters
- Ironclad, Silent, Defect (returning from STS1)
- Necrobinder, Regent (new to STS2)
- Deprived (appears to be locked/unreleased)

### Acts
- Act 1a: Overgrowth (15 rooms, 3 weak encounters, 12 normal, 3 elites, 3 bosses)
- Act 1b: Underdocks (alternate Act 1, same structure)
- Act 2: The Hive (14 rooms, 2 weak, 12 normal, 3 elites, 3 bosses)
- Act 3: Glory (13 rooms, 2 weak, 11 normal, 3 elites, 3 bosses)

### Art Assets in PCK
The PCK contains structured image directories under `images/`:
- `ancients/`, `characters/`, `enchantments/`, `events/`, `monsters/`
- `orbs/`, `potions/`, `powers/`, `relics/`, `rooms/`
- `card_overlays/`, `atlases/`, `map/`, `timeline/`, `ui/`, `vfx/`

Images are stored as `.ctex` (Godot compressed textures) which need conversion to PNG. Card art is in texture atlases (`card_atlas_0.png` through `card_atlas_2.png`, ~40MB total).

## Decompiled Code Structure

### Key base classes

**CardModel** (`MegaCrit.Sts2.Core.Models/CardModel.cs`):
- Constructor: `base(cost, CardType, CardRarity, TargetType)`
- `CanonicalVars`: defines DamageVar, BlockVar, PowerVar etc. with base values
- `OnPlay(PlayerChoiceContext, CardPlay)`: the actual card behavior
- `OnUpgrade()`: what changes on upgrade
- `ExtraHoverTips`: linked keyword/power descriptions
- Keywords: Exhaust, Ethereal, Innate, Retain, Unplayable, etc.
- Description templates live in `cards.json` with `{Damage:diff()}` style substitution

**MonsterModel** (`MegaCrit.Sts2.Core.Models/MonsterModel.cs`):
- `GenerateMoveStateMachine()`: returns a state machine of `MoveState` objects
- Each MoveState has: ID, execute method, Intent objects (BuffIntent, SingleAttackIntent, etc.)
- MoveStates link via `FollowUpState` to define move sequences/cycles
- Intents describe what the player sees (attack damage, debuff icon, etc.)

**RelicModel** (`MegaCrit.Sts2.Core.Models/RelicModel.cs`):
- Rarity: Starter, Common, Uncommon, Rare, Shop, Event, Ancient
- `IsTradable`: excludes Starter/Event/Ancient, used-up, melted, pet-spawning relics
- Powers/hooks for combat events

**EventModel** (`MegaCrit.Sts2.Core.Models/EventModel.cs`):
- `GenerateInitialOptions()`: the choices presented to the player
- `IsAllowed(RunState)`: conditions for the event to appear
- Ancients are a subclass (`AncientEventModel`) with dialogue trees

**EncounterModel** (`MegaCrit.Sts2.Core.Models/EncounterModel.cs`):
- `RoomType`: Normal/Elite/Boss
- `GenerateMonsters()`: which monsters and their positions
- `Tags`: encounter tags for non-repeat logic (Slugs, Slimes, Workers, etc.)

### Key systems

**Localization**: JSON key-value files with SmartFormat-style templates. Card descriptions use `{Damage:diff()}`, `{Block:diff()}`, `{VulnerablePower:diff()}` etc. Rich text tags: `[gold]...[/gold]`, `[red]...[/red]`, `[sine]...[/sine]`.

**Dynamic Variables**: `DamageVar`, `BlockVar`, `PowerVar<T>`, `EnergyVar`, `CardsVar`, `HpLossVar`, `GenericVar`, `SummonVar`, `ForgeVar`, etc. Each has a base value and upgrade delta.

**Relic Pools**: Common/Uncommon/Rare/Shop/Event pools, managed by `RelicGrabBag` with rarity rolling (50% Common, 33% Uncommon, 17% Rare).

**Enchantments**: Card modifiers (23 types) like Swift, Goopy, Instinct, Sharp, etc. Applied to cards to modify their behavior.

**Orbs**: Defect mechanic — Lightning, Frost, Dark, Plasma orbs with channel/evoke behavior.

## Extraction Pipeline Design

### Step 1: Decompile + Extract (per version)

Tools needed:
- `ilspycmd` (installed at `~/.dotnet/tools/ilspycmd`, version 10.0.0.8282-preview2)
- `extract_pck.py` (custom script in `~/sts-scratch/`)

Process:
1. Read `release_info.json` to get version string
2. Check if this version has already been processed (compare against cached versions)
3. Decompile `sts2.dll` with ilspycmd → `decompiled/<version>/`
4. Extract localization + image files from PCK → `extracted/<version>/`
5. Convert `.ctex` textures to PNG (needs Godot's texture format decoder or GDRE tools)

### Step 2: Structured Data Extraction (per version)

For each content type, parse the decompiled C# files and localization JSON into structured JSON data files. This is the most complex step and benefits from caching — only re-extract what changed.

#### Cards (`cards.json`)
Already partially implemented in `extract_cards.py`. Needs enhancement for:
- Full variable substitution into descriptions
- Upgraded values (base + upgrade delta)
- Character assignment (which character's card pool)
- Complete keyword list
- Card pool membership (Common/Uncommon/Rare per character)

#### Monsters (`monsters.json`)
Parse each monster's decompiled `.cs` file to extract:
- HP values (may vary by ascension — look for `GetMaxHp()`)
- Move state machine: move sequence, damage values, applied powers
- Intent types per move
- Special mechanics (thresholds, phases)

This is the hardest extraction because movesets are defined as procedural code, not declarative data. A Claude pass will be essential for interpreting move logic into human-readable descriptions.

#### Encounters (`encounters.json`)
- Which monsters appear together
- Room type (Normal/Weak/Elite/Boss)
- Which act they belong to
- Monster positioning

#### Events (`events.json`)
- Options and their effects (gold costs, HP costs, card/relic rewards)
- Conditions for appearing (`IsAllowed`)
- For Ancients: which relics they offer, dialogue trees
- Multi-page event flows

#### Relics (`relics.json`)
- Title, description, flavor text
- Rarity and pool
- Mechanical effect (from decompiled code)
- Which ancient/event/shop offers it

#### Potions (`potions.json`)
- Title, description
- Rarity
- Effect (from decompiled code)

#### Powers (`powers.json`)
- Title, description
- Whether it's a buff or debuff
- Duration/stacking behavior
- Mechanical effect

#### Enchantments (`enchantments.json`)
- Title, description
- Effect on cards

### Step 3: Claude Enrichment Pass

For each extracted data item, run a headless Claude Code pass that:
1. Reads the raw extracted data
2. Reads the decompiled source code for that item
3. Generates a human-readable description of behavior, strategy tips, and interactions
4. Identifies cross-references (e.g., "this card synergizes with X power")

This pass should use a structured prompt that produces consistent output format across all items of a given type. Output goes into an `enriched/<version>/` directory.

Things Claude is particularly needed for:
- **Monster movesets**: Translating state machine code into "Turn 1: does X, Turn 2: does Y, then cycles" descriptions
- **Event decision analysis**: Summarizing what each choice gives you and when each is optimal
- **Card strategy notes**: When a card is strong, what archetypes it fits
- **Relic interactions**: Non-obvious synergies between relics and card/character mechanics

### Step 4: Page Generation

Convert structured data into wiki pages. Each page type has a template:

#### Card Page
- Name, cost, type, rarity, character
- Base description, upgraded description (with actual numbers filled in)
- Keywords
- Card art (from texture atlas)
- Strategy notes (from Claude pass)
- Version history (diff against previous versions)

#### Monster Page
- Name, HP
- Moveset table (move name, intent, damage/block values, effects)
- Move pattern description
- Which encounters it appears in
- Which act(s)

#### Encounter Page
- Name, act, room type (Normal/Elite/Boss)
- Monster composition
- Tips

#### Event Page
- Name, which acts it appears in
- Full option tree with effects
- Conditions for appearing
- For Ancients: relic offerings, dialogue

#### Relic Page
- Name, rarity, pool
- Description
- Detailed mechanical behavior
- How to obtain
- Art

### Step 5: Version Diffing

When a new game version is detected:
1. Run steps 1-2 for the new version
2. Diff the structured data against the previous version
3. Generate changelogs per item (new, removed, changed)
4. Re-run Claude enrichment only for changed items
5. Update pages with version history section
6. Keep old version data archived

Diffing should operate on the structured JSON level, not the decompiled code level, to avoid false positives from decompiler output changes.

## Technical Decisions Still Needed

### Wiki platform
Static site built with Astro, hosted on GitHub Pages. Astro's content collections are a natural fit — each content type (cards, relics, monsters, etc.) maps to a collection with a typed schema. The pipeline generates markdown files with frontmatter that Astro consumes. Astro's island architecture also allows for interactive components (e.g., filterable card tables, moveset diagrams) without shipping a full JS framework.

### Image extraction
Godot `.ctex` files need conversion. Options:
- Use GDRE Tools (gdsdecomp) for batch conversion
- Write a custom decoder (ctex format is documented)
- Card art is in texture atlases — need atlas metadata to split individual card portraits

### Hosting
GitHub Pages. All output must be static assets (HTML, CSS, JS, images). No server-side rendering.

### Data versioning
All extracted data is stored per game version (keyed by the version string from `release_info.json`, e.g. `v0.98.2`). The latest commit always contains the full history of every version we've seen — not one version per git commit. Structure:

```
data/
  v0.98.2/
    cards.json
    relics.json
    monsters.json
    ...
  v0.98.1/
    cards.json
    ...
```

Each item's page shows its current state plus a version history section generated by diffing across these versioned data directories. When a new game version is detected, we extract it into a new versioned directory alongside all previous ones.

### Caching strategy
- Hash each decompiled `.cs` file; only re-extract if hash changes
- Hash localization JSON entries per key
- Claude enrichment is expensive — cache aggressively, only re-run for items whose structured data changed between the previous and current game version

### Character card pool assignment
Cards belong to specific characters but this isn't always obvious from the card file alone. Need to check:
- `CardPoolModel` classes in `MegaCrit.Sts2.Core.Models.CardPools/`
- Character starting decks in character model files

### Ascension scaling
Many values (monster HP, damage) scale with ascension level. Need to determine how to present this — probably show base values with ascension modifiers noted.

## Justfile

All pipeline commands are managed through a `justfile` at the project root.

```just
# Default: full build
default: check build

# Path to STS2 installation
sts2_app := "~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app"
sts2_dll := sts2_app / "Contents/Resources/data_sts2_macos_arm64/sts2.dll"
sts2_pck := sts2_app / "Contents/Resources/Slay the Spire 2.pck"
sts2_release := sts2_app / "Contents/Resources/release_info.json"

# --- Sanity checks ---

# Run all checks
check: check-format check-types check-data check-links

# Check Python formatting (ruff or black)
check-format:
    ruff check scripts/
    ruff format --check scripts/

# Type-check Python extraction scripts
check-types:
    mypy scripts/

# Validate extracted data against schemas
check-data:
    python scripts/validate_data.py data/

# Check for broken internal links in generated pages
check-links:
    python scripts/check_links.py site/src/content/

# --- Extraction pipeline ---

# Read current game version
version:
    @python -c "import json; print(json.load(open('{{sts2_release}}'))['version'])"

# Decompile sts2.dll for current game version
decompile:
    #!/usr/bin/env bash
    version=$(just version)
    if [ -d "decompiled/$version" ]; then
        echo "Already decompiled: $version"
    else
        echo "Decompiling $version..."
        ~/.dotnet/tools/ilspycmd -p -o "decompiled/$version" "{{sts2_dll}}"
    fi

# Extract localization + assets from PCK for current game version
extract-pck:
    #!/usr/bin/env bash
    version=$(just version)
    if [ -d "extracted/$version/localization" ]; then
        echo "Already extracted: $version"
    else
        echo "Extracting PCK for $version..."
        python scripts/extract_pck.py "{{sts2_pck}}" "extracted/$version" "localization/eng"
    fi

# Extract structured data from decompiled code + localization
extract-data: decompile extract-pck
    #!/usr/bin/env bash
    version=$(just version)
    echo "Extracting structured data for $version..."
    python scripts/extract_cards.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_relics.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_monsters.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_encounters.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_events.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_potions.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_powers.py "decompiled/$version" "extracted/$version" "data/$version"
    python scripts/extract_enchantments.py "decompiled/$version" "extracted/$version" "data/$version"

# Extract images from PCK and convert ctex to PNG
extract-images: extract-pck
    #!/usr/bin/env bash
    version=$(just version)
    python scripts/extract_images.py "{{sts2_pck}}" "extracted/$version" "site/public/images/$version"

# Full extraction for current version
extract: extract-data extract-images

# --- Diffing ---

# Diff current version against previous version
diff-versions:
    python scripts/diff_versions.py data/

# --- Claude enrichment ---

# Run Claude enrichment on changed items only
enrich:
    python scripts/enrich.py data/ enriched/

# --- Site generation ---

# Generate Astro content files from data + enrichment
generate-pages:
    python scripts/generate_pages.py data/ enriched/ site/src/content/

# Build the Astro site
build-site:
    cd site && npm run build

# --- Top-level commands ---

# Full pipeline: extract, enrich, generate, build
build: extract diff-versions generate-pages build-site

# Preview the site locally
preview:
    cd site && npm run dev

# Run the full pipeline for a new game version
update: extract diff-versions enrich generate-pages build-site
```

## Recommended Implementation Order

1. **Version detection + decompile pipeline** — detect game updates, auto-decompile
2. **Card extraction** — best understood, mostly working already
3. **Localization extraction** — PCK extraction is working
4. **Relic extraction** — moderately complex, large volume
5. **Monster + encounter extraction** — most complex due to moveset state machines
6. **Event extraction** — complex due to branching option trees
7. **Image extraction** — needs ctex converter
8. **Page generation templates** — per content type
9. **Claude enrichment pipeline** — prompts + caching
10. **Version diffing** — compare structured data across versions
11. **Static site build** — tie it all together

## Risks and Considerations

- **Early access churn**: Content changes frequently. The pipeline must be resilient to renamed/removed/added classes. Use localization keys (stable) rather than class names (may change) as primary identifiers where possible.
- **Decompiler output instability**: Different ilspycmd versions or even the same version on different code can produce subtly different output. Structured data extraction should be robust to formatting differences.
- **Legal**: This is for personal/community use. Game assets (art, text) are Mega Crit's IP. Common practice for game wikis, but worth noting.
- **Multiplayer-only content**: Some cards/relics/events are multiplayer-only (e.g., Beacon of Hope, Believe in You). Should be tagged as such.
- **Unreleased content**: The Deprived character and some locked epochs exist in the code but aren't playable. Decide whether to include or exclude these.
