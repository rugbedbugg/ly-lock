"""The session row: ly's session list and which entry it shows for a user.

ly builds the list in a fixed order (shell, xinitrc, Wayland, X11, custom),
reading each session directory in its on-disk order, and remembers each
user's choice by position in <config dir>/save.txt.
"""

import os


class Session:
    def __init__(self, name, specifier, file_name="", desktop_names=None):
        self.name = name
        self.specifier = specifier
        self.file_name = file_name
        self.desktop_names = desktop_names


def _read_desktop_entry(path):
    entry = {}
    section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                section = line.strip("[]")
                continue
            if section == "Desktop Entry":
                key, sep, value = line.partition("=")
                if sep:
                    entry.setdefault(key.strip(), value.strip())
    return entry


def _crawl(sessions, directories, specifier):
    for directory in (directories or "").split(":"):
        if not os.path.isabs(directory):
            continue
        try:
            # os.listdir keeps readdir order, which is the order ly sees.
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".desktop"):
                continue
            try:
                entry = _read_desktop_entry(os.path.join(directory, name))
            except (OSError, UnicodeDecodeError):
                continue
            stem = name[: -len(".desktop")]
            names_value = entry.get("DesktopNames")
            sessions.append(Session(entry.get("Name", stem), specifier, stem, names_value))


def x11_enabled(config):
    """Whether ly lists X11 sessions. Builds without X11 have an empty x_cmd."""
    return bool(config.x_cmd)


def list_sessions(config, lang):
    sessions = []
    if config.shell:
        sessions.append(Session(lang["shell"], lang["other"]))
    x11 = x11_enabled(config)
    if x11 and config.xinitrc is not None:
        sessions.append(Session(lang["xinitrc"], lang["other"]))
    _crawl(sessions, config.waylandsessions, lang["wayland"])
    if x11:
        _crawl(sessions, config.xsessions, lang["x11"])
    _crawl(sessions, config.custom_sessions, lang["custom"])
    return sessions


def saved_session_index(config, user):
    """The session index ly saved for user, or None."""
    base = os.path.dirname(config.path or "/etc/ly/config.ini")
    try:
        with open(os.path.join(base, "save.txt"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines[1:]:
        name, sep, index = line.rpartition(":")
        if sep and name == user:
            try:
                return int(index)
            except ValueError:
                return None
    return None


def find_by_name(sessions, name):
    """ly's findSessionByName."""
    name = name.lower()
    for i, s in enumerate(sessions):
        candidates = [s.file_name, s.name]
        if s.desktop_names:
            candidates.append(s.desktop_names.split(";")[0])
            candidates.append(s.desktop_names.replace(";", ":"))
        if any(c and c.lower() == name for c in candidates):
            return i
    return None


def current_session(config, lang, user, desktop=None):
    """The session ly would show for user: their saved one, else the running one."""
    sessions = list_sessions(config, lang)
    if not sessions:
        return None
    index = saved_session_index(config, user) if config.save else None
    if index is not None:
        return sessions[min(index, len(sessions) - 1)]
    if desktop:
        found = find_by_name(sessions, desktop)
        if found is not None:
            return sessions[found]
    # ly selects the last session it added.
    return sessions[-1]
