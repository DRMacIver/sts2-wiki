"""Regression tests for extract_cards parsing bugs."""

from scripts.extract_cards import compute_upgraded_vars, parse_card_file

MAD_SCIENCE_SNIPPET = """
public sealed class MadScience : CardModel
{
	public MadScience()
		: base(1, CardType.Attack, CardRarity.Event, TargetType.AnyEnemy, shouldShowInCardLibrary: false)
	{
	}
}
"""

PLAIN_CARD_SNIPPET = """
public sealed class Strike : CardModel
{
	public Strike()
		: base(1, CardType.Attack, CardRarity.Basic, TargetType.AnyEnemy)
	{
	}
}
"""


def test_parses_constructor_with_extra_args() -> None:
    """Cards with optional args after TargetType (e.g. MadScience) must not be dropped."""
    card = parse_card_file("MadScience", MAD_SCIENCE_SNIPPET)
    assert card["energy_cost"] == 1
    assert card["type"] == "Attack"
    assert card["rarity"] == "Event"
    assert card["target"] == "AnyEnemy"


def test_parses_plain_constructor() -> None:
    card = parse_card_file("Strike", PLAIN_CARD_SNIPPET)
    assert card["energy_cost"] == 1
    assert card["rarity"] == "Basic"


def test_upgrade_amounts_accumulate() -> None:
    """Two UpgradeValueBy calls on the same var must sum, not overwrite."""
    card = {
        "vars": [{"type": "Damage", "base_value": 6}],
        "upgrades": [
            {"var": "Damage", "amount": 2},
            {"var": "Damage", "amount": 3},
        ],
    }
    result = compute_upgraded_vars(card)
    assert result == [{"type": "Damage", "base_value": 6, "upgraded_value": 11}]
