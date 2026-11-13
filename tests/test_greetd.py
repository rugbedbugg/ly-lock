import socket
import struct
import threading

import pytest

from ly_lock import greetd
from ly_lock.sessions import Session


class FakeGreetd:
    """Answers each request with the next reply of a script and records them."""

    def __init__(self, path, replies):
        self.requests = []
        self.replies = list(replies)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(1)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.server.accept()
        with conn:
            try:
                while True:
                    self.requests.append(greetd.receive(conn))
                    if not self.replies:
                        return
                    greetd.send(conn, self.replies.pop(0))
            except greetd.GreetdError:
                return

    def close(self):
        self.thread.join(timeout=2)
        self.server.close()


@pytest.fixture
def sock_path(tmp_path):
    return str(tmp_path / "greetd.sock")


def run(sock_path, replies, secret="hunter2"):
    server = FakeGreetd(sock_path, replies)
    try:
        error = None
        try:
            greetd.login("alice", secret, ["uwsm", "start"], ["A=1"], path=sock_path)
        except greetd.GreetdError as err:
            error = err
    finally:
        server.close()
    return server.requests, error


SECRET = {"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password: "}
OK = {"type": "success"}


def test_login_starts_the_session(sock_path):
    requests, error = run(sock_path, [SECRET, OK, OK])
    assert error is None
    assert requests == [
        {"type": "create_session", "username": "alice"},
        {"type": "post_auth_message_response", "response": "hunter2"},
        {"type": "start_session", "cmd": ["uwsm", "start"], "env": ["A=1"]},
    ]


def test_info_prompts_get_an_empty_answer(sock_path):
    info = {"type": "auth_message", "auth_message_type": "info", "auth_message": "hello"}
    requests, error = run(sock_path, [info, SECRET, OK, OK])
    assert error is None
    assert requests[1] == {"type": "post_auth_message_response", "response": None}
    assert requests[2] == {"type": "post_auth_message_response", "response": "hunter2"}


def test_wrong_password_is_an_auth_error_and_cancels(sock_path):
    bad = {"type": "error", "error_type": "auth_error", "description": "denied"}
    requests, error = run(sock_path, [SECRET, bad, OK])
    assert error.key == greetd.ERROR_AUTH
    assert requests[-1] == {"type": "cancel_session"}


def test_a_second_password_prompt_fails(sock_path):
    requests, error = run(sock_path, [SECRET, SECRET, OK])
    assert error.key == greetd.ERROR_AUTH
    assert requests[-1] == {"type": "cancel_session"}


def test_start_session_failure(sock_path):
    bad = {"type": "error", "error_type": "error", "description": "no such command"}
    _, error = run(sock_path, [SECRET, OK, bad])
    assert error.key == greetd.ERROR_OTHER


def test_missing_socket_variable(monkeypatch):
    monkeypatch.delenv("GREETD_SOCK", raising=False)
    with pytest.raises(greetd.GreetdError) as err:
        greetd.login("alice", "x", ["true"], [])
    assert err.value.key == greetd.ERROR_OTHER


def test_unreachable_socket(tmp_path):
    with pytest.raises(greetd.GreetdError) as err:
        greetd.login("alice", "x", ["true"], [], path=str(tmp_path / "none"))
    assert err.value.key == greetd.ERROR_OTHER


def test_message_framing_uses_native_length():
    a, b = socket.socketpair()
    with a, b:
        greetd.send(a, {"type": "cancel_session"})
        body = b'{"type": "cancel_session"}'
        assert b.recv(4 + len(body)) == struct.pack("=I", len(body)) + body


def test_session_env_follows_the_desktop_names():
    session = Session("Hyprland", "wayland", "hyprland-uwsm", "Hyprland;")
    assert greetd.session_env(session) == [
        "XDG_SESSION_TYPE=wayland",
        "XDG_SESSION_DESKTOP=Hyprland",
        "XDG_CURRENT_DESKTOP=Hyprland",
    ]


def test_session_env_joins_several_names():
    session = Session("Plasma", "wayland", "plasma", "KDE;GNOME")
    env = greetd.session_env(session)
    assert "XDG_SESSION_DESKTOP=KDE" in env
    assert "XDG_CURRENT_DESKTOP=KDE:GNOME" in env


def test_session_env_falls_back_to_the_file_name():
    assert "XDG_SESSION_DESKTOP=sway" in greetd.session_env(Session("Sway", "wayland", "sway"))


def test_session_env_without_a_session():
    assert greetd.session_env(None) == ["XDG_SESSION_TYPE=wayland"]


def test_mark_done_creates_the_file(tmp_path):
    path = tmp_path / "done"
    assert greetd.mark_done(str(path))
    assert path.exists()


def test_mark_done_survives_an_unwritable_path(tmp_path):
    assert not greetd.mark_done(str(tmp_path / "missing" / "done"))
    assert not greetd.mark_done(None)
