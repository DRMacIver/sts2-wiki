# STS2 Wiki build pipeline

# Path to STS2 game installation
sts2_app := env("STS2_APP", env("HOME") / "Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app")
sts2_dll := sts2_app / "Contents/Resources/data_sts2_macos_arm64/sts2.dll"
sts2_pck := sts2_app / "Contents/Resources/Slay the Spire 2.pck"
sts2_release := sts2_app / "Contents/Resources/release_info.json"

# Game version (auto-detected or override)
version := env("STS2_VERSION", "v0.100.0")

# Default: full build
default: check build

# --- Sanity checks ---

check: check-format check-types check-links check-images

check-format:
    uv run ruff check scripts/
    uv run ruff format --check scripts/

check-types:
    uv run mypy scripts/

check-links:
    uv run python -m scripts.check_links site/dist

check-images:
    uv run python -m scripts.check_images data/{{version}} site/public/images

format:
    uv run ruff format scripts/
    uv run ruff check --fix scripts/

# --- Decompile + extract from game ---

detect-version:
    @python3 -c "import json; print(json.load(open('{{sts2_release}}'))['version'])"

decompile:
    #!/usr/bin/env bash
    export DOTNET_ROOT="${DOTNET_ROOT:-$(dirname $(dirname $(readlink -f $(which dotnet) 2>/dev/null || echo /opt/homebrew/Cellar/dotnet/10.0.103/libexec/dotnet)))}"
    if [ -d "decompiled/{{version}}" ]; then
        echo "Already decompiled: {{version}}"
    else
        echo "Decompiling {{version}}..."
        ~/.dotnet/tools/ilspycmd -p -o "decompiled/{{version}}" "{{sts2_dll}}"
    fi

extract-pck:
    #!/usr/bin/env bash
    if [ -d "extracted/{{version}}/localization" ]; then
        echo "Already extracted PCK: {{version}}"
    else
        echo "Extracting PCK for {{version}}..."
        uv run python -m scripts.extract_pck "{{sts2_pck}}" "extracted/{{version}}" --prefix localization/eng
        uv run python -m scripts.extract_pck "{{sts2_pck}}" "extracted/{{version}}" --prefix images/atlases
    fi

# --- Extraction pipeline ---

extract-cards:
    uv run python -m scripts.extract_cards decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-powers:
    uv run python -m scripts.extract_powers decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-monsters:
    uv run python -m scripts.extract_monsters decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-encounters:
    uv run python -m scripts.extract_encounters decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-ancients:
    uv run python -m scripts.extract_ancients decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-images:
    uv run python scripts/extract_images.py "{{sts2_pck}}" extracted/{{version}} site/public/images

extract-potions:
    uv run python -m scripts.extract_potions decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-relics:
    uv run python -m scripts.extract_relics decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-epochs:
    uv run python -m scripts.extract_epochs decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-events:
    uv run python -m scripts.extract_events decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-characters:
    uv run python -m scripts.extract_characters decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract-enchantments:
    uv run python -m scripts.extract_enchantments decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

extract: extract-powers extract-cards extract-monsters extract-encounters extract-potions extract-relics extract-ancients extract-events extract-enchantments extract-characters extract-epochs

# --- Site generation ---

generate-cards:
    uv run python -m scripts.generate_cards data/{{version}} site/src/content/cards

generate-powers:
    uv run python -m scripts.generate_powers data/{{version}} site/src/content/powers

generate-monsters:
    uv run python -m scripts.generate_monsters data/{{version}} site/src/content/monsters

generate-encounters:
    uv run python -m scripts.generate_encounters data/{{version}} site/src/content/encounters

generate-ancients:
    uv run python -m scripts.generate_ancients data/{{version}} site/src/content/ancients

generate-potions:
    uv run python -m scripts.generate_potions data/{{version}} site/src/content/potions

generate-relics:
    uv run python -m scripts.generate_relics data/{{version}} site/src/content/relics

generate-events:
    uv run python -m scripts.generate_events data/{{version}} site/src/content/events

generate-epochs:
    uv run python -m scripts.generate_epochs data/{{version}} site/src/content/epochs

generate-characters:
    uv run python -m scripts.generate_characters data/{{version}} site/src/content/characters

generate-ascensions:
    uv run python -m scripts.generate_ascensions extracted/{{version}}/localization/eng site/src/content/ascensions --decompiled-dir decompiled/{{version}} --data-dir data/{{version}}

# Generate from committed data only (safe for CI — no decompiled/extracted dirs needed)
generate-enchantments:
    uv run python -m scripts.generate_enchantments data/{{version}} site/src/content/enchantments

generate-from-data: generate-cards generate-powers generate-monsters generate-encounters generate-potions generate-relics generate-ancients generate-events generate-epochs generate-characters generate-enchantments

# Full generate including ascensions (requires extracted/ and decompiled/ dirs)
generate: generate-from-data generate-ascensions

site-install:
    cd site && npm install

build-site:
    cd site && npm run build

# Full pipeline: extract, generate, build
build: extract generate build-site

preview:
    cd site && npm run dev

# Build all versions into a merged dist-final directory
build-all-versions:
    #!/usr/bin/env bash
    set -euo pipefail

    VERSIONS="v0.98.2 v0.99.1 v0.100.0"
    LATEST="v0.100.0"
    ALL_VERSIONS="v0.100.0,v0.99.1,v0.98.2"
    DIST_FINAL="site/dist-final"

    rm -rf "$DIST_FINAL"
    mkdir -p "$DIST_FINAL"

    for ver in $VERSIONS; do
        echo "=== Building $ver ==="

        # Generate content for this version
        STS2_VERSION="$ver" just generate-from-data

        # Set base URL and version env vars
        export PUBLIC_STS2_VERSION="$ver"
        export PUBLIC_STS2_ALL_VERSIONS="$ALL_VERSIONS"
        export PUBLIC_STS2_LATEST="$LATEST"

        if [ "$ver" = "$LATEST" ]; then
            export ASTRO_BASE="/sts2-wiki/"
        else
            export ASTRO_BASE="/sts2-wiki/$ver/"
        fi

        # Build the Astro site
        cd site && npm run build && cd ..

        # Check internal links (only for latest — older versions have expected broken links
        # to content added in later versions)
        if [ "$ver" = "$LATEST" ]; then
            uv run python -m scripts.check_links site/dist
        fi

        # Copy output to final directory
        if [ "$ver" = "$LATEST" ]; then
            cp -r site/dist/* "$DIST_FINAL/"
        else
            mkdir -p "$DIST_FINAL/$ver"
            cp -r site/dist/* "$DIST_FINAL/$ver/"
        fi

        echo "=== Done $ver ==="
    done

    echo "All versions built into $DIST_FINAL"

# Full update from game files
update: decompile extract-pck extract extract-images generate build-site
