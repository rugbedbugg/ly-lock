from ly_lock.config import expand_lang_refs, load_config, load_lang


def write(path, text):
    path.write_text(text)
    return str(path)


def test_defaults_when_missing(tmp_path):
    config, warnings = load_config(str(tmp_path / "missing.ini"))
    assert config.animation == "none"
    assert config.fg == 0x00FFFFFF
    assert warnings


def test_values_are_typed(tmp_path):
    path = write(
        tmp_path / "config.ini",
        "# comment\n"
        "animation = matrix\n"
        "bg = 0x20000000\n"
        "hide_borders = true\n"
        "clock = %a %d %b  %H:%M\n"
        "battery_id = null\n"
        "asterisk = 0x2022\n"
        "gameoflife_initial_density = 0.25\n"
        "min_refresh_delta = 7\n"
        "unknown_key = whatever\n",
    )
    config, warnings = load_config(path)
    assert warnings == []
    assert config.animation == "matrix"
    assert config.bg == 0x20000000
    assert config.hide_borders is True
    assert config.clock == "%a %d %b  %H:%M"
    assert config.battery_id is None
    assert config.asterisk == 0x2022
    assert config.gameoflife_initial_density == 0.25
    assert config.animation_frame_delay == 7


def test_bad_value_warns_and_keeps_default(tmp_path):
    config, warnings = load_config(write(tmp_path / "c.ini", "blank_box = maybe\n"))
    assert config.blank_box is True
    assert len(warnings) == 1


def test_custom_sections(tmp_path):
    path = write(
        tmp_path / "config.ini",
        "[cmd:F8]\ncmd = touch /tmp/x\nname = custom $brightness_up\n"
        "[lbl:kernel]\ncmd = uname -r\nrefresh = 5\n",
    )
    config, _ = load_config(path)
    assert config.binds == {"F8": {"name": "custom $brightness_up", "cmd": "touch /tmp/x"}}
    assert config.labels["kernel"]["refresh"] == 5


def test_lang_file_overrides_defaults(tmp_path):
    (tmp_path / "lang").mkdir()
    write(tmp_path / "lang" / "de.ini", "login = Anmeldung\n")
    config, _ = load_config(write(tmp_path / "config.ini", "lang = de\n"))
    lang = load_lang(config)
    assert lang["login"] == "Anmeldung"
    assert lang["password"] == "password"


def test_lang_refs():
    assert expand_lang_refs("x $shutdown y", {"shutdown": "off"}) == "x off y"
