#!/usr/bin/env python3
"""LLM-based game data extraction using Claude Agent SDK.

Replaces regex-based extraction with an LLM agent that reads decompiled
C# source code, produces structured JSON, and reviews the generated
wiki pages for accuracy.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import anyio
from anyio import Semaphore
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)

from scripts.common import class_name_to_loc_key
from scripts.versions import latest_version

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs" / "llm_extract"

# Maps entity type to the decompiled source subdirectory
ENTITY_TYPE_DIRS: dict[str, str] = {
    "events": "MegaCrit.Sts2.Core.Models.Events",
    "monsters": "MegaCrit.Sts2.Core.Models.Monsters",
    "enchantments": "MegaCrit.Sts2.Core.Models.Enchantments",
    "potions": "MegaCrit.Sts2.Core.Models.Potions",
    "cards": "MegaCrit.Sts2.Core.Models.Cards",
    "powers": "MegaCrit.Sts2.Core.Models.Powers",
    "relics": "MegaCrit.Sts2.Core.Models.Relics",
    "encounters": "MegaCrit.Sts2.Core.Models.Encounters",
}

# Maps entity type to the localization file name
ENTITY_TYPE_LOC: dict[str, str] = {
    "events": "events",
    "monsters": "monsters",
    "enchantments": "enchantments",
    "potions": "potions",
    "cards": "cards",
    "powers": "powers",
    "relics": "relics",
    "encounters": "encounters",
}

CACHE_PATH = PROJECT_ROOT / "data" / ".llm_cache.json"
PROMPTS_DIR = PROJECT_ROOT / "scripts" / "prompts"
MODEL = "claude-haiku-4-5"


def load_cache() -> dict[str, object]:
    if not CACHE_PATH.exists():
        return {}
    result: dict[str, object] = json.loads(CACHE_PATH.read_text())

    # Migrate legacy `{entity_type}:{class_name}` keys to the new
    # `{version}:{entity_type}:{class_name}` format. Legacy entries are
    # attributed to whichever version's data/ directory actually contains
    # the per-entity JSON (the cache was originally built against v0.101.0).
    data_root = PROJECT_ROOT / "data"
    migrated: dict[str, object] = {}
    for key, value in result.items():
        if key.count(":") == 1 and isinstance(value, dict):
            entity_type, class_name = key.split(":", 1)
            for version_dir in data_root.iterdir():
                if not version_dir.is_dir():
                    continue
                if (version_dir / entity_type / f"{class_name}.json").exists():
                    migrated[f"{version_dir.name}:{entity_type}:{class_name}"] = value
                    break
        else:
            migrated[key] = value
    return migrated


def save_cache(cache: dict[str, object]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2) + "\n")


# Known-trivial rename/refactor substitutions between decompiled versions.
# When ilspycmd output changes between versions because of a non-semantic
# refactor (an interface being extracted, a utility being renamed), listing
# the pair here lets cross-version reuse treat the change as a no-op.
# Add a new entry only when you've verified every occurrence is truly
# interchangeable for data extraction purposes.
_TRIVIAL_TOKEN_RENAMES: list[tuple[str, str]] = [
    # IsAllowed(RunState) was refactored to IsAllowed(IRunState) in v0.102.x
    # without any behavior change.
    (r"\bIRunState\b", "RunState"),
]


def normalize_source(content: str) -> str:
    """Strip non-semantic differences so that byte-different decompiled
    source files can still be recognized as equivalent for extraction
    purposes. This is an over-approximation — only add transformations
    that preserve the information the LLM extracts."""
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    for pattern, replacement in _TRIVIAL_TOKEN_RENAMES:
        content = re.sub(pattern, replacement, content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


def compute_cache_key(source_content: str, loc_entries: str, prompt_content: str) -> str:
    combined = (
        normalize_source(source_content)
        + "\n---LOC---\n"
        + loc_entries
        + "\n---PROMPT---\n"
        + prompt_content
    )
    return hashlib.sha256(combined.encode()).hexdigest()


def load_localization(loc_dir: str, loc_type: str) -> dict[str, str]:
    loc_path = os.path.join(loc_dir, f"{loc_type}.json")
    if not os.path.exists(loc_path):
        return {}
    with open(loc_path) as f:
        result: dict[str, str] = json.load(f)
        return result


def get_loc_entries_for_entity(loc_data: dict[str, str], class_name: str) -> dict[str, str]:
    """Extract localization entries relevant to a specific entity."""
    key = class_name_to_loc_key(class_name)
    entries = {k: v for k, v in loc_data.items() if k.startswith(f"{key}.")}
    if not entries:
        for k, v in loc_data.items():
            if k.upper().startswith(class_name.upper() + "."):
                entries[k] = v
    return entries


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def is_event_class(content: str) -> bool:
    """Check if this .cs file defines an EventModel subclass."""
    return ": EventModel" in content and ": AncientEventModel" not in content


def is_monster_class(content: str) -> bool:
    """Check if this .cs file defines a MonsterModel subclass (direct or indirect)."""
    # Match any public class with inheritance — all files in the Monsters directory
    # are MonsterModel subclasses (some extend MonsterModel directly, others extend
    # intermediate subclasses like DecimillipedeSegment or FlailKnight).
    return bool(re.search(r"public\s+(?:sealed\s+|abstract\s+)?class\s+\w+\s*:", content))


def is_enchantment_class(content: str, class_name: str) -> bool:
    """Check if this .cs file defines a concrete EnchantmentModel subclass."""
    if "Deprecated" in class_name or "Mock" in class_name:
        return False
    if f"abstract class {class_name}" in content:
        return False
    return ": EnchantmentModel" in content


def is_potion_class(content: str) -> bool:
    """Check if this .cs file defines a PotionModel subclass."""
    return ": PotionModel" in content


def is_card_class(content: str) -> bool:
    """Check if this .cs file defines a CardModel subclass."""
    return ": CardModel" in content


def is_power_class(content: str) -> bool:
    """Check if this .cs file defines a PowerModel subclass."""
    return ": PowerModel" in content


def is_relic_class(content: str) -> bool:
    """Check if this .cs file defines a RelicModel subclass."""
    return ": RelicModel" in content


def is_encounter_class(content: str) -> bool:
    """Check if this .cs file defines an EncounterModel subclass."""
    return ": EncounterModel" in content


def get_shared_events(decompiled_dir: str) -> set[str]:
    """Find event class names in ModelDb.AllSharedEvents."""
    model_db_path = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models", "ModelDb.cs")
    shared: set[str] = set()
    if os.path.exists(model_db_path):
        with open(model_db_path) as f:
            content = f.read()
        m = re.search(
            r"AllSharedEvents.*?new\s+EventModel\[.*?\{(.*?)\}\)",
            content,
            re.DOTALL,
        )
        if m:
            for em in re.finditer(r"Event<(\w+)>\(\)", m.group(1)):
                shared.add(em.group(1))
    return shared


def get_act_names(decompiled_dir: str) -> list[str]:
    acts_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Acts")
    if not os.path.isdir(acts_dir):
        return []
    return sorted(f.removesuffix(".cs") for f in os.listdir(acts_dir) if f.endswith(".cs"))


def get_act_events(decompiled_dir: str) -> dict[str, list[str]]:
    acts_dir = os.path.join(decompiled_dir, "MegaCrit.Sts2.Core.Models.Acts")
    result: dict[str, list[str]] = {}
    if not os.path.isdir(acts_dir):
        return result
    for fname in os.listdir(acts_dir):
        if not fname.endswith(".cs"):
            continue
        act_name = fname.removesuffix(".cs")
        with open(os.path.join(acts_dir, fname)) as f:
            content = f.read()
        for m in re.finditer(r"ModelDb\.Event<(\w+)>\(\)", content):
            event_class = m.group(1)
            if event_class not in result:
                result[event_class] = []
            if act_name not in result[event_class]:
                result[event_class].append(act_name)
    return result


def _build_instructions(entity_type: str, version: str, skip_build: bool) -> str:
    """Build the Instructions section for the agent prompt."""
    if skip_build:
        return """\
