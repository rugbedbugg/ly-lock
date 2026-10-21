import time

from helpers import make_buffer, make_state, row_text

from ly_lock.ui import Screen

NOW = time.mktime((2026, 10, 21, 20, 41, 0, 0, 0, -1))


def draw(width=240, height=67, **config):
    state = make_state(**config)
    buf = make_buffer(width, height)
    cursor = Screen(state).draw(buf, now=NOW)
    return state, buf, cursor


def test_layout_matches_ly_on_a_1080p_tty():
    _, buf, cursor = draw(clock="%a %d %b  %H:%M")
    assert row_text(buf, 0).startswith(
        "F1 shutdown F2 reboot F7 toggle password F5 decrease brightness F6 increase brightness"
    )
    assert row_text(buf, 0).endswith(time.strftime("%a %d %b  %H:%M", time.localtime(NOW)))
    corners = {(95, 28): "┌", (143, 28): "┐", (95, 38): "└", (143, 38): "┘"}
    for (x, y), ch in corners.items():
        assert chr(buf.ch[y, x]) == ch
    assert row_text(buf, 30)[98:141].rstrip() == "< host" + " " * 36 + ">"
    assert row_text(buf, 32)[98:141] == "wayland  < Hyprland (uwsm-managed)" + " " * 8 + ">"
    assert row_text(buf, 34)[98:107] == "login    "
    assert row_text(buf, 36)[98:106] == "password"
    assert cursor == (107, 36)
    assert row_text(buf, 66).startswith("Ly-lock version 0.1.1")


def test_password_mask_and_cursor():
    state, _, _ = draw()
    for ch in "hunter2":
        state.password.write(ch)
    buf = make_buffer(240, 67)
    cursor = Screen(state).draw(buf, now=NOW)
    assert row_text(buf, 36)[107:115] == "******* "
    assert cursor == (114, 36)
    state.password.masked = False
    buf = make_buffer(240, 67)
    Screen(state).draw(buf, now=NOW)
    assert row_text(buf, 36)[107:114] == "hunter2"


def test_hidden_mask_keeps_cursor_at_start():
    state, _, _ = draw(asterisk=None)
    state.password.write("x")
    buf = make_buffer(240, 67)
    assert Screen(state).draw(buf, now=NOW) == (107, 36)
    assert row_text(buf, 36)[107] == " "


def test_hide_options():
    _, buf, _ = draw(hide_key_hints=True, hide_version_string=True, hide_borders=True)
    assert row_text(buf, 0).strip() == ""
    assert row_text(buf, 66).strip() == ""
    assert chr(buf.ch[28, 95]) == " "


def test_bigclock_draws_digits():
    _, buf, _ = draw(bigclock="en")
    assert (buf.ch == 0x2593).sum() > 20


def test_small_screen_does_not_crash():
    draw(width=30, height=8)
