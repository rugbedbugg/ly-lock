import os
import struct

import numpy as np
import pytest

from ly_lock.console import TB_BOLD, TB_BRIGHT, TB_HI_BLACK, TB_REVERSE, ColorModel, Font, find_font

WHITE, GREEN, RED = 0x00FFFFFF, 0x0000FF00, 0x00FF0000


@pytest.fixture
def tc():
    return ColorModel(full_color=True)


def test_truecolor_maps_like_the_console(tc):
    assert tc.resolve(WHITE, 0) == (15, 0)
    assert tc.resolve(GREEN, 0) == (10, 0)
    assert tc.resolve(RED | TB_BOLD, 0) == (9, 0)
    assert tc.resolve(0x00800000, 0) == (1, 0)
    assert tc.resolve(0x00404040, 0) == (8, 0)


def test_default_colors(tc):
    assert tc.resolve(0, 0) == (7, 0)
    assert tc.resolve(TB_BOLD, 0) == (15, 0)


def test_hi_black(tc):
    assert tc.resolve(TB_HI_BLACK, 0) == (0, 0)
    assert tc.resolve(WHITE, TB_HI_BLACK) == (15, 0)


def test_background_errs_dark(tc):
    assert tc.resolve(0, RED) == (7, 1)
    assert tc.resolve(0, 0x00700000) == (7, 0)


def test_reverse(tc):
    assert tc.resolve(WHITE | TB_REVERSE, 0) == (8, 7)


def test_eight_color_mode():
    m = ColorModel(full_color=False)
    assert m.resolve(3, 0) == (2, 0)
    assert m.resolve(3 | TB_BOLD, 0) == (10, 0)
    assert m.resolve(3 | TB_BRIGHT, 2) == (10, 1)


def psf2(glyphs, table):
    header = struct.pack("<8I", 0x864AB572, 0, 32, 1, len(glyphs), 16, 16, 8)
    data = header + b"".join(glyphs)
    for cps in table:
        data += "".join(cps).encode() + b"\xff"
    return data


def test_psf2_font(tmp_path):
    a = bytes([0xFF] + [0] * 15)
    q = bytes([0x81] * 16)
    path = tmp_path / "f.psfu"
    path.write_bytes(psf2([a, q], [["A", "─"], ["?"]]))
    font = Font(str(path))
    assert (font.width, font.height) == (8, 16)
    idx = font.glyph_indices(np.array([ord("A"), 0x2500, ord("z"), 0x1F600]))
    assert list(idx) == [0, 0, 1, 1]
    assert font.glyphs[0][0].all() and not font.glyphs[0][1].any()
    assert font.glyphs[1][0][0] and font.glyphs[1][0][7] and not font.glyphs[1][0][3]


def test_system_font_has_box_glyphs():
    try:
        path = find_font("default8x16")
    except FileNotFoundError:
        pytest.skip("no console fonts installed")
    font = Font(path)
    for cp in (0x250C, 0x2500, 0x2502, 0x2588, 0x2593):
        assert font.lut[cp] != font.fallback


def test_font_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LY_LOCK_FONT", str(tmp_path / "x.psf"))
    assert find_font() == str(tmp_path / "x.psf")
    monkeypatch.delenv("LY_LOCK_FONT")
    assert os.path.isabs(find_font("/abs/font.psf"))
