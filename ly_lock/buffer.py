"""termbox2's back buffer: a grid of cells, each a codepoint and two colors.

Colors are stored as resolved palette indices (see console.ColorModel), so
the renderer only has to look them up.
"""

import unicodedata

import numpy as np

SPACE = 0x20


def char_width(ch):
    """Cells a character takes, like termbox2's tb_wcwidth."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def str_width(text):
    """ly's TerminalBuffer.strWidth."""
    return sum(char_width(ch) for ch in text)


class Buffer:
    def __init__(self, width, height, colors):
        self.width = width
        self.height = height
        self.colors = colors
        self.default_fg, self.default_bg = colors.resolve(0, 0)
        self.ch = np.full((height, width), SPACE, dtype=np.int32)
        self.fg = np.full((height, width), self.default_fg, dtype=np.uint8)
        self.bg = np.full((height, width), self.default_bg, dtype=np.uint8)

    def clear(self):
        """tb_clear(): blank cells in the terminal's default colors."""
        self.ch.fill(SPACE)
        self.fg.fill(self.default_fg)
        self.bg.fill(self.default_bg)

    def put(self, x, y, ch, fg, bg):
        """Cell.put(): a zero codepoint leaves the cell as it is."""
        if ch == 0 or not (0 <= x < self.width and 0 <= y < self.height):
            return
        f, b = self.colors.resolve(fg, bg)
        self.ch[y, x] = ch if isinstance(ch, int) else ord(ch)
        self.fg[y, x] = f
        self.bg[y, x] = b

    def fill(self, x, y, width, height, ch, fg, bg):
        """put() the same cell over a rectangle, clipped to the buffer."""
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + width, self.width), min(y + height, self.height)
        if ch == 0 or x0 >= x1 or y0 >= y1:
            return
        f, b = self.colors.resolve(fg, bg)
        self.ch[y0:y1, x0:x1] = ch
        self.fg[y0:y1, x0:x1] = f
        self.bg[y0:y1, x0:x1] = b

    def text(self, text, x, y, fg, bg, max_length=None):
        """drawText() and, with max_length, drawConfinedText()."""
        if not 0 <= y < self.height:
            return
        f, b = self.colors.resolve(fg, bg)
        i = x
        for ch in text:
            if max_length is not None and i - x >= max_length:
                break
            if 0 <= i < self.width:
                self.ch[y, i] = ord(ch)
                self.fg[y, i] = f
                self.bg[y, i] = b
            i += char_width(ch)

    def snapshot(self):
        return self.ch.copy(), self.fg.copy(), self.bg.copy()
