"""ly's widgets: positionWidgets() and each widget's draw(), from src/main.zig
and ly-ui/src/components.

Everything is drawn into a Buffer in ly's layer order, after the animation.
"""

import time

from . import bigclock
from .buffer import str_width

BOX = {
    "left_up": 0x250C,  # ┌
    "left_down": 0x2514,  # └
    "right_up": 0x2510,  # ┐
    "right_down": 0x2518,  # ┘
    "top": 0x2500,  # ─
    "bottom": 0x2500,
    "left": 0x2502,  # │
    "right": 0x2502,
}


class Password:
    """ly's Text widget: the password field."""

    def __init__(self, width, mask):
        self.text = []
        self.cursor = 0
        self.visible_start = 0
        self.width = width
        self.mask = mask
        self.masked = True

    def go_left(self):
        if self.cursor == 0:
            return
        if self.visible_start > 0:
            self.visible_start -= 1
        self.cursor -= 1

    def go_right(self):
        if self.cursor >= len(self.text):
            return
        if self.cursor - self.visible_start == self.width - 1:
            self.visible_start += 1
        self.cursor += 1

    def delete(self):
        if self.cursor < len(self.text):
            del self.text[self.cursor]

    def backspace(self):
        if self.cursor == 0:
            return
        self.go_left()
        self.delete()

    def write(self, ch):
        self.text.insert(self.cursor, ch)
        self.go_right()

    def clear(self):
        self.text = []
        self.cursor = 0
        self.visible_start = 0

    def draw(self, buf, x, y, fg, bg):
        if self.masked:
            if self.mask is None or self.width < 1:
                return
            length = min(len(self.text), self.width - 1)
            for i in range(length):
                buf.put(x + i, y, self.mask, fg, bg)
            return
        length = len(self.text)
        if min(length, self.width) == 0:
            return
        if length > self.width and self.cursor < length:
            visible = self.text[self.visible_start : self.visible_start + self.width]
        else:
            visible = self.text[self.visible_start :]
        buf.text("".join(visible), x, y, fg, bg)

    def cursor_x(self, x):
        if self.masked and self.mask is None:
            return x
        return x + (self.cursor - self.visible_start)


