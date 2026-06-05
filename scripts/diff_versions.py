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


def diff_file(old_dir: str, new_dir: str, fname: str) -> None:
    old_path = os.path.join(old_dir, fname)
    new_path = os.path.join(new_dir, fname)
    if not (os.path.exists(old_path) and os.path.exists(new_path)):
        old_exists = os.path.exists(old_path)
        new_exists = os.path.exists(new_path)
        print(f"## {fname}: MISSING in one version (old={old_exists}, new={new_exists})")
        return

    old = {key_of(e): e for e in load(old_path)}
    new = {key_of(e): e for e in load(new_path)}

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
