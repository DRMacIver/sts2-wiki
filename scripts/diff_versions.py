#!/usr/bin/env python3
"""Diff two versions of extracted STS2 data, field by field, keyed by class_name."""

import argparse
import json
import os


def load(path: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        # some files may be dicts keyed by name
        return list(data.values())
    return list(data)


def key_of(entry: dict) -> str:
    return (
        entry.get("class_name")
        or entry.get("name")
        or entry.get("title")
        or json.dumps(entry, sort_keys=True)
    )


def load_entity_dir(path: str) -> list[dict]:
    """Load all per-entity JSON files in a directory as a list of entities."""
    entities = []
    for fname in sorted(os.listdir(path)):
        if fname.endswith(".json"):
            with open(os.path.join(path, fname)) as f:
                entities.append(json.load(f))
    return entities


def load_kind(version_dir: str, fname: str) -> list[dict] | None:
    """Load one entity kind: the aggregate file, with per-entity JSON merged over
    it (per-entity data is what the generators actually render for most fields).

    Events have no aggregate file and exist only per-entity.
    """
    agg_path = os.path.join(version_dir, fname)
    entity_dir = os.path.join(version_dir, fname.removesuffix(".json"))

    by_key: dict[str, dict] = {}
    if os.path.exists(agg_path):
        by_key = {key_of(e): e for e in load(agg_path)}
    if os.path.isdir(entity_dir):
        for entity in load_entity_dir(entity_dir):
            key = key_of(entity)
            if key in by_key:
                by_key[key] = {**by_key[key], **entity}
            else:
                by_key[key] = entity
    if not by_key:
        return None
    return list(by_key.values())


def diff_file(old_dir: str, new_dir: str, fname: str) -> None:
    old_entities = load_kind(old_dir, fname)
    new_entities = load_kind(new_dir, fname)
    if old_entities is None or new_entities is None:
        print(
            f"## {fname}: MISSING in one version "
            f"(old={old_entities is not None}, new={new_entities is not None})"
        )
        return

    old = {key_of(e): e for e in old_entities}
    new = {key_of(e): e for e in new_entities}

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []

    # Fields too noisy to report directly
    skip_fields = {"description_html", "upgraded_description_html"}

    for k in sorted(set(old) & set(new)):
        o, n = old[k], new[k]
        field_changes = []
        for field in sorted(set(o) | set(n)):
            if field in skip_fields:
                continue
            ov, nv = o.get(field), n.get(field)
            if ov != nv:
                field_changes.append((field, ov, nv))
        if field_changes:
            changed.append((k, field_changes))

    if not (added or removed or changed):
        print(f"## {fname}: no changes")
        return

    print(f"## {fname}")
    if added:
        print(f"  ADDED ({len(added)}): {', '.join(added)}")
    if removed:
        print(f"  REMOVED ({len(removed)}): {', '.join(removed)}")
    for k, fcs in changed:
        print(f"  CHANGED {k}:")
        for field, ov, nv in fcs:
            so = json.dumps(ov, ensure_ascii=False)
            sn = json.dumps(nv, ensure_ascii=False)
            if len(so) > 200:
                so = so[:200] + "…"
            if len(sn) > 200:
                sn = sn[:200] + "…"
            print(f"      {field}: {so}  ->  {sn}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("old_dir")
    parser.add_argument("new_dir")
    args = parser.parse_args()

    files = [
        "cards.json",
        "monsters.json",
        "relics.json",
        "potions.json",
        "powers.json",
        "encounters.json",
        "events.json",
        "enchantments.json",
        "characters.json",
        "epochs.json",
        "ancients.json",
        "acts.json",
    ]
    for fname in files:
        diff_file(args.old_dir, args.new_dir, fname)


if __name__ == "__main__":
    main()
