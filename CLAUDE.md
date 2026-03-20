# STS2 Wiki

Static Astro site generated from decompiled Slay the Spire 2 game data.

## DOTNET_ROOT Fix

The `ilspycmd` tool requires `DOTNET_ROOT` to point to the dotnet libexec directory, NOT the bin directory. On macOS with Homebrew:

```bash
export DOTNET_ROOT=/opt/homebrew/Cellar/dotnet/10.0.103/libexec
```

Set this before running `just decompile` or any ilspycmd commands. The justfile's auto-detection does not reliably find the correct path.

## Commands

Scripts run as modules: `uv run python -m scripts.extract_cards` (not `python scripts/extract_cards.py`).

Justfile orchestrates everything:
- `just detect-version` — show installed game version
- `just decompile` — decompile sts2.dll with ilspycmd
- `just extract-pck` — extract localization from PCK
- `just extract` — run all extraction scripts
- `just generate` — generate site content from extracted data
- `just build-site` — build Astro site
- `just check` — run ruff + mypy (must pass before committing)

## Quality

- `just check` must pass before committing
- Don't commit `decompiled/`, `extracted/`, or scratch files
- Data files in `data/` are committed per version

<!-- claude-reliability:binary-instructions managed section - DO NOT EDIT -->
## claude-reliability Binary

The `claude-reliability` binary for this project is located at:

    .claude-reliability/bin/claude-reliability

Always use this path when running commands. Do NOT use bare `claude-reliability`,
do NOT use paths containing `~/.claude-reliability/`, and do NOT use `$PLUGIN_ROOT_DIR`
or any other variable to construct the path.

Example usage:

    .claude-reliability/bin/claude-reliability work list
    .claude-reliability/bin/claude-reliability work next
    .claude-reliability/bin/claude-reliability work on <id>
    .claude-reliability/bin/claude-reliability work update <id> --status complete
<!-- end claude-reliability:binary-instructions -->
