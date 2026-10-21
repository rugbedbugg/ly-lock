"""Render the README screenshots without a display.

usage: python tools/screenshots.py OUT_DIR [DUR_FILE]

Draws one 1920x1080 frame per background with ly-lock's own CPU renderer,
which produces the same pixels as the GPU one. Each animation runs for a
fixed number of steps from a fixed seed, so the images only change when the
drawing code does. DUR_FILE is a .dur movie for the dur_file shot, such as
res/example.dur from ly's source.
"""

import random
import sys
import time
import types
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ly_lock import __version__, animations
from ly_lock.buffer import Buffer, str_width
from ly_lock.config import LANG_DEFAULTS, Config
from ly_lock.console import ColorModel, Font, find_font, read_palette
from ly_lock.render import Renderer
from ly_lock.sessions import Session
from ly_lock.ui import Password, Screen

WIDTH, HEIGHT = 1920, 1080
# A fixed moment, so the clocks read the same on every run.
NOW = time.mktime((2026, 10, 21, 21, 40, 0, 0, 0, -1))

# name, extra config, animation steps
SHOTS = [
    ("matrix", {"animation": "matrix"}, 2500),
    ("doom", {"animation": "doom"}, 120),
    ("colormix", {"animation": "colormix"}, 400),
    ("gameoflife", {"animation": "gameoflife"}, 300),
    ("dur_file", {"animation": "dur_file"}, 1),
    ("none", {"animation": "none", "bigclock": "en"}, 0),
]


def state_for(config):
    lang = dict(LANG_DEFAULTS)
    labels = max(
        str_width(lang[k]) for k in ("login", "password", "wayland", "x11", "shell", "xinitrc", "custom")
    )
    box_w = 2 * config.margin_box_h + config.input_len + 1 + labels
    password = Password(box_w - 2 * config.margin_box_h - labels - 1, config.asterisk)
    for ch in "hunter2":
        password.write(ch)
    return types.SimpleNamespace(
        config=config,
        lang=lang,
        user="user",
        session=Session("Hyprland", lang["wayland"]),
        version=__version__,
        tty="1",
        labels_max_length=labels,
        password=password,
        insert_mode=True,
        messages=[("ly-lock", config.fg, config.bg)],
        bind_labels=[],
        info_labels=[],
        battery=None,
        animating=config.animation != "none",
        lock_keys=lambda: (False, False),
    )


def write_png(path, pixels):
    """pixels: (h, w) uint32 0xFFRRGGBB."""
    h, w = pixels.shape
    rgb = np.empty((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = (pixels >> 16) & 0xFF
    rgb[..., 1] = (pixels >> 8) & 0xFF
    rgb[..., 2] = pixels & 0xFF
    raw = b"".join(b"\x00" + row.tobytes() for row in rgb)

    def chunk(kind, data):
        body = kind + data
        return len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")

    header = w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", header))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def main():
    out = Path(sys.argv[1])
    dur = sys.argv[2] if len(sys.argv) > 2 else None
    out.mkdir(parents=True, exist_ok=True)
    font = Font(find_font("default8x16"))
    palette = read_palette()
    cols, rows = WIDTH // font.width, HEIGHT // font.height
    for name, extra, steps in SHOTS:
        if name == "dur_file" and dur is None:
            print("skipping dur_file: no DUR_FILE given")
            continue
        values = {"clock": "%a %d %b  %H:%M", **extra}
        if dur:
            values["dur_file_path"] = dur
        config = Config(values)
        colors = ColorModel(config.full_color)
        buf = Buffer(cols, rows, colors)
        anim = animations.create(
            config, cols, rows, random.Random(7), np.random.default_rng(7), colors, print
        )
        for _ in range(steps):
            anim.step()
        buf.clear()
        if anim is not None:
            anim.paint(buf)
        cursor = Screen(state_for(config)).draw(buf, now=NOW)
        pixels = np.full((HEIGHT, WIDTH), 0xFF000000, dtype=np.uint32)
        Renderer(font, palette).render(buf, pixels, cursor)
        write_png(out / f"{name}.png", pixels)
        print(f"wrote {out / name}.png")


if __name__ == "__main__":
    main()
