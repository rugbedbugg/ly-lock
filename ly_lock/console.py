"""The Linux console as ly sees it: its font, its palette and its colors.

ly always runs on a virtual terminal, so its colors go through the kernel's
console driver before they reach the screen. ly-lock repeats that path:

  ly's 0xSSRRGGBB value -> the SGR sequence termbox2 sends -> the attribute
  the kernel builds from it (drivers/tty/vt/vt.c) -> a 16-color palette entry.

The font is the console font from /etc/vconsole.conf, read from its PSF file,
so every glyph is the same bitmap the tty draws.
"""

import gzip
import os
import struct

import numpy as np

# termbox2 styles in the top byte of a ly color.
TB_BOLD = 0x01000000
TB_UNDERLINE = 0x02000000
TB_REVERSE = 0x04000000
TB_ITALIC = 0x08000000
TB_BLINK = 0x10000000
TB_HI_BLACK = 0x20000000
TB_BRIGHT = 0x40000000
TB_DIM = 0x80000000

# vt.c's color_table: ANSI color number <-> VGA attribute index (its own
# inverse).
COLOR_TABLE = (0, 4, 2, 6, 1, 5, 3, 7, 8, 12, 10, 14, 9, 13, 11, 15)

# The kernel's default palette, in ANSI order (vt.c default_red/grn/blu).
DEFAULT_PALETTE = (
    (0x00, 0x00, 0x00),
    (0xAA, 0x00, 0x00),
    (0x00, 0xAA, 0x00),
    (0xAA, 0x55, 0x00),
    (0x00, 0x00, 0xAA),
    (0xAA, 0x00, 0xAA),
    (0x00, 0xAA, 0xAA),
    (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55),
    (0xFF, 0x55, 0x55),
    (0x55, 0xFF, 0x55),
    (0xFF, 0xFF, 0x55),
    (0x55, 0x55, 0xFF),
    (0xFF, 0x55, 0xFF),
    (0x55, 0xFF, 0xFF),
    (0xFF, 0xFF, 0xFF),
)

VT_PARAMS = "/sys/module/vt/parameters"

FONT_DIRS = (
    "/etc/kbd/consolefonts",
    "/usr/share/kbd/consolefonts",
    "/usr/share/consolefonts",
    "/usr/lib/kbd/consolefonts",
    "/lib/kbd/consolefonts",
)
FONT_SUFFIXES = ("", ".psfu.gz", ".psf.gz", ".psfu", ".psf", ".gz")
DEFAULT_FONT = "default8x16"


def _read_vt_param(name):
    try:
        with open(os.path.join(VT_PARAMS, name)) as f:
            return f.read().strip()
    except OSError:
        return None


def read_palette():
    """The palette the console uses now, in ANSI order, as (r, g, b)."""
    channels = []
    for name in ("default_red", "default_grn", "default_blu"):
        raw = _read_vt_param(name)
        try:
            values = [int(v) for v in raw.split(",")]
        except (AttributeError, ValueError):
            return DEFAULT_PALETTE
        if len(values) != 16:
            return DEFAULT_PALETTE
        channels.append(values)
    return tuple(zip(*channels, strict=True))


def _vt_color_param(name, default):
    raw = _read_vt_param(name)
    try:
        return int(raw) & 0x0F
    except (TypeError, ValueError):
        return default


class ColorModel:
    """Turns a ly fg/bg pair into palette indices, like the console does."""

    def __init__(self, full_color=True):
        self.full_color = full_color
        # VGA attribute indices the kernel substitutes for italic, underline
        # and dim text (vt.italic, vt.underline, and vc_halfcolor = 8).
        self.itcolor = _vt_color_param("italic", 2)
        self.ulcolor = _vt_color_param("underline", 3)
        self.halfcolor = 8
        self._cache = {}

    def resolve(self, fg, bg):
        """(fg, bg) as ANSI palette indices 0-15."""
        key = (fg, bg)
        hit = self._cache.get(key)
        if hit is None:
            hit = self._cache[key] = self._resolve(fg, bg)
        return hit

    def _resolve(self, fg, bg):
        # SGR0: the default color 0x07, everything off.
        color = 0x07
        intensity = 1  # 0 half, 1 normal, 2 bold
        underline = italic = reverse = blink = False

        # termbox2's send_attr: styles first, then the colors.
        if fg & TB_BOLD:
            intensity = 2
        if fg & TB_BLINK:
            blink = True
        if fg & TB_UNDERLINE:
            underline = True
        if fg & TB_ITALIC:
            italic = True
        if fg & TB_DIM:
            intensity = 0
        if (fg & TB_REVERSE) or (bg & TB_REVERSE):
            reverse = True

        if self.full_color:
            fg_default = (fg & 0xFFFFFF) == 0 and not fg & TB_HI_BLACK
            bg_default = (bg & 0xFFFFFF) == 0 and not bg & TB_HI_BLACK
            if not fg_default:
                rgb = 0 if fg & TB_HI_BLACK else fg & 0xFFFFFF
                color, intensity = _rgb_foreground(color, rgb)
            if not bg_default:
                rgb = 0 if bg & TB_HI_BLACK else bg & 0xFFFFFF
                color = _rgb_background(color, rgb)
        else:
            if fg & 0xFF:
                n = (fg & 0x0F) - 1
                color = (color & 0xF0) | COLOR_TABLE[n & 7]
                if fg & TB_BRIGHT:
                    intensity = 2
            if bg & 0xFF:
                n = (bg & 0x0F) - 1
                color = (COLOR_TABLE[n & 7] << 4) | (color & 0x0F)

        # vt.c build_attr()
        a = color
        if italic:
            a = (a & 0xF0) | self.itcolor
        elif underline:
            a = (a & 0xF0) | self.ulcolor
        elif intensity == 0:
            a = (a & 0xF0) | self.halfcolor
        if reverse:
            a = (a & 0x88) | (((a >> 4) | (a << 4)) & 0x77)
        if blink:
            a ^= 0x80
        if intensity == 2:
            a ^= 0x08

        # fbcon: low nibble is the fg, high nibble (with the blink bit) the bg.
        return COLOR_TABLE[a & 0x0F], COLOR_TABLE[(a >> 4) & 0x0F]


