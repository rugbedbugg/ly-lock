"""ly's config.ini and language files, read the way ly 1.4.1 reads them.

The schema mirrors src/config/Config.zig. Keys ly-lock has no use for (login
commands, X11 setup and so on) are still accepted so a real ly config parses
cleanly.
"""

import os
import re

DEFAULT_CONFIG_PATH = "/etc/ly/config.ini"

BOOL = "bool"
INT = "int"
FLOAT = "float"
STR = "str"
COLOR = "color"
CHAR = "char"

# name: (type, optional, default)
SCHEMA = {
    "allow_empty_password": (BOOL, False, True),
    "animation": (STR, False, "none"),
    "animation_frame_delay": (INT, False, 5),
    "animation_timeout_sec": (INT, False, 0),
    "asterisk": (CHAR, True, ord("*")),
    "auth_fails": (INT, False, 10),
    "battery_id": (STR, True, None),
    "auto_login_service": (STR, False, "ly-autologin"),
    "auto_login_session": (STR, True, None),
    "auto_login_user": (STR, True, None),
    "bg": (COLOR, False, 0x00000000),
    "bigclock": (STR, False, "none"),
    "bigclock_12hr": (BOOL, False, False),
    "bigclock_seconds": (BOOL, False, False),
    "blank_box": (BOOL, False, True),
    "border_fg": (COLOR, False, 0x00FFFFFF),
    "box_title": (STR, True, None),
    "brightness_down_cmd": (STR, False, "brightnessctl -q -n s 10%-"),
    "brightness_down_key": (STR, True, "F5"),
    "brightness_up_cmd": (STR, False, "brightnessctl -q -n s +10%"),
    "brightness_up_key": (STR, True, "F6"),
    "clear_password": (BOOL, False, False),
    "clock": (STR, True, None),
    "cmatrix_fg": (COLOR, False, 0x0000FF00),
    "cmatrix_head_col": (COLOR, False, 0x01FFFFFF),
    "cmatrix_min_codepoint": (INT, False, 0x21),
    "cmatrix_max_codepoint": (INT, False, 0x7B),
    "colormix_col1": (COLOR, False, 0x00FF0000),
    "colormix_col2": (COLOR, False, 0x000000FF),
    "colormix_col3": (COLOR, False, 0x20000000),
    "custom_bind_width": (INT, True, None),
    "custom_sessions": (STR, False, "/etc/ly/custom-sessions"),
    "default_input": (STR, False, "login"),
    "doom_fire_height": (INT, False, 6),
    "doom_fire_spread": (INT, False, 2),
    "doom_top_color": (COLOR, False, 0x00FF0000),
    "doom_middle_color": (COLOR, False, 0x00FFFF00),
    "doom_bottom_color": (COLOR, False, 0x00FFFFFF),
    "dur_file_path": (STR, False, "/etc/ly/example.dur"),
    "dur_offset_alignment": (STR, False, "center"),
    "dur_x_offset": (INT, False, 0),
    "dur_y_offset": (INT, False, 0),
    "edge_margin": (INT, False, 0),
    "error_bg": (COLOR, False, 0x00000000),
    "error_fg": (COLOR, False, 0x01FF0000),
    "fg": (COLOR, False, 0x00FFFFFF),
    "full_color": (BOOL, False, True),
    "gameoflife_fg": (COLOR, False, 0x0000FF00),
    "gameoflife_entropy_interval": (INT, False, 10),
    "gameoflife_frame_delay": (INT, False, 6),
    "gameoflife_initial_density": (FLOAT, False, 0.4),
    "hibernate_cmd": (STR, True, None),
    "hibernate_key": (STR, False, "F4"),
    "hide_borders": (BOOL, False, False),
    "hide_key_hints": (BOOL, False, False),
    "hide_keyboard_locks": (BOOL, False, False),
    "hide_version_string": (BOOL, False, False),
    "inactivity_cmd": (STR, True, None),
    "inactivity_delay": (INT, False, 0),
    "initial_info_text": (STR, True, None),
    "input_len": (INT, False, 34),
    "lang": (STR, False, "en"),
    "login_cmd": (STR, True, None),
    "login_defs_path": (STR, False, "/etc/login.defs"),
    "logout_cmd": (STR, True, None),
    "ly_log": (STR, False, "/var/log/ly.log"),
    "margin_box_h": (INT, False, 2),
    "margin_box_v": (INT, False, 1),
    "numlock": (BOOL, False, False),
    "path": (STR, True, "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
    "restart_cmd": (STR, False, "/sbin/shutdown -r now"),
    "restart_key": (STR, False, "F2"),
    "save": (BOOL, False, True),
    "service_name": (STR, False, "ly"),
    "session_log": (STR, True, "ly-session.log"),
    "setup_cmd": (STR, False, "/etc/ly/setup.sh"),
    "shell": (BOOL, False, True),
    "show_password_key": (STR, False, "F7"),
    "show_tty": (BOOL, False, False),
    "shutdown_cmd": (STR, False, "/sbin/shutdown -a now"),
    "shutdown_key": (STR, False, "F1"),
    "sleep_cmd": (STR, True, None),
    "sleep_key": (STR, False, "F3"),
    "start_cmd": (STR, True, None),
    "text_in_center": (BOOL, False, False),
    "tty": (INT, False, 2),
    "vi_default_mode": (STR, False, "normal"),
    "vi_mode": (BOOL, False, False),
    "waylandsessions": (STR, True, "/usr/share/wayland-sessions"),
    "x_cmd": (STR, False, "/usr/bin/X"),
    "x_vt": (INT, True, None),
    "xauth_cmd": (STR, False, "/usr/bin/xauth"),
    "xinitrc": (STR, True, "~/.xinitrc"),
    "xsessions": (STR, True, "/usr/share/xsessions"),
}

# Keys ly's migrator still maps from older configs (src/config/migrator.zig).
RENAMED = {
    "min_refresh_delta": "animation_frame_delay",
}

ANIMATIONS = ("none", "doom", "matrix", "colormix", "gameoflife", "dur_file")
BIGCLOCKS = ("none", "en", "fa")
DUR_ALIGNMENTS = (
    "topleft",
    "topcenter",
    "topright",
    "centerleft",
    "center",
    "centerright",
    "bottomleft",
    "bottomcenter",
    "bottomright",
)

# src/config/Lang.zig: the strings ly uses when no language file is found.
LANG_DEFAULTS = {
    "authenticating": "authenticating...",
    "brightness_down": "decrease brightness",
    "brightness_up": "increase brightness",
    "capslock": "capslock",
    "custom": "custom",
    "custom_info_err_output_long": "output too long",
    "custom_info_err_no_output": "no output",
    "custom_info_err_no_output_error": ", possible error",
    "err_alloc": "failed memory allocation",
    "err_args": "unable to parse command line arguments",
    "err_autologin_session": "autologin session not found",
    "err_bounds": "out-of-bounds index",
    "err_brightness_change": "failed to change brightness",
    "err_chdir": "failed to open home folder",
    "err_clock_too_long": "clock string too long",
    "err_config": "unable to parse config file",
    "err_crawl": "failed to crawl session directories",
    "err_dgn_oob": "log message",
    "err_domain": "invalid domain",
    "err_empty_password": "empty password not allowed",
    "err_envlist": "failed to get envlist",
    "err_get_active_tty": "failed to get active tty",
    "err_hibernate": "failed to execute hibernate command",
    "err_hostname": "failed to get hostname",
    "err_inactivity": "failed to execute inactivity command",
    "err_lock_state": "failed to get lock state",
    "err_log": "failed to open log file",
    "err_mlock": "failed to lock password memory",
    "err_null": "null pointer",
    "err_numlock": "failed to set numlock",
    "err_pam": "pam transaction failed",
    "err_pam_abort": "pam transaction aborted",
    "err_pam_acct_expired": "account expired",
    "err_pam_auth": "authentication error",
    "err_pam_authinfo_unavail": "failed to get user info",
    "err_pam_authok_reqd": "token expired",
    "err_pam_buf": "memory buffer error",
    "err_pam_cred_err": "failed to set credentials",
    "err_pam_cred_expired": "credentials expired",
    "err_pam_cred_insufficient": "insufficient credentials",
    "err_pam_cred_unavail": "failed to get credentials",
    "err_pam_maxtries": "reached maximum tries limit",
    "err_pam_perm_denied": "permission denied",
    "err_pam_session": "session error",
    "err_pam_sys": "system error",
    "err_pam_user_unknown": "unknown user",
    "err_path": "failed to set path",
    "err_perm_dir": "failed to change current directory",
    "err_perm_group": "failed to downgrade group permissions",
    "err_perm_user": "failed to downgrade user permissions",
    "err_pwnam": "failed to get user info",
    "err_sleep": "failed to execute sleep command",
    "err_start": "failed to execute start command",
    "err_battery": "failed to load battery status",
    "err_switch_tty": "failed to switch tty",
    "err_tty_ctrl": "tty control transfer failed",
    "err_no_users": "no users found",
    "err_uid_range": "failed to dynamically get uid range",
    "err_user_gid": "failed to set user GID",
    "err_user_init": "failed to initialize user",
    "err_user_uid": "failed to set user UID",
    "err_xauth": "xauth command failed",
    "err_xcb_conn": "xcb connection failed",
    "err_xsessions_dir": "failed to find sessions folder",
    "err_xsessions_open": "failed to open sessions folder",
    "hibernate": "hibernate",
    "insert": "insert",
    "login": "login",
    "logout": "logged out",
    "no_x11_support": "x11 support disabled at compile-time",
    "normal": "normal",
    "numlock": "numlock",
    "other": "other",
    "password": "password",
    "restart": "reboot",
    "shell": "shell",
    "shutdown": "shutdown",
    "sleep": "sleep",
    "toggle_password": "toggle password",
    "wayland": "wayland",
    "x11": "x11",
    "xinitrc": "xinitrc",
}


class Config:
    """Parsed settings, with ly's defaults for anything missing."""

    def __init__(self, values=None, binds=None, labels=None, path=None):
        self.values = {name: spec[2] for name, spec in SCHEMA.items()}
        if values:
            self.values.update(values)
        # [cmd:KEY] sections: key -> {"name", "cmd"}
        self.binds = binds or {}
        # [lbl:ID] sections: id -> {"name", "cmd", "refresh"}
        self.labels = labels or {}
        self.path = path

    def __getattr__(self, name):
        try:
            return self.__dict__["values"][name]
        except KeyError:
            raise AttributeError(name) from None


def parse_value(kind, optional, raw):
    """One value, typed by the schema. Raises ValueError on bad input."""
    if optional and raw == "null":
        return None
    if kind == BOOL:
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise ValueError(f"not a boolean: {raw!r}")
    if kind in (INT, COLOR):
        return int(raw, 0)
    if kind == FLOAT:
        return float(raw)
    if kind == CHAR:
        if raw.lower().startswith("0x"):
            return int(raw, 16)
        if len(raw) == 1:
            return ord(raw)
        raise ValueError(f"not a single character: {raw!r}")
    return raw


def read_ini(path):
    """Sections of key/value pairs. Lines starting with '#' are comments."""
    sections = {"": {}}
    current = sections[""]
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = sections.setdefault(line[1:-1].strip(), {})
                continue
            key, sep, value = line.partition("=")
            if sep:
                current[key.strip()] = value.strip()
    return sections


def load_config(path=DEFAULT_CONFIG_PATH):
    """Read ly's config.ini. Missing file or bad values fall back to defaults.

    Returns the config and a list of warnings to show or log.
    """
    warnings = []
    try:
        sections = read_ini(path)
    except OSError as err:
        warnings.append(f"{path}: {err.strerror}, using ly's defaults")
        return Config(path=path), warnings

    values = {}
    for key, raw in sections.pop("", {}).items():
        key = RENAMED.get(key, key)
        spec = SCHEMA.get(key)
        if spec is None:
            continue
        try:
            values[key] = parse_value(spec[0], spec[1], raw)
        except ValueError as err:
            warnings.append(f"{path}: {key}: {err}")

    binds, labels = {}, {}
    for name, entries in sections.items():
        kind, _, ident = name.partition(":")
        if kind == "cmd" and ident:
            binds[ident] = {"name": entries.get("name", ""), "cmd": entries.get("cmd", "")}
        elif kind == "lbl" and ident:
            try:
                refresh = int(entries.get("refresh", "0"), 0)
            except ValueError:
                refresh = 0
            labels[ident] = {
                "name": entries.get("name", ""),
                "cmd": entries.get("cmd"),
                "refresh": refresh,
            }
    return Config(values, binds, labels, path), warnings


def load_lang(config):
    """The language strings ly would use for this config.

    ly reads <config dir>/lang/<lang>.ini and keeps its built-in English for
    any key the file lacks, or for every key when the file is missing.
    """
    lang = dict(LANG_DEFAULTS)
    base = os.path.dirname(config.path or DEFAULT_CONFIG_PATH)
    path = os.path.join(base, "lang", f"{config.lang}.ini")
    try:
        entries = read_ini(path).get("", {})
    except OSError:
        return lang
    for key, value in entries.items():
        if key in lang:
            lang[key] = value
    return lang


_LANG_REF = re.compile(r"\$([a-z_0-9]+)")


def expand_lang_refs(text, lang):
    """Replace "$key" with the language string, as ly does for [cmd:] names."""
    return _LANG_REF.sub(lambda m: lang.get(m.group(1), m.group(0)), text)
