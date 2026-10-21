import gzip
import json
import random

import numpy as np
from helpers import make_buffer

from ly_lock.animations import create
from ly_lock.config import Config
from ly_lock.console import ColorModel

W, H = 48, 20


def build(name, **values):
    config = Config({"animation": name, **values})
    colors = ColorModel(True)
    anim = create(config, W, H, random.Random(1), np.random.default_rng(1), colors, print)
    assert anim is not None
    return anim


def run(anim, steps=200):
    buf = make_buffer(W, H)
    for _ in range(steps):
        anim.step()
    buf.clear()
    anim.paint(buf)
    return buf


def test_matrix_uses_even_columns_and_ascii():
    buf = run(build("matrix"), 400)
    shown = buf.ch != 0x20
    assert shown.any()
    assert not shown[:, 1::2].any()
    assert ((buf.ch[shown] >= 0x21) & (buf.ch[shown] < 0x7B)).all()
    assert set(np.unique(buf.fg[shown])) <= {10, 15}


def test_matrix_is_deterministic():
    a, b = run(build("matrix"), 300), run(build("matrix"), 300)
    assert (a.ch == b.ch).all()


def test_doom_has_a_fire_source():
    buf = run(build("doom"), 50)
    assert (buf.ch[-1] == 0x2588).all()
    assert (buf.ch[-3] != 0x20).any()


def test_colormix_fills_the_screen():
    buf = run(build("colormix"), 10)
    assert set(np.unique(buf.ch)) <= {0x2588, 0x2593, 0x2592, 0x2591}


def test_gameoflife_blinker():
    anim = build("gameoflife", gameoflife_frame_delay=1, gameoflife_entropy_interval=0)
    anim.grid[:] = False
    anim.grid[5, 4:7] = True
    anim.step()
    assert anim.grid[4:7, 5].all() and anim.grid.sum() == 3
    anim.step()
    assert anim.grid[5, 4:7].all() and anim.grid.sum() == 3


def test_timeout_stops_drawing():
    anim = build("matrix", animation_timeout_sec=1)
    anim.start -= 5
    assert anim.step() is True
    assert anim.animate is False
    assert (run(anim, 1).ch == 0x20).all()


def test_dur_file(tmp_path):
    movie = {
        "DurMovie": {
            "formatVersion": 7,
            "colorFormat": "256",
            "encoding": "utf-8",
            "framerate": 10.0,
            "columns": 3,
            "lines": 2,
            "frames": [
                {
                    "frameNumber": 1,
                    "delay": 0,
                    "contents": ["abc", "def"],
                    "colorMap": [[[1, 0], [2, 0]], [[9, 0], [10, 0]], [[15, 0], [196, 0]]],
                }
            ],
        }
    }
    path = tmp_path / "x.dur"
    with gzip.open(path, "wt") as f:
        json.dump(movie, f)
    buf = run(build("dur_file", dur_file_path=str(path)), 1)
    y0, x0 = H // 2 - 1, W // 2 - 2
    assert "".join(chr(c) for c in buf.ch[y0, x0 : x0 + 3]) == "abc"


def test_missing_dur_file_means_no_animation():
    config = Config({"animation": "dur_file", "dur_file_path": "/nonexistent.dur"})
    assert (
        create(config, W, H, random.Random(1), np.random.default_rng(1), ColorModel(True), lambda m: None)
        is None
    )
