"""ly's DurFile.zig: plays a durdraw .dur movie (gzipped JSON, format 7)."""

import gzip
import json
import time

import numpy as np

from ..console import TB_BOLD
from . import Animation

ECOL = {
    name: i + 1
    for i, name in enumerate(("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"))
}

TB_COLOR_16 = [ECOL[n] for n in ECOL] + [ECOL[n] | TB_BOLD for n in ECOL]

# Bold makes the bright half show on a tty.
RGB_COLOR_16 = [
    0x00000000,
    0x00800000,
    0x00008000,
    0x00808000,
    0x00000080,
    0x00800080,
    0x00008080,
    0x00C0C0C0,
    0x00000000 | TB_BOLD,
    0x00FF0000 | TB_BOLD,
    0x0000FF00 | TB_BOLD,
    0x00FFFF00 | TB_BOLD,
    0x000000FF | TB_BOLD,
    0x00FF00FF | TB_BOLD,
    0x0000FFFF | TB_BOLD,
    0x00FFFFFF | TB_BOLD,
]

# durdraw's 16-color numbering to the table above.
DURCOLOR_TO_COLOR16 = [0, 0, 4, 2, 6, 1, 5, 3, 7, 8, 12, 10, 14, 9, 13, 11, 15]


class DurError(Exception):
    pass


def _sixcube(level):
    divisions = 0xF0 // 6
    scaler = 0xFF - divisions * 5
    return level * divisions + scaler if level > 0 else 0


def convert_256_to_rgb(color):
    if color < 16:
        return RGB_COLOR_16[color]
    if color < 232:
        c = color - 16
        return (_sixcube((c // 36) % 6) << 16) | (_sixcube((c // 6) % 6) << 8) | _sixcube(c % 6)
    channel = 0x08 + ((0xEE - 0x08) // 23) * (color - 232)
    return channel | (channel << 8) | (channel << 16)


def _center(v):
    return v // 2 + v % 2


def load(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            root = json.load(f)
    except FileNotFoundError:
        raise DurError(f"not found: {path}") from None
    except (OSError, ValueError) as err:
        raise DurError(f"not a valid dur file: {path}: {err}") from None
    movie = root.get("DurMovie") if isinstance(root, dict) else None
    if not isinstance(movie, dict):
        raise DurError(f"not a valid dur file: {path}")
    meta = {
        "formatVersion": movie.get("formatVersion"),
        "colorFormat": movie.get("colorFormat"),
        "encoding": movie.get("encoding"),
        "framerate": movie.get("framerate"),
        "columns": movie.get("columns", movie.get("sizeX")),
        "lines": movie.get("lines", movie.get("sizeY")),
        "frames": movie.get("frames") or [],
    }
    valid = (
        all(v is not None for v in meta.values())
        and meta["formatVersion"] == 7
        and meta["colorFormat"] in ("16", "256")
        and meta["encoding"] == "utf-8"
        and meta["columns"] > 0
        and meta["lines"] > 0
        and meta["framerate"] >= 0
        and len(meta["frames"]) >= 1
    )
    if not valid:
        raise DurError(f"unsupported dur file: {path}")
    return meta


class DurFile(Animation):
    def __init__(self, config, width, height, rng, colors):
        super().__init__(config, width, height, rng, colors)
        self.movie = load(config.dur_file_path)
        self.full_color = config.full_color
        self.color16 = self.movie["colorFormat"] == "16"
        if not self.full_color and not self.color16:
            raise DurError("256-color dur files need full_color = true")
        self.frame_time = int(1000 / self.movie["framerate"]) if self.movie["framerate"] else 0
        self.index = 0
        self.cache = {}
        self.previous = time.monotonic()
        self.place()

    def place(self):
        w, h = self.width, self.height
        mw, mh = self.movie["columns"], self.movie["lines"]
        positions = {
            "center": (_center(w) - _center(mw), _center(h) - _center(mh)),
            "topleft": (0, 0),
            "topcenter": (_center(w) - _center(mw), 0),
            "topright": (w - mw, 0),
            "centerleft": (0, _center(h) - _center(mh)),
            "centerright": (w - mw, _center(h) - _center(mh)),
            "bottomleft": (0, h - mh),
            "bottomcenter": (_center(w) - _center(mw), h - mh),
            "bottomright": (w - mw, h - mh),
        }
        x, y = positions.get(self.config.dur_offset_alignment, positions["center"])
        self.origin = (x + self.config.dur_x_offset, y + self.config.dur_y_offset)

    def advance(self):
        frame = self.movie["frames"][self.index]
        now = time.monotonic()
        delay = int(frame.get("delay", 0) * 1000)
        if (now - self.previous) * 1000 > self.frame_time + delay:
            self.previous = now
            self.index = (self.index + 1) % len(self.movie["frames"])
            return True
        return False

    def cells(self, index):
        """One movie frame as (ys, xs, ch, fg, bg) arrays, built once."""
        cached = self.cache.get(index)
        if cached is not None:
            return cached
        frame = self.movie["frames"][index]
        contents, color_map = frame["contents"], frame["colorMap"]
        sx, sy = self.origin
        out = ([], [], [], [], [])
        for y in range(self.movie["lines"]):
            line = contents[y] if y < len(contents) else ""
            for x in range(self.movie["columns"]):
                if x >= len(line):
                    break
                cx, cy = sx + x, sy + y
                if not (0 <= cx < self.width and 0 <= cy < self.height):
                    continue
                try:
                    fg, bg = color_map[x][y][0], color_map[x][y][1]
                except (IndexError, TypeError):
                    fg = bg = -1
                fg = 0 if fg == -1 else fg
                bg = 0 if bg == -1 else bg
                if self.color16:
                    fg = DURCOLOR_TO_COLOR16[min(fg, 16)]
                    # durdraw stores the background one lower than the fg.
                    bg = DURCOLOR_TO_COLOR16[min(bg + 1, 16)]
                if self.full_color:
                    fg, bg = convert_256_to_rgb(fg), convert_256_to_rgb(bg)
                else:
                    fg, bg = TB_COLOR_16[fg & 15], TB_COLOR_16[bg & 15]
                f, b = self.colors.resolve(fg, bg)
                for lst, value in zip(out, (cy, cx, ord(line[x]), f, b), strict=True):
                    lst.append(value)
        cached = self.cache[index] = tuple(np.array(lst, dtype=np.int64) for lst in out)
        return cached

    def draw(self, buf):
        ys, xs, ch, fg, bg = self.cells(self.index)
        buf.ch[ys, xs] = ch
        buf.fg[ys, xs] = fg
        buf.bg[ys, xs] = bg
