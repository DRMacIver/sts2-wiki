#!/usr/bin/env python3
"""Check all internal links in the built site for broken references.

Usage:
    uv run python -m scripts.check_links site/dist
"""

import argparse
import re
import sys
from pathlib import Path


def find_internal_urls(html: str, base_url: str, attr: str) -> list[str]:
    """Extract internal URL values of an attribute (href/src) from HTML content."""
    links: list[str] = []
    for match in re.finditer(rf'{attr}="([^"]*)"', html):
        href = match.group(1)
        # Skip external links, anchors, mailto, javascript
        if href.startswith(("http://", "https://", "mailto:", "javascript:", "#", "data:")):
            continue
        # Must start with base URL to be an internal link
        if href.startswith(base_url):
            # Strip query string and fragment for resolution
            clean = href.split("?")[0].split("#")[0]
            links.append(clean)
    return links


def resolve_link(dist_dir: Path, base_url: str, href: str) -> Path | None:
    """Resolve an internal link to a filesystem path in dist.

    Returns the expected path, or None if it can't be resolved.
    """
    # Strip base URL prefix to get the relative path
    rel = href.removeprefix(base_url)

    # Strip trailing slash
    rel = rel.rstrip("/")

    if not rel:
        # Root link -> index.html
        return dist_dir / "index.html"

    # Check for directory with index.html (e.g. /cards/prepare/ -> cards/prepare/index.html)
    candidate = dist_dir / rel / "index.html"
    if candidate.exists():
        return candidate

    # Check for direct file (e.g. /styles/global.css)
    candidate = dist_dir / rel
    if candidate.exists():
        return candidate

    # Check for .html extension
    candidate = dist_dir / f"{rel}.html"
    if candidate.exists():
        return candidate

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Check internal links in built site")
    parser.add_argument("dist_dir", help="Path to the built site (e.g. site/dist)")
    args = parser.parse_args()

    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_dir():
        print(f"Error: {dist_dir} is not a directory")
        sys.exit(1)

    # Detect base URL from the built HTML
    index = dist_dir / "index.html"
    if not index.exists():
        print(f"Error: {index} not found — is the site built?")
        sys.exit(1)

    index_html = index.read_text()
    # Extract base URL from a known pattern like href="/sts2-wiki/styles/global.css"
    base_match = re.search(r'href="(/[^"]*/)styles/global\.css"', index_html)
    if base_match:
        base_url = base_match.group(1)
    else:
        base_url = "/"
    print(f"Detected base URL: {base_url}")

    # Scan all HTML files
    html_files = sorted(dist_dir.rglob("*.html"))
    print(f"Scanning {len(html_files)} HTML files...")

    broken: list[tuple[str, str]] = []
    broken_images: dict[str, int] = {}
    checked = 0
    checked_images = 0

    for html_file in html_files:
        content = html_file.read_text()
        rel_path = html_file.relative_to(dist_dir)

        for href in find_internal_urls(content, base_url, "href"):
            checked += 1
            resolved = resolve_link(dist_dir, base_url, href)
            if resolved is None:
                broken.append((str(rel_path), href))

        # Images are non-fatal: pages intentionally hide missing images via
        # onerror for known game-data gaps, but the misses should be visible
        # in the build log rather than silently swallowed.
        for src in find_internal_urls(content, base_url, "src"):
            checked_images += 1
            if resolve_link(dist_dir, base_url, src) is None:
                broken_images[src] = broken_images.get(src, 0) + 1

    print(f"Checked {checked} internal links, {checked_images} image references")

    if broken_images:
        print(f"\nWARNING: {len(broken_images)} distinct missing image target(s):")
        for src, n in sorted(broken_images.items()):
            print(f"  {src} (referenced {n}x)")

    if broken:
        print(f"\n{len(broken)} broken link(s) found:\n")
        # Group by source file
        by_source: dict[str, list[str]] = {}
        for source, href in broken:
            by_source.setdefault(source, []).append(href)

        for source, hrefs in sorted(by_source.items()):
            print(f"  {source}:")
            for href in sorted(set(hrefs)):
                print(f"    -> {href}")
        print()
        sys.exit(1)
    else:
        print("All internal links OK")


if __name__ == "__main__":
    main()
