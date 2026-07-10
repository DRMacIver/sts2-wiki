"""Regression tests for extract_images helpers."""

from PIL import Image

from scripts.extract_images import find_ctex_path, save_if_changed


def _img(pixels: list[tuple[int, int, int, int]], size: tuple[int, int] = (2, 1)) -> Image.Image:
    img = Image.new("RGBA", size)
    img.putdata(pixels)
    return img


def test_save_skipped_when_only_invisible_pixels_differ(tmp_path) -> None:
    """RGB garbage under alpha=0 (BC7 decode noise) must not count as a change."""
    existing = _img([(255, 0, 0, 255), (12, 34, 56, 0)])
    out = tmp_path / "sprite.png"
    existing.save(out, "PNG")

    candidate = _img([(255, 0, 0, 255), (99, 88, 77, 0)])
    assert save_if_changed(candidate, str(out)) is False


def test_save_happens_on_visible_change(tmp_path) -> None:
    existing = _img([(255, 0, 0, 255), (0, 0, 0, 0)])
    out = tmp_path / "sprite.png"
    existing.save(out, "PNG")

    candidate = _img([(0, 255, 0, 255), (0, 0, 0, 0)])
    assert save_if_changed(candidate, str(out)) is True
    assert Image.open(out).convert("RGBA").getpixel((0, 0)) == (0, 255, 0, 255)


def test_save_happens_when_missing(tmp_path) -> None:
    out = tmp_path / "sprite.png"
    assert save_if_changed(_img([(1, 2, 3, 255), (0, 0, 0, 0)]), str(out)) is True
    assert out.exists()


def test_find_ctex_path_exact_texture_match() -> None:
    """card_atlas_1 must not match a card_atlas_10 path."""
    pck_index = {
        ".godot/imported/card_atlas_10.png-aaaa.bptc.ctex": (0, 0),
        ".godot/imported/card_atlas_1.png-bbbb.bptc.ctex": (0, 0),
    }
    assert find_ctex_path(pck_index, "card_atlas_1") == (
        ".godot/imported/card_atlas_1.png-bbbb.bptc.ctex"
    )
    assert find_ctex_path(pck_index, "card_atlas_10") == (
        ".godot/imported/card_atlas_10.png-aaaa.bptc.ctex"
    )
    assert find_ctex_path(pck_index, "card_atlas_2") is None