## Instructions

1. Read the source file to understand the monster fully
2. Write the JSON data file using the Write tool
3. When satisfied, say "Done"

Note: Do NOT run the page generator or site build — this is batch mode."""
    return f"""\
## Instructions

1. Read the source file to understand the entity fully
2. Write the JSON data file using the Write tool
3. Run the page generator and site build using Bash:
   ```
   uv run python -m scripts.generate_{entity_type} \\
     data/{version} site/src/content/{entity_type}
   cd site && npm run build
   ```
4. Read the rendered HTML to review the page
5. Fix any problems by updating the data file or creating an override, then rebuild
6. When satisfied, say "Done"
"""


async def process_entity(
    class_name: str,
    source_path: str,
    entity_type: str,
    version: str,
    loc_entries: dict[str, str],
    prompt_content: str,
    act_info: str,
    cache: dict[str, object],
    force: bool,
    skip_build: bool = False,
    semaphore: Semaphore | None = None,
) -> None:
    """Process a single entity through the LLM agent."""
    with open(source_path) as f:
        source_content = f.read()

    cache_key = compute_cache_key(
        source_content,
        json.dumps(loc_entries, sort_keys=True),
        prompt_content,
    )

    entity_file = PROJECT_ROOT / "data" / version / entity_type / f"{class_name}.json"

    # Cache key includes version because an entity's output lives in a
    # version-specific directory. Without this, a v0.101.0 hit would cause
    # us to skip v0.100.0 processing for an identical source file and never
    # write data/v0.100.0/.../ClassName.json.
    entity_cache_key = f"{version}:{entity_type}:{class_name}"
    if not force and entity_cache_key in cache and entity_file.exists():
        cached = cache[entity_cache_key]
        if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
            print(f"  Skipping {class_name} (cached)")
            return

    # If the entity file already exists but has no cache entry (e.g. because
    # a previous run was killed before it could save the cache), trust the
    # file and populate the cache. Use --force to override.
    if not force and entity_file.exists() and entity_cache_key not in cache:
        print(f"  Backfilling cache for {class_name} (file exists)")
        cache[entity_cache_key] = {
            "cache_key": cache_key,
            "last_processed": str(Path(source_path).stat().st_mtime),
        }
        save_cache(cache)
        return

    # Cross-version reuse: if another version's decompiled source + loc for
    # this entity are byte-identical to the current version's, copy its data
    # file rather than re-running the LLM. We intentionally compare source
    # content directly (not stored cache keys) because the stored keys can
    # drift when the cache-key schema or the prompt file changes, even
    # though the underlying source has not.
    if not force and not entity_file.exists():
        src_subdir = ENTITY_TYPE_DIRS[entity_type]
        for other_version_dir in sorted((PROJECT_ROOT / "data").iterdir()):
            if not other_version_dir.is_dir() or other_version_dir.name == version:
                continue
            other_file = other_version_dir / entity_type / f"{class_name}.json"
            if not other_file.exists():
                continue
            other_src_path = (
                PROJECT_ROOT
                / "decompiled"
                / other_version_dir.name
                / src_subdir
                / f"{class_name}.cs"
            )
            if not other_src_path.exists():
                continue
            other_src = other_src_path.read_text()
            other_loc_dir = (
                PROJECT_ROOT / "extracted" / other_version_dir.name / "localization" / "eng"
            )
            other_loc_data = load_localization(str(other_loc_dir), ENTITY_TYPE_LOC[entity_type])
            other_loc_entries = get_loc_entries_for_entity(other_loc_data, class_name)
            other_cache_key = compute_cache_key(
                other_src,
                json.dumps(other_loc_entries, sort_keys=True),
                prompt_content,
            )
            if other_cache_key == cache_key:
                print(f"  Copying {class_name} from {other_version_dir.name} (identical source)")
                entity_file.parent.mkdir(parents=True, exist_ok=True)
                entity_file.write_text(other_file.read_text())
                cache[entity_cache_key] = {
                    "cache_key": cache_key,
                    "last_processed": str(Path(source_path).stat().st_mtime),
                }
                save_cache(cache)
                return

    print(f"Processing {class_name}...")

    # Build the prompt for the agent
    agent_prompt = f"""{prompt_content}

