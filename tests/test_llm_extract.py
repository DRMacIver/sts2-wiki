"""Regression tests for llm_extract helpers."""

from scripts.llm_extract import get_loc_entries_for_entity


def test_loc_entries_for_single_letter_word_class() -> None:
    """IAmInvincible's loc entries live under I_AM_INVINCIBLE, not IAM_INVINCIBLE."""
    loc = {
        "I_AM_INVINCIBLE.title": "I Am Invincible",
        "I_AM_INVINCIBLE.description": "desc",
        "OTHER.title": "x",
    }
    entries = get_loc_entries_for_entity(loc, "IAmInvincible")
    assert entries == {
        "I_AM_INVINCIBLE.title": "I Am Invincible",
        "I_AM_INVINCIBLE.description": "desc",
    }


def test_loc_entries_basic() -> None:
    loc = {"SWORD_BOOMERANG.title": "Sword Boomerang"}
    assert get_loc_entries_for_entity(loc, "SwordBoomerang") == loc
