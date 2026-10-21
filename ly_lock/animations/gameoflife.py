"""ly's GameOfLife.zig: Conway's Game of Life on a wrapping grid."""

import numpy as np

from . import Animation

ALIVE_CHAR = 0x2588  # █
DEAD_CHAR = 0x20


class GameOfLife(Animation):
    def __init__(self, config, width, height, rng, colors):
        super().__init__(config, width, height, rng, colors)
        self.frame_counter = 0
        self.generation = 0
        self.alive = colors.resolve(config.gameoflife_fg, config.bg)
        self.dead = colors.resolve(0, config.bg)
        self.grid = rng.random((height, width), dtype=np.float32) < np.float32(
            config.gameoflife_initial_density
        )

    def advance(self):
        self.frame_counter += 1
        if self.frame_counter < self.config.gameoflife_frame_delay:
            return False
        self.frame_counter = 0
        g = self.grid.astype(np.uint8)
        neighbors = sum(
            np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dy, dx) != (0, 0)
        )
        self.grid = (neighbors == 3) | (self.grid & (neighbors == 2))
        self.generation += 1
        interval = self.config.gameoflife_entropy_interval
        if interval > 0 and self.generation % interval == 0:
            self.add_entropy()
        return True

    def add_entropy(self):
        w, h = self.width, self.height
        for _ in range(2):
            cx = int(self.rng.integers(1, w - 1))
            cy = int(self.rng.integers(1, h - 1))
            for dy in range(3):
                for dx in range(3):
                    if self.rng.random(dtype=np.float32) < 0.4:
                        self.grid[(cy + dy) % h, (cx + dx) % w] = True

    def draw(self, buf):
        g = self.grid
        buf.ch[:, :] = np.where(g, ALIVE_CHAR, DEAD_CHAR)
        buf.fg[:, :] = np.where(g, self.alive[0], self.dead[0])
        buf.bg[:, :] = np.where(g, self.alive[1], self.dead[1])