class Screen:
    """Lays out and draws ly's widgets for one buffer size."""

    def __init__(self, state):
        self.state = state

    def draw(self, buf, now=None):
        """Draw every widget. Returns the cursor cell (x, y)."""
        st = self.state
        cfg, lang = st.config, st.lang
        w, h = buf.width, buf.height
        fg, bg = cfg.fg, cfg.bg
        edge = cfg.edge_margin
        now = time.time() if now is None else now

        def label(text, x, y, color=fg, back=bg):
            buf.text(text, x, y, color, back)

        # Key hints along the top.
        y_offset = 1
        brightness_up_children_y = edge + 1
        if not cfg.hide_key_hints:
            x = edge
            label(f"{cfg.shutdown_key} {lang['shutdown']}", x, edge)
            x += str_width(f"{cfg.shutdown_key} {lang['shutdown']}") + 1
            label(f"{cfg.restart_key} {lang['restart']}", x, edge)
            x += str_width(f"{cfg.restart_key} {lang['restart']}") + 1
            if cfg.sleep_cmd is not None:
                text = f"{cfg.sleep_key} {lang['sleep']}"
                label(text, x, edge)
                x += str_width(text) + 1
            if cfg.hibernate_cmd is not None:
                text = f"{cfg.hibernate_key} {lang['hibernate']}"
                label(text, x, edge)
                x += str_width(text) + 1
            text = f"{cfg.show_password_key} {lang['toggle_password']}"
            label(text, x, edge)
            x += str_width(text) + 1
            if cfg.brightness_down_key is not None:
                text = f"{cfg.brightness_down_key} {lang['brightness_down']}"
                label(text, x, edge)
                x += str_width(text) + 1
            if cfg.brightness_up_key is not None:
                label(f"{cfg.brightness_up_key} {lang['brightness_up']}", x, edge)

            x_offset = 0
            limit = cfg.custom_bind_width if cfg.custom_bind_width is not None else w
            for text in st.bind_labels:
                label(text, edge + x_offset, edge + y_offset)
                x_offset += len(text.encode()) + 1
                if x_offset + len(text.encode()) > limit:
                    x_offset = 0
                    y_offset += 1

        infos = st.info_labels
        for i, text in enumerate(infos):
            label(text, w - edge - str_width(text), h - edge - len(infos) + i)

        if cfg.battery_id is not None and st.battery is not None:
            y = edge
            if not cfg.hide_key_hints:
                y = brightness_up_children_y + y_offset
            label(f"BAT: {st.battery}%", edge, y)

        tty_text = f"tty{st.tty}" if cfg.show_tty else ""
        tty_w = str_width(tty_text)
        clock_text = time.strftime(cfg.clock, time.localtime(now)) if cfg.clock else ""
        gap = 1 if cfg.show_tty and cfg.clock is not None else 0
        if cfg.clock is not None:
            span = str_width(clock_text) + tty_w + gap
            x = w - edge - span if w > span + edge else w - edge
            label(clock_text, x, edge)
        if cfg.show_tty:
            x = w - edge - tty_w if w > tty_w + edge else w - edge
            label(tty_text, x, edge)

        box_w = 2 * cfg.margin_box_h + cfg.input_len + 1 + st.labels_max_length
        box_h = 7 + 2 * cfg.margin_box_v

        if cfg.bigclock != "none":
            self.draw_bigclock(buf, now, box_h)

        if not cfg.hide_keyboard_locks:
            numlock, capslock = st.lock_keys()
            num_text = lang["numlock"] if numlock else ""
            caps_text = lang["capslock"] if capslock else ""
            y = edge + 1 if cfg.clock is not None else edge
            num_w = str_width(lang["numlock"])
            x = w - edge - num_w if w > num_w + edge else w - edge
            label(num_text, x, y)
            caps_x = x + str_width(num_text) - (num_w + str_width(lang["capslock"]) + 1)
            label(caps_text, caps_x, y)

        # The box.
        left = (w - min(w - 2, box_w)) // 2
        top = (h - min(h - 2, box_h)) // 2
        right = left + min(w, box_w)
        bottom = top + min(h, box_h)
        if not cfg.hide_borders:
            bfg = cfg.border_fg
            buf.put(left - 1, top - 1, BOX["left_up"], bfg, bg)
            buf.put(right, top - 1, BOX["right_up"], bfg, bg)
            buf.put(left - 1, bottom, BOX["left_down"], bfg, bg)
            buf.put(right, bottom, BOX["right_down"], bfg, bg)
            for i in range(box_w):
                buf.put(left + i, top - 1, BOX["top"], bfg, bg)
                buf.put(left + i, bottom, BOX["bottom"], bfg, bg)
            for i in range(box_h):
                buf.put(left - 1, top + i, BOX["left"], bfg, bg)
                buf.put(right, top + i, BOX["right"], bfg, bg)
        if cfg.blank_box:
            buf.fill(left, top, box_w, box_h, 0x20, fg, bg)
        if cfg.box_title is not None:
            buf.text(cfg.box_title, left, top - 1, fg, bg, box_w)
        if cfg.vi_mode:
            title = lang["insert"] if st.insert_mode else lang["normal"]
            buf.text(title, left, top + box_h, fg, bg, box_w)

        cx, cy = left + cfg.margin_box_h, top + cfg.margin_box_v
        info_w = box_w - 2 * cfg.margin_box_h
        text, mfg, mbg = st.messages[-1]
        self.cyclable(buf, text, cx, cy, info_w, mfg, mbg)

        value_x = cx + st.labels_max_length + 1
        field_w = box_w - 2 * cfg.margin_box_h - st.labels_max_length - 1
        session = st.session
        if session is not None:
            label(session.specifier, cx, cy + 2)
            self.cyclable(buf, session.name, value_x, cy + 2, field_w, fg, bg, trim=True)
        label(lang["login"], cx, cy + 4)
        self.cyclable(buf, st.user, value_x, cy + 4, field_w, fg, bg, trim=True)
        label(lang["password"], cx, cy + 6)
        st.password.draw(buf, value_x, cy + 6, fg, bg)

        if not cfg.hide_version_string:
            label(f"Ly version {st.version}", edge, h - 1 - edge)

        return st.password.cursor_x(value_x), cy + 6

    def cyclable(self, buf, item, x, y, width, fg, bg, trim=False):
        """generic.zig CyclableLabel: "< item >" across width cells."""
        if width < 2:
            return
        buf.put(x, y, "<", fg, bg)
        buf.put(x + width - 1, y, ">", fg, bg)
        inner = width - 2
        length = str_width(item)
        if trim:
            # Session and user rows cap the name at width - 3 for centering.
            if inner < 3:
                return
            length = min(length, inner - 3)
            if length == 0:
                return
        elif length == 0:
            return
        offset = (inner - length) // 2 if self.state.config.text_in_center and inner >= length else 0
        buf.text(item, x + 2 + offset, y, fg, bg, inner)

    def draw_bigclock(self, buf, now, box_h):
        st, cfg = self.state, self.state.config
        w, h = buf.width, buf.height
        cw, ch = bigclock.CHAR_WIDTH, bigclock.CHAR_HEIGHT
        if box_h + (ch + 2) * 2 >= h:
            return
        blink = st.animating and int((now % 1) * 1_000_000) // 500_000 != 0
        sep = " " if blink else ":"
        fmt = ("%I" if cfg.bigclock_12hr else "%H") + sep + "%M"
        if cfg.bigclock_seconds:
            fmt += sep + "%S"
        if cfg.bigclock_12hr:
            fmt += "%P"
        # %P (lowercase am/pm) is a glibc extension, as in ly.
        text = time.strftime(fmt, time.localtime(now))
        half_w = w // 2
        half_label = (str_width(text) * (cw + 1)) // 2
        half_h = (h - box_h if h > box_h else h) // 2
        x = half_w - half_label if half_w > half_label else half_w
        y = half_h - (ch + 2) if half_h > ch + 2 else half_h
        for i, c in enumerate(text):
            cells = bigclock.glyph(c, cfg.bigclock)
            bx = x + i * (cw + 1)
            if bx + cw >= w or y + ch >= h:
                continue
            for yy in range(ch):
                for xx in range(cw):
                    buf.put(bx + xx, y + yy, cells[yy * cw + xx], cfg.fg, cfg.bg)
