# STS2 Wiki Audit Findings

Generated 2026-03-15. Updated after fixes.

## Status: All high-priority items resolved

### Fixed in this session
- Event options now use localization system for titles (was showing ALL_CAPS keys)
- 3 events with missing options now extracted (Amalgamator, ColorfulPhilosophers, HungryForMushrooms)
- {TemplateVar} placeholders converted to readable gold labels
- [star] BBCode rendered as star character
- Stray } from template syntax cleaned up
- cleanDescription applied to all content types (cards, relics, potions, powers, events, ancients, epochs)
- Monster portraits rendered from Spine data (100 monsters) with alias mapping
- Test/placeholder content filtered from all index pages and search
- Circlet relic (rarity: None) filtered

### Remaining low-priority items
- 26 relics and 4 potions show `?` for runtime-computed values (cannot be resolved statically)
- 51 ancient relic offering descriptions show `?` (same reason — DynamicVars resolved at runtime)
- 2 ColossalFlower options have dynamic string-concatenated keys (EXTRACT_CURRENT_PRIZE_{N})
- Fake relics occupy canonical slugs, pushing real relics to compound URLs
- 20 events have no act assignments (extracted from game data as-is)
- `[sine]`/`[jitter]` animation BBCode stripped to plain text (no CSS animation equivalent)
