# STS2 Wiki build pipeline

# Default source data paths (already decompiled/extracted)
decompiled_dir := env("STS2_DECOMPILED", "~/sts-scratch/sts2-decompiled")
loc_dir := env("STS2_LOC", "~/sts-scratch/pck-extracted/localization/eng")
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

# --- Extraction pipeline ---

# Extract card data from decompiled source
extract-cards:
    uv run python -m scripts.extract_cards {{decompiled_dir}} {{loc_dir}} data/{{version}}

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
