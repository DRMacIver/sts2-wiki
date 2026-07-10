"""Shared helpers for the generate_* scripts."""

import json
import os
import re

# A new frontmatter field starts at column 0 as "key:"; continuation lines
# (e.g. a multi-line JSON array value) are folded into the previous field.
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")


def parse_override(content: str) -> tuple[dict[str, object], str]:
    """Parse an overrides/*.md file into (frontmatter fields, body).

    Frontmatter values are parsed as JSON where possible (numbers, lists,
    quoted strings — including multi-line JSON arrays) and fall back to the
    raw string. Comment lines (#...) are ignored. A file without frontmatter
    is treated as body-only.
    """
    content = content.strip()
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fields: dict[str, object] = {}
    current_key: str | None = None
    current_value: list[str] = []

    def commit() -> None:
        if current_key is None:
            return
        raw = "\n".join(current_value).strip()
        try:
            fields[current_key] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            fields[current_key] = raw

    for line in parts[1].split("\n"):
        if line.lstrip().startswith("#"):
            continue
        m = _FIELD_RE.match(line)
        if m:
            commit()
            current_key = m.group(1)
            current_value = [m.group(2)]
        elif current_key is not None:
            current_value.append(line)
    commit()

    return fields, parts[2].strip()


def load_override(data_dir: str, kind: str, slug: str) -> tuple[dict[str, object], str] | None:
    """Load overrides/<kind>/<slug>.md relative to the repo root, if present.

    data_dir is the versioned data directory (e.g. data/v0.108.0); overrides/
    sits next to data/.
    """
    overrides_dir = os.path.join(os.path.dirname(os.path.dirname(data_dir)), "overrides", kind)
    path = os.path.join(overrides_dir, f"{slug}.md")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return parse_override(f.read())
