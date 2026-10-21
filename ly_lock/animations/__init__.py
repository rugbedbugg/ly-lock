"""ly's background animations (src/animations).

Each one splits ly's draw() in two: step() advances the state exactly as one
draw() call would, and paint() writes the current state into a buffer. ly
calls draw() every animation_frame_delay ms. ly-lock calls step() on the same
schedule and paints only when the screen is about to be redrawn.
"""

import time


class Animation:
    def __init__(self, config, width, height, rng, colors):
        self.config = config
        self.width = width
        self.height = height
        self.rng = rng
        self.colors = colors
        self.start = time.monotonic()
        self.animate = True

    @property
    def frame_delay(self):
        return self.config.animation_frame_delay

    def step(self):
        """One draw() worth of state change. Returns True if the picture changed."""
        timeout = self.config.animation_timeout_sec
        if timeout > 0 and time.monotonic() - self.start > timeout:
            # ly stops drawing the animation, leaving the cleared screen.
            changed = self.animate
            self.animate = False
            return changed
        return self.advance()

    def advance(self):
        raise NotImplementedError

    def paint(self, buf):
        if self.animate:
            self.draw(buf)

    def draw(self, buf):
        raise NotImplementedError


def create(config, width, height, rng, np_rng, colors, log):
    """The animation ly's config asks for, or None."""
    name = config.animation
    if name == "matrix":
        from .matrix import Matrix

        return Matrix(config, width, height, rng, colors)
    if name == "doom":
        from .doom import Doom

        return Doom(config, width, height, np_rng, colors)
    if name == "colormix":
        from .colormix import ColorMix

        return ColorMix(config, width, height, np_rng, colors)
    if name == "gameoflife":
        from .gameoflife import GameOfLife

        return GameOfLife(config, width, height, np_rng, colors)
    if name == "dur_file":
        from .durfile import DurError, DurFile

        try:
            return DurFile(config, width, height, np_rng, colors)
        except DurError as err:
            log(f"dur_file: {err}")
            return None
    if name != "none":
        log(f"unknown animation {name!r}")
    return None
