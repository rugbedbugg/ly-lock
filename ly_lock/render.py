"""Cells to pixels: the framebuffer console's job, done with numpy.

Each distinct (glyph, fg, bg) cell is drawn once into a tile and cached.
A frame is then a gather of tiles into the dirty rows.
"""

import numpy as np


class Renderer:
    def __init__(self, font, palette, center=True):
        self.font = font
        self.center = center
        # 0xFFRRGGBB: B, G, R, X bytes in memory on little-endian machines.
        self.colors = np.array(
            [0xFF000000 | (r << 16) | (g << 8) | b for r, g, b in palette],
            dtype=np.uint32,
        )
        # fbcon's underline cursor: the bottom 2 rows (1 for fonts under 10px).
        self.cursor_rows = 1 if font.height < 10 else 2
        self.tile_index = {}
        self.tiles = np.zeros((64, font.height, font.width), dtype=np.uint32)
        self.prev = None

    def invalidate(self):
        self.prev = None

    def tile(self, key):
        """Index of the tile for a packed (glyph, fg, bg, cursor) key."""
        i = self.tile_index.get(key)
        if i is not None:
            return i
        glyph, fg, bg, cursor = key >> 9, (key >> 5) & 15, (key >> 1) & 15, key & 1
        bits = self.font.glyphs[glyph]
        if cursor:
            # The soft cursor XORs its rows into the glyph.
            bits = bits.copy()
            bits[self.font.height - self.cursor_rows :] ^= True
        i = len(self.tile_index)
        if i == len(self.tiles):
            self.tiles = np.concatenate([self.tiles, np.zeros_like(self.tiles)])
        self.tiles[i] = np.where(bits, self.colors[fg], self.colors[bg])
        self.tile_index[key] = i
        return i

    def render(self, buf, pixels, cursor=None):
        """Draw every row of buf that changed since the last call.

        pixels is a (height, width) uint32 array at least the grid's size.
        The grid sits in its center, so the leftover pixels split evenly
        between the edges. Without center it sits in the top left like fbcon.
        cursor is the (x, y) cell showing the cursor, or None.
        Returns True if anything was drawn.
        """
        fw, fh = self.font.width, self.font.height
        rows, cols = buf.height, buf.width
        keys = (
            (self.font.glyph_indices(buf.ch).astype(np.int64) << 9)
            | (buf.fg.astype(np.int64) << 5)
            | (buf.bg.astype(np.int64) << 1)
        )
        if cursor is not None and 0 <= cursor[0] < cols and 0 <= cursor[1] < rows:
            keys[cursor[1], cursor[0]] |= 1

        if self.prev is None or self.prev.shape != keys.shape:
            dirty = np.ones(rows, dtype=bool)
        else:
            dirty = (keys != self.prev).any(axis=1)
        self.prev = keys
        y_rows = np.flatnonzero(dirty)
        if y_rows.size == 0:
            return False

        uniq, inverse = np.unique(keys[y_rows], return_inverse=True)
        lut = np.fromiter((self.tile(int(k)) for k in uniq), dtype=np.int64, count=len(uniq))
        idx = lut[inverse.reshape(len(y_rows), cols)]
        top = left = 0
        if self.center:
            h, w = pixels.shape
            top, left = (h - rows * fh) // 2, (w - cols * fw) // 2
        # (rows, fh, cols, fw) view of the grid's pixels.
        grid = pixels[top : top + rows * fh, left : left + cols * fw].reshape(rows, fh, cols, fw)
        grid[y_rows] = self.tiles[idx].transpose(0, 2, 1, 3)
        return True
