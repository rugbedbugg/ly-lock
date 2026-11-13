"""The greetd side of the greeter: log a user in and start their session.

greetd speaks JSON over the socket named by GREETD_SOCK. Every message is
a four byte length in native byte order followed by that many bytes.
"""

import json
import os
import socket
import struct

ERROR_AUTH = "err_pam_auth"
ERROR_OTHER = "err_pam"


class GreetdError(Exception):
    """A login that failed. key names the message ly-lock shows for it."""

    def __init__(self, key, detail=""):
        super().__init__(detail or key)
        self.key = key


def send(sock, message):
    data = json.dumps(message).encode()
    sock.sendall(struct.pack("=I", len(data)) + data)


def _read(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise GreetdError(ERROR_OTHER, "greetd closed the socket")
        data += chunk
    return data


def receive(sock):
    (size,) = struct.unpack("=I", _read(sock, 4))
    return json.loads(_read(sock, size))


def _cancel(sock):
    try:
        send(sock, {"type": "cancel_session"})
        receive(sock)
    except (OSError, GreetdError, ValueError):
        pass


def login(user, secret, cmd, env, path=None):
    """Authenticate user with secret, then start cmd with env.

    Raises GreetdError when greetd refuses. The session is cancelled first,
    so the next call starts clean.
    """
    path = path or os.environ.get("GREETD_SOCK")
    if not path:
        raise GreetdError(ERROR_OTHER, "GREETD_SOCK is not set")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(path)
            return _login(sock, user, secret, cmd, env)
        except GreetdError:
            _cancel(sock)
            raise
        except (OSError, ValueError) as err:
            raise GreetdError(ERROR_OTHER, str(err)) from err


def _login(sock, user, secret, cmd, env):
    answered = False
    send(sock, {"type": "create_session", "username": user})
    while True:
        reply = receive(sock)
        kind = reply.get("type")
        if kind == "success":
            break
        if kind == "error":
            if reply.get("error_type") == "auth_error":
                raise GreetdError(ERROR_AUTH, reply.get("description", ""))
            raise GreetdError(ERROR_OTHER, reply.get("description", ""))
        if kind != "auth_message":
            raise GreetdError(ERROR_OTHER, f"unexpected reply {kind!r}")
        if reply.get("auth_message_type") in ("secret", "visible"):
            # One password answers one prompt. A second prompt is a
            # challenge ly-lock cannot show, so the login fails.
            if answered:
                raise GreetdError(ERROR_AUTH, "greetd asked for more than the password")
            answered = True
            send(sock, {"type": "post_auth_message_response", "response": secret})
        else:
            send(sock, {"type": "post_auth_message_response", "response": None})
    send(sock, {"type": "start_session", "cmd": cmd, "env": env})
    reply = receive(sock)
    if reply.get("type") != "success":
        raise GreetdError(ERROR_OTHER, reply.get("description", "greetd could not start the session"))


def session_env(session):
    """The XDG variables ly sets for session, a sessions.Session or None."""
    env = ["XDG_SESSION_TYPE=wayland"]
    if session is None:
        return env
    names = session.desktop_names or session.file_name
    if names:
        names = names.strip(";")
        env.append(f"XDG_SESSION_DESKTOP={names.split(';')[0]}")
        env.append(f"XDG_CURRENT_DESKTOP={names.replace(';', ':')}")
    return env


def mark_done(path):
    """Create the marker a launcher looks for. True when it exists."""
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8"):
            pass
    except OSError:
        return False
    return True
