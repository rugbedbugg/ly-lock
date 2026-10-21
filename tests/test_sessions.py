from ly_lock.config import LANG_DEFAULTS, Config
from ly_lock.sessions import current_session, list_sessions


def desktop(path, name, names=None):
    text = f"[Desktop Entry]\nName={name}\nExec=x\n"
    if names:
        text += f"DesktopNames={names}\n"
    path.write_text(text)


def setup(tmp_path, save=None):
    sessions = tmp_path / "wayland-sessions"
    sessions.mkdir()
    desktop(sessions / "sway.desktop", "Sway", "sway")
    if save is not None:
        (tmp_path / "save.txt").write_text(save)
    return Config(
        {"waylandsessions": str(sessions), "x_cmd": "", "custom_sessions": str(tmp_path / "none")},
        path=str(tmp_path / "config.ini"),
    )


def test_list_order(tmp_path):
    config = setup(tmp_path)
    names = [s.name for s in list_sessions(config, LANG_DEFAULTS)]
    assert names == ["shell", "Sway"]


def test_saved_index_wins(tmp_path):
    config = setup(tmp_path, "0\nalice:0\nbob:1\n")
    assert current_session(config, LANG_DEFAULTS, "alice").name == "shell"
    assert current_session(config, LANG_DEFAULTS, "bob").name == "Sway"


def test_running_desktop_then_last(tmp_path):
    config = setup(tmp_path)
    assert current_session(config, LANG_DEFAULTS, "carol", "sway").name == "Sway"
    assert current_session(config, LANG_DEFAULTS, "carol", "nope").name == "Sway"
    assert current_session(config, LANG_DEFAULTS, "carol").specifier == "wayland"
