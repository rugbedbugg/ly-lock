"""ly's Doom.zig: the PSX DOOM fire.

ly walks the screen column by column, each column top to bottom. A cell
writes into the row above, up to two columns either side. Columns to the
right have not been walked yet, so fire can climb several rows in one frame.
That order is kept here. Within one column a cell only writes to rows ly has
already passed, so each column is a single vectorized update.
"""

import numpy as np

from . import Animation

STEPS = 12
HEIGHT_MAX = 9
SPREAD_MAX = 4


class Doom(Animation):
    def __init__(self, config, width, height, rng, colors):
        super().__init__(config, width, height, rng, colors)
        self.fire_height = min(HEIGHT_MAX, config.doom_fire_height)
        self.spread = min(SPREAD_MAX, config.doom_fire_spread)
        top, mid, bot, bg = (
            config.doom_top_color,
            config.doom_middle_color,
            config.doom_bottom_color,
            config.bg,
        )
        levels = [
            (0x20, bg, bg),
            (0x2591, top, bg),
            (0x2592, top, bg),
            (0x2593, top, bg),
            (0x2588, top, bg),
            (0x2591, mid, top),
            (0x2592, mid, top),
            (0x2593, mid, top),
            (0x2588, mid, top),
            (0x2591, bot, mid),
            (0x2592, bot, mid),
            (0x2593, bot, mid),
            (0x2588, bot, mid),
        ]
        resolved = [colors.resolve(fg, b) for _, fg, b in levels]
        self.level_ch = np.array([ch for ch, _, _ in levels], dtype=np.int32)
        self.level_fg = np.array([f for f, _ in resolved], dtype=np.uint8)
        self.level_bg = np.array([b for _, b in resolved], dtype=np.uint8)
        # Black everywhere except the fire source on the last row.
        self.buffer = np.zeros(width * height, dtype=np.uint8)
        self.buffer[-width:] = STEPS
        # Offsets of rows 1..height-1; adding x gives one column's cells.
        self.rows = np.arange(1, height) * width

    def advance(self):
        w, h, buf = self.width, self.height, self.buffer
        loss = (self.rng.integers(0, HEIGHT_MAX + 1, (w, h - 1)) >= self.fire_height).astype(np.uint8)
        spread = self.rng.integers(0, self.spread * 2 + 1, (w, h - 1))
        src = self.rows[None, :] + np.arange(w)[:, None]
        # (from -| width) + spread -| rand_spread
        dst = np.maximum(src - w + self.spread - spread, 0)
        for x in range(w):
            level = buf[src[x]]
            buf[dst[x]] = level - np.minimum(loss[x], level)
        return True

    def draw(self, buf):
        levels = self.buffer.reshape(self.height, self.width).copy()
        # The fire source is drawn on the last row every frame.
        levels[-1] = STEPS
        buf.ch[:, :] = self.level_ch[levels]
        buf.fg[:, :] = self.level_fg[levels]
        buf.bg[:, :] = self.level_bg[levels]
