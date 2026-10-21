"""The lock client: one surface per monitor, keyboard input, PAM."""

import argparse
import os
import pwd
import random
import re
import socket
import subprocess
import sys
import threading
import time
from ctypes import CDLL

# gtk4-layer-shell has to be loaded before libwayland-client, and GI loads
# libwayland first. Packages that keep it off the library path point
# LY_LOCK_LAYER_SHELL at it.
try:
    CDLL(os.environ.get("LY_LOCK_LAYER_SHELL", "libgtk4-layer-shell.so.0"))
except OSError:
    pass


import gi
import numpy as np

import pam

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4SessionLock", "1.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Gtk4SessionLock  # noqa: E402

from . import __version__, animations  # noqa: E402
from .buffer import Buffer, str_width  # noqa: E402
from .config import DEFAULT_CONFIG_PATH, expand_lang_refs, load_config, load_lang  # noqa: E402
from .console import ColorModel, Font, find_font, read_palette  # noqa: E402
from .render import Renderer  # noqa: E402

try:
    from .glrender import GLRenderer
except ImportError:  # PyOpenGL is optional; the CPU renderer covers for it.
    GLRenderer = None
from .sessions import current_session  # noqa: E402
from .ui import Password, Screen  # noqa: E402

PAM_SERVICE = "ly-lock"
CURSOR_BLINK = 0.2  # fbcon's default blink interval, in seconds
CASCADE_STEP_MS = 10
CASCADE_REST = 7.0

PAM_ERRORS = {
    26: "err_pam_abort",
    13: "err_pam_acct_expired",
    7: "err_pam_auth",
    9: "err_pam_authinfo_unavail",
    12: "err_pam_authok_reqd",
    5: "err_pam_buf",
    17: "err_pam_cred_err",
    16: "err_pam_cred_expired",
    8: "err_pam_cred_insufficient",
    15: "err_pam_cred_unavail",
    11: "err_pam_maxtries",
    6: "err_pam_perm_denied",
    14: "err_pam_session",
    4: "err_pam_sys",
    10: "err_pam_user_unknown",
}


def log(message):
    print(f"ly-lock: {message}", file=sys.stderr)


