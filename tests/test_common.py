"""Regression tests for shared rich-text and localization-key helpers."""

from scripts.common import class_name_to_loc_key, rich_text_to_html, strip_rich_text


def test_loc_key_single_letter_words() -> None:
    assert class_name_to_loc_key("IAmInvincible") == "I_AM_INVINCIBLE"
    assert class_name_to_loc_key("ExpectAFight") == "EXPECT_A_FIGHT"


def test_loc_key_basic() -> None:
    assert class_name_to_loc_key("SwordBoomerang") == "SWORD_BOOMERANG"


def test_unknown_tags_do_not_leak_into_html() -> None:
    html = rich_text_to_html("[rainbow freq=0.3]wow[/rainbow] [font_size=28]big[/font_size]")
    assert "[rainbow" not in html
    assert "[font_size" not in html
    assert "wow" in html
    assert "big" in html


def test_color_span_across_newline() -> None:
    html = rich_text_to_html("[gold]two\nlines[/gold]")
    assert "[gold]" not in html
    assert '<span class="desc-gold">' in html


def test_lb_rb_render_as_literal_brackets() -> None:
    assert strip_rich_text("[lb]note[rb]") == "[note]"
    html = rich_text_to_html("[lb]note[rb]")
    assert "[note]" in html


def test_prose_brackets_are_preserved() -> None:
    """LLM-written event text like "[your top relic]" is prose, not markup."""
    assert "[your top relic]" in rich_text_to_html("Trade [your top relic] away.")
    assert "[your top relic]" in strip_rich_text("Trade [your top relic] away.")


def test_known_color_tags_still_work() -> None:
    assert rich_text_to_html("[gold]hi[/gold]") == '<span class="desc-gold">hi</span>'
    assert strip_rich_text("[gold]hi[/gold]") == "hi"
