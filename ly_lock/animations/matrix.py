"""ly's Matrix.zig, ported step for step."""

import numpy as np

from . import Animation

SPACE = 0x20
NULL = -1

FRAME_DELAY = 8
# Characters change mid-scroll
MID_SCROLL_CHANGE = True


class Matrix(Animation):
    def __init__(self, config, width, height, rng, colors):
        super().__init__(config, width, height, rng, colors)
        self.min_codepoint = config.cmatrix_min_codepoint
        self.max_codepoint = config.cmatrix_max_codepoint - config.cmatrix_min_codepoint
        self.frame = 3
        self.count = 0
        self.fg = colors.resolve(config.cmatrix_fg, config.bg)
        self.head = colors.resolve(config.cmatrix_head_col, config.bg)
        self.even = (np.arange(width) % 2 == 0)[None, :]
        self.init_buffers()

    def rand(self):
        return self.rng.getrandbits(16)

    def init_buffers(self):
        w, h = self.width, self.height
        size = w * (h + 1)
        self.value = [NULL] * size
        self.is_head = [False] * size
        self.space = [0] * w
        self.length = [0] * w
        self.update = [0] * w
        for x in range(0, w, 2):
            self.space[x] = self.rand() % h + 1
            self.length[x] = self.rand() % (h - 3) + 3
            self.update[x] = self.rand() % 3 + 1
            self.value[w + x] = SPACE

    def advance(self):
        self.count += 1
        if self.count <= FRAME_DELAY:
            return False
        self.frame += 1
        if self.frame > 4:
            self.frame = 1
        self.count = 0

        w, h = self.width, self.height
        value, is_head = self.value, self.is_head
        for x in range(0, w, 2):
            if self.frame <= self.update[x]:
                continue

            if value[x] == NULL and value[w + x] == SPACE:
                if self.space[x] > 0:
                    self.space[x] -= 1
                else:
                    r = self.rand()
                    self.length[x] = r % (h - 3) + 3
                    value[x] = r % self.max_codepoint + self.min_codepoint
                    self.space[x] = r % (h + 1)

            y = 0
            first_col = True
            while y <= h:
                i = w * y + x
                # Skip over spaces
                done = False
                while value[i] == SPACE or value[i] == NULL:
                    y += 1
                    if y > h:
                        done = True
                        break
                    i = w * y + x
                if done:
                    break

                # Find the head of this column
                tail = y
                seg_len = 0
                while value[i] != SPACE and value[i] != NULL:
                    is_head[i] = False
                    if MID_SCROLL_CHANGE:
                        r = self.rand()
                        if r % 8 == 0:
                            value[i] = r % self.max_codepoint + self.min_codepoint
                    y += 1
                    seg_len += 1
                    # Head's down offscreen
                    if y > h:
                        value[w * tail + x] = SPACE
                        done = True
                        break
                    i = w * y + x
                if done:
                    break

                r = self.rand()
                value[i] = r % self.max_codepoint + self.min_codepoint
                is_head[i] = True

                if seg_len > self.length[x] or not first_col:
                    value[w * tail + x] = SPACE
                    value[x] = NULL
                first_col = False
                y += 1
        return True

    def draw(self, buf):
        w, h = self.width, self.height
        v = np.array(self.value[w:], dtype=np.int32).reshape(h, w)
        head = np.array(self.is_head[w:], dtype=bool).reshape(h, w)
        shown = (v != NULL) & (v != SPACE) & self.even
        head &= shown
        # Every cell is written: dots on even columns, blanks everywhere else.
        buf.ch[:h, :w] = np.where(shown, v, SPACE)
        buf.fg[:h, :w] = np.where(head, self.head[0], self.fg[0])
        buf.bg[:h, :w] = np.where(head, self.head[1], self.fg[1])
