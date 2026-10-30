import types

from ly_lock.buffer import Buffer, str_width
from ly_lock.config import LANG_DEFAULTS, Config
from ly_lock.console import ColorModel
from ly_lock.sessions import Session
from ly_lock.ui import Password


def make_state(**overrides):
    config = Config(overrides)
    lang = dict(LANG_DEFAULTS)
    labels_max = max(
        str_width(lang[k]) for k in ("login", "password", "wayland", "x11", "shell", "xinitrc", "custom")
    )
    box_w = 2 * config.margin_box_h + config.input_len + 1 + labels_max
    field_w = box_w - 2 * config.margin_box_h - labels_max - 1
    return types.SimpleNamespace(
        config=config,
        lang=lang,
        user="alice",
        session=Session("Hyprland (uwsm-managed)", lang["wayland"]),
        version="0.2.1",
        tty="1",
        labels_max_length=labels_max,
        password=Password(field_w, config.asterisk),
        insert_mode=True,
        messages=[("host", config.fg, config.bg)],
        bind_labels=[],
        info_labels=[],
        battery=None,
        animating=False,
        lock_keys=lambda: (False, False),
    )


def make_buffer(width, height, full_color=True):
    return Buffer(width, height, ColorModel(full_color))


def row_text(buf, y):
    return "".join(chr(c) for c in buf.ch[y])
