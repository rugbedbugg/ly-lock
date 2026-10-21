"""ly's ColorMix.zig: the color mixing shader, evaluated for every cell."""

import numpy as np

from . import Animation

TIME_SCALE = np.float32(0.01)
PALETTE_LEN = 12


class ColorMix(Animation):
    def __init__(self, config, width, height, rng, colors):
        super().__init__(config, width, height, rng, colors)
        self.frames = 0
        self.cos_mod = np.float32(rng.random(dtype=np.float32) * np.pi * 2.0)
        self.sin_mod = np.float32(rng.random(dtype=np.float32) * np.pi * 2.0)
        c1, c2, c3 = config.colormix_col1, config.colormix_col2, config.colormix_col3
        palette = [
            (0x2588, c1, c2),
            (0x2593, c1, c2),
            (0x2592, c1, c2),
            (0x2591, c1, c2),
            (0x2588, c2, c3),
            (0x2593, c2, c3),
            (0x2592, c2, c3),
            (0x2591, c2, c3),
            (0x2588, c3, c1),
            (0x2593, c3, c1),
            (0x2592, c3, c1),
            (0x2591, c3, c1),
        ]
        resolved = [colors.resolve(fg, bg) for _, fg, bg in palette]
        self.pal_ch = np.array([ch for ch, _, _ in palette], dtype=np.int32)
        self.pal_fg = np.array([f for f, _ in resolved], dtype=np.uint8)
        self.pal_bg = np.array([b for _, b in resolved], dtype=np.uint8)

        x = np.arange(width, dtype=np.int32)[None, :]
        y = np.arange(height, dtype=np.int32)[:, None]
        self.u0 = ((x * 2 - width).astype(np.float32) / np.float32(height * 2)) + np.zeros(
            (height, 1), np.float32
        )
        self.v0 = ((y * 2 - height).astype(np.float32) / np.float32(height)) + np.zeros(
            (1, width), np.float32
        )

    def advance(self):
        self.frames += 1
        return True

    def draw(self, buf):
        f32 = np.float32
        t = f32(self.frames) * TIME_SCALE
        u, v = self.u0.copy(), self.v0.copy()
        u2 = u + v
        v2 = u2.copy()
        for _ in range(3):
            length = np.sqrt(u * u + v * v)
            u2 = u2 + u + length
            v2 = v2 + v + length
            u = u + f32(0.5) * np.cos(self.cos_mod + v2 * f32(0.2) + t * f32(0.1))
            v = v + f32(0.5) * np.sin(self.sin_mod + u2 - t * f32(0.1))
            shift = f32(1.0) * np.cos(u + v) - np.sin(u * f32(0.7) - v)
            u = u - shift
            v = v - shift
        index = (np.floor(np.sqrt(u * u + v * v) * f32(5.0)).astype(np.int64)) % PALETTE_LEN
        buf.ch[:, :] = self.pal_ch[index]
        buf.fg[:, :] = self.pal_fg[index]
        buf.bg[:, :] = self.pal_bg[index]