def _rgb_foreground(color, rgb):
    """vt.c rgb_foreground(): the nearest of the 8 hues, bright if strong."""
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    top = max(r, g, b)
    hue = 0
    if r > top // 2:
        hue |= 4
    if g > top // 2:
        hue |= 2
    if b > top // 2:
        hue |= 1
    if hue == 7 and top <= 0x55:
        hue = 0
        intensity = 2
    elif top > 0xAA:
        intensity = 2
    else:
        intensity = 1
    return (color & 0xF0) | hue, intensity


def _rgb_background(color, rgb):
    """vt.c rgb_background(): one bit per channel, erring on the dark side."""
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return (color & 0x0F) | (r & 0x80) >> 1 | (g & 0x80) >> 2 | (b & 0x80) >> 3


def find_font(name=None):
    """Path of the console font: $LY_LOCK_FONT, vconsole.conf, or default8x16."""
    override = os.environ.get("LY_LOCK_FONT")
    if override:
        return override
    if name is None:
        name = DEFAULT_FONT
        try:
            with open("/etc/vconsole.conf") as f:
                for line in f:
                    key, _, value = line.strip().partition("=")
                    if key == "FONT" and value:
                        name = value.strip().strip('"')
        except OSError:
            pass
    if os.path.isabs(name):
        return name
    dirs = list(FONT_DIRS)
    extra = os.environ.get("LY_LOCK_FONT_DIRS")
    if extra:
        dirs = extra.split(":") + dirs
    for d in dirs:
        for suffix in FONT_SUFFIXES:
            path = os.path.join(d, name + suffix)
            if os.path.isfile(path):
                return path
    if name != DEFAULT_FONT:
        return find_font(DEFAULT_FONT)
    raise FileNotFoundError(f"console font {name!r} not found in {', '.join(dirs)}")


class Font:
    """A PSF1 or PSF2 console font as a stack of boolean glyph bitmaps."""

    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)

        if data[:4] == b"\x72\xb5\x4a\x86":
            _, _, header, flags, length, size, height, width = struct.unpack_from("<8I", data)
            has_table = flags & 1
            table_v2 = True
        elif data[:2] == b"\x36\x04":
            mode, height = data[2], data[3]
            header, width, size = 4, 8, data[3]
            length = 512 if mode & 1 else 256
            has_table = mode & 2
            table_v2 = False
        else:
            raise ValueError(f"{path}: not a PSF font")

        self.width, self.height = width, height
        row_bytes = (width + 7) // 8
        raw = np.frombuffer(data, dtype=np.uint8, count=length * size, offset=header)
        raw = raw.reshape(length, height, row_bytes)
        bits = np.unpackbits(raw, axis=2)[:, :, :width]
        self.glyphs = bits.astype(bool)

        index = {}
        if has_table:
            pos = header + length * size
            if table_v2:
                for i in range(length):
                    end = data.index(b"\xff", pos)
                    for ch in data[pos:end].split(b"\xfe")[0].decode("utf-8", "replace"):
                        index.setdefault(ord(ch), i)
                    pos = end + 1
            else:
                for i in range(length):
                    while True:
                        (cp,) = struct.unpack_from("<H", data, pos)
                        pos += 2
                        if cp == 0xFFFF:
                            break
                        if cp == 0xFFFE:
                            # Sequences follow until the terminator.
                            while struct.unpack_from("<H", data, pos)[0] != 0xFFFF:
                                pos += 2
                            continue
                        index.setdefault(cp, i)
        else:
            index = {i: i for i in range(min(length, 256))}

        # Codepoints the font lacks show as U+FFFD if it has one, else '?'.
        fallback = self.fallback = index.get(0xFFFD, index.get(ord("?"), 0))
        self.lut = np.full(0x10000, fallback, dtype=np.int32)
        for cp, i in index.items():
            if cp < 0x10000:
                self.lut[cp] = i
        self.blank = index.get(0x20, fallback)

    def glyph_indices(self, codepoints):
        """Glyph index for each codepoint in an integer array."""
        cps = np.asarray(codepoints)
        out = self.lut[np.clip(cps, 0, 0xFFFF)]
        return np.where(cps > 0xFFFF, self.lut[0xFFFD], out)
