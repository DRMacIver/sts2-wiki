"""Regression tests for extract_enchantments parsing bugs."""

from scripts.extract_enchantments import find_enchantment_sources_in_content, parse_enchantment_file

STRIKE_AND_DEFEND_SNIPPET = """
public sealed class Spiral : EnchantmentModel
{
	public override bool CanEnchant(CardModel card)
	{
		if (!card.HasTag(CardTag.Strike))
		{
			return card.HasTag(CardTag.Defend);
		}
		return true;
	}
}
"""

DEFEND_ONLY_SNIPPET = """
public sealed class Bulwark : EnchantmentModel
{
	public override bool CanEnchant(CardModel card)
	{
		return card.HasTag(CardTag.Defend);
	}
}
"""


def test_strike_and_defend_restriction_not_duplicated() -> None:
    """Strike+Defend enchantments must not also claim to be Defend-only."""
    result = parse_enchantment_file("Spiral", STRIKE_AND_DEFEND_SNIPPET)
    assert result is not None
    assert result["restrictions"] == ["Strike or Defend-tagged Basic cards only"]


def test_defend_only_restriction() -> None:
    result = parse_enchantment_file("Bulwark", DEFEND_ONLY_SNIPPET)
    assert result is not None
    assert result["restrictions"] == ["Defend-tagged cards only"]


TWO_ENCHANTMENT_RELIC = """
public sealed class DoubleEnchanter : RelicModel
{
	public void First(CardModel card)
	{
		EnchantmentModel obj = ModelDb.Enchantment<Sharp>();
		CardCmd.Enchant(obj, card, 2m);
	}

	public void Second(CardModel card)
	{
		EnchantmentModel other = ModelDb.Enchantment<Goopy>();
		CardCmd.Enchant(other, card, 5m);
	}
}
"""


def test_enchant_amount_attributed_to_nearby_enchantment() -> None:
    """Each generic Enchant call must bind to the enchantment declared near it."""
    sources = find_enchantment_sources_in_content(
        TWO_ENCHANTMENT_RELIC, "relic", "DoubleEnchanter", {}
    )
    amounts = {name: [s["amount"] for s in srcs] for name, srcs in sources.items()}
    assert amounts == {"Sharp": [2], "Goopy": [5]}
