import struct

import numpy as np
import pytest
from helpers import make_buffer

from ly_lock.console import Font
from ly_lock.render import Renderer

BLACK, WHITE = 0xFF000000, 0xFFFFFFFF
PALETTE = [(0, 0, 0), (255, 255, 255)] + [(0, 0, 0)] * 14


@pytest.fixture
def block_font(tmp_path):
    """An 8x16 font whose only glyph is a solid block."""
    header = struct.pack("<8I", 0x864AB572, 0, 32, 1, 1, 16, 16, 8)
    path = tmp_path / "block.psfu"
    path.write_bytes(header + b"\xff" * 16 + b"A" + b"\xff")
    return Font(str(path))


def lit(block_font, center):
    """Bounds of the lit pixels after drawing a 2x2 grid of blocks on 20x40."""
    buf = make_buffer(2, 2)
    buf.ch[:] = ord("A")
    buf.fg[:], buf.bg[:] = 1, 0
    pixels = np.full((40, 20), BLACK, dtype=np.uint32)
    Renderer(block_font, PALETTE, center).render(buf, pixels)
    ys, xs = np.nonzero(pixels == WHITE)
    return ys.min(), ys.max(), xs.min(), xs.max()


def test_grid_is_centered(block_font):
    # 4 pixels spare across and 8 down.
    assert lit(block_font, True) == (4, 35, 2, 17)


def test_grid_pinned_top_left(block_font):
    assert lit(block_font, False) == (0, 31, 0, 15)
