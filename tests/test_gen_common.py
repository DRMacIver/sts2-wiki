"""Tests for the shared override loader."""

from scripts.gen_common import parse_override

MULTILINE_OVERRIDE = """---
title: Bowlbug Swarm
monsters: [
  {"class_name": "BowlbugRock", "title": "Bowlbug (Rock)", "slug": "bowlbug-rock"},
  {"class_name": "BowlbugEgg", "title": "Bowlbug (Egg)", "slug": "bowlbug-egg"}
]
total_monsters: 3
---

## Encounter Composition

Always one Rock plus two random workers.
"""


def test_multiline_json_values() -> None:
    fields, body = parse_override(MULTILINE_OVERRIDE)
    assert fields["title"] == "Bowlbug Swarm"
    assert fields["total_monsters"] == 3
    assert isinstance(fields["monsters"], list)
    assert fields["monsters"][0]["class_name"] == "BowlbugRock"
    assert body.startswith("## Encounter Composition")


def test_comments_and_escaped_strings() -> None:
    fields, body = parse_override(
        '---\n# fix pluralization\ndescription: "Gain 1 Star.\\nForge 5."\n---\n'
    )
    assert fields["description"] == "Gain 1 Star.\nForge 5."
    assert body == ""


def test_body_only() -> None:
    fields, body = parse_override("Just some notes.")
    assert fields == {}
    assert body == "Just some notes."
