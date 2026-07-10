"""Regression tests for site-generation bugs."""

from scripts.generate_encounters import compute_total_monsters
from scripts.generate_powers import resolve_placeholders


def test_curated_total_monsters_wins() -> None:
    """Per-entity JSON total_monsters (LLM-curated) must not be recomputed away."""
    enc = {"monsters": ["Chomper"], "total_monsters": 2}
    assert compute_total_monsters(enc, test_monster_classes=set()) == 2


def test_total_monsters_falls_back_to_monster_list() -> None:
    enc = {"monsters": ["Chomper", "Axebot", "BigDummy"]}
    assert compute_total_monsters(enc, test_monster_classes={"BigDummy"}) == 2


def test_icon_placeholders_survive_resolution() -> None:
    """{singleStarIcon} etc. are rendered to <img> later; stripping them garbles text."""
    desc = "Whenever you spend or gain {singleStarIcon}, deal {Amount} damage."
    resolved = resolve_placeholders(desc)
    assert "{singleStarIcon}" in resolved
    assert "X damage" in resolved


def test_energy_icon_call_form_survives() -> None:
    desc = "At the start of your turn, gain {Amount:energyIcons()}."
    resolved = resolve_placeholders(desc)
    assert "Energy" in resolved or "energyIcons" in resolved or "{" in resolved


def test_unknown_placeholders_still_stripped() -> None:
    assert resolve_placeholders("Deal {SomeInternalVar} damage.") == "Deal  damage."
