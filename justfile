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

# Read current game version from release_info.json
detect-version:
    @python3 -c "import json; print(json.load(open('{{sts2_release}}'))['version'])"

# Decompile sts2.dll for the current version
decompile:
    #!/usr/bin/env bash
    if [ -d "decompiled/{{version}}" ]; then
        echo "Already decompiled: {{version}}"
    else
        echo "Decompiling {{version}}..."
        ~/.dotnet/tools/ilspycmd -p -o "decompiled/{{version}}" "{{sts2_dll}}"
    fi

# Extract localization from PCK for the current version
extract-pck:
    #!/usr/bin/env bash
    if [ -d "extracted/{{version}}/localization" ]; then
        echo "Already extracted PCK: {{version}}"
    else
        echo "Extracting PCK for {{version}}..."
        uv run python -m scripts.extract_pck "{{sts2_pck}}" "extracted/{{version}}" --prefix localization/eng
    fi

# --- Extraction pipeline (works from local decompiled/extracted dirs) ---

# Extract card data from decompiled source
extract-cards:
    uv run python -m scripts.extract_cards decompiled/{{version}} extracted/{{version}}/localization/eng data/{{version}}

# Extract all structured data
extract: extract-cards

# --- Site generation ---

# Generate Astro content from extracted data
generate-cards:
    uv run python -m scripts.generate_cards data/{{version}} site/src/content/cards

# Generate all content
generate: generate-cards

# Install site dependencies
site-install:
    cd site && npm install

# Build the Astro site
build-site:
    cd site && npm run build

# Full pipeline: extract, generate, build
build: extract generate build-site

# Preview the site locally
preview:
    cd site && npm run dev

# Full update from game files: decompile, extract PCK, extract data, generate, build
update: decompile extract-pck extract generate build-site
