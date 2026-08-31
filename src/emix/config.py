"""Settings that persist between sessions.

Emix works with no configuration at all, and that must stay true: a fresh
install run from a checkout should behave exactly as documented. This file
only removes repetition — the drives you always mount, the personality you
always start, the colour you prefer.

Precedence is the ordinary one, and is worth stating because it is the thing
people get wrong: **command line, then configuration file, then the built-in
default.** A flag always wins, which is what makes a script's behaviour
readable from the script alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib

from emix.assist import COLOURS
from emix.errors import Code, EmixError

#: Checked before the default location.
ENVIRONMENT = "EMIX_CONFIG"

_DEFAULT = Path("~/.config/emix/emix.toml")


@dataclass(frozen=True)
class Config:
    """Everything a configuration file may set."""

    personality: str = ""
    #: Host directories to mount, per personality, plus a ``default`` key.
    drives: dict[str, list[Path]] = field(default_factory=dict)
    strict: bool | None = None
    #: Empty means "not chosen", which lets Emix ask the terminal instead of
    #: quietly overriding the answer with a default.
    hint_colour: str = ""

    def mounts_for(self, personality: str) -> list[Path]:
        """Configured drives for a personality, falling back to the default."""
        return self.drives.get(personality) or self.drives.get("default") or []


def config_path() -> Path:
    override = os.environ.get(ENVIRONMENT)
    return Path(override).expanduser() if override else _DEFAULT.expanduser()


def load(path: Path | None = None) -> Config:
    """Read the configuration file, or return defaults if there is none."""
    source = path or config_path()
    if not source.is_file():
        return Config()
    try:
        payload = tomllib.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        raise EmixError(Code.IO_ERROR, str(source), str(error)) from error
    except tomllib.TOMLDecodeError as error:
        raise EmixError(Code.SYNTAX, str(source), str(error)) from error

    emix = payload.get("emix", {})
    if not isinstance(emix, dict):
        raise EmixError(Code.SYNTAX, str(source), "'emix' must be a table")

    colour = str(emix.get("hint-colour", ""))
    if colour and colour not in COLOURS:
        raise EmixError(
            Code.SYNTAX, str(source), f"unknown hint-colour {colour!r} (try {', '.join(COLOURS)})"
        )

    strict = emix.get("strict")
    if strict is not None and not isinstance(strict, bool):
        raise EmixError(Code.SYNTAX, str(source), "'strict' must be true or false")

    configured = payload.get("drives") or {}
    if not isinstance(configured, dict):
        raise EmixError(Code.SYNTAX, str(source), "'drives' must be a table")
    drives: dict[str, list[Path]] = {}
    for key, value in configured.items():
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise EmixError(Code.SYNTAX, f"drives.{key}", "expected a path or a list of paths")
        drives[key] = [Path(item).expanduser() for item in value]

    return Config(
        personality=str(emix.get("personality", "")),
        drives=drives,
        strict=strict,
        hint_colour=colour,
    )


EXAMPLE = (
    "# ~/.config/emix/emix.toml — every key is optional.\n"
    "\n"
    "[emix]\n"
    'personality = "cpm"\n'
    "strict = false\n"
    'hint-colour = "yellow"     # or cyan, green, magenta, blue, red, grey, none\n'
    "\n"
    "[drives]\n"
    '# Mounted in order. "default" applies to any personality without its own.\n'
    'default = ["~/Documents"]\n'
    'cpm = ["~/Documents", "~/src"]\n'
)