def ly_version():
    try:
        out = subprocess.run(
            ["ly", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    match = re.search(r"version\s+(\S+)", out)
    return match.group(1) if match else os.environ.get("LY_LOCK_LY_VERSION", "")


def run_shell(command):
    if not command:
        return
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as err:
        log(f"{command}: {err}")


def parse_key(spec):
    """A ly key name such as "F1" or "Ctrl+U" as (keyval, modifier mask)."""
    if not spec:
        return None
    *mods, name = spec.split("+")
    mask = Gdk.ModifierType(0)
    for m in mods:
        mask |= {
            "ctrl": Gdk.ModifierType.CONTROL_MASK,
            "alt": Gdk.ModifierType.ALT_MASK,
            "shift": Gdk.ModifierType.SHIFT_MASK,
        }.get(m.lower(), Gdk.ModifierType(0))
    keyval = Gdk.keyval_from_name(name if len(name) > 1 else name.lower())
    if keyval in (0, Gdk.KEY_VoidSymbol):
        return None
    return Gdk.keyval_to_lower(keyval), mask


MOD_MASK = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SHIFT_MASK


class State:
    """Everything the screens share: config, the password, messages."""

    def __init__(self, config, lang, preview):
        self.config = config
        self.lang = lang
        self.preview = preview
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.session = current_session(config, lang, self.user, os.environ.get("XDG_SESSION_DESKTOP"))
        self.version = ly_version()
        self.tty = os.environ.get("XDG_VTNR", str(config.tty))
        self.labels_max_length = max(
            str_width(lang[k]) for k in ("login", "password", "wayland", "x11", "shell", "xinitrc", "custom")
        )
        box_w = 2 * config.margin_box_h + config.input_len + 1 + self.labels_max_length
        field_w = box_w - 2 * config.margin_box_h - self.labels_max_length - 1
        self.password = Password(field_w, config.asterisk)
        self.insert_mode = not config.vi_mode or config.vi_default_mode == "insert"
        self.messages = []
        if config.initial_info_text is not None:
            self.message(config.initial_info_text)
        else:
            self.message(socket.gethostname())
        self.bind_labels = [expand_lang_refs(f"{key} {b['name']}", lang) for key, b in config.binds.items()]
        self.custom_info = [
            {"cmd": lbl["cmd"], "name": lbl["name"], "refresh": lbl["refresh"], "counter": 1, "text": ""}
            for lbl in config.labels.values()
        ]
        self.battery = None
        self.auth_fails = 0
        self.busy = False
        self.animating = config.animation != "none"

    @property
    def info_labels(self):
        return [i["text"] for i in self.custom_info]

    def message(self, text, fg=None, bg=None):
        if text:
            fg = self.config.fg if fg is None else fg
            bg = self.config.bg if bg is None else bg
            self.messages.append((text, fg, bg))

    def error(self, key):
        self.message(self.lang.get(key, key), self.config.error_fg, self.config.error_bg)

    def lock_keys(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat() if display else None
        kbd = seat.get_keyboard() if seat else None
        if kbd is None:
            return False, False
        return kbd.get_num_lock_state(), kbd.get_caps_lock_state()


def _setup_canvas(widget, view):
    widget.view = view
    widget.set_hexpand(True)
    widget.set_vexpand(True)
    widget.set_focusable(True)
    # A tty has no mouse pointer.
    widget.set_cursor(Gdk.Cursor.new_from_name("none", None))


class Canvas(Gtk.Widget):
    """Shows a View's pixels as a texture drawn on the CPU."""

    def __init__(self, view):
        super().__init__()
        _setup_canvas(self, view)

    def do_size_allocate(self, width, height, _baseline):
        self.view.resize(width, height)

    def do_snapshot(self, snapshot):
        texture = self.view.texture
        if texture is None:
            return
        rect = Graphene.Rect().init(0, 0, self.get_width(), self.get_height())
        # Nearest-neighbour keeps the font's pixels square on scaled outputs.
        snapshot.append_scaled_texture(texture, Gsk.ScalingFilter.NEAREST, rect)


class GLCanvas(Gtk.GLArea):
    """Draws a View's cells with the GPU (see glrender)."""

    def __init__(self, view):
        super().__init__()
        _setup_canvas(self, view)
        self.set_auto_render(False)
        self.connect("realize", self.on_realize)
        self.connect("unrealize", self.on_unrealize)
        self.connect("render", self.on_render)

    def do_size_allocate(self, width, height, baseline):
        Gtk.GLArea.do_size_allocate(self, width, height, baseline)
        self.view.resize(width, height)

    def on_realize(self, _area):
        self.make_current()
        error = self.get_error()
        try:
            if error is not None:
                raise RuntimeError(error.message)
            self.view.gl.realize(self.get_context().get_use_es())
        except Exception as err:
            log(f"GPU rendering unavailable, drawing on the CPU: {err}")
            GLib.idle_add(self.view.use_cpu)

    def on_unrealize(self, _area):
        self.make_current()
        if self.view.gl is not None:
            self.view.gl.unrealize()

    def on_render(self, _area, _context):
        gl = self.view.gl
        if gl is not None:
            pw, ph = self.view.pixel_size
            gl.render(pw, ph)
        return True


class View:
    """One monitor: its buffer, animation and renderer."""

    def __init__(self, app, rng_seed):
        self.app = app
        self.state = app.state
        self.font = app.font
        self.rng = random.Random(rng_seed)
        self.np_rng = np.random.default_rng(rng_seed)
        self.buf = None
        self.anim = None
        self.ui = Screen(app.state)
        self.size = (0, 0)
        self.pixel_size = (0, 0)
        self.scale = 1.0
        self.dirty = True
        self.last_cursor = None
        self.shown_cursor = None
        self.texture = None
        self.pixels = None
        # Milliseconds per monitor refresh.
        self.period = 1000 / 60
        if app.use_gl:
            self.gl = GLRenderer(app.font, app.palette)
            self.renderer = None
            self.area = GLCanvas(self)
        else:
            self.gl = None
            self.renderer = Renderer(app.font, app.palette)
            self.area = Canvas(self)

    def use_cpu(self):
        """Swap the GL widget for the CPU one after GL failed to start."""
        old = self.area
        self.gl = None
        self.renderer = Renderer(self.font, self.app.palette)
        self.area = Canvas(self)
        self.size = (0, 0)
        root = old.get_root()
        if root is not None:
            root.set_child(self.area)
            self.area.grab_focus()
        return GLib.SOURCE_REMOVE

    def resize(self, width, height):
        native = self.area.get_native()
        surface = native.get_surface() if native else None
        scale = surface.get_scale() if surface else self.area.get_scale_factor()
        if (width, height, scale) == (*self.size, self.scale):
            return
        self.size, self.scale = (width, height), scale
        pw, ph = round(width * scale), round(height * scale)
        self.pixel_size = (pw, ph)
        cols, rows = pw // self.font.width, ph // self.font.height
        if cols < 2 or rows < 4:
            self.buf = None
            return
        if self.buf is None or (cols, rows) != (self.buf.width, self.buf.height):
            self.buf = Buffer(cols, rows, self.app.colors)
            self.anim = animations.create(
                self.state.config, cols, rows, self.rng, self.np_rng, self.app.colors, log
            )
        if self.renderer is not None:
            self.pixels = np.full((ph, pw), 0xFF000000, dtype=np.uint32)
            self.renderer.invalidate()
            self.texture = None
        self.dirty = True
        self.present()

    def step(self, budget=1):
        """Run up to budget of ly's frames, stopping at the first that
        changes the picture: in ly that frame costs a full redraw."""
        if self.anim is None:
            return
        for _ in range(budget):
            if self.anim.step():
                self.dirty = True
                return

    def compose(self):
        self.buf.clear()
        if self.anim is not None:
            self.anim.paint(buf=self.buf)
        return self.ui.draw(self.buf)

    def cascade_step(self):
        """ly's Cascade.zig: one pass of letting characters fall."""
        buf = self.buf
        ws = np.isin(buf.ch & 0xFF, (0x20, 0x09, 0x0A, 0x0B, 0x0C, 0x0D))
        changed = False
        for y in range(buf.height - 2, 0, -1):
            falls = ~ws[y - 1] & ws[y]
            if not falls.any():
                continue
            changed = True
            # Each falling cell skips this pass with a 2 in 10 chance.
            rolls = self.np_rng.integers(0, 0x10000, buf.width) % 10
            falls &= rolls <= 7
            if not falls.any():
                continue
            under_fg = buf.fg[y, falls].copy()
            under_bg = buf.bg[y, falls].copy()
            buf.ch[y, falls] = buf.ch[y - 1, falls]
            buf.fg[y, falls] = buf.fg[y - 1, falls]
            buf.bg[y, falls] = buf.bg[y - 1, falls]
            # The emptied cell takes the colors of the space it swapped with.
            buf.ch[y - 1, falls] = 0x20
            buf.fg[y - 1, falls] = under_fg
            buf.bg[y - 1, falls] = under_bg
            ws[y, falls] = False
            ws[y - 1, falls] = True
        if changed:
            self.dirty = True
        return changed

    def present(self):
        """ly's draw-and-present: rebuild the frame if anything changed.

        Returns True if the screen got a new picture.
        """
        if self.buf is None:
            return False
        app = self.app
        if not app.cascading and self.dirty:
            self.last_cursor = self.compose()
        cursor = self.last_cursor if app.cursor_on and not app.cascading else None
        if not self.dirty and cursor == self.shown_cursor and not app.cascading:
            return False
        self.dirty = False
        self.shown_cursor = cursor
        if self.gl is not None:
            if self.gl.update(self.buf, cursor):
                self.area.queue_render()
                return True
            return False
        if self.renderer.render(self.buf, self.pixels, cursor) or self.texture is None:
            ph, pw = self.pixels.shape
            data = GLib.Bytes.new(self.pixels.tobytes())
            self.texture = Gdk.MemoryTexture.new(
                pw, ph, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, pw * 4
            )
            self.area.queue_draw()
            return True
        return False


class App:
    def __init__(self, args):
        self.args = args
        config, warnings = load_config(args.config)
        for w in warnings:
            log(w)
        self.state = State(config, load_lang(config), args.preview)
        self.colors = ColorModel(config.full_color)
        self.font = Font(find_font())
        self.palette = read_palette()
        self.use_gl = GLRenderer is not None and os.environ.get("LY_LOCK_RENDERER") != "cpu"
        if self.use_gl:
            # A GLArea under GTK's Vulkan renderer pays for a GL to Vulkan
            # handoff every frame. The GL renderer avoids it.
            os.environ.setdefault("GSK_RENDERER", "gl")
        self.views = []
        self.cursor_on = True
        self.last_blink = time.monotonic()
        self.last_second = 0
        self.cascading = False
        self.cascade_rest_until = None
        self.last_tick = time.monotonic()
        self.last_half = 0
        self.last_input = time.monotonic()
        self.inactivity_ran = False
        self.keys = self.build_keys()
        self.gtk = Gtk.Application(application_id=None)
        self.gtk.connect("activate", self.on_activate)
        self.lock = None
        self.status = 0

    def build_keys(self):
        cfg = self.state.config
        actions = []

        def add(spec, action):
            key = parse_key(spec)
            if key:
                actions.append((key, action))

        for spec, bind in cfg.binds.items():
            add(spec, lambda b=bind: run_shell(b["cmd"]))
        add(cfg.shutdown_key, lambda: run_shell("systemctl poweroff"))
        add(cfg.restart_key, lambda: run_shell("systemctl reboot"))
        add(cfg.show_password_key, self.toggle_mask)
        if cfg.sleep_cmd:
            add(cfg.sleep_key, lambda: run_shell(cfg.sleep_cmd))
        if cfg.hibernate_cmd:
            add(cfg.hibernate_key, lambda: run_shell(cfg.hibernate_cmd))
        add(cfg.brightness_down_key, lambda: run_shell(cfg.brightness_down_cmd))
        add(cfg.brightness_up_key, lambda: run_shell(cfg.brightness_up_cmd))
        return actions

    def toggle_mask(self):
        self.state.password.masked = not self.state.password.masked

    # GTK setup

    def on_activate(self, _gtk):
        self.gtk.hold()
        if self.args.preview:
            window = Gtk.Window(application=self.gtk, title="ly-lock preview")
            window.set_default_size(1280, 720)
            self.add_view(window)
            window.connect("close-request", lambda _w: self.quit(0) or False)
            window.present()
        else:
            if not Gtk4SessionLock.is_supported():
                log("the compositor does not support ext-session-lock-v1")
                self.quit(1)
                return
            self.lock = Gtk4SessionLock.Instance.new()
            self.lock.connect("monitor", self.on_monitor)
            self.lock.connect("failed", lambda _l: (log("could not lock the session"), self.quit(1)))
            self.lock.connect("unlocked", lambda _l: self.quit(0))
            self.lock.lock()
        self.schedule()

    def on_monitor(self, _lock, monitor):
        window = Gtk.Window(application=self.gtk)
        view = self.add_view(window)
        rate = monitor.get_refresh_rate()
        if rate > 0:
            # The rate is in millihertz.
            view.period = 1_000_000 / rate
        self.lock.assign_window_to_monitor(window, monitor)
        window.present()

    def add_view(self, window):
        view = View(self, random.getrandbits(64))
        self.views.append(view)
        window.set_child(view.area)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        window.add_controller(keys)
        window.connect("destroy", lambda _w: view in self.views and self.views.remove(view))
        view.area.grab_focus()
        return view

    def quit(self, status):
        self.status = status
        self.gtk.release()
        self.gtk.quit()

    def run(self):
        self.gtk.run([sys.argv[0]])
        return self.status

    # The loop

    def schedule(self):
        if self.cascading:
            delay = CASCADE_STEP_MS
        elif self.state.animating:
            # Wake at most once per monitor refresh. frame() catches up on
            # the ly frames in between.
            period = min(v.period for v in self.views) if self.views else 1000 / 60
            delay = max(self.state.config.animation_frame_delay, period)
            spent = (time.monotonic() - self.last_tick) * 1000
            delay = max(1, round(delay - spent))
        else:
            delay = 50
        GLib.timeout_add(delay, self.on_tick)

    def on_tick(self):
        """One pass of ly's event loop."""
        now = time.monotonic()
        if self.cascading:
            self.cascade_tick(now)
        else:
            self.frame(now)
        self.schedule()
        return GLib.SOURCE_REMOVE

    def frame(self, now):
        st = self.state
        if now - self.last_blink >= CURSOR_BLINK:
            self.last_blink = now
            self.cursor_on = not self.cursor_on

        # ly draws a frame every animation_frame_delay ms.
        elapsed = (now - self.last_tick) * 1000
        self.last_tick = now
        budget = max(1, int(elapsed // max(1, st.config.animation_frame_delay)))
        for v in self.views:
            v.step(budget)
        st.animating = any(v.anim is not None and v.anim.animate for v in self.views)

        second = int(time.time())
        if second != self.last_second:
            self.last_second = second
            self.update_battery()
            self.redraw(present=False)
        # The big clock's colon blinks every half second while animating.
        half = int(time.time() * 2)
        if st.config.bigclock != "none" and half != self.last_half:
            self.last_half = half
            self.redraw(present=False)

        self.update_custom_info()
        self.check_inactivity(now)
        for v in self.views:
            v.present()

    def redraw(self, present=True):
        for v in self.views:
            v.dirty = True
            if present:
                v.present()

    def cascade_tick(self, now):
        if self.cascade_rest_until is not None:
            if now >= self.cascade_rest_until:
                self.cascading = False
                self.cascade_rest_until = None
                self.state.auth_fails = 0
                self.redraw()
            return
        moving = False
        for v in self.views:
            if v.buf is not None and v.cascade_step():
                moving = True
                v.present()
        if not moving:
            self.cascade_rest_until = now + CASCADE_REST

    def update_battery(self):
        bid = self.state.config.battery_id
        if bid is None:
            return
        try:
            with open(f"/sys/class/power_supply/{bid}/capacity") as f:
                self.state.battery = int(f.read().strip())
        except (OSError, ValueError):
            self.state.battery = None

    def update_custom_info(self):
        for info in self.state.custom_info:
            if info["counter"] == 1 and not info.get("running"):
                info["running"] = True
                threading.Thread(target=self.run_info, args=(info,), daemon=True).start()
                if info["refresh"] != 0:
                    info["counter"] = info["refresh"]
            if info["counter"] != 0:
                info["counter"] -= 1

    def run_info(self, info):
        lang = self.state.lang
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", info["cmd"] or "echo \"You forgot to define 'cmd'!\""],
                capture_output=True,
                check=False,
                timeout=10,
            )
            out = proc.stdout.decode("utf-8", "replace").split("\n")[0]
            if out and not out[-1].isprintable():
                out = out[:-1]
            if not out:
                hint = lang["custom_info_err_no_output_error"] if proc.stderr else ""
                out = f"{info['name']}: [{lang['custom_info_err_no_output']}{hint}]"
        except (OSError, subprocess.SubprocessError):
            out = f"{info['name']}: [{lang['custom_info_err_no_output']}]"

        def done():
            info["text"] = out
            info["running"] = False
            for v in self.views:
                v.dirty = True
            return GLib.SOURCE_REMOVE

        GLib.idle_add(done)

    def check_inactivity(self, now):
        cfg = self.state.config
        if cfg.inactivity_cmd and not self.inactivity_ran and now - self.last_input > cfg.inactivity_delay:
            self.inactivity_ran = True
            run_shell(cfg.inactivity_cmd)

    # Input

    def on_key(self, _ctrl, keyval, _keycode, mods):
        st = self.state
        if st.busy or self.cascading:
            return True
        self.last_input = time.monotonic()
        self.inactivity_ran = False
        handled = self.handle_key(keyval, mods & MOD_MASK)
        # ly redraws everything after each key, and its animations take one
        # more step with it.
        self.cursor_on = True
        self.last_blink = time.monotonic()
        for v in self.views:
            v.step()
        self.redraw()
        return handled

    def handle_key(self, keyval, mods):
        st, cfg, pw = self.state, self.state.config, self.state.password
        low = Gdk.keyval_to_lower(keyval)
        ctrl = bool(mods & Gdk.ModifierType.CONTROL_MASK)

        for (kv, kmods), action in self.keys:
            if low == kv and (mods & ~Gdk.ModifierType.SHIFT_MASK) == (kmods & ~Gdk.ModifierType.SHIFT_MASK):
                action()
                return True

        if cfg.vi_mode:
            if keyval == Gdk.KEY_Escape and st.insert_mode:
                st.insert_mode = False
                return True
            if not st.insert_mode:
                if low == Gdk.KEY_i:
                    st.insert_mode = True
                elif low == Gdk.KEY_h:
                    pw.go_left()
                elif low == Gdk.KEY_l:
                    pw.go_right()
                elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                    self.submit()
                elif keyval == Gdk.KEY_Left:
                    pw.go_left()
                elif keyval == Gdk.KEY_Right:
                    pw.go_right()
                return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.submit()
        elif keyval == Gdk.KEY_Left:
            pw.go_left()
        elif keyval == Gdk.KEY_Right:
            pw.go_right()
        elif keyval == Gdk.KEY_Delete:
            pw.delete()
        elif keyval == Gdk.KEY_BackSpace:
            pw.backspace()
        elif ctrl and low == Gdk.KEY_u:
            pw.clear()
        else:
            cp = Gdk.keyval_to_unicode(keyval)
            if ctrl or not 0x20 <= cp <= 0x7E:
                return False
            pw.write(chr(cp))
        return True

    # Authentication

    def submit(self):
        st, cfg = self.state, self.state.config
        if st.busy:
            return
        if not cfg.allow_empty_password and not st.password.text:
            st.error("err_empty_password")
            return
        st.message(st.lang["authenticating"])
        st.busy = True
        secret = "".join(st.password.text)
        threading.Thread(target=self.authenticate, args=(secret,), daemon=True).start()

    def authenticate(self, secret):

        p = pam.pam()
        ok = p.authenticate(self.state.user, secret, service=PAM_SERVICE, resetcreds=False)
        del secret
        GLib.idle_add(self.auth_done, ok, p.code)

    def auth_done(self, ok, code):
        st, cfg = self.state, self.state.config
        st.busy = False
        if ok:
            st.password.clear()
            if self.lock is not None:
                self.lock.unlock()
            else:
                self.quit(0)
            return GLib.SOURCE_REMOVE
        st.error(PAM_ERRORS.get(code, "err_pam"))
        st.auth_fails += 1
        if cfg.clear_password:
            st.password.clear()
        if cfg.auth_fails > 0 and st.auth_fails >= cfg.auth_fails:
            self.start_cascade()
        self.redraw()
        return GLib.SOURCE_REMOVE

    def start_cascade(self):
        # The cascade starts from the screen as it is now.
        for v in self.views:
            if v.buf is not None:
                v.compose()
        self.cascading = True
        self.cascade_rest_until = None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ly-lock",
        description="Lock the screen with ly's login screen.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=os.environ.get("LY_LOCK_CONFIG", DEFAULT_CONFIG_PATH),
        help=f"ly config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="show the lock screen in a normal window without locking",
    )
    parser.add_argument("-v", "--version", action="version", version=f"ly-lock {__version__}")
    args = parser.parse_args(argv)
    try:
        app = App(args)
    except (OSError, ValueError) as err:
        log(str(err))
        return 1
    return app.run()