---

## Entity to Process

**Type:** {entity_type}
**Class:** {class_name}
**Version:** {version}
**Project root:** {PROJECT_ROOT}

## Source Code

The source file is at: {source_path}

## Localization Data

```json
{json.dumps(loc_entries, indent=2)}
```

## Act Assignment Info

{act_info}

## File Paths

- Per-entity data file: data/{version}/{entity_type}/{class_name}.json
- Override file (if needed): overrides/{entity_type}/{{slug}}.md
- Generated page will be at: site/src/content/{entity_type}/{{slug}}.md
- Rendered HTML will be at: site/dist/{entity_type}/{{slug}}/index.html

{_build_instructions(entity_type, version, skip_build)}"""

    # Set up transcript logging
    log_dir = LOGS_DIR / entity_type
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{class_name}.log"
    log_file = open(log_path, "w")

    def log(text: str) -> None:
        log_file.write(text + "\n")
        log_file.flush()

    log(f"=== Processing {entity_type}/{class_name} ===")
    log(f"Source: {source_path}")
    log(f"Cache key: {cache_key}")
    log("")

    async def _run_agent() -> None:
        async for message in query(
            prompt=agent_prompt,
            options=ClaudeAgentOptions(
                cwd=str(PROJECT_ROOT),
                model=MODEL,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="bypassPermissions",
                max_turns=30,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        log(f"[assistant] {block.text}")
                    elif hasattr(block, "type"):
                        log(f"[assistant tool_use] {block.type}")
            elif isinstance(message, SystemMessage):
                log(f"[system:{message.subtype}] {str(message.data)[:200]}")
            elif isinstance(message, ResultMessage):
                result_text = message.result[:500] if message.result else "(empty)"
                log(f"[result] {result_text}")
                print(f"  [{class_name}] {result_text[:200]}")

    try:
        if semaphore is not None:
            async with semaphore:
                await _run_agent()
        else:
            await _run_agent()
    except Exception as e:
        # Never cache after an agent failure: the entity file (if present) may be
        # stale data from an earlier run, and caching the new key would make it
        # look up-to-date forever.
        log(f"[error] {e}")
        print(f"  Error: [{class_name}] agent failed, not caching: {e}")
        return
    finally:
        log_file.close()

    print(f"  Transcript: {log_path.relative_to(PROJECT_ROOT)}")

    # Update cache — but only when the agent actually produced a valid entity file.
    if not entity_file.exists():
        print(f"  Error: [{class_name}] agent finished without writing {entity_file}, not caching")
        return
    try:
        json.loads(entity_file.read_text())
    except json.JSONDecodeError as e:
        print(f"  Error: [{class_name}] agent wrote invalid JSON ({e}), not caching")
        return
    cache[entity_cache_key] = {
        "cache_key": cache_key,
        "last_processed": str(Path(source_path).stat().st_mtime),
    }
    save_cache(cache)


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="LLM-based game data extraction")
    parser.add_argument("--type", required=True, choices=list(ENTITY_TYPE_DIRS.keys()))
    parser.add_argument(
        "--version",
        default=None,
        help="Game version (default: latest under data/)",
    )
    parser.add_argument("--entity", help="Process a single entity by class name")
    parser.add_argument("--force", action="store_true", help="Ignore cache")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip page generation and site build (batch mode — review separately)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of entities to process in parallel (default: 1)",
    )
    args = parser.parse_args()

    entity_type = args.type
    version = args.version or latest_version()
    decompiled_dir = str(PROJECT_ROOT / "decompiled" / version)
    loc_dir = str(PROJECT_ROOT / "extracted" / version / "localization" / "eng")

    # Load prompt
    prompt_path = PROMPTS_DIR / f"extract_{entity_type.rstrip('s')}.md"
    if not prompt_path.exists():
        print(f"Error: prompt not found at {prompt_path}")
        sys.exit(1)
    prompt_content = prompt_path.read_text()

    # Load localization
    loc_type = ENTITY_TYPE_LOC[entity_type]
    loc_data = load_localization(loc_dir, loc_type)

    # Load shared events and act assignments
    shared_events = get_shared_events(decompiled_dir)
    act_events = get_act_events(decompiled_dir)
    act_names = get_act_names(decompiled_dir)

    # Find source files
    source_dir = os.path.join(decompiled_dir, ENTITY_TYPE_DIRS[entity_type])
    if not os.path.isdir(source_dir):
        print(f"Error: source directory not found: {source_dir}")
        sys.exit(1)

    cache = load_cache()

    # Collect entities to process
    entities: list[tuple[str, str, str]] = []  # (class_name, source_path, act_info)
    for fname in sorted(os.listdir(source_dir)):
        if not fname.endswith(".cs"):
            continue
        class_name = fname.removesuffix(".cs")

        if args.entity and class_name != args.entity:
            continue

        source_path = os.path.join(source_dir, fname)
        with open(source_path) as f:
            content = f.read()

        if entity_type == "events" and not is_event_class(content):
            continue
        if entity_type == "monsters" and not is_monster_class(content):
            continue
        if entity_type == "enchantments" and not is_enchantment_class(content, class_name):
            continue
        if entity_type == "potions" and not is_potion_class(content):
            continue
        if entity_type == "cards" and not is_card_class(content):
            continue
        if entity_type == "powers" and not is_power_class(content):
            continue
        if entity_type == "relics" and not is_relic_class(content):
            continue
        if entity_type == "encounters" and not is_encounter_class(content):
            continue

        # Determine act info (events only)
        act_info = ""
        if entity_type == "events":
            if class_name in shared_events:
                all_acts = ", ".join(act_names)
                act_info = (
                    "This is a SHARED event (ModelDb.AllSharedEvents), available "
                    f"in all acts: {all_acts}. However, check IsAllowed() for "
                    "act restrictions that may limit which acts it actually appears in."
                )
            elif class_name in act_events:
                acts = act_events[class_name]
                act_info = f"This event is specific to: {', '.join(acts)}"
            else:
                act_info = "No act assignment found."

        entities.append((class_name, source_path, act_info))

    semaphore = Semaphore(args.concurrency)

    async def process_one(class_name: str, source_path: str, act_info: str) -> None:
        loc_entries = get_loc_entries_for_entity(loc_data, class_name)
        async with semaphore:
            await process_entity(
                class_name=class_name,
                source_path=source_path,
                entity_type=entity_type,
                version=version,
                loc_entries=loc_entries,
                prompt_content=prompt_content,
                act_info=act_info,
                cache=cache,
                force=args.force,
                skip_build=args.skip_build,
            )

    async with anyio.create_task_group() as tg:
        for class_name, source_path, act_info in entities:
            tg.start_soon(process_one, class_name, source_path, act_info)

    print("\nDone.")


def main() -> None:
    anyio.run(async_main)


if __name__ == "__main__":
    main()
