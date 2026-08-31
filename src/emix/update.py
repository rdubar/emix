"""Updating Emix itself.

Emix can be installed four ways that each want a different upgrade command,
and telling someone the wrong one is worse than telling them nothing. So this
works out how *this* copy got here and offers the command that matches.

It follows the same rule as the rest of the project: nothing is executed on a
guess. The exact command is printed, the user confirms it, and it runs through
the argument-list runner with no shell involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys
from typing import TextIO
import urllib.error
import urllib.request

import emix
from emix.host import run_host_command

#: Where the published package lives.
DISTRIBUTION = "emix-shell"

#: How long to wait for the package index before giving up and saying so.
_TIMEOUT = 5.0

_PYPI = f"https://pypi.org/pypi/{DISTRIBUTION}/json"


class Method(Enum):
    """How this copy of Emix was installed."""

    UV_TOOL = "uv tool"
    PIPX = "pipx"
    PIP = "pip"
    SOURCE = "a source checkout"


@dataclass(frozen=True)
class Installation:
    """This copy of Emix, and what would update it."""

    method: Method
    #: The command that upgrades it, or empty when a checkout should be pulled.
    command: tuple[str, ...]
    #: Where the running code lives.
    location: Path

    @property
    def is_source(self) -> bool:
        return self.method is Method.SOURCE


def detect(module_file: str | None = None, prefix: str | None = None) -> Installation:
    """Work out how this copy was installed, from where it is running.

    An editable install points back at its checkout, so it is reported as a
    source checkout — which is correct: ``git pull`` is what updates it, and
    running ``uv tool upgrade`` there would do nothing useful.
    """
    location = Path(module_file or emix.__file__).resolve().parent
    root = str(prefix if prefix is not None else sys.prefix)

    checkout = location.parent.parent
    if (checkout / "pyproject.toml").is_file() and location.parent.name == "src":
        return Installation(Method.SOURCE, (), checkout)
    if "uv/tools" in root.replace("\\", "/"):
        return Installation(Method.UV_TOOL, ("uv", "tool", "upgrade", DISTRIBUTION), location)
    if "pipx" in root.replace("\\", "/"):
        return Installation(Method.PIPX, ("pipx", "upgrade", DISTRIBUTION), location)
    return Installation(
        Method.PIP,
        (sys.executable, "-m", "pip", "install", "--upgrade", DISTRIBUTION),
        location,
    )


def latest_version(timeout: float = _TIMEOUT) -> str | None:
    """The newest published version, or ``None`` if the index cannot be read.

    This is the only network request Emix ever makes, and it happens only when
    the user asks for an update.
    """
    try:
        with urllib.request.urlopen(_PYPI, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    version = payload.get("info", {}).get("version")
    return str(version) if version else None


def update(
    *,
    stream: TextIO = sys.stdout,
    confirm: object = None,
    check: bool = True,
    runner: object = None,
) -> int:
    """Report what is installed and offer the matching upgrade command."""
    installation = detect()
    stream.write(f"Emix {emix.__version__}, installed via {installation.method.value}\n")
    stream.write(f"  {installation.location}\n")

    if check:
        newest = latest_version()
        if newest is None:
            stream.write("\nCould not reach the package index to check for a newer version.\n")
        elif newest == emix.__version__:
            stream.write(f"\n{DISTRIBUTION} {newest} is the newest published version.\n")
        else:
            stream.write(f"\nThe newest published version is {newest}.\n")

    if installation.is_source:
        stream.write(
            "\nThis is a source checkout, so git is what updates it:\n"
            f"  git -C {installation.location} pull\n"
            "An editable install picks that up with no further step.\n"
        )
        return 0

    command = " ".join(installation.command)
    stream.write(f"\nTo update:\n  {command}\n")

    ask = confirm if callable(confirm) else input
    if not sys.stdin.isatty() and confirm is None:
        stream.write("\nRun that command to update. (Not run here: no terminal to confirm from.)\n")
        return 0
    try:
        answer = ask("\nRun it now? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        stream.write("\n")
        return 0
    if str(answer).strip().upper() not in {"Y", "YES"}:
        stream.write("Not updated.\n")
        return 0

    execute = runner if callable(runner) else run_host_command
    return int(execute(list(installation.command), cwd=Path.cwd()))
