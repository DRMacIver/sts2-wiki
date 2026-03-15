# STS2 Wiki build pipeline

# Path to STS2 game installation
sts2_app := env("STS2_APP", "~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app")
sts2_dll := sts2_app / "Contents/Resources/data_sts2_macos_arm64/sts2.dll"
sts2_pck := sts2_app / "Contents/Resources/Slay the Spire 2.pck"
sts2_release := sts2_app / "Contents/Resources/release_info.json"

# Game version (auto-detected or override)
version := env("STS2_VERSION", "v0.98.2")

# Default: full build
default: check build

# --- Sanity checks ---

check: check-format check-types

check-format:
    uv run ruff check scripts/
    uv run ruff format --check scripts/

check-types:
    uv run mypy scripts/

format:
    uv run ruff format scripts/
    uv run ruff check --fix scripts/

# --- Decompile + extract from game ---

detect-version:
    @python3 -c "import json; print(json.load(open('{{sts2_release}}'))['version'])"

decompile:
    #!/usr/bin/env bash
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

extract: extract-powers extract-epochs extract-cards extract-monsters extract-encounters extract-potions extract-relics extract-ancients extract-events

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

generate: generate-cards generate-powers generate-monsters generate-encounters generate-potions generate-relics generate-ancients generate-events generate-epochs

site-install:
    cd site && npm install

build-site:
    cd site && npm run build

# Full pipeline: extract, generate, build
build: extract generate build-site

preview:
    cd site && npm run dev

# Full update from game files
update: decompile extract-pck extract generate build-site
